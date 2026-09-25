"""Q2b: úplný kruh model → tools/call přes MCP → výsledek (text + obrázek) jako tool zpráva → odpověď.

server-filesystem, všech 14 nástrojů po normalizaci, jména `fs__<tool>`. Úloha: přečíst hello.txt
(text) a barva.png (obrázek, read_media_file) a říct text + barvu. 3 opakování na model.
Použití: python q2b_roundtrip.py [--image-mode tool_array|user_followup] [--n 3]
Výsledek: results/q2b_roundtrip_<mode>.json.
"""
import struct, sys, zlib

import anyio
from mcp import Client

from common import (MODELS, SANDBOX, fs_params, make_dispatch, mcp_tool_to_openai, run_agent,
                    safe_tool_name, save, spent)

MODE = sys.argv[sys.argv.index("--image-mode") + 1] if "--image-mode" in sys.argv else "tool_array"
N = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 3


def red_png(size=32):
    """Jednobarevné červené PNG jen ze stdlib (aby barvu nešlo uhodnout z textu nástroje)."""
    raw = b"".join(b"\x00" + b"\xdc\x14\x14" * size for _ in range(size))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PROMPT = (f"V adresáři {SANDBOX} jsou soubory hello.txt a barva.png. Přečti text ze souboru hello.txt "
          "a podívej se na obrázek barva.png (nástroj pro média). Odpověz česky jednou větou: jaký text "
          "je v souboru a jakou barvu má obrázek.")


async def main():
    SANDBOX.mkdir(exist_ok=True)
    (SANDBOX / "hello.txt").write_text("Ahoj ze sandboxu.\n")
    (SANDBOX / "barva.png").write_bytes(red_png())
    runs = []
    async with Client(fs_params()) as fs:
        mcp_tools = (await fs.list_tools()).tools
        allowed = {safe_tool_name("fs", t.name): ("fs", t) for t in mcp_tools}
        tools = [mcp_tool_to_openai(t, name=n) for n, (_, t) in allowed.items()]
        dispatch = make_dispatch({"fs": fs}, allowed)
        for model in MODELS:
            for i in range(N):
                log = await run_agent(model, [{"role": "user", "content": PROMPT}], tools, dispatch,
                                      label=f"q2b:{model}", image_mode=MODE)
                final = (log["final"] or "").lower()
                log["ok_text"] = "ahoj ze sandboxu" in final
                log["ok_color"] = "červen" in final or "red" in final
                log["ok"] = log["ok_text"] and log["ok_color"] and not log["error"]
                runs.append(log)
                print(model.split("/")[1], i, "ok" if log["ok"] else "FAIL", f"{log['cost']:.4f} USD",
                      f"{log['latency_s']:.1f}s", [c["name"] for t in log["turns"] for c in t["calls"]],
                      log["error"] or "", (log["final"] or "")[:160].replace("\n", " "), flush=True)
    save(f"q2b_roundtrip_{MODE}.json", {"image_mode": MODE, "runs": runs, "spent_total_usd": spent()})
    print("spent_total_usd", round(spent(), 4))


if __name__ == "__main__":
    anyio.run(main)
