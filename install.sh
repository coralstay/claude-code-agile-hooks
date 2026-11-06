#!/bin/bash
# ---
# title: install
# description: 훅 스크립트를 ~/.claude/hooks로 복사하고 설정을 병합하는 설치 스크립트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
# Installs claude-code-agile-hooks globally: copies hook scripts to ~/.claude/hooks/claude-code-agile-hooks,
# merges settings.hooks.json into ~/.claude/settings.json additively via
# scripts/merge_settings.py (other tools' hooks are kept, nothing is duplicated), and
# appends the workflow snippet to ~/.claude/CLAUDE.md. Safe to re-run.
set -euo pipefail

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ "${1:-}" = "help" ]; then
  cat <<'EOF'
사용법 (Usage): agile-hooks-install [-h|--help]

설치 동작:
  1. 훅 스크립트(hooks/*.py) 및 work_order.py를 ~/.claude/hooks/claude-code-agile-hooks/ 에 복사
  2. settings.hooks.json을 ~/.claude/settings.json에 병합 (기존 다른 훅 보존)
  3. 워크플로 규칙(CLAUDE.md.snippet)을 ~/.claude/CLAUDE.md에 추가
EOF
  exit 0
fi

_SRC="${BASH_SOURCE[0]}"
while [ -h "$_SRC" ]; do
  _DIR="$(cd -P "$(dirname "$_SRC")" && pwd)"
  _SRC="$(readlink "$_SRC")"
  [[ $_SRC != /* ]] && _SRC="$_DIR/$_SRC"
done
REPO_DIR="$(cd -P "$(dirname "$_SRC")" && pwd)"
TARGET_HOOKS_DIR="$HOME/.claude/hooks/claude-code-agile-hooks"
SETTINGS_FILE="$HOME/.claude/settings.json"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"

command -v python3 >/dev/null 2>&1 || { echo "python3가 필요합니다"; exit 1; }
command -v backlog >/dev/null 2>&1 || echo "경고: backlog CLI가 안 보입니다 (npm i -g backlog.md)"

echo "==> hooks 스크립트 설치: $TARGET_HOOKS_DIR"
mkdir -p "$TARGET_HOOKS_DIR"
cp "$REPO_DIR"/hooks/*.py "$TARGET_HOOKS_DIR/"
echo "    훅 본체 + 테스트(test_*.py)를 같은 디렉토리에 나란히 설치함 (로컬 실제 구성과 동일)"
# TASK-60: 작업 순서 생성기. require_work_order.py가 옆자리의 work_order.py를 안내하므로 같은 곳에 둔다
cp "$REPO_DIR/scripts/work_order.py" "$TARGET_HOOKS_DIR/"

echo "==> settings.json에 hooks 병합 (추가 전용 — 다른 도구의 훅은 보존)"
python3 "$REPO_DIR/scripts/merge_settings.py" "$SETTINGS_FILE" "$REPO_DIR/settings.hooks.json"

echo "==> CLAUDE.md에 워크플로 규칙 추가"
MARKER="<!-- CLAUDE-CODE-AGILE-HOOKS:BEGIN -->"
if [ -f "$CLAUDE_MD" ] && grep -q "$MARKER" "$CLAUDE_MD"; then
  echo "    이미 설치되어 있어 건너뜀 (갱신하려면 마커 블록을 지우고 다시 실행)"
else
  cat "$REPO_DIR/CLAUDE.md.snippet" >> "$CLAUDE_MD"
  echo "    추가 완료: $CLAUDE_MD"
fi

# TASK-54: claude-rails에서 claude-code-agile-hooks로 이름이 바뀌었다. 옛 설치 흔적은 안내만 하고
# 절대 직접 고치거나 지우지 않는다(사용자 판단).
LEGACY_MARKER="<!-- CLAUDE-RAILS:BEGIN -->"
if [ -f "$CLAUDE_MD" ] && grep -q "$LEGACY_MARKER" "$CLAUDE_MD"; then
  echo "==> 안내: $CLAUDE_MD 에 옛 claude-rails 마커 블록(CLAUDE-RAILS:BEGIN ~ END)이 남아 있습니다."
  echo "    새 CLAUDE-CODE-AGILE-HOOKS 블록과 내용이 겹치니 옛 블록을 직접 지워 주세요 (자동으로 고치지 않음)."
fi
LEGACY_HOOKS_DIR="$HOME/.claude/hooks/claude-rails"
if [ -d "$LEGACY_HOOKS_DIR" ]; then
  echo "==> 안내: 옛 설치본 $LEGACY_HOOKS_DIR 가 남아 있습니다."
  echo "    새 설치본($TARGET_HOOKS_DIR)이 동작하는 것을 확인한 뒤 직접 지워도 됩니다 (자동으로 지우지 않음)."
fi

# TASK-72: 사람 서명 판정은 훅 디렉터리의 사람 키 지문 목록으로 한다. 사람만 만들어야 하므로
# 설치 스크립트는 이 파일을 만들지 않고 안내만 한다.
HUMAN_SIGNERS_FILE="$TARGET_HOOKS_DIR/human-signers"
if [ ! -s "$HUMAN_SIGNERS_FILE" ]; then
  echo "==> 사람 키 지문 목록 필요: $HUMAN_SIGNERS_FILE 이 없거나 비어 있습니다."
  echo "    이 파일을 만들기 전까지는 모든 프로젝트에서 backlog task edit <ID> -s \"In Progress\"가 막힙니다."
  echo "    사람이 직접 만드세요 (자동으로 만들지 않음, Claude는 이 디렉터리에 쓸 수 없음):"
  echo "      ssh-keygen -lf <사람 공개키 .pub>   # 두 번째 칸 SHA256:... 이 지문"
  echo "      그 SHA256:... 값을 한 줄에 하나씩 $HUMAN_SIGNERS_FILE 에 적기 (빈 줄 · # 주석 허용)"
  echo "    프로젝트 설정의 humanSigners는 더 이상 판정에 쓰지 않습니다."
fi

echo "==> 설치 완료."
