import io
import json
import textwrap

import pytest

import dedup_drift_guard as ddg

COMMIT = {"command": "git commit -m x"}


def run_main(monkeypatch, stdin_data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        ddg.main()
    return exc_info.value.code


def write_hook(hooks_dir, filename, body):
    (hooks_dir / filename).write_text(textwrap.dedent(body))


IDENTICAL_BODY = """
    def is_backlog_project(cwd):
        import os
        return os.path.isdir(os.path.join(cwd, ".git"))
    """

DIFFERENT_BODY = """
    def is_backlog_project(cwd):
        import os
        return os.path.isfile(os.path.join(cwd, ".git"))
    """

NO_FUNCTION_BODY = """
    def something_else(cwd):
        return True
    """

# Baseline (identical-across-files) stub for every function currently in
# ddg.REGISTRY. Real REGISTRY entries can cover more than just
# is_backlog_project (see hooks/dedup_drift_guard.py), and
# registry_files_present() requires *every* file referenced by *any*
# REGISTRY entry to exist, so a fake hooks/ dir must supply a baseline
# definition for each function a given file is registered under - not just
# the one function a test cares about perturbing.
BASELINE_BODIES = {
    "is_backlog_project": IDENTICAL_BODY,
    "command_invokes_git_subcommand": """
        def command_invokes_git_subcommand(command, subcommand):
            return subcommand in command.split()
        """,
    "has_command": """
        def has_command(name):
            import shutil
            return shutil.which(name) is not None
        """,
    "has_active_task": """
        def has_active_task(cwd):
            return True
        """,
    "run_shell": """
        def run_shell(cwd, command):
            return ""
        """,
    "tokenize": """
        def tokenize(command):
            return command.split()
        """,
    "split_segments": """
        def split_segments(tokens):
            return [tokens]
        """,
    "background_tasks_running": """
        def background_tasks_running(data):
            return bool(data.get("background_tasks"))
        """,
    "strip_heredoc_bodies": """
        def strip_heredoc_bodies(command):
            return command
        """,
    "is_outside_project": """
        def is_outside_project(path, cwd):
            return False
        """,
}

DIFFERENT_HAS_COMMAND_BODY = """
    def has_command(name):
        import shutil
        return shutil.which(name) is None
    """


def build_full_hooks_dir(tmp_path, overrides=None):
    """Creates tmp_path/hooks/ with one file per entry referenced anywhere
    in ddg.REGISTRY. Every file gets a baseline (identical) stub for each
    function it's registered under, so the whole fake tree satisfies
    registry_files_present() and, by default, finds zero drift.

    `overrides`: dict of filename -> {function_name: source text}, used to
    replace one function's stub in one file (e.g. to introduce drift, or to
    omit a function entirely by defining something else under that key).
    """
    overrides = overrides or {}
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()

    file_functions = {}
    for function_name, files in ddg.REGISTRY.items():
        for filename in files:
            file_functions.setdefault(filename, []).append(function_name)

    for filename, function_names in file_functions.items():
        parts = []
        for function_name in function_names:
            body = overrides.get(filename, {}).get(
                function_name, BASELINE_BODIES[function_name]
            )
            parts.append(textwrap.dedent(body))
        (hooks_dir / filename).write_text("\n".join(parts))

    return hooks_dir


def make_fake_registry_dir(tmp_path, monkeypatch, bodies):
    """bodies: dict of filename -> override source for that file's
    is_backlog_project function. Every other REGISTRY-required function in
    every file gets its baseline (identical) stub, so only
    is_backlog_project is perturbed.
    """
    return build_full_hooks_dir(
        tmp_path,
        overrides={
            filename: {"is_backlog_project": body} for filename, body in bodies.items()
        },
    )


def test_no_op_when_command_is_not_a_commit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps({"cwd": str(tmp_path), "tool_input": {"command": "git status"}})
        ),
    )
    with pytest.raises(SystemExit) as exc_info:
        ddg.main()
    assert exc_info.value.code == 0


def test_passes_when_hooks_dir_missing_registry_files(monkeypatch, tmp_path):
    # self-guard: not the claude-rails repo (no hooks/ at all)
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": COMMIT}) == 0


def test_allows_commit_when_all_copies_identical(monkeypatch, tmp_path):
    make_fake_registry_dir(tmp_path, monkeypatch, {})
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": COMMIT}) == 0


def test_blocks_commit_when_one_copy_differs(monkeypatch, capsys, tmp_path):
    make_fake_registry_dir(tmp_path, monkeypatch, {"session_start.py": DIFFERENT_BODY})
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": COMMIT})
    assert code == 2
    err = capsys.readouterr().err
    assert "is_backlog_project" in err
    assert "session_start.py" in err


def test_blocks_commit_when_function_missing_in_one_copy(monkeypatch, capsys, tmp_path):
    make_fake_registry_dir(
        tmp_path, monkeypatch, {"pre_push_check.py": NO_FUNCTION_BODY}
    )
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": COMMIT})
    assert code == 2
    err = capsys.readouterr().err
    assert "is_backlog_project" in err
    assert "pre_push_check.py" in err
    assert "찾을 수 없습니다" in err


