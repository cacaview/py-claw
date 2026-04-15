#!/usr/bin/env bash
set -u

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="${CLAUDE_PLUGIN_ROOT:-$(cd -- "$script_dir/.." && pwd)}"
loop_file="$repo_root/.claude/ralph-loop.local.md"

content="$(cat "$loop_file" 2>/dev/null || true)"
if [ -z "$content" ]; then
  exit 0
fi

printf '%s\n' "$content"
exit 0
