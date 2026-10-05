import io
import json

import pytest

import pre_push_coverage_check as ppc

PUSH_INPUT = {"command": "git push"}


def run_main(monkeypatch, stdin_data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        ppc.main()
    return exc_info.value.code


def test_no_op_when_command_is_not_a_push(tmp_path, monkeypatch, capsys):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": "git status"}}
    )
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".interlock" / "coverage-log.jsonl").exists()


def test_no_op_when_no_config_file(tmp_path, monkeypatch, capsys):
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".interlock" / "coverage-log.jsonl").exists()


def test_no_op_when_coverage_command_key_missing(tmp_path, monkeypatch, capsys):
    (tmp_path / ".interlock.json").write_text(json.dumps({}))
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".interlock" / "coverage-log.jsonl").exists()


def test_allows_and_reports_when_command_succeeds(tmp_path, monkeypatch, capsys):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "echo 'TOTAL 100%' && exit 0"})
    )
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"
    assert "TOTAL 100%" in hso["systemMessage"]

    log_file = tmp_path / ".interlock" / "coverage-log.jsonl"
    lines = log_file.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["passed"] is True
    assert record["exit_code"] == 0
    assert "TOTAL 100%" in record["output"]
    assert "timestamp" in record


def test_denies_and_reports_when_command_fails(tmp_path, monkeypatch, capsys):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "echo 'TOTAL 42%' && exit 1"})
    )
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0  # blocking happens via JSON permissionDecision, not exit code
    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "미달" in hso["permissionDecisionReason"]
    assert "TOTAL 42%" in hso["systemMessage"]

    log_file = tmp_path / ".interlock" / "coverage-log.jsonl"
    record = json.loads(log_file.read_text().splitlines()[0])
    assert record["passed"] is False
    assert record["exit_code"] == 1


def test_fires_on_dash_c_push(tmp_path, monkeypatch, capsys):
    # Regression: `git -C <path> push ...` must still be recognized, not
    # just a literal `git push` prefix.
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "echo ran && exit 0"})
    )
    code = run_main(
        monkeypatch,
        {
            "cwd": str(tmp_path),
            "tool_input": {"command": f"git -C {tmp_path} push -u origin x"},
        },
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"


def _init_git_repo(cwd, branch):
    import subprocess

    subprocess.run(
        ["git", "init", "-q", "-b", branch], cwd=cwd, check=True, capture_output=True
    )
    (cwd / "f.txt").write_text("hi")
    subprocess.run(["git", "add", "f.txt"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=T",
            "commit",
            "-q",
            "-m",
            "init",
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_log_includes_session_project_branch_task_id(tmp_path, monkeypatch):
    _init_git_repo(tmp_path, "task/TASK-42")
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 0"})
    )
    run_main(
        monkeypatch,
        {"cwd": str(tmp_path), "session_id": "sess-abc123", "tool_input": PUSH_INPUT},
    )

    log_file = tmp_path / ".interlock" / "coverage-log.jsonl"
    record = json.loads(log_file.read_text().splitlines()[0])
    assert record["session_id"] == "sess-abc123"
    assert record["project"] == tmp_path.name
    assert record["branch"] == "task/TASK-42"
    assert record["task_id"] == "TASK-42"


def test_log_task_id_is_none_off_task_branch(tmp_path, monkeypatch):
    _init_git_repo(tmp_path, "main")
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 0"})
    )
    run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})

    log_file = tmp_path / ".interlock" / "coverage-log.jsonl"
    record = json.loads(log_file.read_text().splitlines()[0])
    assert record["branch"] == "main"
    assert record["task_id"] is None


def test_task_id_from_branch():
    assert ppc.task_id_from_branch("task/TASK-7") == "TASK-7"
    assert ppc.task_id_from_branch("main") is None
    assert ppc.task_id_from_branch("") is None


def test_log_appends_across_multiple_push_attempts(tmp_path, monkeypatch):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 0"})
    )
    run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})

    log_file = tmp_path / ".interlock" / "coverage-log.jsonl"
    lines = log_file.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["passed"] is False
    assert json.loads(lines[1])["passed"] is True


def test_append_log_creates_directory(tmp_path):
    ppc.append_log(str(tmp_path), {"a": 1})
    log_file = tmp_path / ".interlock" / "coverage-log.jsonl"
    assert json.loads(log_file.read_text().strip()) == {"a": 1}


def test_log_path(tmp_path):
    assert ppc.log_path(str(tmp_path)) == str(
        tmp_path / ".interlock" / "coverage-log.jsonl"
    )


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        ppc.main()
    assert exc_info.value.code == 0
    assert capsys.readouterr().out == ""


def test_configured_coverage_command_reads_file(tmp_path):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "pytest --cov"})
    )
    assert ppc.configured_coverage_command(str(tmp_path)) == "pytest --cov"


def test_configured_coverage_command_none_without_file(tmp_path):
    assert ppc.configured_coverage_command(str(tmp_path)) is None


def test_run_shell_captures_combined_output():
    code, output = ppc.run_shell(".", "echo out; echo err >&2; exit 5")
    assert code == 5
    assert "out" in output and "err" in output


