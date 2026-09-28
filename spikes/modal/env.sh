# načte .env z hlavního checkoutu bez CRLF; nic nevypisuje
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
set -a; . <(tr -d '\r' < "$repo/.env"); set +a
export PATH="$PWD/.venv/bin:$PATH"
