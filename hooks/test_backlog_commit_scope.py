import io
import json
import os
import subprocess

import pytest

import backlog_commit_scope as bcs

DRAFT = "backlog/drafts/draft-1 - 새-기능.md"
TASK = "backlog/tasks/task-7 - 새-기능.md"
OTHER_TASK = "backlog/tasks/task-3 - 기존.md"
DRAFT_BODY = (
    "---\nid: DRAFT-1\ntitle: 새 기능\nstatus: Draft\nlabels: []\n---\n\n"
    "## Description\n\n" + "긴 설명 줄입니다.\n" * 20
)


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def write(repo, rel, text="x\n"):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "commit.gpgsign", "false")
    write(tmp_path, "backlog/config.yml", "project_name: t\n")
    write(tmp_path, "src/app.py", "print(1)\n")
    write(tmp_path, OTHER_TASK, "---\nid: TASK-3\n---\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


@pytest.fixture
def repo_with_draft(repo):
    write(repo, DRAFT, DRAFT_BODY)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "draft")
    return repo


def promote(repo):
    """Mimic `backlog draft promote`: move the file and rewrite its id/status."""
    os.makedirs(repo / "backlog/tasks", exist_ok=True)
    body = (repo / DRAFT).read_text()
    (repo / DRAFT).unlink()
    write(
        repo,
        TASK,
        body.replace("DRAFT-1", "TASK-7").replace("status: Draft", "status: To Do"),
    )


