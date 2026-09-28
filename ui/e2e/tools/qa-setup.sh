#!/usr/bin/env bash
# Průzkumné QA GUI (vlna D): `agencast serve --fake` s ukázkovými projekty a krajními daty.
# Použití: ui/e2e/tools/qa-setup.sh [port]  → vypíše URL; stav v /tmp/agencast-qa/srv.
set -euo pipefail
PORT=${1:-28950}
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
BIN=$REPO/framework/.venv/bin/agencast
S=${QA_SRV:-/tmp/agencast-qa/srv}
pkill -f "agencast serve --fake $S/fake.yaml" 2>/dev/null || true
rm -rf "$S" && mkdir -p "$S/cfg" "$S/projekty"
printf 'projects_root: %s\nprojects: []\n' "$S/projekty" > "$S/cfg/projects.yaml"
cat > "$S/fake.yaml" <<'Y'
napis: [{text: "Dvě věty."}]
pomalu: [{text: "Pomalá odpověď.", sleep: 4}]
velmi_pomalu: [{text: "Hodně pomalá odpověď.", sleep: 600}]
Y
export AGENCAST_CONFIG_DIR=$S/cfg AGENCAST_TOKEN=test-token OPENROUTER_API_KEY=qa-falesny-klic
cd "$S" && nohup setsid "$BIN" serve --fake "$S/fake.yaml" --host 127.0.0.1 --port "$PORT" > "$S/serve.log" 2>&1 < /dev/null &
for _ in $(seq 50); do curl -fs -H "Authorization: Bearer test-token" "http://127.0.0.1:$PORT/projects" >/dev/null && break; sleep 0.2; done
api() { curl -fs -X "$1" -H "Authorization: Bearer test-token" -H "Content-Type: application/json" "http://127.0.0.1:$PORT$2" ${3:+-d "$3"}; echo; }
api POST /projects/new '{"name":"demo"}'
api POST /projects/new '{"name":"krajni"}'
# reálná vrstva uživatele z repa (workflows/) jako třetí projekt
mkdir -p "$S/projekty/thtd" && cp -r "$REPO/workflows" "$S/projekty/thtd/"
api POST /projects '{"root":"'"$S/projekty/thtd"'"}'
# nedostupný projekt (N3)
mkdir -p "$S/projekty/stary"
"$REPO/framework/.venv/bin/python" - "$S/cfg/projects.yaml" "$S/projekty/stary" <<'P'
import sys, yaml; p, root = sys.argv[1:]
d = yaml.safe_load(open(p)); d["projects"].append({"name": "stary", "root": root})
open(p, "w").write(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))
P
W=$S/projekty/demo/workflows
cp "$REPO/ui/e2e/tools/qa-fixtures/"*.yaml "$W/scenarios/"
K=$S/projekty/krajni/workflows
python3 "$REPO/ui/e2e/tools/qa-fixtures/krajni.py" "$K"
# běhy: úspěch, chyba, dry-run, živý (10 min), fronta
api POST /projects/demo/runs '{"scenario":"ukazka","inputs":{}}'
api POST /projects/demo/runs '{"scenario":"chyba","inputs":{}}'
api POST /projects/demo/runs '{"scenario":"ukazka","inputs":{"tema":"čaj"},"dry_run":true}'
sleep 3
api POST /projects/demo/runs '{"scenario":"zive","inputs":{}}'
api POST /projects/demo/runs '{"scenario":"zive","inputs":{}}'
api POST /projects/krajni/runs '{"scenario":"velky","inputs":{}}'
echo "http://127.0.0.1:$PORT"
