#!/usr/bin/env python3
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
  string points into ~/.claude/hooks/interlock/, so the repo is its source of truth;
  without this, re-running install.sh would never propagate such changes. Entries with
  other commands (other tools' hooks) are never modified.
- Nothing is ever removed, so re-running gives the same result.

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


def merge_hooks(settings, repo_hooks):
    """Return (merged_settings, changes); inputs are not mutated.

    changes is a list of (event, matcher, command, "added" | "updated")."""
    merged = copy.deepcopy(settings)
    installed = merged.setdefault("hooks", {})
    changes = []
    for event, groups in repo_hooks.items():
        inst_groups = installed.setdefault(event, [])
        for group in groups:
            matcher = group.get("matcher")
            for hook in group.get("hooks", []):
                command = hook.get("command")
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
                    if g["hooks"][i] != hook:
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
        except ValueError as e:
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
        shutil.copy2(settings_path, backup)
        print(f"    기존 설정 백업: {backup}")

    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        if _load(tmp) != merged:
            raise ValueError("temp file did not round-trip")
        if os.path.exists(settings_path):
            shutil.copymode(settings_path, tmp)
        os.replace(tmp, settings_path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise

    for event, matcher, command, kind in changes:
        label = "추가" if kind == "added" else "갱신"
        where = event if matcher is None else f"{event} [{matcher}]"
        print(f"    {label}: {where}  {command}")
    added = sum(1 for c in changes if c[3] == "added")
    print(
        f"    총 {added}개 추가, {len(changes) - added}개 갱신 (다른 도구의 훅은 그대로 보존)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
