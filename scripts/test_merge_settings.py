"""Tests for scripts/merge_settings.py (install.sh's settings.json hooks merge).

Run from the repo root together with the hook tests: `uvx pytest -q hooks scripts`.
These live next to the script (not in hooks/) because install.sh copies hooks/*.py to
~/.claude/hooks/interlock, where the script and install.sh would not exist.
"""

import copy
import json
import os
import subprocess
import sys

import pytest

import merge_settings as ms

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPTS_DIR)
SCRIPT = os.path.join(SCRIPTS_DIR, "merge_settings.py")
INSTALL_SH = os.path.join(REPO_DIR, "install.sh")
REPO_HOOKS_JSON = os.path.join(REPO_DIR, "settings.hooks.json")

OURS = "python3 $HOME/.claude/hooks/interlock/"
ITERM = "~/.claude/iterm-status.sh"
WEBFETCH_GUARD = "python3 ~/.claude/webfetch_guard.py"


def cmd(command, **extra):
    return {"type": "command", "command": command, **extra}


def repo_hooks():
    return {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [cmd(OURS + "block_dangerous_commands.py")]},
            {"hooks": [cmd(OURS + "instructions_audit.py")]},
        ],
        "Stop": [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}],
    }


def foreign_settings():
    return {
        "model": "opus",
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {
            "PreToolUse": [
                {"matcher": "WebFetch", "hooks": [cmd(WEBFETCH_GUARD)]},
                {"hooks": [cmd(ITERM)]},
            ],
            "Stop": [{"hooks": [cmd(ITERM)]}],
            "Notification": [{"hooks": [cmd(ITERM)]}],
        },
    }


def commands(groups, matcher=None):
    return [
        h["command"]
        for g in groups
        if g.get("matcher") == matcher
        for h in g.get("hooks", [])
    ]


def test_foreign_hooks_preserved_across_events():
    merged, _ = ms.merge_hooks(foreign_settings(), repo_hooks())
    hooks = merged["hooks"]
    assert commands(hooks["PreToolUse"], "WebFetch") == [WEBFETCH_GUARD]
    assert ITERM in commands(hooks["PreToolUse"])
    assert ITERM in commands(hooks["Stop"])
    assert hooks["Notification"] == [{"hooks": [cmd(ITERM)]}]
    assert OURS + "block_stop_if_dirty.py" in commands(hooks["Stop"])
    assert commands(hooks["PreToolUse"], "Bash") == [
        OURS + "block_dangerous_commands.py"
    ]


def test_matcherless_group_is_reused_not_duplicated():
    merged, _ = ms.merge_hooks(foreign_settings(), repo_hooks())
    matcherless = [g for g in merged["hooks"]["PreToolUse"] if "matcher" not in g]
    assert len(matcherless) == 1
    assert [h["command"] for h in matcherless[0]["hooks"]] == [
        ITERM,
        OURS + "instructions_audit.py",
    ]


def test_same_matcher_group_reused():
    settings = {
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [cmd("other-bash-guard")]}]
        }
    }
    merged, _ = ms.merge_hooks(settings, repo_hooks())
    bash_groups = [
        g for g in merged["hooks"]["PreToolUse"] if g.get("matcher") == "Bash"
    ]
    assert len(bash_groups) == 1
    assert [h["command"] for h in bash_groups[0]["hooks"]] == [
        "other-bash-guard",
        OURS + "block_dangerous_commands.py",
    ]


def test_new_group_has_matcher_key_only_when_repo_group_has_one():
    merged, _ = ms.merge_hooks({"hooks": {}}, repo_hooks())
    pre = merged["hooks"]["PreToolUse"]
    assert {
        "matcher": "Bash",
        "hooks": [cmd(OURS + "block_dangerous_commands.py")],
    } in pre
    assert {"hooks": [cmd(OURS + "instructions_audit.py")]} in pre


def test_new_event_added():
    repo = {"SessionEnd": [{"hooks": [cmd(OURS + "session_logger.py")]}]}
    merged, changes = ms.merge_hooks(foreign_settings(), repo)
    assert merged["hooks"]["SessionEnd"] == [
        {"hooks": [cmd(OURS + "session_logger.py")]}
    ]
    assert changes == [("SessionEnd", None, OURS + "session_logger.py", "added")]


