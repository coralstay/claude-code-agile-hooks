import io
import json
import os

import pytest

import require_test_first as rtf

CONFIG = {
    "testFirst": {
        "sourceGlobs": ["src/main/java/**"],
        "testGlobs": ["src/test/java/**"],
    }
}


def make_card(acs, rules=None, task_id="AO-27", status="◒ In Progress", desc=None):
    """`acs`: list of (checked, text); `rules`: list of raw lines under the
    `## 비즈니스 규칙` heading (None = no heading)."""
    description = desc if desc is not None else "설명 본문"
    if rules is not None:
        description += "\n\n## 비즈니스 규칙\n" + "\n".join(rules)
    ac_lines = [
        f"- [{'x' if checked else ' '}] #{i} {text}"
        for i, (checked, text) in enumerate(acs, start=1)
    ] or ["No acceptance criteria defined"]
    return "\n".join(
        [
            f"File: /x/backlog/tasks/{task_id.lower()} - t.md",
            "",
            f"Task {task_id} - 제목",
            "=" * 50,
            "",
            f"Status: {status}",
            "Created: 2026-10-11 08:33 (UTC)",
            "",
            "Description:",
            "-" * 50,
            description,
            "",
            "Acceptance Criteria:",
            "-" * 50,
            *ac_lines,
            "",
            "Definition of Done:",
            "-" * 50,
            "No Definition of Done items defined",
        ]
    )


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A fake opted-in backlog project on branch task/AO-27; tests set the
    card through `project.card`."""

    class Project:
        root = tmp_path
        card = make_card([(False, "첫 기능"), (False, "둘째 기능")])
        branch = "task/AO-27"

        def write(self, rel, text):
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            return path

        def config(self, data):
            self.write(".claude-code-agile-hooks.json", json.dumps(data))

    p = Project()
    p.config(CONFIG)
    monkeypatch.setattr(rtf, "has_command", lambda name: True)
    monkeypatch.setattr(rtf, "is_backlog_project", lambda cwd: True)
    monkeypatch.setattr(rtf, "current_branch", lambda cwd: p.branch)
    monkeypatch.setattr(rtf, "task_view", lambda cwd, task_id: p.card)
    return p


def run_main(monkeypatch, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rtf.main()
    return exc_info.value.code


def edit(project, rel):
    return {
        "cwd": str(project.root),
        "tool_name": "Edit",
        "tool_input": {"file_path": os.path.join(str(project.root), rel)},
    }


SOURCE = "src/main/java/a/Router.java"


# --- AC #1: Edit|Write on a source file needs the next AC's markers ---


def test_denies_source_edit_when_next_ac_marker_missing(project, monkeypatch, capsys):
    code = run_main(monkeypatch, edit(project, SOURCE))
    assert code == 2
    err = capsys.readouterr().err
    assert err.startswith("[claude-code-agile-hooks]")
    assert "AO-27#1" in err
    assert "AO-27#2" not in err


def test_allows_source_edit_when_next_ac_marker_present(project, monkeypatch):
    project.write("src/test/java/a/RouterTest.java", '@DisplayName("AO-27#1 고른다")')
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_write_tool_is_gated_too(project, monkeypatch):
    payload = edit(project, SOURCE)
    payload["tool_name"] = "Write"
    assert run_main(monkeypatch, payload) == 2


def test_relative_file_path_is_resolved_against_cwd(project, monkeypatch):
    payload = edit(project, SOURCE)
    payload["tool_input"]["file_path"] = SOURCE
    assert run_main(monkeypatch, payload) == 2


def test_next_ac_is_the_first_unchecked_one(project, monkeypatch, capsys):
    project.card = make_card([(True, "끝난 기능"), (False, "다음 기능")])
    project.write("src/test/java/a/RouterTest.java", "// AO-27#1")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2
    assert "AO-27#2" in capsys.readouterr().err
    project.write("src/test/java/a/NextTest.java", "// AO-27#2")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_marker_does_not_match_a_longer_number(project, monkeypatch):
    project.write("src/test/java/a/RouterTest.java", "// AO-27#10 and AO-27#1x")
    # `AO-27#1x` has a non-digit right after the number, so it counts
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0
    project.write("src/test/java/a/RouterTest.java", "// AO-27#10 AO-27#12")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2


def test_marker_does_not_match_a_longer_id(project, monkeypatch):
    project.write("src/test/java/a/RouterTest.java", "// XAO-27#1")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2


def test_marker_at_end_of_file_counts(project, monkeypatch):
    project.write("src/test/java/a/RouterTest.java", "AO-27#1")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_marker_outside_test_globs_does_not_count(project, monkeypatch):
    project.write("src/main/java/a/Other.java", "// AO-27#1")
    project.write("docs/notes.md", "AO-27#1")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2


def test_rules_of_the_next_ac_are_required(project, monkeypatch, capsys):
    project.card = make_card(
        [(False, "구간 고르기"), (False, "기록")],
        rules=[
            "- B1 (AC #1) 상한과 같으면 그 구간의 모델을 고른다",
            "",
            "- B2 (AC #1) 음수면 거부한다",
            "- B3 (AC #2) 고른 정책을 기록한다",
        ],
    )
    project.write("src/test/java/a/RouterTest.java", "AO-27#1\nAO-27#B1\n")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2
    err = capsys.readouterr().err
    assert "AO-27#B2" in err
    assert "음수면 거부한다" in err
    assert "AO-27#B1" not in err.split("빠진 표식")[1]
    assert "AO-27#B3" not in err
    project.write("src/test/java/a/RuleTest.java", "AO-27#B2")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_rule_marker_does_not_match_a_longer_number(project, monkeypatch):
    project.card = make_card(
        [(False, "x")], rules=["- B1 (AC #1) 규칙"]
    )
    project.write("src/test/java/a/T.java", "AO-27#1 AO-27#B12")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2


def test_test_file_edit_is_always_allowed(project, monkeypatch):
    # a path matching both globs is a test, not a source
    project.config(
        {"testFirst": {"sourceGlobs": ["src/**"], "testGlobs": ["src/test/**"]}}
    )
    assert run_main(monkeypatch, edit(project, "src/test/java/a/RouterTest.java")) == 0
    assert run_main(monkeypatch, edit(project, "src/main/java/a/Router.java")) == 2


def test_non_source_edit_is_allowed(project, monkeypatch):
    assert run_main(monkeypatch, edit(project, "README.md")) == 0
    assert run_main(monkeypatch, edit(project, "backlog/tasks/x.md")) == 0


def test_file_outside_project_is_allowed(project, monkeypatch):
    payload = edit(project, SOURCE)
    payload["tool_input"]["file_path"] = "/somewhere/else/src/main/java/A.java"
    assert run_main(monkeypatch, payload) == 0


def test_legacy_config_name_is_read(project, monkeypatch):
    os.remove(project.root / ".claude-code-agile-hooks.json")
    project.write(".claude-rails.json", json.dumps(CONFIG))
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2


def test_task_view_failure_passes(project, monkeypatch):
    project.card = None
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


# --- glob semantics ---


@pytest.mark.parametrize(
    "pattern, path, expected",
    [
        ("src/main/java/**", "src/main/java/A.java", True),
        ("src/main/java/**", "src/main/java/a/b/A.java", True),
        ("src/main/java/**", "src/main/javaX/A.java", False),
        ("src/**/*.py", "src/a.py", True),
        ("src/**/*.py", "src/a/b/c.py", True),
        ("src/**/*.py", "src/a/b/c.txt", False),
        ("*.py", "a.py", True),
        ("*.py", "a/b.py", False),
        ("**/test_*.py", "test_a.py", True),
        ("**/test_*.py", "x/y/test_a.py", True),
        ("hooks/?.py", "hooks/a.py", True),
        ("hooks/?.py", "hooks/ab.py", False),
        ("a.b/[x]", "a.b/[x]", True),
        ("a.b/[x]", "aXb/x", False),
        ("lib**", "lib/a/b", True),
    ],
)
def test_glob_semantics(pattern, path, expected):
    assert rtf.glob_matches(pattern, path) is expected


def test_test_files_are_found_under_glob_base(project):
    project.write("src/test/java/a/T.java", "x")
    project.write("src/main/java/a/S.java", "x")
    project.write("t/x_test.py", "x")
    found = sorted(rtf.iter_test_files(str(project.root), ["src/test/java/**", "**/*_test.py"]))
    assert found == [
        os.path.join(str(project.root), "src/test/java/a/T.java"),
        os.path.join(str(project.root), "t/x_test.py"),
    ]


def test_test_files_skip_git_dir_and_missing_base(project):
    project.write(".git/x_test.py", "x")
    assert list(rtf.iter_test_files(str(project.root), ["**/*_test.py"])) == []
    assert list(rtf.iter_test_files(str(project.root), ["nope/**"])) == []


# --- AC #2: `backlog task edit <ID> -s Done` needs every AC and rule marker ---


def bash(project, command):
    return {
        "cwd": str(project.root),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


RULED_CARD = make_card(
    [(True, "구간 고르기"), (True, "기록")],
    rules=["- B1 (AC #1) 상한과 같으면 고른다", "- B2 (AC #2) 고른 정책을 기록한다"],
)


@pytest.mark.parametrize(
    "command",
    [
        "backlog task edit AO-27 -s Done",
        "backlog task edit AO-27 --status Done",
        "backlog task edit AO-27 --status=Done",
        "backlog task edit ao-27 -s done",
        "backlog task edit 27 -s Done --final-summary 'x'",
        "backlog task edit AO-27 --check-ac 2 -s 'Done'",
        "cd x && /opt/homebrew/bin/backlog task edit AO-27 -s Done",
        "FOO=1 backlog task edit AO-27 \\\n  -s Done",
    ],
)
def test_done_denied_when_rule_marker_missing(project, monkeypatch, capsys, command):
    project.card = RULED_CARD
    project.write("src/test/java/a/T.java", "AO-27#1 AO-27#2 AO-27#B1")
    assert run_main(monkeypatch, bash(project, command)) == 2
    err = capsys.readouterr().err
    assert err.startswith("[claude-code-agile-hooks]")
    assert "AO-27#B2" in err and "고른 정책을 기록한다" in err
    assert "AO-27#B1 " not in err


def test_done_denied_when_ac_marker_missing(project, monkeypatch, capsys):
    project.card = make_card([(True, "a"), (True, "b")])
    project.write("src/test/java/a/T.java", "AO-27#2")
    assert run_main(monkeypatch, bash(project, "backlog task edit AO-27 -s Done")) == 2
    assert "AO-27#1" in capsys.readouterr().err


def test_done_allowed_when_every_marker_present(project, monkeypatch):
    project.card = RULED_CARD
    project.write("src/test/java/a/T.java", "AO-27#1 AO-27#2 AO-27#B1 AO-27#B2")
    assert run_main(monkeypatch, bash(project, "backlog task edit AO-27 -s Done")) == 0


@pytest.mark.parametrize(
    "command",
    [
        "backlog task edit AO-27 -s 'In Progress'",
        "backlog task edit AO-27 --check-ac 1",
        "backlog task edit AO-28 -s Done",
        "backlog task view AO-27 --plain",
        "echo backlog task edit AO-27 -s Done",
        "git commit -m 'backlog task edit AO-27 -s Done'",
        "cat <<EOF\nbacklog task edit AO-27 -s Done\nEOF",
        "backlog task edit AO-27 -s",
        "backlog",
        "ls",
        "",
    ],
)
def test_other_commands_pass(project, monkeypatch, command):
    project.card = RULED_CARD
    assert run_main(monkeypatch, bash(project, command)) == 0


def test_unbalanced_quote_falls_back_to_text_match(project, monkeypatch):
    project.card = RULED_CARD
    command = "backlog task edit AO-27 -s Done --notes \"unclosed"
    assert run_main(monkeypatch, bash(project, command)) == 2
    assert run_main(monkeypatch, bash(project, "echo \"unclosed")) == 0


@pytest.mark.parametrize(
    "command, expected",
    [
        ("backlog task edit AO-27 -s Done", ["AO-27"]),
        ("backlog tasks edit 3 --status=DONE", ["3"]),
        ("backlog.md task edit X-1 -s Done; backlog task edit X-2 -s Done", ["X-1", "X-2"]),
        ("sudo backlog task edit X-1 -s Done", ["X-1"]),
        ("backlog task edit -s Done X-1", ["X-1"]),
        ("backlog task edit X-1 -s Doneish", []),
        ("backlog task create X -s Done", []),
        ("backlog draft edit X-1 -s Done", []),
    ],
)
def test_done_targets(command, expected):
    assert rtf.done_targets(command) == expected


def test_same_task_matches_id_forms():
    assert rtf.same_task("AO-27", "AO-27")
    assert rtf.same_task("ao-27", "AO-27")
    assert rtf.same_task("27", "AO-27")
    assert not rtf.same_task("2", "AO-27")
    assert not rtf.same_task("AO-270", "AO-27")


# --- AC #3: no rules section, malformed rules, all ACs checked, non-targets ---


def test_without_rules_section_only_ac_markers_are_needed(project, monkeypatch):
    project.card = make_card([(False, "a")], desc="설명\n\n## 메모\n- B1 아무 형식")
    project.write("src/test/java/a/T.java", "AO-27#1")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0
    project.card = make_card([(True, "a")])
    assert run_main(monkeypatch, bash(project, "backlog task edit AO-27 -s Done")) == 0


@pytest.mark.parametrize(
    "bad_line",
    [
        "- B1 상한과 같으면 고른다",
        "- B1 (AC 1) 상한",
        "- (AC #1) 상한",
        "* B1 (AC #1) 상한",
        "- B1 (AC #1)",
        "B1 (AC #1) 상한",
    ],
)
def test_malformed_rule_line_denies_with_expected_format(
    project, monkeypatch, capsys, bad_line
):
    project.card = make_card([(False, "a")], rules=["- B2 (AC #1) 정상", bad_line])
    project.write("src/test/java/a/T.java", "AO-27#1 AO-27#B2")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2
    err = capsys.readouterr().err
    assert err.startswith("[claude-code-agile-hooks]")
    assert "- B<k> (AC #<n>) <규칙>" in err
    assert bad_line.strip() in err


def test_malformed_rules_deny_done_too(project, monkeypatch, capsys):
    project.card = make_card([(True, "a")], rules=["- B1 규칙"])
    project.write("src/test/java/a/T.java", "AO-27#1 AO-27#B1")
    assert run_main(monkeypatch, bash(project, "backlog task edit AO-27 -s Done")) == 2
    assert "- B<k> (AC #<n>) <규칙>" in capsys.readouterr().err


def test_rule_naming_a_missing_ac_is_a_format_error(project, monkeypatch, capsys):
    project.card = make_card([(False, "a")], rules=["- B1 (AC #9) 없는 AC"])
    project.write("src/test/java/a/T.java", "AO-27#1 AO-27#B1")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2
    assert "AC #9" in capsys.readouterr().err


def test_rules_section_ends_at_next_heading(project, monkeypatch):
    project.card = make_card(
        [(False, "a")], rules=["- B1 (AC #1) 규칙", "", "## 메모", "자유 형식 메모"]
    )
    project.write("src/test/java/a/T.java", "AO-27#1 AO-27#B1")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_all_acs_checked_allows_source_edit(project, monkeypatch):
    project.card = make_card([(True, "a"), (True, "b")], rules=["- B1 (AC #1) r"])
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_card_without_acs_allows_source_edit(project, monkeypatch):
    project.card = make_card([])
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_task_id_falls_back_to_branch_when_card_has_no_header(
    project, monkeypatch, capsys
):
    project.card = make_card([(False, "a")]).replace("Task AO-27 - 제목", "")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2
    assert "AO-27#1" in capsys.readouterr().err


def test_passes_when_backlog_not_installed(project, monkeypatch):
    monkeypatch.setattr(rtf, "has_command", lambda name: False)
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_passes_when_not_a_backlog_project(project, monkeypatch):
    monkeypatch.setattr(rtf, "is_backlog_project", lambda cwd: False)
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_passes_without_project_config(project, monkeypatch):
    os.remove(project.root / ".claude-code-agile-hooks.json")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_passes_when_config_has_no_test_first(project, monkeypatch):
    project.config({"testCommand": "pytest"})
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


@pytest.mark.parametrize(
    "config",
    [
        {"testFirst": ["src/**"]},
        {"testFirst": {"sourceGlobs": "src/**", "testGlobs": ["t/**"]}},
        {"testFirst": {"sourceGlobs": ["src/**"]}},
        {"testFirst": {"sourceGlobs": [], "testGlobs": ["t/**"]}},
        {"testFirst": {"sourceGlobs": ["src/**"], "testGlobs": [1]}},
    ],
)
def test_malformed_test_first_config_denies(project, monkeypatch, capsys, config):
    project.config(config)
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2
    assert "testFirst" in capsys.readouterr().err


def test_unreadable_config_json_denies(project, monkeypatch, capsys):
    project.write(".claude-code-agile-hooks.json", "{not json")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 2
    assert "testFirst" in capsys.readouterr().err


def test_passes_off_task_branch(project, monkeypatch):
    project.branch = "main"
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_passes_when_task_not_in_progress(project, monkeypatch):
    project.card = make_card([(False, "a")], status="○ To Do")
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


def test_done_for_another_task_passes(project, monkeypatch):
    project.card = make_card([(True, "a")])
    assert run_main(monkeypatch, bash(project, "backlog task edit AO-28 -s Done")) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Read", "tool_input": {"file_path": SOURCE}},
        {"tool_name": "Edit", "tool_input": "not a dict"},
        {"tool_name": "Edit", "tool_input": {}},
        {},
    ],
)
def test_other_payloads_pass(project, monkeypatch, payload):
    payload = dict(payload, cwd=str(project.root))
    assert run_main(monkeypatch, payload) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        rtf.main()
    assert exc_info.value.code == 0


# --- subprocess wrappers ---


class Done:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


def test_task_view_returns_stdout_or_none(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs.get("cwd")))
        return Done(0, "card")

    monkeypatch.setattr(rtf.subprocess, "run", fake_run)
    assert rtf.task_view("/p", "AO-27") == "card"
    assert calls == [(["backlog", "task", "view", "AO-27", "--plain"], "/p")]
    monkeypatch.setattr(rtf.subprocess, "run", lambda *a, **k: Done(1, "err"))
    assert rtf.task_view("/p", "AO-27") is None


def test_current_branch_strips_output(monkeypatch):
    monkeypatch.setattr(rtf.subprocess, "run", lambda *a, **k: Done(0, "task/AO-27\n"))
    assert rtf.current_branch("/p") == "task/AO-27"


def test_malformed_config_still_lets_the_config_be_fixed(project, monkeypatch):
    project.config({"testFirst": ["src/**"]})
    assert run_main(monkeypatch, edit(project, ".claude-code-agile-hooks.json")) == 0
    assert run_main(monkeypatch, edit(project, ".claude-rails.json")) == 0
    assert run_main(monkeypatch, edit(project, "README.md")) == 2


def test_malformed_config_off_task_branch_passes(project, monkeypatch):
    project.config({"testFirst": ["src/**"]})
    project.branch = "main"
    assert run_main(monkeypatch, edit(project, SOURCE)) == 0


# --- copied helpers (REGISTRY keeps them identical to their originals) ---


def test_has_command_and_is_backlog_project(tmp_path):
    assert rtf.has_command("python3")
    assert not rtf.has_command("definitely-not-a-command-xyz")
    assert not rtf.is_backlog_project("")
    assert not rtf.is_backlog_project(str(tmp_path))
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x")
    assert rtf.is_backlog_project(str(tmp_path))


def test_is_outside_project(tmp_path):
    assert not rtf.is_outside_project("", str(tmp_path))
    assert not rtf.is_outside_project("a/b", str(tmp_path))
    assert rtf.is_outside_project("../x", str(tmp_path))


def test_done_targets_skip_wrapper_flags():
    assert rtf.done_targets("sudo -E -H backlog task edit X-1 -s Done") == ["X-1"]
    assert rtf.done_targets("FOO=1 sudo -E") == []