# --- TASK-39: only a `git push` in command position counts ------------------

PUSH_TEXT_ONLY = [
    "echo git push",
    "echo /usr/bin/git",
    'echo "git push origin task/x"',
    "git commit -m 'then git push'",
    "backlog task edit TASK-1 --notes 'git push after review'",
    "cat <<'EOF' > notes.md\ngit push\nEOF",
    "cat <<EOF\n  git -C /p push\nEOF\necho done",
    "git -C /p status",
    "git log --grep push",
    "git --no-pager",
    "",
]

PUSH_REAL = [
    "git push",
    "/usr/bin/git push",
    "./git push",
    "git -C /p push",
    "git -c push.default=current push",
    "git --git-dir=.git push",
    "git -q push",
    "FOO=1 git push",
    "env FOO=1 git push origin task/x",
    "sudo -E git push",
    "cd /p && git push",
    "git commit -m x; git push",
    "false || git push",
    "(git push)",
    "git \\\npush",
    "cat <<'EOF' > f\nbody\nEOF\ngit push",
    'git push "unterminated',
]


@pytest.mark.parametrize("command", PUSH_TEXT_ONLY)
def test_command_runs_git_ignores_text(command):
    assert ppc.command_runs_git(command, "push") is False


@pytest.mark.parametrize("command", PUSH_REAL)
def test_command_runs_git_detects_real_push(command):
    assert ppc.command_runs_git(command, "push") is True


def test_command_runs_git_unparsable_falls_back_to_substring():
    assert ppc.command_runs_git('git commit -m "x', "push") is False
    assert ppc.command_runs_git('git push "x', "push") is True


@pytest.mark.parametrize("command", PUSH_TEXT_ONLY)
def test_text_mentioning_push_runs_no_coverage(tmp_path, monkeypatch, capsys, command):
    # Regression (TASK-39): `echo git push` and heredoc bodies used to run the
    # coverage command and log an attempt.
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": command}}
    )
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".interlock" / "coverage-log.jsonl").exists()


def test_fires_on_prefixed_absolute_push_in_chain(tmp_path, monkeypatch, capsys):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    command = "git commit -m x && FOO=1 /usr/bin/git push"
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": command}}
    )
    assert code == 0
    hso = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"


# --- TASK-46: no `if` filter any more, so this runs on every Bash call ---


@pytest.mark.parametrize(
    "command",
    ["ls -la", "git status", "cd x && gh pr view 1", "echo git push", ""],
)
def test_non_push_line_exits_before_config_or_subprocess(
    tmp_path, monkeypatch, capsys, command
):
    """A line without a push must stay cheap: no config read, no
    subprocess, no output."""
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run before a push is detected")

    monkeypatch.setattr(ppc.subprocess, "run", forbidden)
    monkeypatch.setattr(ppc, "configured_coverage_command", forbidden)
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": command}}
    )
    assert code == 0
    assert capsys.readouterr().out == ""


def test_segment_of_only_assignments_is_not_a_push():
    assert ppc.command_runs_git("FOO=1 BAR=2", "push") is False
    assert ppc.command_runs_git("FOO=1 BAR=2; git push", "push") is True


# TASK-54: .interlock.json 우선, 옛 .claude-rails.json fallback.
# 로그는 옛 설정만 쓰고 .interlock/이 아직 없을 때만 .claude-rails/에 남는다.
def test_config_only_new_name_logs_to_interlock(tmp_path, monkeypatch, capsys):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "echo new && exit 0"})
    )
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT}) == 0
    assert "new" in capsys.readouterr().out
    assert (tmp_path / ".interlock" / "coverage-log.jsonl").exists()
    assert not (tmp_path / ".claude-rails").exists()


def test_config_only_legacy_name_logs_to_legacy_dir(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-rails.json").write_text(
        json.dumps({"coverageCommand": "echo old && exit 0"})
    )
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT}) == 0
    assert "old" in capsys.readouterr().out
    assert (tmp_path / ".claude-rails" / "coverage-log.jsonl").exists()
    assert not (tmp_path / ".interlock").exists()


def test_config_both_names_new_wins(tmp_path, monkeypatch, capsys):
    (tmp_path / ".interlock.json").write_text(
        json.dumps({"coverageCommand": "echo new && exit 0"})
    )
    (tmp_path / ".claude-rails.json").write_text(
        json.dumps({"coverageCommand": "echo old && exit 1"})
    )
    assert ppc.configured_coverage_command(str(tmp_path)) == "echo new && exit 0"
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT}) == 0
    out = capsys.readouterr().out
    assert "new" in out and "old" not in out
    assert (tmp_path / ".interlock" / "coverage-log.jsonl").exists()
    assert not (tmp_path / ".claude-rails").exists()


def test_legacy_config_with_existing_interlock_dir_logs_to_interlock(tmp_path):
    (tmp_path / ".claude-rails.json").write_text(json.dumps({}))
    (tmp_path / ".interlock").mkdir()
    assert ppc.log_path(str(tmp_path)) == str(
        tmp_path / ".interlock" / "coverage-log.jsonl"
    )


def test_project_config_path_none(tmp_path):
    assert ppc.project_config_path(str(tmp_path)) is None