def test_idempotent_on_rerun():
    once, changes_once = ms.merge_hooks(foreign_settings(), repo_hooks())
    twice, changes_twice = ms.merge_hooks(once, repo_hooks())
    assert twice == once
    assert len(changes_once) == 3
    assert changes_twice == []


def test_settings_without_hooks_key():
    merged, changes = ms.merge_hooks({"model": "opus"}, repo_hooks())
    assert merged["model"] == "opus"
    assert set(merged["hooks"]) == {"PreToolUse", "Stop"}
    assert len(changes) == 3


def test_non_hook_keys_untouched_and_input_not_mutated():
    settings = foreign_settings()
    before = copy.deepcopy(settings)
    merged, _ = ms.merge_hooks(settings, repo_hooks())
    assert settings == before
    assert {k: v for k, v in merged.items() if k != "hooks"} == {
        k: v for k, v in before.items() if k != "hooks"
    }


def test_existing_interlock_entry_updated_in_place_when_fields_change():
    target = OURS + "block_dangerous_commands.py"
    settings = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [cmd("x"), cmd(target), cmd("y")]}
            ]
        }
    }
    new_entry = cmd(target, **{"if": "Bash(git *)", "timeout": 5})
    repo = {"PreToolUse": [{"matcher": "Bash", "hooks": [new_entry]}]}
    merged, changes = ms.merge_hooks(settings, repo)
    group = merged["hooks"]["PreToolUse"][0]
    assert group["hooks"] == [cmd("x"), new_entry, cmd("y")]
    assert changes == [("PreToolUse", "Bash", target, "updated")]
    again, changes_again = ms.merge_hooks(merged, repo)
    assert again == merged and changes_again == []


def test_same_command_under_other_matcher_is_a_separate_entry():
    target = OURS + "block_dangerous_commands.py"
    settings = {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [cmd(target)]}]}}
    merged, _ = ms.merge_hooks(settings, repo_hooks())
    assert commands(merged["hooks"]["PreToolUse"], "Edit") == [target]
    assert commands(merged["hooks"]["PreToolUse"], "Bash") == [target]


def test_real_settings_hooks_json_merges_idempotently():
    with open(REPO_HOOKS_JSON) as f:
        repo = json.load(f)["hooks"]
    once, changes = ms.merge_hooks(foreign_settings(), repo)
    total = sum(len(g["hooks"]) for groups in repo.values() for g in groups)
    assert len(changes) == total
    twice, again = ms.merge_hooks(once, repo)
    assert twice == once and again == []


# --- CLI ---------------------------------------------------------------------


def run_cli(*args):
    return subprocess.run(
        [sys.executable, SCRIPT, *args], capture_output=True, text=True
    )


def write_json(path, data):
    path.write_text(json.dumps(data))


def setup_files(tmp_path, settings_data):
    settings = tmp_path / "settings.json"
    repo = tmp_path / "settings.hooks.json"
    if settings_data is not None:
        write_json(settings, settings_data)
    write_json(repo, {"hooks": repo_hooks()})
    return settings, repo


