import io
import json

import pytest

import pre_git_safety_check as gsc


def run_main(monkeypatch, command):
    stdin_data = {"tool_name": "Bash", "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        gsc.main()
    return exc_info.value.code


def test_blocks_push_to_main(monkeypatch, capsys):
    code = run_main(monkeypatch, "git push origin main")
    assert code == 2
    assert "main" in capsys.readouterr().err


def test_blocks_push_to_master(monkeypatch):
    assert run_main(monkeypatch, "git push origin master") == 2


def test_blocks_push_with_refspec_to_main(monkeypatch):
    assert run_main(monkeypatch, "git push origin HEAD:main") == 2


def test_allows_push_to_task_branch(monkeypatch):
    assert run_main(monkeypatch, "git push -u origin task/TASK-3") == 0


def test_allows_bare_push(monkeypatch):
    # Documented limitation: bare `git push` (implicit current branch) isn't
    # checked, since determining the current branch would require shelling
    # out to git from within the hook.
    assert run_main(monkeypatch, "git push") == 0


def test_allows_dash_c_push_to_task_branch(monkeypatch):
    assert run_main(monkeypatch, "git -C /some/path push origin task/TASK-9") == 0


def test_blocks_dash_c_push_to_main(monkeypatch):
    assert run_main(monkeypatch, "git -C /some/path push origin main") == 2


def test_blocks_branch_delete_main(monkeypatch, capsys):
    code = run_main(monkeypatch, "git branch -D main")
    assert code == 2
    assert "main" in capsys.readouterr().err


def test_blocks_branch_delete_master_long_flag(monkeypatch):
    assert run_main(monkeypatch, "git branch --delete master") == 2


def test_allows_branch_delete_task_branch(monkeypatch):
    assert run_main(monkeypatch, "git branch -d task/TASK-3") == 0


def test_allows_branch_list(monkeypatch):
    assert run_main(monkeypatch, "git branch -a") == 0


def test_blocks_gh_pr_merge(monkeypatch, capsys):
    code = run_main(monkeypatch, "gh pr merge 5 --squash")
    assert code == 2
    assert "gh pr merge" in capsys.readouterr().err


def test_blocks_gh_pr_close(monkeypatch):
    assert run_main(monkeypatch, "gh pr close 5") == 2


def test_blocks_gh_issue_close(monkeypatch):
    assert run_main(monkeypatch, "gh issue close 12") == 2


def test_blocks_gh_release_delete(monkeypatch):
    assert run_main(monkeypatch, "gh release delete v1.0.0") == 2


def test_blocks_gh_repo_delete(monkeypatch):
    assert run_main(monkeypatch, "gh repo delete owner/repo") == 2


def test_allows_gh_pr_create(monkeypatch):
    assert run_main(monkeypatch, "gh pr create --title x --body y") == 0


def test_allows_gh_pr_view(monkeypatch):
    assert run_main(monkeypatch, "gh pr view 5") == 0


def test_allows_unrelated_command(monkeypatch):
    assert run_main(monkeypatch, "git status") == 0


def test_no_op_when_command_missing(monkeypatch):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {}}))
    )
    with pytest.raises(SystemExit) as exc_info:
        gsc.main()
    assert exc_info.value.code == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        gsc.main()
    assert exc_info.value.code == 0


def test_git_args_after_subcommand_returns_none_when_absent():
    assert gsc.git_args_after_subcommand("git status", "push") is None


def test_git_args_after_subcommand_falls_back_on_unparsable():
    assert gsc.git_args_after_subcommand('git push "unterminated', "push") is None


# --- TASK-37: basename 정규화, 명령 위치 판정, 파싱 실패 시 보수적 판정 ---


@pytest.mark.parametrize(
    "command",
    [
        # decision-1: the git executable is compared by basename
        "/usr/bin/git push origin main",
        "/opt/homebrew/bin/git push origin HEAD:master",
        "../bin/git push origin main",
        "/usr/bin/git -C /some/path push origin main",
        "git -C x push origin main",
        "git -c user.name=x --git-dir=.git push origin main",
        # env assignments / wrappers in front of the executable
        "sudo git push origin main",
        "sudo -E /usr/bin/git push origin main",
        "env GIT_TRACE=1 git push origin main",
        "FOO=1 /usr/bin/git push origin master",
        "command git push origin main",
        # a later segment of a compound line
        "git status && git push origin main",
        "git push -u origin task/TASK-3 && git push origin main",
        "cd repo; git push origin main",
        "(git push origin main)",
        "git fetch\ngit push origin main",
        # backslash-newline continuation is joined before parsing
        "git push origin \\\nmain",
        # a heredoc on the same line does not hide the push itself
        "git push origin main <<EOF\nbody\nEOF",
        "cat <<EOF\nnote\nEOF\ngit push origin main",
        # conservative: an unquoted git word handed to a runner still counts
        "timeout 60 git push origin main",
        "xargs git push origin main",
    ],
)
def test_blocks_push_to_protected_branch_in_any_command_form(monkeypatch, command):
    assert run_main(monkeypatch, command) == 2


@pytest.mark.parametrize(
    "command",
    [
        # quoted arguments are text, not a push
        'echo "git push origin main"',
        "git commit -m 'never git push origin main directly'",
        'backlog task edit TASK-37 --notes "git push origin main 금지"',
        # heredoc bodies are text, not commands
        "cat <<EOF\ngit push origin main\nEOF",
        "cat <<'EOF' > notes.md\ngit push origin master\ngit branch -D main\nEOF",
        "git commit -F - <<EOF\nblocks git push origin main\nEOF",
        # protected names outside the push segment
        "git push origin task/TASK-37; echo main",
        "/usr/bin/git push -u origin task/TASK-37",
    ],
)
def test_allows_text_mentions_and_non_protected_pushes(monkeypatch, command):
    assert run_main(monkeypatch, command) == 0


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/git branch -D main",
        "sudo git branch --delete master",
        "git status && git branch -d main",
    ],
)
def test_blocks_protected_branch_delete_in_any_command_form(monkeypatch, command):
    assert run_main(monkeypatch, command) == 2


def test_allows_branch_delete_text_in_heredoc(monkeypatch):
    assert run_main(monkeypatch, "cat <<EOF\ngit branch -D main\nEOF") == 0


@pytest.mark.parametrize(
    "command",
    [
        'git push origin main "unterminated',
        "/usr/bin/git push origin master 'x",
        'git branch -D main "x',
        "echo 'it is; git push origin main",
    ],
)
def test_blocks_unparsable_line_that_may_hit_protected_branch(
    monkeypatch, capsys, command
):
    # AC3: an unbalanced quote means command position can't be told from
    # text, so a line that could be a protected push/delete is blocked.
    assert run_main(monkeypatch, command) == 2
    assert "해석" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        'git push origin task/TASK-37 "unterminated',
        'git commit -m "unterminated',
        "echo 'push to main",  # no git word at all
        "git log 'main",  # neither push nor branch
    ],
)
def test_allows_unparsable_line_without_guarded_operation(monkeypatch, command):
    assert run_main(monkeypatch, command) == 0


def test_git_args_after_subcommand_handles_absolute_path():
    assert gsc.git_args_after_subcommand("/usr/bin/git push origin main", "push") == [
        "origin",
        "main",
    ]


def test_git_args_after_subcommand_ignores_heredoc_body():
    assert (
        gsc.git_args_after_subcommand("cat <<EOF\ngit push origin main\nEOF", "push")
        is None
    )
