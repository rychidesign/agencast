"""Local callback receiver for `agencast serve` (tutorial, part 7). Stdlib only.

    python3 docs/tutorials/callback-receiver.py [port]      # default 8799

Listen on http://127.0.0.1:<port>/ (agencast allows http:// only on 127.0.0.1),
print each POST and verify its signature as described in docs/spec/run-record.md:
`X-Signature: sha256=<hex>` = HMAC-SHA256 of the exact body bytes with the
CALLBACK_SECRET secret. Read the secret from the environment, otherwise from `.env`
at the repository root; never print it. Save the latest body to /tmp/last-callback.json.
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
    sys.exit("missing CALLBACK_SECRET (in the environment or .env) — required to verify the signature")


SECRET = secret()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        expected = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        ok = hmac.compare_digest(expected, self.headers.get("X-Signature") or "")
        print(f"POST {self.path}  X-Run-Id: {self.headers.get('X-Run-Id')}")
        print("signature: valid" if ok else "signature: INVALID — do not trust the message")
        try:
            print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
        except ValueError:
            print(body.decode(errors="replace"))
        Path("/tmp/last-callback.json").write_bytes(body)
        # a real receiver would reject a message with an invalid signature; 401 → agencast retries, then records callback_failed
        self.send_response(200 if ok else 401)
        self.end_headers()
        sys.stdout.flush()

    def log_message(self, format, *args):
        pass  # custom output above


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"waiting for a callback at http://127.0.0.1:{port}/ (Ctrl+C to stop)", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