def test_cli_merges_backs_up_and_reports(tmp_path):
    settings, repo = setup_files(tmp_path, foreign_settings())
    result = run_cli(str(settings), str(repo))
    assert result.returncode == 0, result.stderr
    assert (
        json.loads(settings.read_text())
        == ms.merge_hooks(foreign_settings(), repo_hooks())[0]
    )
    backups = list(tmp_path.glob("settings.json.bak.*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text()) == foreign_settings()
    assert "block_stop_if_dirty.py" in result.stdout
    assert not list(tmp_path.glob("*.tmp*"))


def test_cli_rerun_leaves_file_unchanged(tmp_path):
    settings, repo = setup_files(tmp_path, foreign_settings())
    run_cli(str(settings), str(repo))
    first = settings.read_text()
    result = run_cli(str(settings), str(repo))
    assert result.returncode == 0, result.stderr
    assert settings.read_text() == first
    assert "추가/갱신할 항목 없음" in result.stdout


def test_cli_creates_missing_settings(tmp_path):
    settings = tmp_path / "sub" / "settings.json"
    repo = tmp_path / "settings.hooks.json"
    write_json(repo, {"hooks": repo_hooks()})
    result = run_cli(str(settings), str(repo))
    assert result.returncode == 0, result.stderr
    assert json.loads(settings.read_text()) == ms.merge_hooks({}, repo_hooks())[0]


def test_cli_refuses_invalid_settings_json_without_touching_it(tmp_path):
    settings, repo = setup_files(tmp_path, None)
    settings.write_text("{not json")
    result = run_cli(str(settings), str(repo))
    assert result.returncode != 0
    assert settings.read_text() == "{not json"
    assert not list(tmp_path.glob("settings.json.bak.*"))


# --- CLI in-process (main() called directly so coverage measures it) -----------


def test_main_usage_error_without_two_paths(capsys):
    assert ms.main(["merge_settings.py", "only-one.json"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_main_merges_backs_up_preserves_mode_and_reports(tmp_path, capsys):
    target = OURS + "block_dangerous_commands.py"
    existing = foreign_settings()
    existing["hooks"]["PreToolUse"].append(
        {"matcher": "Bash", "hooks": [cmd(target, timeout=1)]}
    )
    settings, repo = setup_files(tmp_path, existing)
    os.chmod(settings, 0o640)

    assert ms.main(["merge_settings.py", str(settings), str(repo)]) == 0

    assert json.loads(settings.read_text()) == ms.merge_hooks(existing, repo_hooks())[0]
    assert settings.read_text().endswith("\n")
    assert os.stat(settings).st_mode & 0o777 == 0o640
    [backup] = tmp_path.glob("settings.json.bak.*")
    assert json.loads(backup.read_text()) == existing
    assert not list(tmp_path.glob(".settings.*"))
    out = capsys.readouterr().out
    assert f"기존 설정 백업: {backup}" in out
    assert f"갱신: PreToolUse [Bash]  {target}" in out
    assert f"추가: Stop  {OURS}block_stop_if_dirty.py" in out
    assert "총 2개 추가, 1개 갱신" in out


def test_main_no_changes_writes_and_backs_up_nothing(tmp_path, capsys):
    merged = ms.merge_hooks(foreign_settings(), repo_hooks())[0]
    settings, repo = setup_files(tmp_path, merged)
    before = settings.read_text()

    assert ms.main(["merge_settings.py", str(settings), str(repo)]) == 0

    assert settings.read_text() == before
    assert not list(tmp_path.glob("settings.json.bak.*"))
    assert "추가/갱신할 항목 없음" in capsys.readouterr().out


def test_main_creates_missing_settings_without_backup(tmp_path, capsys):
    settings = tmp_path / "sub" / "settings.json"
    repo = tmp_path / "settings.hooks.json"
    write_json(repo, {"hooks": repo_hooks()})

    assert ms.main(["merge_settings.py", str(settings), str(repo)]) == 0

    assert json.loads(settings.read_text()) == ms.merge_hooks({}, repo_hooks())[0]
    assert os.listdir(tmp_path / "sub") == ["settings.json"]
    assert "기존 설정 백업" not in capsys.readouterr().out


def test_main_invalid_json_exits_1_without_touching(tmp_path, capsys):
    settings, repo = setup_files(tmp_path, None)
    settings.write_text("{not json")

    assert ms.main(["merge_settings.py", str(settings), str(repo)]) == 1

    assert settings.read_text() == "{not json"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.hooks.json", "settings.json"]
    assert "올바른 JSON이 아닙니다" in capsys.readouterr().err


def test_main_non_object_top_level_exits_1_without_touching(tmp_path, capsys):
    settings, repo = setup_files(tmp_path, ["not", "an", "object"])

    assert ms.main(["merge_settings.py", str(settings), str(repo)]) == 1

    assert json.loads(settings.read_text()) == ["not", "an", "object"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["settings.hooks.json", "settings.json"]
    assert "최상위가 객체가 아닙니다" in capsys.readouterr().err


def test_main_aborts_when_temp_file_does_not_round_trip(tmp_path, monkeypatch):
    # Simulate the temp file reading back different from what was written
    # (disk/concurrent-writer corruption): the original must stay as it was
    # and the temp file must be cleaned up.
    settings, repo = setup_files(tmp_path, foreign_settings())
    before = settings.read_text()
    real_load = ms._load
    monkeypatch.setattr(ms, "_load", lambda path: {} if path.endswith(".tmp") else real_load(path))

    with pytest.raises(ValueError, match="round-trip"):
        ms.main(["merge_settings.py", str(settings), str(repo)])

    assert settings.read_text() == before
    assert not list(tmp_path.glob(".settings.*"))


# --- install.sh end-to-end (HOME redirected to tmp_path; never the real home) ----


def test_install_sh_preserves_foreign_hooks(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings = home / ".claude" / "settings.json"
    write_json(settings, foreign_settings())
    env = {**os.environ, "HOME": str(home)}
    for _ in range(2):  # re-run must be safe too
        result = subprocess.run(
            ["bash", INSTALL_SH],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, result.stdout + result.stderr
    with open(REPO_HOOKS_JSON) as f:
        repo = json.load(f)["hooks"]
    merged = json.loads(settings.read_text())
    assert merged == ms.merge_hooks(foreign_settings(), repo)[0]
    assert commands(merged["hooks"]["PreToolUse"], "WebFetch") == [WEBFETCH_GUARD]
    assert ITERM in commands(merged["hooks"]["Stop"])
    assert merged["model"] == "opus"
    assert (
        home / ".claude" / "hooks" / "interlock" / "require_active_task.py"
    ).is_file()
    assert (home / ".claude" / "CLAUDE.md").read_text().count(
        "<!-- INTERLOCK:BEGIN -->"
    ) == 1


def test_install_sh_only_notifies_about_legacy_install(tmp_path):
    """TASK-54: the old claude-rails install dir and CLAUDE.md marker block are
    reported, never edited or deleted."""
    home = tmp_path / "home"
    legacy_dir = home / ".claude" / "hooks" / "claude-rails"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "require_active_task.py").write_text("# old copy\n")
    claude_md = home / ".claude" / "CLAUDE.md"
    legacy_block = "<!-- CLAUDE-RAILS:BEGIN -->\nold rules\n<!-- CLAUDE-RAILS:END -->\n"
    claude_md.write_text(legacy_block)
    result = subprocess.run(
        ["bash", INSTALL_SH],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLAUDE-RAILS:BEGIN" in result.stdout
    assert str(legacy_dir) in result.stdout
    assert (legacy_dir / "require_active_task.py").read_text() == "# old copy\n"
    text = claude_md.read_text()
    assert text.startswith(legacy_block)
    assert text.count("<!-- INTERLOCK:BEGIN -->") == 1


def test_install_sh_no_legacy_notice_on_clean_home(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    result = subprocess.run(
        ["bash", INSTALL_SH],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "안내:" not in result.stdout
    assert not (home / ".claude" / "hooks" / "claude-rails").exists()


# --- TASK-54: migration from the old claude-rails install dir ------------------------

OLD = "python3 $HOME/.claude/hooks/claude-rails/"
HOME = "/Users/x"


def test_legacy_entry_replaced_in_place_not_duplicated():
    existing = foreign_settings()
    existing["hooks"]["PreToolUse"].insert(
        0, {"matcher": "Bash", "hooks": [cmd(OLD + "block_dangerous_commands.py", timeout=9)]}
    )
    existing["hooks"]["Stop"][0]["hooks"].append(cmd(OLD + "block_stop_if_dirty.py"))
    merged, changes = ms.merge_hooks(existing, repo_hooks(), home=HOME)
    pre = merged["hooks"]["PreToolUse"]
    assert pre[0] == {
        "matcher": "Bash",
        "hooks": [cmd(OURS + "block_dangerous_commands.py")],
    }
    assert commands(merged["hooks"]["Stop"]) == [ITERM, OURS + "block_stop_if_dirty.py"]
    assert commands(pre, "WebFetch") == [WEBFETCH_GUARD]
    assert ("PreToolUse", "Bash", OURS + "block_dangerous_commands.py", "migrated") in changes
    assert ("Stop", None, OURS + "block_stop_if_dirty.py", "migrated") in changes
    assert not any(OLD in c for c in commands(pre, "Bash") + commands(pre))
    # re-running is a no-op
    assert ms.merge_hooks(merged, repo_hooks(), home=HOME)[1] == []


@pytest.mark.parametrize(
    "spelling",
    [
        "python3 ~/.claude/hooks/claude-rails/",
        "python3 ${HOME}/.claude/hooks/claude-rails/",
        "python3 /Users/x/.claude/hooks/claude-rails/",
    ],
)
def test_legacy_entry_spelled_with_other_home_forms_is_migrated(spelling):
    existing = {"hooks": {"Stop": [{"hooks": [cmd(spelling + "block_stop_if_dirty.py")]}]}}
    repo = {"Stop": [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]}
    merged, changes = ms.merge_hooks(existing, repo, home=HOME)
    assert merged["hooks"]["Stop"] == [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]
    assert changes == [("Stop", None, OURS + "block_stop_if_dirty.py", "migrated")]


def test_legacy_entry_dropped_when_new_one_already_installed():
    existing = {
        "hooks": {
            "Stop": [
                {"hooks": [cmd(OLD + "block_stop_if_dirty.py")]},
                {"hooks": [cmd(ITERM), cmd(OURS + "block_stop_if_dirty.py")]},
            ]
        }
    }
    repo = {"Stop": [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]}
    merged, changes = ms.merge_hooks(existing, repo, home=HOME)
    assert merged["hooks"]["Stop"] == [
        {"hooks": [cmd(ITERM), cmd(OURS + "block_stop_if_dirty.py")]}
    ]
    assert changes == [("Stop", None, OURS + "block_stop_if_dirty.py", "migrated")]


def test_legacy_entry_under_other_matcher_removed_and_new_one_added():
    existing = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Edit", "hooks": [cmd(ITERM), cmd(OLD + "block_dangerous_commands.py")]}
            ]
        }
    }
    repo = {"PreToolUse": [{"matcher": "Bash", "hooks": [cmd(OURS + "block_dangerous_commands.py")]}]}
    merged, changes = ms.merge_hooks(existing, repo, home=HOME)
    assert merged["hooks"]["PreToolUse"] == [
        {"matcher": "Edit", "hooks": [cmd(ITERM)]},
        {"matcher": "Bash", "hooks": [cmd(OURS + "block_dangerous_commands.py")]},
    ]
    assert [c[3] for c in changes] == ["migrated", "added"]


def test_duplicate_legacy_copies_collapse_to_one():
    existing = {
        "hooks": {
            "Stop": [
                {"hooks": [cmd(OLD + "block_stop_if_dirty.py")]},
                {"hooks": [cmd(OLD + "block_stop_if_dirty.py")]},
            ]
        }
    }
    repo = {"Stop": [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]}
    merged, _ = ms.merge_hooks(existing, repo, home=HOME)
    assert merged["hooks"]["Stop"] == [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]


def test_legacy_without_counterpart_and_foreign_hooks_untouched():
    gone = OLD + "hook_removed_from_repo.py"
    lookalike = "python3 $HOME/.claude/hooks/other-tool/block_stop_if_dirty.py"
    existing = {"hooks": {"Stop": [{"hooks": [cmd(gone), cmd(lookalike)]}]}}
    repo = {"Stop": [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]}
    merged, changes = ms.merge_hooks(existing, repo, home=HOME)
    assert commands(merged["hooks"]["Stop"]) == [
        gone,
        lookalike,
        OURS + "block_stop_if_dirty.py",
    ]
    assert changes == [("Stop", None, OURS + "block_stop_if_dirty.py", "added")]


def test_is_legacy_copy_edge_cases():
    assert ms.is_legacy_copy(None, OURS + "a.py", HOME) is False
    assert ms.is_legacy_copy(OLD + "a.py", None, HOME) is False
    assert ms.is_legacy_copy(OLD + "a.py", OURS + "b.py", HOME) is False
    assert ms.is_legacy_copy(OLD + "a.py", OURS + "a.py", HOME) is True


def test_merge_hooks_default_home_uses_expanduser(monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    old = "python3 /home/someone/.claude/hooks/claude-rails/block_stop_if_dirty.py"
    existing = {"hooks": {"Stop": [{"hooks": [cmd(old)]}]}}
    repo = {"Stop": [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]}
    merged, _ = ms.merge_hooks(existing, repo)
    assert merged["hooks"]["Stop"] == [{"hooks": [cmd(OURS + "block_stop_if_dirty.py")]}]


def test_main_reports_migration(tmp_path, capsys):
    existing = {"hooks": {"Stop": [{"hooks": [cmd(OLD + "block_stop_if_dirty.py")]}]}}
    settings, repo = setup_files(tmp_path, existing)
    assert ms.main(["merge_settings.py", str(settings), str(repo)]) == 0
    out = capsys.readouterr().out
    assert f"이전: Stop  {OURS}block_stop_if_dirty.py" in out
    assert "1개 옛 경로에서 이전" in out
    assert OLD not in settings.read_text()
