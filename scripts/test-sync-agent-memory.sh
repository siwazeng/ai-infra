#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_FILE="${ROOT_DIR}/AGENTS.md"

TEMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TEMP_HOME"' EXIT

export HOME="$TEMP_HOME"

npm --prefix "$ROOT_DIR" run sync:memory >/dev/null

assert_same_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "缺少目标文件: $file" >&2
    exit 1
  fi

  if ! cmp -s "$SOURCE_FILE" "$file"; then
    echo "内容不一致: $file" >&2
    exit 1
  fi
}

assert_same_file "$HOME/.claude/CLAUDE.md"
assert_same_file "$HOME/.codex/AGENTS.md"
assert_same_file "$HOME/.gemini/GEMINI.md"

echo "sync:memory smoke test passed"