def run_main(monkeypatch, cwd, command="git commit -m x"):
    payload = {"cwd": str(cwd), "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        bcs.main()
    return exc_info.value.code


# --- check_scope (pure) ----------------------------------------------------


def test_check_scope_empty_is_fine():
    assert bcs.check_scope([]) is None


def test_check_scope_draft_only_is_fine():
    assert bcs.check_scope([("A", DRAFT, None)]) is None


def test_check_scope_draft_plus_draft_edit_is_fine():
    entries = [("A", DRAFT, None), ("M", "backlog/drafts/draft-0 - old.md", None)]
    assert bcs.check_scope(entries) is None


def test_check_scope_draft_mixed_is_denied():
    msg = bcs.check_scope([("A", DRAFT, None), ("M", "src/app.py", None)])
    assert "드래프트 생성 커밋은 드래프트만" in msg
    assert "src/app.py" in msg


def test_check_scope_promotion_only_is_fine():
    assert bcs.check_scope([("R", DRAFT, TASK)]) is None


def test_check_scope_promotion_with_task_edits_is_fine():
    entries = [("R", DRAFT, TASK), ("M", OTHER_TASK, None)]
    assert bcs.check_scope(entries) is None


def test_check_scope_promotion_mixed_is_denied():
    msg = bcs.check_scope([("R", DRAFT, TASK), ("M", "README.md", None)])
    assert "승격 커밋은 승격만" in msg
    assert "README.md" in msg


def test_check_scope_unpaired_delete_add_counts_as_promotion():
    entries = [("D", DRAFT, None), ("A", TASK, None), ("M", "src/app.py", None)]
    assert "승격 커밋은 승격만" in bcs.check_scope(entries)


def test_check_scope_plain_code_commit_is_fine():
    assert bcs.check_scope([("M", "src/app.py", None), ("A", "x.py", None)]) is None


def test_check_scope_task_edits_with_code_are_fine():
    # A normal implementation commit touching a task file is not a promotion.
    entries = [("M", OTHER_TASK, None), ("M", "src/app.py", None)]
    assert bcs.check_scope(entries) is None


# --- parse_name_status ------------------------------------------------------


def test_parse_name_status_handles_renames_and_spaces():
    raw = f"R089\0{DRAFT}\0{TASK}\0M\0src/a b.py\0"
    assert bcs.parse_name_status(raw) == [
        ("R", DRAFT, TASK),
        ("M", "src/a b.py", None),
    ]


# --- main against real repos ------------------------------------------------


def test_new_draft_alone_passes(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    git(repo, "add", DRAFT)
    assert run_main(monkeypatch, repo) == 0


def test_new_draft_mixed_with_code_denied(monkeypatch, capsys, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", "-A")
    assert run_main(monkeypatch, repo) == 2
    err = capsys.readouterr().err
    assert "드래프트 생성 커밋은 드래프트만" in err
    assert "src/app.py" in err


def test_promotion_alone_passes(monkeypatch, repo_with_draft):
    promote(repo_with_draft)
    git(repo_with_draft, "add", "-A")
    assert run_main(monkeypatch, repo_with_draft) == 0


def test_promotion_with_edit_of_promoted_task_passes(monkeypatch, repo_with_draft):
    promote(repo_with_draft)
    path = repo_with_draft / TASK
    path.write_text(
        path.read_text().replace("labels: []", "labels: []\nreferences: [decision-1]")
    )
    git(repo_with_draft, "add", "-A")
    assert run_main(monkeypatch, repo_with_draft) == 0


def test_promotion_mixed_with_code_denied(monkeypatch, capsys, repo_with_draft):
    promote(repo_with_draft)
    write(repo_with_draft, "src/app.py", "print(3)\n")
    git(repo_with_draft, "add", "-A")
    assert run_main(monkeypatch, repo_with_draft) == 2
    assert "승격 커밋은 승격만" in capsys.readouterr().err


def test_git_dash_c_commit_is_recognized(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", "-A")
    assert run_main(monkeypatch, repo, f"git -C {repo} commit -m x") == 2


def test_non_commit_command_passes(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", "-A")
    assert run_main(monkeypatch, repo, "git status") == 0


def test_non_backlog_repo_passes(monkeypatch, repo):
    (repo / "backlog/config.yml").unlink()
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", "-A")
    assert run_main(monkeypatch, repo) == 0


def test_passes_when_git_missing(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", "-A")
    monkeypatch.setattr(bcs, "has_command", lambda name: False)
    assert run_main(monkeypatch, repo) == 0


def test_passes_on_invalid_json(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("nope"))
    with pytest.raises(SystemExit) as exc_info:
        bcs.main()
    assert exc_info.value.code == 0


def test_initial_commit_with_mixed_draft_denied(monkeypatch, tmp_path):
    git(tmp_path, "init", "-q")
    write(tmp_path, "backlog/config.yml", "project_name: t\n")
    write(tmp_path, DRAFT, DRAFT_BODY)
    git(tmp_path, "add", "-A")
    # config.yml is outside backlog/drafts/ -> mixed
    assert run_main(monkeypatch, tmp_path) == 2


# --- same-command `git add` / `commit -a` simulation -------------------------


def test_same_command_git_add_is_simulated(monkeypatch, capsys, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", DRAFT)
    code = run_main(monkeypatch, repo, "git add src/app.py && git commit -m x")
    assert code == 2
    assert "src/app.py" in capsys.readouterr().err


def test_same_command_git_add_all_is_simulated(monkeypatch, repo_with_draft):
    promote(repo_with_draft)
    write(repo_with_draft, "src/app.py", "print(3)\n")
    assert run_main(monkeypatch, repo_with_draft, "git add -A && git commit -m p") == 2


def test_same_command_git_add_of_promotion_only_passes(monkeypatch, repo_with_draft):
    promote(repo_with_draft)
    write(repo_with_draft, "src/app.py", "print(3)\n")  # left unstaged
    command = "git add backlog && git commit -m 'TASK-7: 승격'"
    assert run_main(monkeypatch, repo_with_draft, command) == 0


def test_simulation_does_not_touch_real_index(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", DRAFT)
    run_main(monkeypatch, repo, "git add src/app.py; git commit -m x")
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    ).stdout
    assert "src/app.py" not in staged


@pytest.mark.parametrize("flag", ["-a", "--all", "-am", "-qam"])
def test_commit_all_flag_is_simulated(monkeypatch, repo, flag):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")  # tracked, modified, unstaged
    git(repo, "add", DRAFT)
    command = (
        f"git commit {flag} x" if flag.endswith("m") else f"git commit {flag} -m x"
    )
    assert run_main(monkeypatch, repo, command) == 2


def test_message_containing_a_is_not_commit_all(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")  # unstaged, must stay out
    git(repo, "add", DRAFT)
    assert run_main(monkeypatch, repo, "git commit -m a") == 0


def test_git_add_with_shell_expansion_is_not_simulated(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", DRAFT)
    # `$F` can't be resolved here; fall back to the real index (draft only).
    assert run_main(monkeypatch, repo, "git add $F && git commit -m x") == 0


def test_cd_before_commit_disables_simulation(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", DRAFT)
    command = "cd elsewhere && git add src/app.py && git commit -m x"
    assert run_main(monkeypatch, repo, command) == 0


def test_git_add_with_redirection_is_not_simulated(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", DRAFT)
    command = "git add src/app.py > /dev/null && git commit -m x"
    assert run_main(monkeypatch, repo, command) == 0


# --- TASK-39: only a `git commit`/`git add` in command position counts -------


@pytest.mark.parametrize(
    "command",
    [
        "echo git commit",
        "echo /usr/bin/git commit -m x",
        "backlog task edit TASK-1 --notes 'git commit 전에 확인'",
        "cat <<'EOF' > notes.md\ngit commit -m x\nEOF",
        "git status",
    ],
)
def test_text_mentioning_commit_is_not_checked(monkeypatch, repo, command):
    # Regression: these used to be judged as a commit against a mixed index.
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", "-A")
    assert run_main(monkeypatch, repo, command) == 0


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/git commit -m x",
        "FOO=1 git commit -m x",
        "sudo -E git commit -m x",
        "echo ok && git commit -m x",
        "(git commit -m x)",
        "git \\\ncommit -m x",
        'git commit -m "unterminated',
    ],
)
def test_real_commit_forms_are_checked(monkeypatch, repo, command):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", "-A")
    assert run_main(monkeypatch, repo, command) == 2


def test_heredoc_body_git_add_is_not_replayed(monkeypatch, repo):
    # The `git add` line is heredoc text, not a command: only the draft is
    # really staged, so the commit passes.
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", DRAFT)
    command = "cat <<'EOF' > n.txt\ngit add src/app.py\nEOF\ngit commit -m x"
    assert run_main(monkeypatch, repo, command) == 0


@pytest.mark.parametrize(
    "command",
    [
        "sudo git add src/app.py && git commit -m x",
        "/usr/bin/git add src/app.py; FOO=1 git commit -m x",
        "git add src/app.py && sudo git commit -m x",
    ],
)
def test_prefixed_git_add_is_replayed(monkeypatch, repo, command):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")
    git(repo, "add", DRAFT)
    assert run_main(monkeypatch, repo, command) == 2


def test_prefixed_commit_all_is_simulated(monkeypatch, repo):
    write(repo, DRAFT, DRAFT_BODY)
    write(repo, "src/app.py", "print(2)\n")  # tracked, unstaged
    git(repo, "add", DRAFT)
    assert run_main(monkeypatch, repo, "FOO=1 git commit -am x") == 2


# --- staging_plan (pure) ----------------------------------------------------


@pytest.mark.parametrize(
    "command, expected",
    [
        ("git commit -m x", ([], False)),
        ("git add a b && git commit -a", ([["a", "b"]], True)),
        ("git status; git add a; git log; git commit", ([["a"]], False)),
        ("FOO=1 git; git commit", ([], False)),
        ("git add a && git -C /p commit -a", ([["a"]], False)),
        ("git add a && git --no-pager commit -a", ([["a"]], False)),
        ("git add a && GIT_DIR=/p git commit -a", ([["a"]], False)),
        ("git -C /p add a && git commit", None),
        ("GIT_INDEX_FILE=/tmp/i git add a && git commit", None),
        ("cd /p && git commit", None),
        ("sudo cd /p; git commit", None),
        ("git add $F && git commit", None),
        ('git commit -m "x', None),
        ("echo git commit", None),
        ("cat <<EOF\ngit add a\ngit commit\nEOF", None),
    ],
)
def test_staging_plan(command, expected):
    assert bcs.staging_plan(command) == expected


# --- commit_stages_all ------------------------------------------------------


@pytest.mark.parametrize(
    "args, expected",
    [
        (["--all"], True),
        (["-a"], True),
        (["-qa"], True),
        (["-m", "-a"], False),
        (["-ma"], False),
        (["--message", "-a"], False),
        (["--message=-a"], False),
        (["--amend"], False),
        (["--", "-a"], False),
        (["-"], False),
        (["path"], False),
    ],
)
def test_commit_stages_all(args, expected):
    assert bcs.commit_stages_all(args) is expected


# --- remaining branches -----------------------------------------------------


def test_parse_name_status_skips_empty_and_truncated_fields():
    assert bcs.parse_name_status("\0M\0a.py\0\0D") == [("M", "a.py", None)]


def test_parse_name_status_truncated_rename_falls_back():
    # `R` without both paths is read as a plain entry with one path.
    assert bcs.parse_name_status("R100\0old") == [("R", "old", None)]


def test_is_backlog_project_false_for_empty_cwd():
    assert bcs.is_backlog_project("") is False


def test_has_command_real():
    assert bcs.has_command("python3") is True
    assert bcs.has_command("definitely-not-a-real-command-xyz") is False


def test_staged_entries_none_outside_repo(tmp_path):
    assert bcs.staged_entries(str(tmp_path)) is None


def test_simulated_entries_none_outside_repo(tmp_path):
    assert bcs.simulated_entries(str(tmp_path), [["a"]], False) is None


def test_simulation_without_existing_index(monkeypatch, tmp_path):
    # Fresh repo: no index file yet, the temp index starts empty.
    git(tmp_path, "init", "-q")
    write(tmp_path, "backlog/config.yml", "project_name: t\n")
    write(tmp_path, DRAFT, DRAFT_BODY)
    command = f"git add '{DRAFT}' && git commit -m x"
    assert run_main(monkeypatch, tmp_path, command) == 0


def test_passes_when_index_unreadable(monkeypatch, repo):
    monkeypatch.setattr(bcs, "staged_entries", lambda cwd, env=None: None)
    assert run_main(monkeypatch, repo) == 0


def test_format_offenders_truncates_long_lists():
    entries = [("M", f"src/f{i}.py", None) for i in range(bcs.MAX_LISTED + 3)]
    listed = bcs.format_offenders(entries + [("M", "src/f0.py", None)])
    assert "src/f9.py" in listed
    assert f"src/f{bcs.MAX_LISTED}.py" not in listed
    assert "... 외 3개" in listed
