#!/usr/bin/env bash
# Exploratory GUI QA (wave D): `agencast serve --fake` with example projects and edge-case data.
# Usage: ui/e2e/tools/qa-setup.sh [port]  → prints the URL; state in /tmp/agencast-qa/srv.
set -euo pipefail
PORT=${1:-28950}
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
BIN=$REPO/framework/.venv/bin/agencast
S=${QA_SRV:-/tmp/agencast-qa/srv}
pkill -f "agencast serve --fake $S/fake.yaml" 2>/dev/null || true
rm -rf "$S" && mkdir -p "$S/cfg" "$S/projects"
printf 'projects_root: %s\nprojects: []\n' "$S/projects" > "$S/cfg/projects.yaml"
cat > "$S/fake.yaml" <<'Y'
write: [{text: "Two sentences."}]
slowly: [{text: "Slow answer.", sleep: 4}]
very_slowly: [{text: "Very slow answer.", sleep: 600}]
Y
export AGENCAST_CONFIG_DIR=$S/cfg AGENCAST_TOKEN=test-token OPENROUTER_API_KEY=qa-fake-key
cd "$S" && nohup setsid "$BIN" serve --fake "$S/fake.yaml" --host 127.0.0.1 --port "$PORT" > "$S/serve.log" 2>&1 < /dev/null &
for _ in $(seq 50); do curl -fs -H "Authorization: Bearer test-token" "http://127.0.0.1:$PORT/projects" >/dev/null && break; sleep 0.2; done
api() { curl -fs -X "$1" -H "Authorization: Bearer test-token" -H "Content-Type: application/json" "http://127.0.0.1:$PORT$2" ${3:+-d "$3"}; echo; }
api POST /projects/new '{"name":"demo"}'
api POST /projects/new '{"name":"edge-cases"}'
# the real example from the repo (examples/showcase/workflows/) as the third project
mkdir -p "$S/projects/lumen" && cp -r "$REPO/examples/showcase/workflows" "$S/projects/lumen/"
api POST /projects '{"root":"'"$S/projects/lumen"'"}'
# an unavailable project (N3)
mkdir -p "$S/projects/stale"
"$REPO/framework/.venv/bin/python" - "$S/cfg/projects.yaml" "$S/projects/stale" <<'P'
import sys, yaml; p, root = sys.argv[1:]
d = yaml.safe_load(open(p)); d["projects"].append({"name": "stale", "root": root})
open(p, "w").write(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))
P
W=$S/projects/demo/workflows
cp "$REPO/ui/e2e/tools/qa-fixtures/"*.yaml "$W/scenarios/"
K=$S/projects/edge-cases/workflows
python3 "$REPO/ui/e2e/tools/qa-fixtures/edge_cases.py" "$K"
# runs: success, failure, dry run, live (10 min), queue
api POST /projects/demo/runs '{"scenario":"demo","inputs":{}}'
api POST /projects/demo/runs '{"scenario":"failing","inputs":{}}'
api POST /projects/demo/runs '{"scenario":"demo","inputs":{"topic":"tea"},"dry_run":true}'
sleep 3
api POST /projects/demo/runs '{"scenario":"live","inputs":{}}'
api POST /projects/demo/runs '{"scenario":"live","inputs":{}}'
api POST /projects/edge-cases/runs '{"scenario":"big","inputs":{}}'
echo "http://127.0.0.1:$PORT"
