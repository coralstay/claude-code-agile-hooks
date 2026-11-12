#!/usr/bin/env python3
# ---
# title: merge_settings
# description: settings.hooks.json을 ~/.claude/settings.json에 다른 도구의 훅을 지우지 않고 더하는 스크립트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""Additive merge of settings.hooks.json into ~/.claude/settings.json (used by install.sh).

Usage: merge_settings.py <settings.json> <settings.hooks.json>

Why not `jq -s '.[0] * .[1]'`: jq's object merge replaces arrays wholesale, so any other
tool's hooks under the same event (PreToolUse, Stop, ...) were wiped. This merge only adds:

- Non-hook top-level keys of settings.json are never touched.
- Each repo hook entry is identified by (event, matcher, command). If no installed group
  under that event+matcher already holds that command, the entry is appended to the first
  group with the same matcher (a new group is created if none exists; matcher-less repo
  groups map to matcher-less installed groups).
- If the command already exists there but its other fields differ (e.g. the repo changed
  `if` or `timeout`), that entry is replaced in place with the repo version. The command
  string points into ~/.claude/hooks/claude-code-agile-hooks/, so the repo is its source of truth;
  without this, re-running install.sh would never propagate such changes. Entries with
  other commands (other tools' hooks) are never modified.
- Migration from the old name (TASK-54: claude-rails was renamed to claude-code-agile-hooks). An installed
  entry under the same event whose command points into the old install dir
  (`$HOME/.claude/hooks/claude-rails/<file>`, also written as `~/...`, `${HOME}/...` or the
  expanded home path) and becomes exactly a repo command once that dir is read as
  `.../hooks/claude-code-agile-hooks/` is the old copy of that repo hook. The first such entry under the
  same matcher is replaced in place by the repo entry ("migrated"), so the hook does not run
  twice from both dirs. Any other old copies of that same hook (a different matcher, or the
  new command was already installed) are removed, and a group left empty by that removal is
  dropped. Old-dir commands with no counterpart in the repo (a hook since deleted) and every
  other command are left untouched.
- Apart from that migration nothing is ever removed, so re-running gives the same result.

The CLI backs up the existing file (<settings>.bak.<timestamp>), writes to a temp file in
the same directory, re-validates it as JSON, then atomically replaces the original, and
prints what was added/updated. Invalid existing JSON aborts without touching anything.
"""

import contextlib
import copy
import json
import os
import shutil
import sys
import tempfile
import time


LEGACY_DIR = "/.claude/hooks/claude-rails/"
CURRENT_DIR = "/.claude/hooks/claude-code-agile-hooks/"


def _canonical(command, home):
    """Spell the home dir one way ($HOME) so `~/...`, `${HOME}/...` and the
    expanded path compare equal."""
    for prefix in (home, "~", "${HOME}"):
        command = command.replace(prefix + "/.claude/", "$HOME/.claude/")
    return command


def is_legacy_copy(installed_command, repo_command, home):
    """True if installed_command is the pre-rename (claude-rails dir) copy of
    repo_command."""
    if not isinstance(installed_command, str) or LEGACY_DIR not in installed_command:
        return False
    if not isinstance(repo_command, str):
        return False
    renamed = _canonical(installed_command, home).replace(LEGACY_DIR, CURRENT_DIR)  # ---- 1
    return renamed == _canonical(repo_command, home)


def _migrate_legacy(inst_groups, matcher, hook, has_current, home):
    """Replace/remove old-dir copies of `hook` in inst_groups (see module
    docstring). Returns (found, replaced_in_place)."""
    command = hook.get("command")
    legacy = [
        (g, i)
        for g in inst_groups
        for i, h in enumerate(g.get("hooks", []))
        if is_legacy_copy(h.get("command"), command, home)
    ]
    if not legacy:
        return False, False
    keep = None
    if not has_current:
        keep = next((gi for gi in legacy if gi[0].get("matcher") == matcher), None)  # ---- 2
    emptied = []
    for g, i in reversed(legacy):
        if keep is not None and g is keep[0] and i == keep[1]:
            g["hooks"][i] = copy.deepcopy(hook)
        else:
            del g["hooks"][i]
            if not g["hooks"]:
                emptied.append(g)
    inst_groups[:] = [g for g in inst_groups if not any(g is e for e in emptied)]  # ---- 3
    return True, keep is not None


def merge_hooks(settings, repo_hooks, home=None):
    """Return (merged_settings, changes); inputs are not mutated.

    changes is a list of (event, matcher, command, "added" | "updated" | "migrated").
    home defaults to the current user's home dir (for spotting expanded paths)."""
    if home is None:
        home = os.path.expanduser("~")
    merged = copy.deepcopy(settings)  # ---- 4
    installed = merged.setdefault("hooks", {})
    changes = []
    for event, groups in repo_hooks.items():
        inst_groups = installed.setdefault(event, [])
        for group in groups:
            matcher = group.get("matcher")
            for hook in group.get("hooks", []):
                command = hook.get("command")
                has_current = any(
                    h.get("command") == command
                    for g in inst_groups
                    if g.get("matcher") == matcher
                    for h in g.get("hooks", [])
                )
                found, replaced = _migrate_legacy(
                    inst_groups, matcher, hook, has_current, home
                )
                if found:
                    changes.append((event, matcher, command, "migrated"))
                if replaced:
                    continue
                same_matcher = [g for g in inst_groups if g.get("matcher") == matcher]
                existing = next(
                    (
                        (g, i)
                        for g in same_matcher
                        for i, h in enumerate(g.get("hooks", []))
                        if h.get("command") == command
                    ),
                    None,
                )
                if existing is not None:
                    g, i = existing
                    if g["hooks"][i] != hook:  # ---- 5
                        g["hooks"][i] = copy.deepcopy(hook)
                        changes.append((event, matcher, command, "updated"))
                    continue
                target = same_matcher[0] if same_matcher else None
                if target is None:
                    target = {} if matcher is None else {"matcher": matcher}
                    target["hooks"] = []
                    inst_groups.append(target)
                target.setdefault("hooks", []).append(copy.deepcopy(hook))
                changes.append((event, matcher, command, "added"))
    return merged, changes


def _load(path):
    with open(path) as f:
        return json.load(f)


def main(argv):
    if len(argv) != 3:
        print(
            "usage: merge_settings.py <settings.json> <settings.hooks.json>",
            file=sys.stderr,
        )
        return 2
    settings_path, repo_path = argv[1], argv[2]

    repo_hooks = _load(repo_path).get("hooks", {})
    if os.path.exists(settings_path):
        try:
            settings = _load(settings_path)
        except ValueError as e:  # ---- 6
            print(
                f"오류: {settings_path}가 올바른 JSON이 아닙니다 ({e}). 변경하지 않았습니다.",
                file=sys.stderr,
            )
            return 1
        if not isinstance(settings, dict):
            print(
                f"오류: {settings_path}의 최상위가 객체가 아닙니다. 변경하지 않았습니다.",
                file=sys.stderr,
            )
            return 1
    else:
        settings = {}

    merged, changes = merge_hooks(settings, repo_hooks)
    if not changes:
        print("    추가/갱신할 항목 없음 (이미 모두 설치됨)")
        return 0

    directory = os.path.dirname(os.path.abspath(settings_path))
    os.makedirs(directory, exist_ok=True)
    if os.path.exists(settings_path):
        backup = f"{settings_path}.bak.{int(time.time())}"
        shutil.copy2(settings_path, backup)  # ---- 7
        print(f"    기존 설정 백업: {backup}")

    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        if _load(tmp) != merged:  # ---- 8
            raise ValueError("temp file did not round-trip")
        if os.path.exists(settings_path):
            shutil.copymode(settings_path, tmp)
        os.replace(tmp, settings_path)  # ---- 9
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise

    labels = {"added": "추가", "updated": "갱신", "migrated": "이전"}
    for event, matcher, command, kind in changes:
        where = event if matcher is None else f"{event} [{matcher}]"
        print(f"    {labels[kind]}: {where}  {command}")
    counts = {kind: sum(1 for c in changes if c[3] == kind) for kind in labels}
    print(
        f"    총 {counts['added']}개 추가, {counts['updated']}개 갱신, "
        f"{counts['migrated']}개 옛 경로에서 이전 (다른 도구의 훅은 그대로 보존)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


# ======== 노트 ========
# 1 옛 경로를 새 경로로 읽어 비교
#   설명: 설치된 명령의 `claude-rails/` 를 `claude-code-agile-hooks/` 로 바꿔 저장소 명령과 정확히 같아질 때만 옛 사본으로 본다. 대응물이 없는 옛 명령과 다른 도구의 훅은 건드리지 않는다.
#   관련: TASK-54
#   개념: 마이그레이션
# 2 같은 matcher의 첫 옛 항목만 제자리 교체
#   설명: 이미 새 명령이 있으면 교체 없이 옛 사본을 모두 지운다. 없으면 같은 matcher의 첫 옛 사본을 저장소 항목으로 바꿔 훅이 두 경로에서 두 번 돌지 않게 한다.
#   관련: TASK-54
# 3 비어 버린 그룹 제거
#   설명: 옛 사본을 지우고 hooks 목록이 빈 그룹은 버린다. 같은 리스트 객체를 슬라이스 대입으로 고쳐 호출자가 든 참조가 유지된다.
# 4 입력은 복사본에서 병합
#   설명: settings를 깊은 복사한 뒤 고친다. 호출자의 원본이 변하지 않아 변경 여부(changes)로 쓰기 여부를 안전하게 판단할 수 있다.
#   개념: 순수 함수
# 5 같은 명령인데 다른 필드면 교체
#   설명: 저장소가 `if`나 `timeout`을 바꿔도 설치본에 퍼지게 하는 경로다. 명령 문자열이 설치 디렉터리를 가리키므로 저장소가 SSOT다. 같으면 아무것도 하지 않아 재실행이 멱등이다.
#   관련: install.sh
#   개념: 멱등, SSOT
# 6 기존 JSON이 깨졌으면 중단
#   설명: 사용자의 settings.json을 파싱하지 못하면 아무것도 쓰지 않고 1로 끝낸다. 잘못 덮어써 다른 도구의 설정까지 잃는 것보다 설치 실패가 낫다.
#   개념: fail-closed
# 7 쓰기 전 타임스탬프 백업
#   설명: 변경이 있을 때만 `.bak.<epoch>` 로 복사한다. 병합이 잘못돼도 되돌릴 수 있다.
# 8 임시 파일을 다시 읽어 왕복 검증
#   설명: 디스크에 쓴 JSON이 병합 결과와 같은지 확인한 뒤에야 교체한다. 불일치면 예외로 임시 파일을 지우고 원본을 건드리지 않는다.
#   개념: 검증 후 교체
# 9 원자적 교체
#   설명: 같은 디렉터리의 임시 파일을 os.replace로 바꿔 중간 상태의 settings.json이 보이지 않게 한다. 직전 줄에서 원본 파일 권한을 복사해 유지한다.
#   개념: 원자적 쓰기
