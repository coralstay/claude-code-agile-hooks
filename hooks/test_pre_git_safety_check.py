import io
import json
import subprocess

import pytest

import pre_git_safety_check as gsc


@pytest.fixture(autouse=True)
def hermetic_git(monkeypatch, tmp_path):
    """TASK-38: the hook now runs git for pushes. Keep that away from the
    user's git config and from this repo's real remote (no network): the
    default cwd is an empty non-repo directory."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("CDPATH", raising=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)


def run_main(monkeypatch, command, cwd=None):
    stdin_data = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        stdin_data["cwd"] = str(cwd)
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


def test_blocks_bare_push_outside_a_repository(monkeypatch, capsys):
    # TASK-38: bare `git push` is no longer skipped. Outside a repository the
    # current branch can't be determined, so it is blocked (fail-closed) -
    # git itself would fail there anyway.
    assert run_main(monkeypatch, "git push") == 2
    assert "현재 브랜치" in capsys.readouterr().err


def test_allows_dash_c_push_to_task_branch(monkeypatch, tmp_path):
    work = make_repo(tmp_path)
    assert run_main(monkeypatch, f"git -C {work} push origin task/TASK-9") == 0


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


# --- TASK-38: 최초 push 예외(ls-remote) + refspec 없는 bare push 판정 ---
# Real repositories: a local bare repo is the remote, so ls-remote works
# offline. The hook's own git calls run with the hermetic config above.


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def make_repo(tmp_path, seeded=False):
    """tmp_path/work on `main` (one commit), origin = empty bare repo
    tmp_path/remote.git. `seeded` pushes main there first."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(work, "commit", "-q", "--allow-empty", "-m", "init")
    git(work, "remote", "add", "origin", str(remote))
    if seeded:
        git(work, "push", "-q", "origin", "main")
    return work


@pytest.fixture
def fresh(tmp_path):
    return make_repo(tmp_path)


@pytest.fixture
def seeded(tmp_path):
    return make_repo(tmp_path, seeded=True)


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin main",
        "git push origin main",
        "git push origin HEAD:main",
        "git push",
        "git push -u origin",
        "/usr/bin/git push origin master",
        "git push --all origin",
    ],
)
def test_allows_first_push_to_protected_branch(monkeypatch, fresh, command):
    # AC1: the remote has no main/master yet - nothing to protect.
    assert run_main(monkeypatch, command, cwd=fresh) == 0


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin main",
        "git push origin HEAD:refs/heads/main",
        "git push origin refs/heads/main:refs/heads/main",
        "git push origin HEAD",
        "git push origin @",
        "git push origin main:",
        "git push --all origin",
        "git push --branches origin",
        "git push --al origin",
        "git push origin :",
    ],
)
def test_blocks_push_when_remote_branch_exists(monkeypatch, capsys, seeded, command):
    assert run_main(monkeypatch, command, cwd=seeded) == 2
    assert "이미 존재" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push origin",
        "git push -u origin",
        "git push --repo=origin",
        "git push -o ci.skip origin",
        "git push -oci.skip origin",
        "git push --push-option ci.skip origin",
        "git push --push-opt=ci.skip origin",
        "git push --no-verify",
        "git push -- origin",
    ],
)
def test_blocks_bare_push_on_main_with_upstream(monkeypatch, seeded, command):
    # AC2: the known bypass - preset upstream, then push without a refspec.
    git(seeded, "config", "branch.main.remote", "origin")
    git(seeded, "config", "branch.main.merge", "refs/heads/main")
    assert run_main(monkeypatch, command, cwd=seeded) == 2


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin",
        "git push -u origin task/TASK-38",
        "git push origin HEAD",
        "git push --tags",
        "git push origin task/TASK-38:task/TASK-38",
    ],
)
def test_allows_push_on_task_branch(monkeypatch, seeded, command):
    git(seeded, "checkout", "-q", "-b", "task/TASK-38")
    assert run_main(monkeypatch, command, cwd=seeded) == 0


