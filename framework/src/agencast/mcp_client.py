"""MCP servery pro krok `task` (DESIGN §5.8, config.md mcp.yaml).

- `load_mcp`: registr `workflows/mcp.yaml` (JSON Schema ze spec, jen `{run_dir}`).
- `api_name`, `provider_schema`, `arg_errors`: normalizace nástrojů pro
  OpenRouter a validace argumentů proti **původnímu** schématu (spike (d)).
- `Pool`: servery jednoho běhu nad oficiálním SDK `mcp` 2.2 — start při
  prvním `task`, sdílení mezi větvemi `parallel`, ukončení na konci běhu.
  Každý server má vlastní úlohu (asyncio task), která drží kontext klienta:
  anyio vyžaduje vstup i výstup z kontextu ve stejné úloze, a první `task`
  může běžet ve větvi `parallel`, která skončí dřív než běh.
"""
import asyncio
import base64
import json
import os
import re
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator, validators
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT

from . import AgencastError
from .loader import LoadError, describe_error, read_yaml, schema_errors, seconds, version_error

DEFAULT_TIMEOUTS = {"handshake": "10s", "call": "60s"}  # config.md mcp.yaml
GUARD_S = 5.0  # vnější pojistka nad timeouty SDK (bez ní SDK může čekat neomezeně, §5.8)


def timeout_s(spec: dict, which: str) -> int:
    return seconds((spec.get("timeouts") or {}).get(which, DEFAULT_TIMEOUTS[which]))


# --- mcp.yaml -----------------------------------------------------------------------

def load_mcp(wf: Path, errs: list) -> dict:
    """Servery z `mcp.yaml` (jméno → nastavení). Bez souboru žádné servery."""
    p = wf / "mcp.yaml"
    if not p.is_file():
        return {}
    try:
        data = read_yaml(p, "mcp.yaml")
    except LoadError as e:
        errs.append(str(e))
        return {}
    if v := version_error(data, "mcp.yaml"):
        errs.append(v)
        return {}
    if e := schema_errors("mcp", data, "mcp.yaml"):
        errs.extend(e)
        return {}
    for name, s in data["servers"].items():
        for a in s.get("args", []):
            for m in re.findall(r"\{[^}]*\}", a):
                if m != "{run_dir}":
                    errs.append(f"mcp.yaml: servers.{name}.args: {m} — jediná povolená náhrada je {{run_dir}}")
    return data["servers"]


def secret_names(servers: dict) -> list[str]:
    """Proměnné prostředí, jejichž hodnoty jsou tajné (bearer_token_env, hodnoty env)."""
    out = []
    for s in servers.values():
        out += list((s.get("env") or {}).values()) + ([s["bearer_token_env"]] if "bearer_token_env" in s else [])
    return out


# --- nástroje pro poskytovatele -------------------------------------------------------

