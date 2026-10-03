import io
import json
import os
import subprocess

import pytest

import pipeline_trace as pt


@pytest.fixture(autouse=True)
def isolate_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "pipeline-state"
    monkeypatch.setenv("CC_PIPELINE_DIR", str(state_dir))
    yield state_dir


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def run_main(monkeypatch, event, capsys=None):
    raw = event if isinstance(event, str) else json.dumps(event)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    with pytest.raises(SystemExit) as exc_info:
        pt.main()
    return exc_info.value.code


def state(state_dir, session_id="s1"):
    path = state_dir / f"{session_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def post_tool(cwd, tool_name, tool_input, session_id="s1", **extra):
    return {
        "hook_event_name": "PostToolUse",
        "session_id": session_id,
        "cwd": str(cwd),
        "tool_name": tool_name,
        "tool_input": tool_input,
        **extra,
    }


def stop(cwd, session_id="s1"):
    return {"hook_event_name": "Stop", "session_id": session_id, "cwd": str(cwd)}


# --- state location ----------------------------------------------------------


def test_state_dir_respects_env(isolate_state_dir):
    assert pt.state_dir() == str(isolate_state_dir)


def test_state_path_strips_directory_parts(isolate_state_dir):
    assert pt.state_path("../../etc/x") == os.path.join(
        str(isolate_state_dir), "x.json"
    )
    assert pt.state_path(None).endswith("unknown.json")


# --- command detection -------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "backlog draft create 'x'",
        "backlog drafts create x",
        "/opt/homebrew/bin/backlog draft create x",
        "cd repo && backlog draft create x -d 'y'",
        "FOO=1 npx backlog.md draft create x",
        "git status; backlog draft create x",
    ],
)
def test_detects_draft_create(command):
    assert pt.backlog_actions(command) == {"draft_create"}


@pytest.mark.parametrize(
    "command",
    [
        "backlog draft promote DRAFT-3",
        "backlog draft promote draft-3 && git add -A",
    ],
)
def test_detects_draft_promote(command):
    assert "draft_promote" in pt.backlog_actions(command)


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "backlog draft create 하고 나서 커밋"',
        "echo backlog draft promote X",
        "backlog draft list",
        "backlog task create x",
        "cat <<EOF\nbacklog draft create x\nEOF",
        "",
    ],
)
def test_ignores_non_invocations(command):
    assert pt.backlog_actions(command) == set()


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m x",
        "git -C /tmp/r commit -m x",
        "/usr/bin/git commit -am x",
        "git add -A && git commit -m 'y'",
    ],
)
def test_detects_git_commit(command):
    assert pt.command_runs_git_commit(command)


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "echo git commit",
        "git log --grep commit",
        'backlog draft create "git commit 금지"',
        "",
    ],
)
def test_ignores_non_commits(command):
    assert not pt.command_runs_git_commit(command)


# --- recording ---------------------------------------------------------------


def test_plan_mode_seen_from_user_prompt(monkeypatch, isolate_state_dir, git_repo):
    code = run_main(
        monkeypatch,
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "cwd": str(git_repo),
            "permission_mode": "plan",
        },
    )
    assert code == 0
    st = state(isolate_state_dir)
    assert st["plan_mode_seen"] is True
    assert st["plan_mode_seen_at"]


def test_default_mode_does_not_mark_plan(monkeypatch, isolate_state_dir, git_repo):
    run_main(
        monkeypatch,
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "cwd": str(git_repo),
            "permission_mode": "default",
        },
    )
    assert not state(isolate_state_dir).get("plan_mode_seen")


def test_plan_mode_seen_from_post_tool_use_permission_mode(
    monkeypatch, isolate_state_dir, git_repo
):
    run_main(
        monkeypatch,
        post_tool(git_repo, "Read", {"file_path": "x"}, permission_mode="plan"),
    )
    assert state(isolate_state_dir)["plan_mode_seen"] is True


def test_enter_plan_mode_tool_marks_plan(monkeypatch, isolate_state_dir, git_repo):
    run_main(monkeypatch, post_tool(git_repo, "EnterPlanMode", {}))
    assert state(isolate_state_dir)["plan_mode_seen"] is True


def test_exit_plan_mode_records_approval(monkeypatch, isolate_state_dir, git_repo):
    run_main(
        monkeypatch,
        post_tool(git_repo, "ExitPlanMode", {"plan": "\n# 계획 제목\n\n본문"}),
    )
    st = state(isolate_state_dir)
    assert st["plan_approved_count"] == 1
    assert st["plan_approved_at"]
    assert st["last_plan_title"] == "# 계획 제목"
    assert st["plan_mode_seen"] is True


def test_draft_and_commit_counts(monkeypatch, isolate_state_dir, git_repo):
    run_main(
        monkeypatch, post_tool(git_repo, "Bash", {"command": "backlog draft create x"})
    )
    run_main(
        monkeypatch,
        post_tool(git_repo, "Bash", {"command": "git add -A && git commit -m d"}),
    )
    run_main(
        monkeypatch,
        post_tool(git_repo, "Bash", {"command": "backlog draft promote DRAFT-1"}),
    )
    run_main(monkeypatch, post_tool(git_repo, "Bash", {"command": "git commit -m p"}))
    st = state(isolate_state_dir)
    assert st["draft_create_count"] == 1
    assert st["draft_promote_count"] == 1
    assert st["commit_count"] == 2


