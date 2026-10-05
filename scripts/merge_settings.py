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
    renamed = _canonical(installed_command, home).replace(LEGACY_DIR, CURRENT_DIR)
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
        keep = next((gi for gi in legacy if gi[0].get("matcher") == matcher), None)
    emptied = []
    for g, i in reversed(legacy):
        if keep is not None and g is keep[0] and i == keep[1]:
            g["hooks"][i] = copy.deepcopy(hook)
        else:
            del g["hooks"][i]
            if not g["hooks"]:
                emptied.append(g)
    inst_groups[:] = [g for g in inst_groups if not any(g is e for e in emptied)]
    return True, keep is not None


def merge_hooks(settings, repo_hooks, home=None):
    """Return (merged_settings, changes); inputs are not mutated.

    changes is a list of (event, matcher, command, "added" | "updated" | "migrated").
    home defaults to the current user's home dir (for spotting expanded paths)."""
    if home is None:
        home = os.path.expanduser("~")
    merged = copy.deepcopy(settings)
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
