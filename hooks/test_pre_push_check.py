import io
import json
import subprocess

import pytest

import pre_push_check as ppc

PUSH = {"command": "git push"}


def run_main(monkeypatch, stdin_data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        ppc.main()
    return exc_info.value.code


def test_passes_when_backlog_not_installed(monkeypatch):
    monkeypatch.setattr(ppc, "has_command", lambda name: False)
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": PUSH}) == 0


def test_passes_when_not_backlog_project(monkeypatch):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: False)
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": PUSH}) == 0


def test_passes_when_not_on_task_branch(monkeypatch):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "main")
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": PUSH}) == 0


def test_passes_when_task_view_fails(monkeypatch):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "task/TASK-3")
    monkeypatch.setattr(ppc, "task_view", lambda cwd, task_id: None)
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": PUSH}) == 0


def test_denies_when_not_done(monkeypatch, capsys):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "task/TASK-3")
    monkeypatch.setattr(
        ppc,
        "task_view",
        lambda cwd, task_id: {"task": {"status": "In Progress", "finalSummary": ""}},
    )
    code = run_main(monkeypatch, {"cwd": "/x", "tool_input": PUSH})
    assert code == 2
    assert "Done 상태가 아닙니다" in capsys.readouterr().err


def test_denies_when_done_but_no_summary(monkeypatch, capsys):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "task/TASK-3")
    monkeypatch.setattr(
        ppc,
        "task_view",
        lambda cwd, task_id: {"task": {"status": "Done", "finalSummary": "   "}},
    )
    code = run_main(monkeypatch, {"cwd": "/x", "tool_input": PUSH})
    assert code == 2
    assert "final summary가 비어있습니다" in capsys.readouterr().err


def test_passes_when_done_with_summary(monkeypatch):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "task/TASK-3")
    monkeypatch.setattr(
        ppc,
        "task_view",
        lambda cwd, task_id: {"task": {"status": "Done", "finalSummary": "Shipped."}},
    )
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": PUSH}) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        ppc.main()
    assert exc_info.value.code == 0


def test_task_view_returns_none_on_nonzero_exit(tmp_path, monkeypatch):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "backlog"
    script.write_text("#!/bin/bash\nexit 1\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + ":" + os.environ.get("PATH", ""))
    assert ppc.task_view(str(tmp_path), "TASK-3") is None


def test_has_command_true_for_python3():
    assert ppc.has_command("python3") is True


def test_has_command_false_for_bogus():
    assert ppc.has_command("definitely-not-a-real-command-xyz") is False


def test_is_backlog_project_true(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert ppc.is_backlog_project(str(tmp_path)) is True


def test_is_backlog_project_false_without_git(tmp_path):
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x: 1")
    assert ppc.is_backlog_project(str(tmp_path)) is False


def test_is_backlog_project_false(tmp_path):
    assert ppc.is_backlog_project(str(tmp_path)) is False


def test_denies_bare_git_dash_c_push_when_not_done(monkeypatch, capsys):
    # Regression: `git -C <path> push ...` previously slipped past because
    # settings.json's `if` filter only recognized `git push` as the literal
    # prefix. The hook must catch this itself now.
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "task/TASK-3")
    monkeypatch.setattr(
        ppc,
        "task_view",
        lambda cwd, task_id: {"task": {"status": "In Progress", "finalSummary": ""}},
    )
    stdin_data = {
        "cwd": "/x",
        "tool_input": {
            "command": "git -C /home/user/project push -u origin task/TASK-3"
        },
    }
    code = run_main(monkeypatch, stdin_data)
    assert code == 2
    assert "Done 상태가 아닙니다" in capsys.readouterr().err


def test_no_op_when_command_is_not_a_push(monkeypatch):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    stdin_data = {"cwd": "/x", "tool_input": {"command": "git status"}}
    assert run_main(monkeypatch, stdin_data) == 0


def test_command_invokes_git_push_handles_dash_c():
    cmd = "git -C /some/path push -u origin task/TASK-3"
    assert ppc.command_invokes_git_push(cmd) is True


def test_command_invokes_git_push_false_for_other_subcommand():
    cmd = "git -C /some/path status"
    assert ppc.command_invokes_git_push(cmd) is False


def test_command_invokes_git_push_plain():
    assert ppc.command_invokes_git_push("git push") is True


def test_command_invokes_git_push_in_compound_command():
    assert ppc.command_invokes_git_push("npm test && git push") is True


def test_command_invokes_git_push_skips_bare_flag():
    assert ppc.command_invokes_git_push("git -q push") is True


def test_command_invokes_git_push_detects_absolute_path_bypass():
    assert ppc.command_invokes_git_push("/usr/bin/git push") is True


def test_command_invokes_git_push_detects_relative_path_bypass():
    assert ppc.command_invokes_git_push("./git push") is True


def test_command_invokes_git_push_ignores_git_outside_verb_position():
    assert ppc.command_invokes_git_push("echo /usr/bin/git") is False


# --- TASK-34: only a command-position `git push` counts ---------------------
#
# Before TASK-34 the whole command was shlex-split as one flat token list, so
# `git` `push` appearing as two adjacent words *anywhere* (an echo argument,
# a heredoc body) counted as a push, and an unbalanced quote anywhere (an
# apostrophe in a heredoc body) fell back to "is 'push' a substring?".


@pytest.mark.parametrize(
    "command",
    [
        # heredoc body mentioning it (quoted and unquoted delimiter)
        "cat > /tmp/notes.md <<'EOF'\nnext: git push origin task/TASK-3\nEOF",
        "cat > /tmp/notes.md <<EOF\ngit push\nEOF\necho done",
        # heredoc body with an apostrophe (unbalanced for shlex) + the word
        "cat > /tmp/notes.md <<'EOF'\ndon't git push yet\nEOF",
        # commit message built from a heredoc (the usual Claude Code pattern)
        "git commit -m \"$(cat <<'EOF'\nTASK-3: git push 전에 Done 처리\n\nit's fine\nEOF\n)\"",
        # commit message as a plain quoted argument
        'git commit -m "git push 전에 확인"',
        # backlog doc / notes text containing the words
        'backlog doc create "릴리스 절차" -c "1. 테스트 2. git push 3. PR"',
        "backlog task edit TASK-3 --notes 'Done 후에 git push 한다'",
        # unquoted words as arguments of another command
        "echo git push",
        "printf '%s\\n' x && echo run git push later",
        # status edit chained with text-only mentions
        'backlog task edit TASK-3 -s Done && echo "이제 git push 가능"',
    ],
)
def test_command_invokes_git_push_ignores_text_mentions(command):
    assert ppc.command_invokes_git_push(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin task/TASK-3",
        "/usr/bin/git push",
        "/opt/homebrew/bin/git -C /repo push origin HEAD",
        "git -c push.default=current push",
        "git --git-dir=/repo/.git --work-tree=/repo push",
        "FOO=1 git push",
        "env FOO=1 git push",
        "sudo git push",
        "command git push",
        "time git push",
        "cd /repo && git push",
        "git status; git push",
        "npm test || git push",
        "(cd /repo && git push)",
        "{ git push; }",
        "echo $(git push)",
        "git add . && git commit -m 'x' && git push",
        "git status\ngit push",
        "git \\\n  push origin task/TASK-3",
        # a heredoc earlier in the line does not hide a later real push
        "cat > /tmp/n <<'EOF'\nbody\nEOF\ngit push",
        # chained after a status edit: still a push (judged before the edit
        # runs - PreToolUse sees the pre-command state)
        "backlog task edit TASK-3 -s Done && git push",
    ],
)
def test_command_invokes_git_push_detects_real_pushes(command):
    assert ppc.command_invokes_git_push(command) is True


