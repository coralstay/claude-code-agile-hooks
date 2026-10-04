"""Tests for scripts/merge_settings.py (install.sh's settings.json hooks merge).

Run from the repo root together with the hook tests: `uvx pytest -q hooks scripts`.
These live next to the script (not in hooks/) because install.sh copies hooks/*.py to
~/.claude/hooks/claude-rails, where the script and install.sh would not exist.
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

RAILS = "python3 $HOME/.claude/hooks/claude-rails/"
ITERM = "~/.claude/iterm-status.sh"
WEBFETCH_GUARD = "python3 ~/.claude/webfetch_guard.py"


def cmd(command, **extra):
    return {"type": "command", "command": command, **extra}


def repo_hooks():
    return {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [cmd(RAILS + "block_dangerous_commands.py")]},
            {"hooks": [cmd(RAILS + "instructions_audit.py")]},
        ],
        "Stop": [{"hooks": [cmd(RAILS + "block_stop_if_dirty.py")]}],
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
    assert RAILS + "block_stop_if_dirty.py" in commands(hooks["Stop"])
    assert commands(hooks["PreToolUse"], "Bash") == [
        RAILS + "block_dangerous_commands.py"
    ]


def test_matcherless_group_is_reused_not_duplicated():
    merged, _ = ms.merge_hooks(foreign_settings(), repo_hooks())
    matcherless = [g for g in merged["hooks"]["PreToolUse"] if "matcher" not in g]
    assert len(matcherless) == 1
    assert [h["command"] for h in matcherless[0]["hooks"]] == [
        ITERM,
        RAILS + "instructions_audit.py",
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
        RAILS + "block_dangerous_commands.py",
    ]


def test_new_group_has_matcher_key_only_when_repo_group_has_one():
    merged, _ = ms.merge_hooks({"hooks": {}}, repo_hooks())
    pre = merged["hooks"]["PreToolUse"]
    assert {
        "matcher": "Bash",
        "hooks": [cmd(RAILS + "block_dangerous_commands.py")],
    } in pre
    assert {"hooks": [cmd(RAILS + "instructions_audit.py")]} in pre


def test_new_event_added():
    repo = {"SessionEnd": [{"hooks": [cmd(RAILS + "session_logger.py")]}]}
    merged, changes = ms.merge_hooks(foreign_settings(), repo)
    assert merged["hooks"]["SessionEnd"] == [
        {"hooks": [cmd(RAILS + "session_logger.py")]}
    ]
    assert changes == [("SessionEnd", None, RAILS + "session_logger.py", "added")]


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


def test_existing_rails_entry_updated_in_place_when_fields_change():
    target = RAILS + "block_dangerous_commands.py"
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
    target = RAILS + "block_dangerous_commands.py"
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
    target = RAILS + "block_dangerous_commands.py"
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
    assert f"추가: Stop  {RAILS}block_stop_if_dirty.py" in out
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
        home / ".claude" / "hooks" / "claude-rails" / "require_active_task.py"
    ).is_file()
    assert (home / ".claude" / "CLAUDE.md").read_text().count(
        "<!-- CLAUDE-RAILS:BEGIN -->"
    ) == 1
