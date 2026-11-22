# ---
# title: test_backlog_commit_scope_merge
# description: backlog_commit_scope.py 가 충돌 병합을 마무리하는 커밋(MERGE_HEAD)은 막지 않고, 병합 중이 아니거나 확인에 실패하면 그대로 검사하는지 실제 git 저장소로 확인하는 테스트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# task: TASK-77
# created_date: '2026-11-22'
# updated_date: '2026-11-22'
# ---
# TASK-77: backlog_commit_scope 가 충돌 병합을 마무리하는 커밋(MERGE_HEAD)은 막지 않는다
#
# Each test builds a throwaway repository with a real conflicting merge: a
# branch moves a task to Done and adds code, main edits backlog/work-order.md
# the other way, so `git merge` stops on that file. After resolving it the
# index holds a status transition mixed with other paths - exactly what rule 4
# denies for an ordinary commit.
import io
import json
import subprocess

import pytest

import backlog_commit_scope as bcs

TASK = "backlog/tasks/task-3 - 기존.md"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )


def write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def task_body(status):
    return f"---\nid: TASK-3\ntitle: 기존\nstatus: {status}\n---\n\n본문\n"


@pytest.fixture
def mixed_index(tmp_path):
    """A repo whose index stages a task transition (To Do -> Done) plus code
    and work-order.md. Returns (repo, finish) where finish(merge) either
    leaves a conflicting merge in progress or stages the same paths without
    any merge."""
    repo = tmp_path
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "commit.gpgsign", "false")
    write(repo, "backlog/config.yml", "project_name: t\n")
    write(repo, TASK, task_body("To Do"))
    write(repo, "backlog/work-order.md", "order: base\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")

    def finish(merge):
        if merge:
            git(repo, "switch", "-q", "-c", "side")
            write(repo, TASK, task_body("Done"))
            write(repo, "src/app.py", "print(1)\n")
            write(repo, "backlog/work-order.md", "order: side\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "side work")
            git(repo, "switch", "-q", "main")
            write(repo, "backlog/work-order.md", "order: main\n")
            git(repo, "commit", "-q", "-am", "main work")
            assert git(repo, "merge", "side").returncode != 0  # conflict on work-order.md
            write(repo, "backlog/work-order.md", "order: regenerated\n")
            git(repo, "add", "backlog/work-order.md")
        else:
            write(repo, TASK, task_body("Done"))
            write(repo, "src/app.py", "print(1)\n")
            write(repo, "backlog/work-order.md", "order: regenerated\n")
            git(repo, "add", "-A")
        return repo

    return finish


def run_main(monkeypatch, cwd, command="git commit --no-edit"):
    payload = {"cwd": str(cwd), "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        bcs.main()
    return exc_info.value.code


# == AC/DoD ==


def test_conflict_merge_conclusion_passes(monkeypatch, mixed_index):
    """TASK-77#1 TASK-77#B1: with MERGE_HEAD present the commit that concludes a
    conflicting merge is not checked by rules 1-5 - the merged commits were
    already checked one by one on their own branch."""
    repo = mixed_index(merge=True)
    assert git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0
    assert run_main(monkeypatch, repo) == 0


def test_same_index_without_a_merge_is_still_denied(monkeypatch, capsys, mixed_index):
    """TASK-77#2 TASK-77#B2: the very same mixed index outside a merge is denied
    as before (rule 4, a status transition carrying other paths)."""
    repo = mixed_index(merge=False)
    assert git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0
    assert run_main(monkeypatch, repo) == 2
    assert "상태 전환" in capsys.readouterr().err


def test_merge_head_check_failure_falls_back_to_checking(monkeypatch, capsys, mixed_index):
    """TASK-77#2 TASK-77#B3: if asking git for MERGE_HEAD fails, the hook does
    not assume a merge - it checks, and the mixed index is denied."""
    repo = mixed_index(merge=True)
    real_run = bcs.subprocess.run

    def run(argv, *args, **kwargs):
        if "MERGE_HEAD" in argv:
            raise OSError("git unavailable")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(bcs.subprocess, "run", run)
    assert run_main(monkeypatch, repo) == 2
    assert "상태 전환" in capsys.readouterr().err


def test_readme_documents_the_merge_exception():
    """TASK-77#3: README names the exception and why it is safe."""
    import os

    readme = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
    with open(readme, encoding="utf-8") as f:
        text = f.read()
    assert "MERGE_HEAD" in text
    assert "충돌 병합" in text


# == Coverage ==


def test_merge_in_progress_is_false_outside_a_repository(tmp_path):
    assert bcs.merge_in_progress(str(tmp_path)) is False


def test_merge_in_progress_is_false_when_git_times_out(monkeypatch, tmp_path):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(bcs.subprocess, "run", run)
    assert bcs.merge_in_progress(str(tmp_path)) is False
