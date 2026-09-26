#!/usr/bin/env bash
# Symlinkuje skilly agencast-* do složek skillů Claude Code a Codexu.
# OMP 18 čte obě složky sám (a ~/.agents/skills), vlastní složku nepotřebuje.
# Idempotentní; --prefix <dir> místo $HOME (na test).
set -euo pipefail

src=~/workspace/multiagent-workflows/skills
home=$HOME
if [[ ${1:-} == --prefix ]]; then home=${2:?--prefix potřebuje složku}; fi

for dir in "$home/.claude/skills" "$home/.codex/skills"; do
  mkdir -p "$dir"
  for name in agencast-run agencast-create; do
    if [[ -e $dir/$name && ! -L $dir/$name ]]; then
      echo "chyba: $dir/$name existuje a není symlink — nepřepisuju" >&2; exit 1
    fi
    ln -sfn "$src/$name" "$dir/$name"
    echo "$dir/$name -> $src/$name"
  done
done
