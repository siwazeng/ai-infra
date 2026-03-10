#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_FILE="${ROOT_DIR}/AGENTS.md"

CLAUDE_MEMORY_TARGET="${CLAUDE_MEMORY_TARGET:-$HOME/.claude/CLAUDE.md}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CODEX_MEMORY_TARGET="${CODEX_MEMORY_TARGET:-$CODEX_HOME_DIR/AGENTS.md}"
GEMINI_MEMORY_TARGET="${GEMINI_MEMORY_TARGET:-$HOME/.gemini/GEMINI.md}"

usage() {
  cat <<'EOF'
用法:
  bash ./scripts/sync-agent-memory.sh           # 同步到 claude + codex + gemini
  bash ./scripts/sync-agent-memory.sh claude    # 仅同步 Claude Code
  bash ./scripts/sync-agent-memory.sh codex     # 仅同步 Codex
  bash ./scripts/sync-agent-memory.sh gemini    # 仅同步 Gemini CLI

可选环境变量:
  CLAUDE_MEMORY_TARGET=/path/to/CLAUDE.md
  CODEX_HOME=/path/to/codex-home
  CODEX_MEMORY_TARGET=/path/to/AGENTS.md
  GEMINI_MEMORY_TARGET=/path/to/GEMINI.md
  EXTRA_MEMORY_TARGETS='label=/path/to/file,foo=/path/to/bar'
EOF
}

backup_existing() {
  local target="$1"
  local ts backup
  ts="$(date +%Y%m%d%H%M%S)"
  backup="${target}.bak.${ts}"
  mv "$target" "$backup"
  echo "已备份: $target -> $backup"
}

sync_one() {
  local label="$1"
  local target="$2"
  local parent

  parent="$(dirname "$target")"
  mkdir -p "$parent"

  if [[ -f "$target" ]] && cmp -s "$SOURCE_FILE" "$target"; then
    echo "已是最新 [$label]: $target"
    return
  fi

  if [[ -e "$target" || -L "$target" ]]; then
    backup_existing "$target"
  fi

  cp "$SOURCE_FILE" "$target"
  echo "已同步 [$label]: $target"
}

sync_extra_targets() {
  local raw="${EXTRA_MEMORY_TARGETS:-}"
  local entry label path

  if [[ -z "$raw" ]]; then
    return
  fi

  IFS=',' read -r -a extra_entries <<< "$raw"
  for entry in "${extra_entries[@]}"; do
    if [[ -z "$entry" ]]; then
      continue
    fi

    if [[ "$entry" != *=* ]]; then
      echo "错误: EXTRA_MEMORY_TARGETS 条目格式必须为 label=/path/to/file，收到: $entry" >&2
      exit 1
    fi

    label="${entry%%=*}"
    path="${entry#*=}"

    if [[ -z "$label" || -z "$path" ]]; then
      echo "错误: EXTRA_MEMORY_TARGETS 条目不能为空，收到: $entry" >&2
      exit 1
    fi

    sync_one "$label" "$path"
  done
}

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "错误: 源文件不存在: $SOURCE_FILE" >&2
  exit 1
fi

case "${1:-all}" in
  all)
    sync_one "claude" "$CLAUDE_MEMORY_TARGET"
    sync_one "codex" "$CODEX_MEMORY_TARGET"
    sync_one "gemini" "$GEMINI_MEMORY_TARGET"
    sync_extra_targets
    ;;
  claude)
    sync_one "claude" "$CLAUDE_MEMORY_TARGET"
    ;;
  codex)
    sync_one "codex" "$CODEX_MEMORY_TARGET"
    ;;
  gemini)
    sync_one "gemini" "$GEMINI_MEMORY_TARGET"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "错误: 不支持的参数 '$1'" >&2
    usage
    exit 1
    ;;
esac
