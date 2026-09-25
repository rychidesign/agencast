"""Q1: oficiální Python SDK `mcp` jako klient — stdio (filesystem, everything) + Streamable HTTP a SSE (everything).

Měří: start+handshake, tools/list, tools/call, chyby nástroje, timeout, ukončení (ps), dva servery
současně, opakované spuštění. Výsledek: results/q1_client.json. Bez sítě a bez klíčů.
"""
import os, socket, subprocess, sys, time, traceback

import anyio
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client

from common import HERE, BIN, SANDBOX, descendants, everything_params, fs_params, save

OUT = {"sdk": {}, "start": {}, "cases": {}}


def ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


def exc(e):
    d = {"type": type(e).__module__ + "." + type(e).__name__, "msg": str(e)[:300]}
    if isinstance(e, BaseExceptionGroup):  # anyio balí chyby z task group — ukázat, co je uvnitř
        d["inner"] = [exc(x) for x in e.exceptions]
    return d


def dump(res):
    """CallToolResult → malý JSON (bez velkých dat)."""
    blocks = []
    for c in res.content:
        d = c.model_dump(exclude_none=True)
        if "data" in d:
            d["data"] = f"<base64 {len(d['data'])} znaků>"
        if "text" in d:
            d["text"] = d["text"][:200]
        blocks.append(d)
    return {"isError": res.is_error, "content": blocks, "structured": bool(res.structured_content)}


async def timed_connect(server, n, label, **kw):
    """n× otevři klienta (spawn + handshake), zavolej tools/list, zavři. Vrátí časy v ms."""
    rows = []
    for _ in range(n):
        t0 = time.perf_counter()
        async with Client(server() if callable(server) else server, **kw) as c:
            t_hs = ms(t0)
            t1 = time.perf_counter()
            tools = (await c.list_tools()).tools
            t_list = ms(t1)
            proto = c.protocol_version
        rows.append({"handshake_ms": t_hs, "tools_list_ms": t_list, "total_with_close_ms": ms(t0)})
    OUT["start"][label] = {"runs": rows, "protocol": proto, "n_tools": len(tools)}
    print(label, [r["handshake_ms"] for r in rows], "proto", proto, flush=True)
    return tools


async def try_call(c, name, args, **kw):
    t0 = time.perf_counter()
    try:
        r = await c.call_tool(name, args, **kw)
        return {"ms": ms(t0), "result": dump(r)}
    except Exception as e:  # zaznamenat přesný tvar chyby
        return {"ms": ms(t0), "exception": exc(e)}


def wait_port(port, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"port {port} neodpovídá")


