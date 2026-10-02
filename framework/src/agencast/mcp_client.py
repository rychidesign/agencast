"""MCP servers for the `task` step (DESIGN §5.8, config.md mcp.yaml).

- `load_mcp`: registry `workflows/mcp.yaml` (JSON Schema from the spec, only `{run_dir}`).
- `api_name`, `provider_schema`, `arg_errors`: tool normalization for
  OpenRouter and argument validation against the **original** schema (spike (d)).
- `Pool`: servers for one run using the official `mcp` 2.2 SDK — start on the
  first `task`, shared across `parallel` branches, stopped at the end of the run.
  Each server has its own asyncio task holding the client context:
  anyio requires entering and exiting the context in the same task, and the first `task`
  may run in a `parallel` branch that ends before the run.
"""
import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import tempfile
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import anyio
import httpx2
from jsonschema import Draft202012Validator, validators
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT
from pydantic import ValidationError

from . import AgencastError
from .loader import LoadError, describe_error, load_yaml, read_text, schema_errors, seconds, version_error
from .providers import _retry_after

DEFAULT_TIMEOUTS = {"handshake": "10s", "call": "60s"}  # config.md mcp.yaml
GUARD_S = 5.0  # outer guard over SDK timeouts (without it the SDK may wait indefinitely, §5.8)
STDERR_TAIL = 5  # last stderr lines of a server that failed to start, quoted in the error message


def _no_traceback(record: logging.LogRecord) -> bool:
    """The SDK logs what it cannot parse with a traceback that quotes the server's raw line or response — unmasked,
    on the stderr of the CLI or the service journal. The message stays, the quote goes; a start that fails for
    this reason has the masked cause in the record (`start_error`)."""
    record.exc_info = record.exc_text = None
    return True


# The SDK loggers that log server content. The session logs as "client" (mcp 2.2 session.py: getLogger("client"));
# a filter on a parent logger would not see the records of its children, so each is named.
for _name in ("mcp.client.stdio", "mcp.client.sse", "mcp.client.streamable_http", "mcp.client.session", "client",
              "mcp.shared.jsonrpc_dispatcher"):
    logging.getLogger(_name).addFilter(_no_traceback)


def timeout_s(spec: dict, which: str) -> int:
    return seconds((spec.get("timeouts") or {}).get(which, DEFAULT_TIMEOUTS[which]))


# --- mcp.yaml -----------------------------------------------------------------------

class Servers(dict):
    """Valid servers from `mcp.yaml` (name → settings). `broken` = names of the entries that failed validation,
    or True when the whole file did: their errors are reported (and block the run), so validate must not add
    "is not in mcp.yaml" for them."""
    broken: bool | set = False

    def missing(self, name: str) -> bool:
        return name not in self and self.broken is not True and name not in (self.broken or ())


def load_mcp(wf: Path, errs: list) -> Servers:
    """Servers from `mcp.yaml`. No file means no servers; a broken entry does not hide the valid ones."""
    p, out = wf / "mcp.yaml", Servers()
    if not p.is_file():
        return out
    out.broken = True
    try:
        text = read_text(p, "mcp.yaml")
        data = load_yaml(text, "mcp.yaml")
    except LoadError as e:
        errs.append(str(e))
        return out
    if v := version_error(data, "mcp.yaml"):
        errs.append(v)
        return out
    errs.extend(schema_errors("mcp", data, "mcp.yaml", source=text))
    if not isinstance(data.get("servers"), dict):
        return out
    out.broken = {n for n, s in data["servers"].items()
                  if schema_errors("mcp", {"version": 1, "servers": {n: s}}, "")}
    out.update({n: s for n, s in data["servers"].items() if n not in out.broken})
    for name, s in out.items():
        for i, a in enumerate(s.get("args", [])):  # named by its place, never quoted: the API serves these errors,
            if set(re.findall(r"\{[^}]*\}", a)) - {"{run_dir}"}:  # and nothing of `args` (a key may sit in the braces)
                errs.append(f"mcp.yaml: servers.{name}.args[{i}]: the only allowed substitution in braces is {{run_dir}}")
    return out


def secret_names(servers: dict) -> list[str]:
    """Environment variables with secret values (bearer_token_env, env values)."""
    out = []
    for s in servers.values():
        out += list((s.get("env") or {}).values()) + ([s["bearer_token_env"]] if "bearer_token_env" in s else [])
    return out


# --- tools for providers -------------------------------------------------------

