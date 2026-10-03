#!/bin/bash
# Installs claude-rails globally: copies hook scripts to ~/.claude/hooks/claude-rails,
# merges settings.hooks.json into ~/.claude/settings.json additively via
# scripts/merge_settings.py (other tools' hooks are kept, nothing is duplicated), and
# appends the workflow snippet to ~/.claude/CLAUDE.md. Safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_HOOKS_DIR="$HOME/.claude/hooks/claude-rails"
SETTINGS_FILE="$HOME/.claude/settings.json"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"

command -v python3 >/dev/null 2>&1 || { echo "python3가 필요합니다"; exit 1; }
command -v backlog >/dev/null 2>&1 || echo "경고: backlog CLI가 안 보입니다 (npm i -g backlog.md)"

echo "==> hooks 스크립트 설치: $TARGET_HOOKS_DIR"
mkdir -p "$TARGET_HOOKS_DIR"
cp "$REPO_DIR"/hooks/*.py "$TARGET_HOOKS_DIR/"
echo "    훅 본체 + 테스트(test_*.py)를 같은 디렉토리에 나란히 설치함 (로컬 실제 구성과 동일)"

echo "==> settings.json에 hooks 병합 (추가 전용 — 다른 도구의 훅은 보존)"
python3 "$REPO_DIR/scripts/merge_settings.py" "$SETTINGS_FILE" "$REPO_DIR/settings.hooks.json"

echo "==> CLAUDE.md에 워크플로 규칙 추가"
MARKER="<!-- CLAUDE-RAILS:BEGIN -->"
if [ -f "$CLAUDE_MD" ] && grep -q "$MARKER" "$CLAUDE_MD"; then
  echo "    이미 설치되어 있어 건너뜀 (갱신하려면 마커 블록을 지우고 다시 실행)"
else
  cat "$REPO_DIR/CLAUDE.md.snippet" >> "$CLAUDE_MD"
  echo "    추가 완료: $CLAUDE_MD"
fi

echo "==> 설치 완료."
