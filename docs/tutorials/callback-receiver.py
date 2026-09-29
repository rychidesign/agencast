"""Místní přijímač callbacku z `agencast serve` (tutoriál, díl 7). Jen stdlib.

    python3 docs/tutorials/callback-prijemac.py [port]      # výchozí 8799

Poslouchá na http://127.0.0.1:<port>/ (agencast dovolí http:// jen na 127.0.0.1),
každý POST vypíše a ověří podpis podle docs/spec/run-record.md: hlavička
`X-Signature: sha256=<hex>` = HMAC-SHA256 přesných bajtů těla s tajemstvím
CALLBACK_SECRET. Tajemství se bere z prostředí, jinak z `.env` v kořeni
repozitáře; nikdy se nevypisuje. Poslední tělo uloží do /tmp/posledni-callback.json.
"""
import hashlib
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ENV = Path(__file__).resolve().parents[2] / ".env"


def secret() -> bytes:
    if value := os.environ.get("CALLBACK_SECRET"):
        return value.encode()
    if ENV.is_file():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            key, _, value = line.strip().removeprefix("export ").partition("=")
            if key.strip() == "CALLBACK_SECRET" and value.strip():
                return value.strip().strip("\"'").encode()
    sys.exit("chybí CALLBACK_SECRET (v prostředí ani v .env) — bez něj nejde ověřit podpis")


SECRET = secret()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        expected = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        ok = hmac.compare_digest(expected, self.headers.get("X-Signature") or "")
        print(f"POST {self.path}  X-Run-Id: {self.headers.get('X-Run-Id')}")
        print("podpis: sedí" if ok else "podpis: NESEDÍ — zprávě nevěř")
        try:
            print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
        except ValueError:
            print(body.decode(errors="replace"))
        Path("/tmp/posledni-callback.json").write_bytes(body)
        # n8n by zprávu s nesedícím podpisem odmítlo; 401 → agencast to zkusí znovu a pak zapíše callback_failed
        self.send_response(200 if ok else 401)
        self.end_headers()
        sys.stdout.flush()

    def log_message(self, format, *args):
        pass  # vlastní výpis výš


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"čekám na callback na http://127.0.0.1:{port}/ (Ctrl+C = konec)", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
