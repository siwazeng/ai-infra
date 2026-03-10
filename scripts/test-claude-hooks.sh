#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DIR="${ROOT_DIR}/.claude/hooks"

assert_contains() {
  local haystack="$1"
  local needle="$2"

  if [[ "${haystack}" != *"${needle}"* ]]; then
    echo "断言失败: 输出中未找到 ${needle}" >&2
    exit 1
  fi
}

run_force_think_tests() {
  local output

  output="$(printf '%s' '{"prompt":"请分析这个问题"}' | python3 "${HOOK_DIR}/force-think.py")"
  assert_contains "${output}" '"additionalContext"'

  output="$(printf '%s' '{"prompt":"please think harder"}' | python3 "${HOOK_DIR}/force-think.py")"
  if [[ -n "${output}" ]]; then
    echo "断言失败: 已包含 think 的 prompt 不应再追加上下文" >&2
    exit 1
  fi
}

run_protect_worktree_tests() {
  local output status

  set +e
  output="$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git reset --hard"}}' | python3 "${HOOK_DIR}/protect-worktree.py")"
  status=$?
  set -e
  if [[ ${status} -ne 2 ]]; then
    echo "断言失败: `git reset --hard` 应被阻断，实际退出码 ${status}" >&2
    exit 1
  fi
  assert_contains "${output}" '"decision": "block"'

  output="$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git status --short"}}' | python3 "${HOOK_DIR}/protect-worktree.py")"
  if [[ -n "${output}" ]]; then
    echo "断言失败: 安全命令不应产出阻断输出" >&2
    exit 1
  fi
}

run_force_think_tests
run_protect_worktree_tests

echo "claude hook smoke test passed"
