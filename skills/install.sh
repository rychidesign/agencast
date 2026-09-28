#!/usr/bin/env bash
# Symlinkuje skilly agencast-* do složek Claude Code, Codexu, OpenCode a OMP.
# Idempotentní; --prefix <dir> místo $HOME (na test).
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
src=$repo/skills
home=$HOME
if [[ ${1:-} == --prefix ]]; then home=${2:?--prefix potřebuje složku}; fi

for dir in "$home/.claude/skills" "$home/.codex/skills" "$home/.config/opencode/skills" "$home/.omp/agent/managed-skills"; do
  mkdir -p "$dir"
  for name in agencast-run agencast-create; do
    if [[ -e $dir/$name && ! -L $dir/$name ]]; then
      echo "chyba: $dir/$name existuje a není symlink — nepřepisuju" >&2; exit 1
    fi
    ln -sfn "$src/$name" "$dir/$name"
    echo "$dir/$name -> $src/$name"
  done
done