def test_task_branch_tracking_main_follows_push_default(monkeypatch, seeded):
    # `git checkout -b task/x origin/main` sets upstream main. With the
    # default push.default=simple, git pushes to the same name -> allowed.
    git(seeded, "checkout", "-q", "-b", "task/TASK-38")
    git(seeded, "config", "branch.task/TASK-38.remote", "origin")
    git(seeded, "config", "branch.task/TASK-38.merge", "refs/heads/main")
    assert run_main(monkeypatch, "git push", cwd=seeded) == 0
    git(seeded, "config", "push.default", "upstream")
    assert run_main(monkeypatch, "git push", cwd=seeded) == 2
    git(seeded, "config", "push.default", "current")
    assert run_main(monkeypatch, "git push", cwd=seeded) == 0
    # git rejects an unknown mode; the hook blocks either way
    git(seeded, "config", "push.default", "bogus")
    assert run_main(monkeypatch, "git push", cwd=seeded) == 2


def test_push_default_matching_and_nothing(monkeypatch, seeded):
    git(seeded, "checkout", "-q", "-b", "task/TASK-38")
    git(seeded, "config", "push.default", "matching")
    assert run_main(monkeypatch, "git push", cwd=seeded) == 2
    git(seeded, "config", "push.default", "nothing")
    assert run_main(monkeypatch, "git push", cwd=seeded) == 0


def test_remote_push_config_maps_to_main(monkeypatch, seeded):
    git(seeded, "checkout", "-q", "-b", "task/TASK-38")
    git(seeded, "config", "--add", "remote.origin.push", "^refs/heads/wip")
    git(
        seeded,
        "config",
        "--add",
        "remote.origin.push",
        "refs/heads/task/TASK-38:refs/heads/main",
    )
    assert run_main(monkeypatch, "git push", cwd=seeded) == 2
    assert run_main(monkeypatch, "git push origin task/TASK-38", cwd=seeded) == 2
    # an explicit `:<dst>` is not remapped
    assert (
        run_main(monkeypatch, "git push origin task/TASK-38:task/TASK-38", cwd=seeded)
        == 0
    )


def test_remote_push_config_wildcard_and_forced(monkeypatch, fresh, capsys):
    git(fresh, "checkout", "-q", "-b", "task/TASK-38")
    git(fresh, "config", "remote.origin.push", "+refs/heads/*:refs/heads/*")
    assert run_main(monkeypatch, "git push", cwd=fresh) == 2
    assert "force" in capsys.readouterr().err


def test_remote_mirror_config_blocks(monkeypatch, fresh):
    git(fresh, "config", "remote.origin.mirror", "true")
    assert run_main(monkeypatch, "git push", cwd=fresh) == 2


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "git push -f -u origin main",
        "git push -uf origin main",
        "git push --forc origin main",
        "git push --force-with-lease origin main",
        "git push origin +main",
        "git push origin +HEAD:main",
        "git push --mirror origin",
        "git push origin :main",
        "git push origin --delete main",
        "git push -d origin master",
    ],
)
def test_force_and_delete_block_even_on_first_push(monkeypatch, capsys, fresh, command):
    # Decision: the first-push exception never covers force/mirror/delete.
    assert run_main(monkeypatch, command, cwd=fresh) == 2
    assert "force" in capsys.readouterr().err


def test_force_push_to_task_branch_is_not_this_hooks_business(monkeypatch, fresh):
    assert run_main(monkeypatch, "git push -f origin task/TASK-38", cwd=fresh) == 0


@pytest.mark.parametrize(
    "command",
    [
        "git push nowhere main",  # no such remote
        "git push -- -x main",  # remote that looks like an option
        # the positional repository wins over --repo, as in git
        "git push --repo=origin main",
    ],
)
def test_blocks_when_remote_cannot_be_checked(monkeypatch, capsys, fresh, command):
    assert run_main(monkeypatch, command, cwd=fresh) == 2
    assert "확인할 수 없어" in capsys.readouterr().err


def test_dash_c_variants(monkeypatch, tmp_path):
    work = make_repo(tmp_path)
    assert run_main(monkeypatch, "git -C work push -u origin main", cwd=tmp_path) == 0
    assert run_main(monkeypatch, f"git -C {work} push", cwd=tmp_path) == 0
    git(work, "push", "-q", "origin", "main")
    assert run_main(monkeypatch, "git -C work push -u origin main", cwd=tmp_path) == 2
    assert run_main(monkeypatch, f"/usr/bin/git -C {work} push", cwd=tmp_path) == 2
    assert run_main(monkeypatch, "git --git-dir=work/.git push", cwd=tmp_path) == 2
    # `-C ""` is a no-op
    assert run_main(monkeypatch, 'git -C "" push', cwd=work) == 2


