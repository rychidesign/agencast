# načte .env z hlavního checkoutu bez CRLF; nic nevypisuje
set -a; . <(tr -d '\r' < ~/workspace/multiagent-workflows/.env); set +a
export PATH="$PWD/.venv/bin:$PATH"