def api_name(server: str, tool: str) -> str:
    """`server__tool`, only [a-zA-Z0-9_-], max 64 characters (otherwise Claude returns 400, §5.8)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server}__{tool}")[:64]


def provider_schema(schema: dict) -> dict:
    """Tool schema simplified for OpenRouter (§5.8): `$ref` inlined, `allOf` merged,
    `oneOf` → `anyOf`, `const` → `enum`, non-string `enum` → `description`.
    Unsupported or recursive `$ref` → ValueError. Arguments are validated against the original."""
    defs = {**schema.get("definitions", {}), **schema.get("$defs", {})}

    def walk(node, seen):
        if isinstance(node, list):
            return [walk(x, seen) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"]
            name = ref.split("/", 2)[-1]
            if not re.fullmatch(r"#/(\$defs|definitions)/[^/]+", ref) or name not in defs:
                raise ValueError(f"unsupported $ref {ref!r}")
            if name in seen:
                raise ValueError(f"recursive $ref {ref!r}")
            return walk({**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}, seen | {name})
        out = {}
        for k, v in node.items():
            if k in ("$schema", "$defs", "definitions"):
                continue
            if k == "allOf":
                for part in walk(v, seen):
                    out.update(part)  # ponytail: shallow merge (Pydantic emits allOf with one $ref); deeper merge when a specific server needs it
            elif k == "oneOf":
                out["anyOf"] = walk(v, seen)
            elif k == "const":
                out["enum"] = [v]
            elif k == "properties" and isinstance(v, dict):
                out[k] = {pk: walk(pv, seen) for pk, pv in v.items()}
            else:
                out[k] = walk(v, seen)
        if any(not isinstance(x, str) for x in out.get("enum", [])):
            vals = ", ".join(json.dumps(x, ensure_ascii=False) for x in out.pop("enum"))
            out["description"] = (out.get("description", "") + f" Allowed values: {vals}.").strip()
        return out

    s = walk(schema, frozenset())
    s["type"] = "object"
    s.setdefault("properties", {})
    return s


def arg_errors(schema: dict, args) -> list[str]:
    """Argument errors against the original tool schema (draft determined by `$schema`)."""
    cls = validators.validator_for(schema, default=Draft202012Validator)
    return [f"{'.'.join(map(str, e.absolute_path)) or 'root'}: {describe_error(e)}"
            for e in cls(schema).iter_errors(args)]


# --- run servers ---------------------------------------------------------------------

@dataclass
class Server:
    name: str
    client: Client
    tools: dict            # name → mcp.types.Tool
    call_s: int
    where: str             # where to look when the connection drops: the stderr log (stdio) or the url (remote)
    error: str | None = None  # the connection dropped during a call → `mcp_server` action `failed` at the end


@dataclass
class ToolResult:
    is_error: bool
    text: str
    images: list           # [(bytes, media_type)]


def _leaves(e: BaseException) -> list:
    if isinstance(e, BaseExceptionGroup):
        return [x for sub in e.exceptions for x in _leaves(sub)]
    return [e]


def _secret(var: str, server: str) -> str:
    """Value of a variable mapped in mcp.yaml. A run checks it in preflight; a dry run gets here."""
    if not (value := os.environ.get(var)):
        raise AgencastError("config", f"missing environment variable {var} (MCP server {server} in mcp.yaml)")
    return value


def _public_url(url: str) -> str:
    """Without userinfo and query — either may carry a key."""
    u = urlsplit(url)
    return f"{u.scheme}://{u.netloc.rpartition('@')[2]}{u.path}"


# An apostrophe inside a URL belongs to it (httpx leaves it as it is in userinfo and query, and quotes the URL in
# apostrophes itself): only one that nothing of the URL follows — the closing quote — ends the match.
# Both run over text a server controls, on the run's event loop: bounded (a scheme is short, pydantic cuts a value
# to about 50 characters), so that a long message costs linear time — not minutes in which no deadline or signal works.
URL = re.compile(r"[a-z][a-z0-9+.-]{0,31}://(?:[^\s'\"<>]|'+(?=[^\s'\"<>]))+", re.I)
INPUT = re.compile(r", input_value=.{0,200}?, input_type=\w+", re.S)  # pydantic's own text, as the SDK puts it into a message


def describe(e: BaseException) -> str:
    """An SDK error as text that may go to the record: its ExceptionGroup layers flattened, every URL without
    userinfo and query (httpx quotes the request URL; a key there is literal text in mcp.yaml, which masking does
    not know) and a pydantic error without its input values (pydantic cuts a long value to its start and end —
    part of a secret, which masking, looking for whole values, cannot find)."""
    parts = []
    for x in _leaves(e):
        text = "; ".join(f"{'.'.join(map(str, d['loc'])) or 'message'}: {d['msg']}"
                         for d in x.errors(include_input=False, include_url=False, include_context=False)) \
            if isinstance(x, ValidationError) else str(x)
        parts.append(f"{type(x).__name__}: {text}")
    return URL.sub(lambda m: _public_url(m[0]), INPUT.sub("", "; ".join(parts)))


def start_error(name: str, spec: dict, e: BaseException, stderr_file: str | None, seen: dict,
                mask=str) -> AgencastError:
    """Startup/handshake failure → class (§5.8): network and 5xx `transient`, otherwise `config`.
    `seen` = what the exception does not carry (all already masked): `status` and `retry_after` — streamable HTTP
    reports any non-2xx as a generic JSON-RPC error and SSE only logs the one of a message POST; `invalid` — a
    stdout line that is not a JSON-RPC message; `stderr` — the server's stderr. `mask` = the record's, applied
    before the detail is cut: a cut through a secret would hide it from the masking of the record."""
    leaves = _leaves(e)
    remote = "url" in spec
    detail = mask(describe(e))[:1000]
    hint = f" (stderr: {stderr_file})" if stderr_file else ""
    lines = [x for x in seen.get("stderr", "").splitlines() if x.strip()][-STDERR_TAIL:]
    tail = f"; stderr: {' | '.join(lines)[-500:]}" if lines else ""
    if seen.get("invalid") and not remote:  # the handshake then times out or the pipe closes: name the cause
        return AgencastError("config", f"MCP server '{name}' wrote a line that is not a JSON-RPC message to stdout "
                                       "instead of answering the handshake — stdout carries only the protocol, logs "
                                       f"belong on stderr{hint}: {seen['invalid']}{tail}")
    # the refused request of SSE is the GET of the event stream, which only its exception carries: status and
    # Retry-After come from the same response
    resp = next((r for x in leaves if getattr(r := getattr(x, "response", None), "status_code", None)), None)
    status = resp.status_code if resp is not None else seen.get("status")
    retry_after = _retry_after(resp.headers) if resp is not None else seen.get("retry_after")
    if not status and any(isinstance(x, TimeoutError) or isinstance(x, MCPError) and x.code == REQUEST_TIMEOUT
                          for x in leaves):
        return AgencastError("transient" if remote else "config",
                        f"MCP server '{name}' did not respond to the handshake within {timeout_s(spec, 'handshake')} s"
                        f"{hint}{tail}")
    # any transport error is a network error, as for a model call (providers.py): reset, closed without an answer
    transient = remote and (not status and any(isinstance(x, (OSError, httpx2.TransportError)) for x in leaves)
                            or status and (status >= 500 or status in (408, 429)))
    http = ""
    if status:
        token = spec.get("bearer_token_env", "not set")
        http = f"HTTP {status}{f' (check bearer_token_env in mcp.yaml: {token})' if status in (401, 403) else ''}: "
    return AgencastError("transient" if transient else "config",
                    f"MCP server '{name}' failed to start{hint}: {http}{detail}{tail}", http_status=status,
                    retry_after=retry_after if transient else None)


class _Remote(AsyncExitStack):
    """The stack of a remote server. Leaving it ends the session with a DELETE that the SDK reads to its end under
    httpx timeouts, which are per read: a server that does not answer, or trickles its answer, would hold the end of
    the run and a signal (ignored while the servers are stopped) for as long as it likes. The exit as a whole gets
    GUARD_S, also after a failed start — there is no process to orphan."""

    async def __aexit__(self, *exc):
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(GUARD_S):
                return await super().__aexit__(*exc)


class Pool:
    """MCP servers for one run. `get` starts a server only once (even with concurrent branches)."""

    def __init__(self, servers: dict, run_dir: Path, rec):
        self.servers, self.run_dir, self.rec = servers, run_dir, rec
        self._ready: dict[str, asyncio.Future] = {}
        self._stops: list[asyncio.Event] = []
        self._owners: dict[asyncio.Task, tuple] = {}  # owner task → (the future of its start, its cancel scope)

    async def get(self, name: str) -> Server:
        """The running server, started on the first call. A failed start is not cached: everyone waiting for
        that attempt gets its AgencastError (`cls` `transient` = worth retrying, `http_status`), and the next
        `get` starts the server again — the caller decides whether and when to retry."""
        fut = self._ready.get(name)
        if fut is None:
            fut = self._ready[name] = asyncio.get_running_loop().create_future()
            # retrieved here: a waiter cancelled meanwhile (step deadline, interrupt) leaves the failure of the
            # start to nobody, and asyncio would print 'Future exception was never retrieved'
            fut.add_done_callback(lambda f: f.cancelled() or f.exception())
            stop = asyncio.Event()
            self._stops.append(stop)
            # The owner is cancelled through an anyio scope (close): Task.cancel() would also land inside the SDK's
            # shielded teardown of a failed start — after stdin was closed, before the kill — and leave close()
            # waiting for a server nobody stops. A scope waits the shield out.
            scope = anyio.CancelScope()

            async def own():
                with scope:
                    await self._own(name, self.servers[name], fut, stop)
            self._owners[asyncio.create_task(own())] = (fut, scope)
        return await asyncio.shield(fut)  # cancelling one waiter (parallel branch) does not stop the server

    async def _transport(self, name: str, spec: dict, stack: AsyncExitStack, hs: int, seen: dict):
        if "command" in spec:
            args = [a.replace("{run_dir}", str(self.run_dir)) for a in spec.get("args", [])]
            for a, raw in zip(args, spec.get("args", [])):
                if raw.startswith("{run_dir}"):  # server-filesystem rejects a nonexistent root (ISSUES 23)
                    Path(a).mkdir(parents=True, exist_ok=True)
            env = {k: _secret(v, name) for k, v in (spec.get("env") or {}).items()}
            # Raw stderr never sits in the run directory (a server may print a mapped secret, and the API serves
            # run files): it goes to an anonymous temporary file and the record gets the masked copy once the
            # server has stopped. A killed framework leaves no stderr log and no raw copy on disk.
            errlog = stack.enter_context(tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace"))

            def keep():
                errlog.seek(0)
                seen["stderr"] = self.rec.mask(errlog.read())
                log = self.rec.dir / f"mcp/{name}.stderr.log"  # appended: the error of an earlier start points here
                self.rec.write(f"mcp/{name}.stderr.log",
                               (log.read_text(encoding="utf-8") if log.is_file() else "") + seen["stderr"])
            stack.callback(keep)  # runs after the client below has stopped the server, before the file closes
            return stdio_client(StdioServerParameters(command=spec["command"], args=args, env=env), errlog=errlog)
        headers = ({"Authorization": f"Bearer {_secret(spec['bearer_token_env'], name)}"}
                   if "bearer_token_env" in spec else None)

        async def status(r):  # GET (the optional event stream) is legitimately answered with 405
            if r.status_code >= 400 and r.request.method == "POST":
                seen["status"], seen["retry_after"] = r.status_code, _retry_after(r.headers)

        def client(**kw):  # a refused POST: streamable HTTP reports a generic error, SSE only logs it and times out
            http = create_mcp_http_client(**kw)
            http.event_hooks["response"].append(status)
            return http
        if spec.get("transport") == "sse":
            return sse_client(spec["url"], headers=headers, timeout=hs, httpx_client_factory=client)
        return streamable_http_client(spec["url"], http_client=await stack.enter_async_context(client(headers=headers)))

    async def _own(self, name: str, spec: dict, fut: asyncio.Future, stop: asyncio.Event):
        hs, t0 = timeout_s(spec, "handshake"), time.monotonic()
        stderr_file = f"mcp/{name}.stderr.log" if "command" in spec else None
        where = {"stderr_file": stderr_file} if stderr_file else {}
        seen, srv = {}, None  # for start_error; the running server

        async def note(m):  # transport faults (a stdout line that is no message) arrive here, not in the handshake error
            if isinstance(m, Exception):  # the whole line (pydantic `input`), so that masking sees a whole secret;
                # a line that is JSON arrives parsed: as JSON again, the form masking knows (not Python's repr)
                line = next((x if isinstance(x := d.get("input"), str) else json.dumps(x, ensure_ascii=False, default=str)
                             for d in getattr(m, "errors", list)()), type(m).__name__)
                seen.setdefault("invalid", self.rec.mask(line)[:200])

        def stopped():  # a server that dropped the connection during a call did not stop, it failed
            self.rec.event("mcp_server", server=name, **({"action": "failed", "error": srv.error}
                                                         if srv and srv.error else {"action": "stopped"}), **where)

        def failed(e):
            err = e if isinstance(e, AgencastError) else start_error(name, spec, e, stderr_file, seen, self.rec.mask)
            fut.set_exception(err)  # waiters first: nothing below may leave get() hanging
            self._ready.pop(name, None)  # see get(): the next call starts the server again
            self.rec.event("mcp_server", server=name, action="failed", error=err.message, **where)
        try:
            async with (_Remote() if "url" in spec else AsyncExitStack()) as stack:
                try:
                    # SSE connects inside the transport, where the SDK's read timeout is 300 s: the guard is the limit
                    async with asyncio.timeout(hs if spec.get("transport") == "sse" else hs + GUARD_S):
                        transport = await self._transport(name, spec, stack, hs, seen)
                        # mode="legacy": saves a fixed 10 s of server/discover for a dead server (§5.8)
                        client = await stack.enter_async_context(
                            Client(transport, mode="legacy", read_timeout_seconds=hs, message_handler=note))
                        tools, cursor = {}, None
                        while True:
                            r = await client.list_tools(cursor=cursor)
                            tools.update({t.name: t for t in r.tools})
                            if not (cursor := r.next_cursor):
                                break
                except Exception as e:
                    if "url" in spec:  # before the stack ends the session (DELETE, up to GUARD_S): the step's retry
                        failed(e)      # and deadline count from the failure. stdio: its stderr comes with the exit
                    raise
                self.rec.event("mcp_server", server=name, action="started",
                               duration_s=round(time.monotonic() - t0, 3), **where)
                srv = Server(name, client, tools, timeout_s(spec, "call"),
                             f"see {stderr_file}" if stderr_file else _public_url(spec["url"]))
                fut.set_result(srv)
                await stop.wait()
            stopped()
        except BaseException as e:  # noqa: BLE001 — errors must reach waiters and the record, not disappear
            if isinstance(e, asyncio.CancelledError):  # run cancelled — shutdown, not failure; also in mid-start
                if fut.cancel():                       # (close): nobody waits for it any more
                    self._ready.pop(name, None)
                if srv or fut.cancelled():  # not after a failed start whose session was still being ended
                    stopped()
                raise
            if srv:
                self.rec.event("mcp_server", server=name, action="failed", error=(
                    f"MCP server '{name}' exited with an error: {self.rec.mask(describe(e))[:1000]}"), **where)
            elif not fut.done():
                failed(e)

    async def close(self):
        """Stop all servers (stdio: close stdin, SIGTERM, SIGKILL the entire tree — SDK)."""
        for s in self._stops:
            s.set()
        for fut, scope in self._owners.values():
            if not fut.done():  # still in its handshake, where nothing looks at `stop`: one cancellation ends it now
                scope.cancel()  # (the SDK's kill escalation still runs) instead of after timeouts.handshake
        done = asyncio.gather(*self._owners, return_exceptions=True)
        try:
            await asyncio.shield(done)
        except asyncio.CancelledError:  # cancelled mid-close: a cancelled owner would skip the SDK's kill
            await done                  # escalation and leave the server running — finish stopping first
            raise

    @staticmethod
    async def call(server: Server, tool: str, args: dict) -> ToolResult:
        """Call a tool. Both isError and server JSON-RPC errors = result for the model;
        timeout = class `timeout` (the tool may have run), crashed server or invalid answer = `config`."""
        try:
            async with asyncio.timeout(server.call_s + GUARD_S):
                res = await server.client.call_tool(tool, args, read_timeout_seconds=server.call_s)
        except TimeoutError:
            raise AgencastError("timeout", f"tool {server.name}.{tool} did not respond within {server.call_s} s "
                                      "(may have run)") from None
        except MCPError as e:
            if e.code == REQUEST_TIMEOUT:
                raise AgencastError("timeout", f"tool {server.name}.{tool} did not respond within {server.call_s} s "
                                          "(may have run)") from None
            if e.code == CONNECTION_CLOSED:
                server.error = (f"MCP server '{server.name}' closed the connection while calling {tool} "
                                f"({server.where})")
                raise AgencastError("config", server.error) from None
            return ToolResult(True, f"MCP error {e.code}: {INPUT.sub('', e.message)}", [])
        except Exception as e:  # e.g. a result that is no tool result: not the SDK's own text, which quotes the input
            raise AgencastError("config", f"tool {server.name}.{tool} failed: {describe(e)}") from None
        texts, images = [], []
        for b in res.content:
            if b.type == "text":
                texts.append(b.text)
            elif b.type == "image":
                try:
                    images.append((base64.b64decode(b.data), b.mime_type))
                except ValueError:  # an invalid answer of the server, not an error of the framework
                    raise AgencastError("config", f"tool {server.name}.{tool} returned an image that is not base64") from None
            else:
                texts.append(f"[content of type {b.type} is not forwarded by the framework]")
        return ToolResult(bool(res.is_error), "\n".join(texts), images)