def test_cd_before_push_is_followed(monkeypatch, tmp_path):
    work = make_repo(tmp_path, seeded=True)
    assert run_main(monkeypatch, "cd work && git push", cwd=tmp_path) == 2
    assert run_main(monkeypatch, f"cd {work}; git push origin main", cwd=tmp_path) == 2
    # a failed cd leaves the cwd where it was
    assert run_main(monkeypatch, "cd nowhere; git push", cwd=work) == 2


def test_cd_not_carried_over_pipe_or_subshell(monkeypatch, tmp_path):
    work = make_repo(tmp_path, seeded=True)
    other = tmp_path / "other"
    git(tmp_path, "init", "-q", "-b", "task/x", str(other))
    git(other, "commit", "-q", "--allow-empty", "-m", "init")
    # the push really runs in `work` (on main) - judging it in `other` would
    # wrongly allow it
    assert run_main(monkeypatch, f"(cd {other}); git push", cwd=work) == 2
    assert run_main(monkeypatch, f"cd {other} | git push", cwd=work) == 2
    assert run_main(monkeypatch, f"cd {other} || git push", cwd=work) == 2
    # and the cd to `other` does apply to a push in the same subshell
    assert run_main(monkeypatch, f"(cd {other} && git push); true", cwd=work) == 0


@pytest.mark.parametrize(
    "command",
    [
        "cd - && git push",
        "cd $REPO && git push",
        "popd && git push",
        "pushd `x` && git push",
    ],
)
def test_unknown_cd_target_blocks_push_that_needs_git(monkeypatch, seeded, command):
    assert run_main(monkeypatch, command, cwd=seeded) == 2


def test_unknown_cd_target_does_not_affect_explicit_task_refspec(monkeypatch, seeded):
    assert run_main(monkeypatch, "cd - && git push origin a:task/x", cwd=seeded) == 0


def test_cd_home_and_tilde_and_cdpath(monkeypatch, tmp_path):
    work = make_repo(tmp_path, seeded=True)
    monkeypatch.setenv("HOME", str(work))
    outside = tmp_path / "outside"
    assert run_main(monkeypatch, "cd && git push", cwd=outside) == 2
    assert run_main(monkeypatch, "cd -P ~ && git push", cwd=outside) == 2
    monkeypatch.setenv("HOME", str(tmp_path))
    assert run_main(monkeypatch, "pushd ~/work && git push", cwd=outside) == 2
    monkeypatch.setenv("CDPATH", str(tmp_path))
    # CDPATH could resolve `work` anywhere - unknown cwd, blocked
    assert (
        run_main(monkeypatch, "cd work && git push origin a:task/x", cwd=outside) == 0
    )
    assert run_main(monkeypatch, "cd work && git push", cwd=outside) == 2


@pytest.mark.parametrize(
    "command",
    [
        "git -c push.default=current push",
        "git --config-env=push.default=X push",
        "git --exec-path=/tmp push",
        "GIT_DIR=elsewhere git push",
        "env GIT_WORK_TREE=x git push origin main",
    ],
)
def test_opaque_git_settings_block_push_that_needs_git(monkeypatch, fresh, command):
    # these change what git would see; the hook doesn't pass them to its own
    # queries (they'd run before the human approves), so it can't verify
    assert run_main(monkeypatch, command, cwd=fresh) == 2


def test_opaque_settings_allowed_for_explicit_task_refspec(monkeypatch, fresh):
    assert run_main(monkeypatch, "git -c x.y=1 push origin a:task/x", cwd=fresh) == 0


def test_detached_head(monkeypatch, seeded):
    git(seeded, "checkout", "-q", "--detach")
    # git itself refuses a bare push from a detached HEAD
    assert run_main(monkeypatch, "git push", cwd=seeded) == 0
    assert run_main(monkeypatch, "git push origin HEAD", cwd=seeded) == 0


def test_push_remote_resolution(monkeypatch, tmp_path):
    work = make_repo(tmp_path)  # origin is empty
    full = tmp_path / "full.git"
    git(tmp_path, "clone", "-q", "--bare", str(work), str(full))  # has main
    git(work, "remote", "add", "full", str(full))
    assert run_main(monkeypatch, "git push", cwd=work) == 0
    git(work, "config", "remote.pushDefault", "full")
    assert run_main(monkeypatch, "git push", cwd=work) == 2
    git(work, "config", "branch.main.pushRemote", "origin")
    assert run_main(monkeypatch, "git push", cwd=work) == 0
    git(work, "config", "--unset", "branch.main.pushRemote")
    git(work, "config", "--unset", "remote.pushDefault")
    git(work, "config", "branch.main.remote", "full")
    assert run_main(monkeypatch, "git push", cwd=work) == 2
    # detached HEAD: only remote.pushDefault applies
    git(work, "checkout", "-q", "--detach")
    git(work, "config", "push.default", "matching")
    assert run_main(monkeypatch, "git push", cwd=work) == 0
    git(work, "config", "remote.pushDefault", "full")
    assert run_main(monkeypatch, "git push", cwd=work) == 2