def test_command_invokes_git_push_falls_back_conservatively_when_unparsable():
    # Unbalanced quote outside any heredoc: can't tell command position from
    # text, so any 'push' in the (heredoc-stripped) line counts as a push.
    assert ppc.command_invokes_git_push('git push origin "unterminated') is True
    assert ppc.command_invokes_git_push('echo "about to push') is True
    assert ppc.command_invokes_git_push('git commit -m "unterminated') is False


def _in_progress(monkeypatch):
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "task/TASK-3")
    monkeypatch.setattr(
        ppc,
        "task_view",
        lambda cwd, task_id: {"task": {"status": "In Progress", "finalSummary": ""}},
    )


def test_main_passes_heredoc_mentioning_push_while_in_progress(monkeypatch):
    _in_progress(monkeypatch)
    cmd = "backlog doc create x <<'EOF'\nDon't git push before Done\nEOF"
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": {"command": cmd}}) == 0


def test_main_passes_commit_message_mentioning_push_while_in_progress(monkeypatch):
    _in_progress(monkeypatch)
    cmd = "git commit -m \"$(cat <<'EOF'\nTASK-3: git push 준비\nEOF\n)\""
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": {"command": cmd}}) == 0


def test_main_still_denies_push_chained_after_status_edit(monkeypatch, capsys):
    # Known limitation, kept on purpose: PreToolUse runs before the whole
    # line, so the `-s Done` edit hasn't happened yet when this is judged.
    _in_progress(monkeypatch)
    cmd = "backlog task edit TASK-3 -s Done && git push"
    code = run_main(monkeypatch, {"cwd": "/x", "tool_input": {"command": cmd}})
    assert code == 2
    assert "Done 상태가 아닙니다" in capsys.readouterr().err


def test_current_branch_real_git(tmp_path):
    subprocess.run(
        ["git", "init", "-q", "-b", "task/TASK-9"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f.txt").write_text("hi")
    subprocess.run(
        ["git", "add", "f.txt"], cwd=tmp_path, check=True, capture_output=True
    )
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
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert ppc.current_branch(str(tmp_path)) == "task/TASK-9"


def test_task_view_returns_none_on_malformed_json(tmp_path, monkeypatch):
    import os

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "backlog"
    script.write_text("#!/bin/bash\necho 'not json'\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + ":" + os.environ.get("PATH", ""))
    assert ppc.task_view(str(tmp_path), "TASK-3") is None


# --- TASK-46: no `if` filter any more, so this runs on every Bash call ---


@pytest.mark.parametrize(
    "command", ["ls -la", "git status", "cd x && gh pr view 1", "echo git push", ""]
)
def test_non_push_line_exits_before_any_lookup(monkeypatch, command):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not run before a push is detected")

    monkeypatch.setattr(ppc.subprocess, "run", forbidden)
    monkeypatch.setattr(ppc, "has_command", forbidden)
    stdin_data = {"cwd": "/x", "tool_input": {"command": command}}
    assert run_main(monkeypatch, stdin_data) == 0


@pytest.mark.parametrize(
    "command",
    ["/usr/bin/git push origin x", "true && git push origin x", "cd y && git push"],
)
def test_path_and_compound_push_reach_the_gate(monkeypatch, capsys, command):
    """The forms the old `if: Bash(git *)` filter hid (path call) or that
    it matched only per subcommand are still judged by main()."""
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(ppc, "current_branch", lambda cwd: "task/TASK-3")
    monkeypatch.setattr(
        ppc,
        "task_view",
        lambda cwd, tid: {"task": {"status": "In Progress", "finalSummary": ""}},
    )
    assert run_main(monkeypatch, {"cwd": "/x", "tool_input": {"command": command}}) == 2
    assert "TASK-3" in capsys.readouterr().err