def test_registry_covers_newly_added_dedup_functions():
    # TASK-9: command_invokes_git_subcommand/has_command/has_active_task/
    # run_shell were hand-copied across several hook files without being
    # registered here, so drift in them went undetected. current_branch is
    # deliberately excluded (its return-value contract differs by file:
    # empty string vs None), so it must never appear.
    assert ddg.REGISTRY["command_invokes_git_subcommand"] == [
        "pre_commit_check.py",
        "pre_push_check.py",
        "pre_push_coverage_check.py",
        "dedup_drift_guard.py",
        "backlog_commit_scope.py",
    ]
    assert ddg.REGISTRY["has_command"] == [
        "block_stop_if_dirty.py",
        "pre_commit_check.py",
        "pre_push_check.py",
        "require_active_task.py",
        "session_start.py",
        "backlog_commit_scope.py",
    ]
    assert ddg.REGISTRY["has_active_task"] == [
        "block_stop_if_dirty.py",
        "pre_commit_check.py",
        "require_active_task.py",
    ]
    assert ddg.REGISTRY["run_shell"] == [
        "pre_commit_check.py",
        "pre_push_coverage_check.py",
    ]
    assert "current_branch" not in ddg.REGISTRY


def test_registry_covers_task29_draft_workflow_hooks():
    # TASK-29: both draft-workflow hooks copy helpers verbatim; every copy
    # must be registered so drift is caught at commit time.
    assert "require_draft_first.py" in ddg.REGISTRY["is_backlog_project"]
    assert "backlog_commit_scope.py" in ddg.REGISTRY["is_backlog_project"]
    for name in ("tokenize", "split_segments"):
        assert ddg.REGISTRY[name][:2] == [
            "require_draft_first.py",
            "backlog_commit_scope.py",
        ]


def test_allows_commit_when_all_registered_functions_identical(monkeypatch, tmp_path):
    build_full_hooks_dir(tmp_path)
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": COMMIT}) == 0


def test_blocks_commit_when_has_command_drifts_in_one_copy(
    monkeypatch, capsys, tmp_path
):
    build_full_hooks_dir(
        tmp_path,
        overrides={"session_start.py": {"has_command": DIFFERENT_HAS_COMMAND_BODY}},
    )
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": COMMIT})
    assert code == 2
    err = capsys.readouterr().err
    assert "has_command" in err
    assert "session_start.py" in err


def test_blocks_commit_when_has_command_missing_in_one_copy(
    monkeypatch, capsys, tmp_path
):
    build_full_hooks_dir(
        tmp_path,
        overrides={"require_active_task.py": {"has_command": NO_FUNCTION_BODY}},
    )
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": COMMIT})
    assert code == 2
    err = capsys.readouterr().err
    assert "has_command" in err
    assert "require_active_task.py" in err
    assert "찾을 수 없습니다" in err


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        ddg.main()
    assert exc_info.value.code == 0


def test_command_invokes_git_subcommand_handles_dash_c():
    assert ddg.command_invokes_git_subcommand("git -C /p commit -m x", "commit") is True


def test_command_invokes_git_subcommand_false_for_other_subcommand():
    assert ddg.command_invokes_git_subcommand("git -C /p push", "commit") is False


def test_command_invokes_git_subcommand_detects_absolute_path_bypass():
    assert (
        ddg.command_invokes_git_subcommand("/usr/bin/git commit -m x", "commit") is True
    )


def test_command_invokes_git_subcommand_detects_relative_path_bypass():
    assert ddg.command_invokes_git_subcommand("./git commit -m x", "commit") is True


def test_command_invokes_git_subcommand_ignores_git_outside_verb_position():
    assert ddg.command_invokes_git_subcommand("echo /usr/bin/git", "commit") is False


def test_registry_files_present_true_against_real_repo():
    import os

    real_hooks_dir = os.path.dirname(os.path.abspath(ddg.__file__))
    assert ddg.registry_files_present(real_hooks_dir) is True


def test_registry_files_present_false_for_unrelated_dir(tmp_path):
    assert ddg.registry_files_present(str(tmp_path)) is False


def test_function_ast_dump_none_for_missing_file(tmp_path):
    assert (
        ddg.function_ast_dump(str(tmp_path / "nope.py"), "is_backlog_project") is None
    )


def test_function_ast_dump_none_for_unparsable_file(tmp_path):
    path = tmp_path / "bad.py"
    path.write_text("def broken(:\n")
    assert ddg.function_ast_dump(str(path), "is_backlog_project") is None


def test_find_drift_empty_when_real_repo_hooks_in_sync():
    import os

    real_hooks_dir = os.path.dirname(os.path.abspath(ddg.__file__))
    assert ddg.find_drift(real_hooks_dir) == []


def test_registry_covers_task31_context_flag_helper():
    # TASK-31: context_flags.py and block_stop_if_dirty.py both derive
    # parallel_session from the Stop payload with the same helper.
    assert ddg.REGISTRY["background_tasks_running"] == [
        "block_stop_if_dirty.py",
        "context_flags.py",
    ]


def test_registry_covers_task32_pipeline_trace_copies():
    # TASK-32: pipeline_trace.py copies the command tokenizer helpers from
    # the TASK-29 hooks and the realpath project check from TASK-27.
    for name in ("tokenize", "split_segments"):
        assert ddg.REGISTRY[name] == [
            "require_draft_first.py",
            "backlog_commit_scope.py",
            "pipeline_trace.py",
        ]
    assert ddg.REGISTRY["strip_heredoc_bodies"] == [
        "require_draft_first.py",
        "pipeline_trace.py",
    ]
    assert ddg.REGISTRY["is_outside_project"] == [
        "require_active_task.py",
        "pipeline_trace.py",
    ]