def test_pushurl_and_multiple_urls_are_checked(monkeypatch, tmp_path):
    work = make_repo(tmp_path)  # origin url is empty
    full = tmp_path / "full.git"
    git(tmp_path, "clone", "-q", "--bare", str(work), str(full))
    git(work, "config", "remote.origin.pushurl", str(full))
    assert run_main(monkeypatch, "git push origin main", cwd=work) == 2
    git(work, "config", "--unset", "remote.origin.pushurl")
    git(work, "config", "--add", "remote.origin.url", str(full))
    assert run_main(monkeypatch, "git push origin main", cwd=work) == 2


def test_push_instead_of_blocks(monkeypatch, capsys, fresh):
    git(fresh, "config", "url.file:///elsewhere/.pushInsteadOf", "/")
    assert run_main(monkeypatch, "git push origin main", cwd=fresh) == 2
    assert "pushInsteadOf" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git branch -D task/x",
        "git branch -D main",
        "git log --oneline main",
        "gh pr view 5",
        "echo hi && ls -la",
        'git commit -m "git push origin main"',
        "cat <<EOF\ngit push\nEOF",
        # explicit `:<dst>` to a non-protected branch needs no git query
        "git push origin HEAD:task/x",
        "git push origin +a:task/x",
    ],
)
def test_no_subprocess_for_commands_that_need_no_git_query(monkeypatch, command):
    def forbidden(*args, **kwargs):
        raise AssertionError(f"subprocess called: {args}")

    monkeypatch.setattr(gsc.subprocess, "run", forbidden)
    run_main(monkeypatch, command)


def test_run_git_returns_code_and_stdout(fresh):
    assert gsc.run_git(str(fresh), [], ["rev-parse", "--abbrev-ref", "HEAD"]) == (
        0,
        "main\n",
    )


def test_run_git_none_for_unknown_cwd():
    assert gsc.run_git(None, [], ["status"]) is None


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired(cmd="git", timeout=gsc.GIT_TIMEOUT),
        FileNotFoundError("git"),
        PermissionError("git"),
    ],
)
def test_run_git_none_on_timeout_or_missing_git(monkeypatch, error):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        raise error

    monkeypatch.setattr(gsc.subprocess, "run", fake_run)
    assert gsc.run_git("/", ["--git-dir=x"], ["ls-remote"]) is None
    assert seen["timeout"] == gsc.GIT_TIMEOUT
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_ls_remote_timeout_blocks(monkeypatch, capsys, fresh):
    def fake_run(cmd, **kwargs):
        if "ls-remote" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=gsc.GIT_TIMEOUT)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(gsc.subprocess, "run", fake_run)
    assert run_main(monkeypatch, "git push origin main", cwd=fresh) == 2
    assert "시간 초과" in capsys.readouterr().err


def test_config_read_failure_blocks(monkeypatch, capsys):
    def fake_run_git(cwd, global_opts, args):
        return (1, "") if args[0] == "config" else (0, "main\n")

    monkeypatch.setattr(gsc, "run_git", fake_run_git)
    assert run_main(monkeypatch, "git push origin task/x") == 2
    assert "config" in capsys.readouterr().err


def test_after_cd_ignores_segment_without_command():
    assert gsc.after_cd(["sudo"], "/x") == "/x"


def test_segments_with_cwd_tolerates_unbalanced_paren():
    assert gsc.segments_with_cwd([")", "git", "push"], "/x") == [
        (["git", "push"], "/x")
    ]


def test_parse_push_args_edge_cases():
    info = gsc.parse_push_args(["-o"])  # option argument missing
    assert info["remote"] is None and info["refspecs"] == []
    info = gsc.parse_push_args(["--repo"])
    assert not info["remote"]
    info = gsc.parse_push_args(["-", "main"])
    assert info["remote"] == "-" and info["refspecs"] == ["main"]
