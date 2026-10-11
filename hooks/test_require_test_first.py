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