def test_project_edit_counted(monkeypatch, isolate_state_dir, git_repo):
    run_main(
        monkeypatch, post_tool(git_repo, "Edit", {"file_path": str(git_repo / "a.py")})
    )
    run_main(monkeypatch, post_tool(git_repo, "Write", {"file_path": "b.py"}))
    run_main(
        monkeypatch, post_tool(git_repo, "NotebookEdit", {"notebook_path": "n.ipynb"})
    )
    st = state(isolate_state_dir)
    assert st["project_edit_count"] == 3
    assert st["edited_before_plan"] is True


def test_outside_project_edit_not_counted(
    monkeypatch, isolate_state_dir, git_repo, tmp_path
):
    plans = tmp_path / "plans"
    plans.mkdir()
    run_main(
        monkeypatch, post_tool(git_repo, "Write", {"file_path": str(plans / "p.md")})
    )
    run_main(monkeypatch, post_tool(git_repo, "Edit", {"file_path": "../plans/p.md"}))
    run_main(monkeypatch, post_tool(git_repo, "Edit", {"file_path": ""}))
    assert not state(isolate_state_dir).get("project_edit_count")


def test_backlog_dir_edit_not_counted(monkeypatch, isolate_state_dir, git_repo):
    run_main(
        monkeypatch, post_tool(git_repo, "Edit", {"file_path": "backlog/docs/doc-1.md"})
    )
    assert not state(isolate_state_dir).get("project_edit_count")


def test_edit_after_plan_not_flagged_before_plan(
    monkeypatch, isolate_state_dir, git_repo
):
    run_main(monkeypatch, post_tool(git_repo, "ExitPlanMode", {"plan": "p"}))
    run_main(monkeypatch, post_tool(git_repo, "Edit", {"file_path": "a.py"}))
    assert state(isolate_state_dir).get("edited_before_plan") is not True


def test_other_tools_do_not_create_state(monkeypatch, isolate_state_dir, git_repo):
    run_main(monkeypatch, post_tool(git_repo, "Read", {"file_path": "a.py"}))
    assert not (isolate_state_dir / "s1.json").exists()


# --- Stop warning --------------------------------------------------------------


def test_stop_warns_when_edits_without_plan(
    monkeypatch, isolate_state_dir, git_repo, capsys
):
    run_main(monkeypatch, post_tool(git_repo, "Edit", {"file_path": "a.py"}))
    capsys.readouterr()
    code = run_main(monkeypatch, stop(git_repo))
    assert code == 0
    out = capsys.readouterr()
    assert "plan mode" in out.err
    payload = json.loads(out.out)
    assert "plan mode" in payload["systemMessage"]
    assert state(isolate_state_dir)["warned_at"]


def test_stop_warns_only_once(monkeypatch, isolate_state_dir, git_repo, capsys):
    run_main(monkeypatch, post_tool(git_repo, "Edit", {"file_path": "a.py"}))
    run_main(monkeypatch, stop(git_repo))
    capsys.readouterr()
    code = run_main(monkeypatch, stop(git_repo))
    assert code == 0
    out = capsys.readouterr()
    assert out.err == "" and out.out == ""


def test_stop_silent_when_plan_approved(
    monkeypatch, isolate_state_dir, git_repo, capsys
):
    run_main(monkeypatch, post_tool(git_repo, "ExitPlanMode", {"plan": "p"}))
    run_main(monkeypatch, post_tool(git_repo, "Edit", {"file_path": "a.py"}))
    capsys.readouterr()
    assert run_main(monkeypatch, stop(git_repo)) == 0
    out = capsys.readouterr()
    assert out.err == "" and out.out == ""


def test_stop_silent_when_plan_mode_seen(
    monkeypatch, isolate_state_dir, git_repo, capsys
):
    run_main(
        monkeypatch,
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "cwd": str(git_repo),
            "permission_mode": "plan",
        },
    )
    run_main(monkeypatch, post_tool(git_repo, "Edit", {"file_path": "a.py"}))
    capsys.readouterr()
    run_main(monkeypatch, stop(git_repo))
    out = capsys.readouterr()
    assert out.err == "" and out.out == ""


def test_stop_silent_without_edits(monkeypatch, isolate_state_dir, git_repo, capsys):
    assert run_main(monkeypatch, stop(git_repo)) == 0
    out = capsys.readouterr()
    assert out.err == "" and out.out == ""
    assert not (isolate_state_dir / "s1.json").exists()


def test_stop_silent_outside_git_repo(monkeypatch, isolate_state_dir, tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    run_main(monkeypatch, post_tool(plain, "Edit", {"file_path": "a.py"}))
    capsys.readouterr()
    assert run_main(monkeypatch, stop(plain)) == 0
    out = capsys.readouterr()
    assert out.err == "" and out.out == ""


# --- fail-open -----------------------------------------------------------------


def test_invalid_json_exits_zero(monkeypatch):
    assert run_main(monkeypatch, "not json") == 0


def test_non_dict_payload_exits_zero(monkeypatch):
    assert run_main(monkeypatch, "[1, 2]") == 0


def test_corrupt_state_file_is_replaced(monkeypatch, isolate_state_dir, git_repo):
    isolate_state_dir.mkdir(parents=True)
    (isolate_state_dir / "s1.json").write_text("{broken")
    assert (
        run_main(
            monkeypatch, post_tool(git_repo, "Bash", {"command": "git commit -m x"})
        )
        == 0
    )
    assert state(isolate_state_dir)["commit_count"] == 1


def test_unwritable_state_dir_fails_open(monkeypatch, tmp_path, git_repo):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x")
    monkeypatch.setenv("CC_PIPELINE_DIR", str(blocker / "sub"))
    assert (
        run_main(
            monkeypatch, post_tool(git_repo, "Bash", {"command": "git commit -m x"})
        )
        == 0
    )