async def main():
    import importlib.metadata as md
    OUT["sdk"] = {"mcp": md.version("mcp"), "python": sys.version.split()[0],
                  "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()}
    SANDBOX.mkdir(exist_ok=True)
    (SANDBOX / "hello.txt").write_text("Ahoj ze sandboxu.\n")

    # 1) start + handshake: lokálně nainstalovaný balíček vs. npx -y (balíček v cache npm)
    fs_tools = await timed_connect(fs_params, 5, "fs_local_bin")
    await timed_connect(lambda: fs_params(via_npx=True), 3, "fs_npx_cached")
    ev_tools = await timed_connect(everything_params, 3, "everything_stdio")
    await timed_connect(fs_params, 3, "fs_local_bin_mode_legacy", mode="legacy")
    OUT["tools"] = {
        "filesystem": [t.model_dump(exclude_none=True, by_alias=True) for t in fs_tools],
        "everything": [t.model_dump(exclude_none=True, by_alias=True) for t in ev_tools],
    }
    OUT["leftover_after_start_tests"] = descendants()

    # 2) volání, chyby, timeout — filesystem
    async with Client(fs_params()) as c:
        C = OUT["cases"]
        C["fs_ok_list_directory"] = await try_call(c, "list_directory", {"path": str(SANDBOX)})
        C["fs_ok_read"] = await try_call(c, "read_text_file", {"path": str(SANDBOX / "hello.txt")})
        C["fs_err_missing_arg"] = await try_call(c, "read_text_file", {})
        C["fs_err_wrong_type"] = await try_call(c, "read_text_file", {"path": 123})
        C["fs_err_outside_root"] = await try_call(c, "read_text_file", {"path": "/etc/hostname"})
        C["fs_err_unknown_tool"] = await try_call(c, "no_such_tool", {})
        C["fs_after_errors_still_ok"] = await try_call(c, "list_allowed_directories", {})

    # 3) everything: obrázek, timeout nástroje, použitelnost session po timeoutu
    async with Client(everything_params()) as c:
        C["ev_image"] = await try_call(c, "get-tiny-image", {})
        C["ev_timeout_2s"] = await try_call(c, "trigger-long-running-operation",
                                            {"duration": 6, "steps": 3}, read_timeout_seconds=2)
        C["ev_after_timeout_still_ok"] = await try_call(c, "get-sum", {"a": 2, "b": 3})

    # 4) server, který nikdy neodpoví — handshake s read_timeout_seconds a vnější pojistka
    hang = StdioServerParameters(command=sys.executable, args=[str(HERE / "hang_server.py")])
    for mode in ("auto", "legacy"):
        t0 = time.perf_counter()
        try:
            with anyio.fail_after(20):
                async with Client(hang, read_timeout_seconds=3, mode=mode):
                    r = {"unexpected": "handshake prošel"}
        except BaseException as e:  # TimeoutError z fail_after i chyby SDK
            r = {"exception": exc(e)}
        r["ms"] = ms(t0)
        C[f"hang_handshake_{mode}"] = r
        print("hang", mode, r, flush=True)
    t0 = time.perf_counter()
    try:
        with anyio.fail_after(4):
            async with Client(hang, mode="legacy"):
                pass
    except BaseException as e:
        C["hang_handshake_no_read_timeout_outer_fail_after_4s"] = {"exception": exc(e), "ms": ms(t0)}
    OUT["leftover_after_hang_tests"] = descendants()

    # 5) dva servery současně v jednom procesu + souběžná volání
    t0 = time.perf_counter()
    async with Client(fs_params()) as a, Client(everything_params()) as b:
        t_both = ms(t0)
        OUT["children_while_two_open"] = descendants()
        res = {}

        async def call(key, cl, name, args):
            res[key] = await try_call(cl, name, args)

        t1 = time.perf_counter()
        async with anyio.create_task_group() as tg:
            tg.start_soon(call, "fs", a, "list_directory", {"path": str(SANDBOX)})
            tg.start_soon(call, "ev", b, "get-sum", {"a": 40, "b": 2})
            tg.start_soon(call, "ev_slow", b, "trigger-long-running-operation", {"duration": 1, "steps": 1})
        C["two_servers"] = {"open_both_ms": t_both, "parallel_calls_ms": ms(t1), "calls": res}
    OUT["leftover_after_two_servers"] = descendants()

    # 6) HTTP: server-everything ve Streamable HTTP a SSE režimu (lokálně)
    for transport, port in (("streamableHttp", 3917), ("sse", 3918)):
        proc = subprocess.Popen([str(BIN / "mcp-server-everything"), transport],
                                env={**os.environ, "PORT": str(port)},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_port(port)
            if transport == "streamableHttp":
                url = f"http://127.0.0.1:{port}/mcp"
                await timed_connect(url, 5, "everything_http")
                srv = url
            else:
                srv = lambda: sse_client(f"http://127.0.0.1:{port}/sse")
                await timed_connect(srv, 3, "everything_sse")
            async with Client(srv() if callable(srv) else srv) as c:
                C[f"{transport}_call"] = await try_call(c, "get-sum", {"a": 1, "b": 1})
                C[f"{transport}_err_wrong_type"] = await try_call(c, "get-sum", {"a": "x"})
                C[f"{transport}_timeout_2s"] = await try_call(c, "trigger-long-running-operation",
                                                              {"duration": 5, "steps": 5}, read_timeout_seconds=2)
                C[f"{transport}_after_timeout_ok"] = await try_call(c, "get-sum", {"a": 1, "b": 2})
        except Exception as e:
            C[f"{transport}_FAILED"] = {"exception": exc(e), "tb": traceback.format_exc()[-800:]}
            print("HTTP FAIL", transport, e, flush=True)
        finally:
            proc.terminate()
            proc.wait(5)

    await anyio.sleep(0.5)
    OUT["leftover_at_end"] = descendants()
    save("q1_client.json", OUT)
    print("leftover_at_end", OUT["leftover_at_end"])
    for k, v in C.items():
        print(k, str(v)[:220])


if __name__ == "__main__":
    anyio.run(main)