def api_name(server: str, tool: str) -> str:
    """`server__tool`, jen [a-zA-Z0-9_-], max 64 znaků (Claude jinak vrátí 400, §5.8)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server}__{tool}")[:64]


def provider_schema(schema: dict) -> dict:
    """Schéma nástroje zjednodušené pro OpenRouter (§5.8): vložené `$ref`, `allOf` sloučené,
    `oneOf` → `anyOf`, `const` → `enum`, ne-řetězcový `enum` → `description`.
    Nepodporovaný nebo rekurzivní `$ref` → ValueError. Argumenty se validují proti původnímu."""
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
                raise ValueError(f"nepodporovaný $ref {ref!r}")
            if name in seen:
                raise ValueError(f"rekurzivní $ref {ref!r}")
            return walk({**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}, seen | {name})
        out = {}
        for k, v in node.items():
            if k in ("$schema", "$defs", "definitions"):
                continue
            if k == "allOf":
                for part in walk(v, seen):
                    out.update(part)  # ponytail: mělké sloučení (Pydantic dává allOf s jedním $ref); hlubší spojení až s konkrétním serverem
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
            out["description"] = (out.get("description", "") + f" Povolené hodnoty: {vals}.").strip()
        return out

    s = walk(schema, frozenset())
    s["type"] = "object"
    s.setdefault("properties", {})
    return s


def arg_errors(schema: dict, args) -> list[str]:
    """Chyby argumentů proti původnímu schématu nástroje (draft podle `$schema`)."""
    cls = validators.validator_for(schema, default=Draft202012Validator)
    return [f"{'.'.join(map(str, e.absolute_path)) or 'kořen'}: {describe_error(e)}"
            for e in cls(schema).iter_errors(args)]


# --- servery běhu ---------------------------------------------------------------------

@dataclass
class Server:
    name: str
    client: Client
    tools: dict            # jméno → mcp.types.Tool
    call_s: int


@dataclass
class ToolResult:
    is_error: bool
    text: str
    images: list           # [(bajty, media_type)]


def _leaves(e: BaseException) -> list:
    if isinstance(e, BaseExceptionGroup):
        return [x for sub in e.exceptions for x in _leaves(sub)]
    return [e]


def start_error(name: str, spec: dict, e: BaseException, stderr_file: str | None) -> AgencastError:
    """Selhání startu/handshaku → třída (§5.8): síť a 5xx `transient`, jinak `config`.
    Chyby přicházejí ve dvou vrstvách ExceptionGroup — rozbalí se na jednu čitelnou hlášku."""
    leaves = _leaves(e)
    remote = "url" in spec
    detail = "; ".join(f"{type(x).__name__}: {x}" for x in leaves)[:1000]
    hint = f" (stderr: {stderr_file})" if stderr_file else ""
    if any(isinstance(x, TimeoutError) or isinstance(x, MCPError) and x.code == REQUEST_TIMEOUT for x in leaves):
        return AgencastError("transient" if remote else "config",
                        f"MCP server '{name}' neodpověděl na handshake do {timeout_s(spec, 'handshake')} s{hint}")
    status = next((getattr(getattr(x, "response", None), "status_code", None) for x in leaves
                   if getattr(getattr(x, "response", None), "status_code", None)), None)
    transient = remote and (status is None and any(isinstance(x, OSError) or "Connect" in type(x).__name__
                                                    for x in leaves) or status and (status >= 500 or status in (408, 429)))
    return AgencastError("transient" if transient else "config",
                    f"MCP server '{name}' se nepodařilo spustit{hint}: {detail}", http_status=status)


class Pool:
    """MCP servery jednoho běhu. `get` spustí server jen jednou (i při souběžných větvích)."""

    def __init__(self, servers: dict, run_dir: Path, rec):
        self.servers, self.run_dir, self.rec = servers, run_dir, rec
        self._ready: dict[str, asyncio.Future] = {}
        self._stops: list[asyncio.Event] = []
        self._owners: list[asyncio.Task] = []

    async def get(self, name: str) -> Server:
        fut = self._ready.get(name)
        if fut is None:
            fut = self._ready[name] = asyncio.get_running_loop().create_future()
            stop = asyncio.Event()
            self._stops.append(stop)
            self._owners.append(asyncio.create_task(self._own(name, self.servers[name], fut, stop)))
        return await asyncio.shield(fut)  # zrušení jednoho čekatele (větev parallel) server nezastaví

    async def _transport(self, name: str, spec: dict, stack: AsyncExitStack, hs: int):
        if "command" in spec:
            args = [a.replace("{run_dir}", str(self.run_dir)) for a in spec.get("args", [])]
            for a, raw in zip(args, spec.get("args", [])):
                if raw.startswith("{run_dir}"):  # server-filesystem neexistující kořen odmítne (ISSUES 23)
                    Path(a).mkdir(parents=True, exist_ok=True)
            env = {k: os.environ[v] for k, v in (spec.get("env") or {}).items()}
            (self.run_dir / "mcp").mkdir(exist_ok=True)
            errlog = stack.enter_context(open(self.run_dir / "mcp" / f"{name}.stderr.log", "w", encoding="utf-8"))
            return stdio_client(StdioServerParameters(command=spec["command"], args=args, env=env), errlog=errlog)
        headers = ({"Authorization": f"Bearer {os.environ[spec['bearer_token_env']]}"}
                   if "bearer_token_env" in spec else None)
        if spec.get("transport") == "sse":
            return sse_client(spec["url"], headers=headers, timeout=hs)
        http = await stack.enter_async_context(create_mcp_http_client(headers=headers))
        return streamable_http_client(spec["url"], http_client=http)

    async def _own(self, name: str, spec: dict, fut: asyncio.Future, stop: asyncio.Event):
        hs, t0 = timeout_s(spec, "handshake"), time.monotonic()
        stderr_file = f"mcp/{name}.stderr.log" if "command" in spec else None
        where = {"stderr_file": stderr_file} if stderr_file else {}
        try:
            async with AsyncExitStack() as stack:
                async with asyncio.timeout(hs + GUARD_S):
                    transport = await self._transport(name, spec, stack, hs)
                    # mode="legacy": u mrtvého serveru ušetří pevných 10 s server/discover (§5.8)
                    client = await stack.enter_async_context(
                        Client(transport, mode="legacy", read_timeout_seconds=hs))
                    tools, cursor = {}, None
                    while True:
                        r = await client.list_tools(cursor=cursor)
                        tools.update({t.name: t for t in r.tools})
                        if not (cursor := r.next_cursor):
                            break
                self.rec.event("mcp_server", server=name, action="started",
                               duration_s=round(time.monotonic() - t0, 3), **where)
                fut.set_result(Server(name, client, tools, timeout_s(spec, "call")))
                await stop.wait()
            self.rec.event("mcp_server", server=name, action="stopped", **where)
        except BaseException as e:  # noqa: BLE001
            import traceback; traceback.print_exc()  # DEBUG — chyba patří čekatelům a do záznamu, ne do prázdna
            if fut.done() and isinstance(e, asyncio.CancelledError):  # běh zrušen — ukončení, ne porucha
                self.rec.event("mcp_server", server=name, action="stopped", **where)
                raise
            err = start_error(name, spec, e, stderr_file) if not fut.done() else \
                AgencastError("config", f"MCP server '{name}' skončil s chybou: {e!r}")
            self.rec.event("mcp_server", server=name, action="failed", error=err.message, **where)
            if not fut.done():
                fut.set_exception(err)
            if isinstance(e, asyncio.CancelledError):
                raise
        finally:
            if stderr_file and (self.run_dir / stderr_file).is_file():  # maskování tajných hodnot i ve stderr
                self.rec.write(stderr_file, (self.run_dir / stderr_file).read_text(encoding="utf-8", errors="replace"))

    async def close(self):
        """Ukončí všechny servery (stdio: zavřít stdin, SIGTERM, SIGKILL celého stromu — SDK)."""
        for s in self._stops:
            s.set()
        await asyncio.gather(*self._owners, return_exceptions=True)

    @staticmethod
    async def call(server: Server, tool: str, args: dict) -> ToolResult:
        """Zavolá nástroj. isError i chyba JSON-RPC od serveru = výsledek pro model;
        timeout = třída `timeout` (nástroj mohl proběhnout), spadlý server = `config`."""
        try:
            async with asyncio.timeout(server.call_s + GUARD_S):
                res = await server.client.call_tool(tool, args, read_timeout_seconds=server.call_s)
        except TimeoutError:
            raise AgencastError("timeout", f"nástroj {server.name}.{tool} neodpověděl do {server.call_s} s "
                                      "(mohl proběhnout)") from None
        except MCPError as e:
            if e.code == REQUEST_TIMEOUT:
                raise AgencastError("timeout", f"nástroj {server.name}.{tool} neodpověděl do {server.call_s} s "
                                          "(mohl proběhnout)") from None
            if e.code == CONNECTION_CLOSED:
                raise AgencastError("config", f"MCP server '{server.name}' ukončil spojení při volání {tool} "
                                         f"(viz mcp/{server.name}.stderr.log)") from None
            return ToolResult(True, f"MCP error {e.code}: {e.message}", [])
        texts, images = [], []
        for b in res.content:
            if b.type == "text":
                texts.append(b.text)
            elif b.type == "image":
                images.append((base64.b64decode(b.data), b.mime_type))
            else:
                texts.append(f"[obsah typu {b.type} framework nepředává]")
        return ToolResult(bool(res.is_error), "\n".join(texts), images)
