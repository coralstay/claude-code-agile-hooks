import io
import json

import pytest

import require_coverage_on_done as rcd

DONE = "backlog task edit TASK-1 -s Done"


def backlog_project(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("")
    return tmp_path


def run_main(monkeypatch, stdin_data):
    if isinstance(stdin_data, str):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
    else:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        rcd.main()
    return exc_info.value.code


def bash(tmp_path, command):
    return {"cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": command}}


def decision(out):
    return json.loads(out)["hookSpecificOutput"]


# --- TASK-62#2: Done move detection (command position, like require_test_first) ---

DONE_REAL = [
    ("backlog task edit TASK-1 -s Done", ["TASK-1"]),
    ("backlog task edit 1 --status done", ["1"]),
    ("backlog task edit ao-27 --status=DONE", ["ao-27"]),
    ("cd x && FOO=1 /usr/local/bin/backlog task edit A-1 -s Done", ["A-1"]),
    ("backlog tasks edit A-1 --check-ac 1 -s Done", ["A-1"]),
    ("backlog task edit A-1 -s Done; backlog task edit A-2 -s Done", ["A-1", "A-2"]),
    ("backlog task edit A-1 -s 'Done", ["A-1"]),  # unbalanced -> text fallback
]
DONE_TEXT_ONLY = [
    "",
    "echo backlog task edit A-1 -s Done",
    "git commit -m 'backlog task edit A-1 -s Done'",
    "backlog task edit A-1 -s 'In Progress'",
    "backlog task edit -s Done",
    "backlog task edit A-1 -s",
    "backlog task view A-1",
    "backlog draft edit A-1 -s Done",
    "backlog",
    "FOO=1",
    "cat <<'EOF'\nbacklog task edit A-1 -s Done\nEOF",
]


@pytest.mark.parametrize("command, targets", DONE_REAL)
def test_task62_2_done_targets_detects_done_move(command, targets):
    """TASK-62#2: 명령 위치의 `backlog task edit <ID> ... -s Done`을 찾는다."""
    assert rcd.done_targets(command) == targets


@pytest.mark.parametrize("command", DONE_TEXT_ONLY)
def test_task62_2_done_targets_ignores_text(command):
    """TASK-62#2: 인자 · 따옴표 · heredoc 안의 글자는 Done 이동이 아니다."""
    assert rcd.done_targets(command) == []


@pytest.mark.parametrize("manifest", ["pyproject.toml", "package.json", "CMakeLists.txt"])
def test_task62_2_language_without_coverage_command_denies_done(
    tmp_path, monkeypatch, capsys, manifest
):
    """TASK-62#2: 언어가 감지됐는데 coverageCommand가 없으면 -s Done을 deny한다."""
    backlog_project(tmp_path)
    (tmp_path / manifest).write_text("")
    code = run_main(monkeypatch, bash(tmp_path, DONE))
    assert code == 0
    hso = decision(capsys.readouterr().out)
    assert hso["permissionDecision"] == "deny"
    assert "coverageCommand" in hso["permissionDecisionReason"]


def test_task62_2_empty_coverage_command_counts_as_missing(tmp_path, monkeypatch, capsys):
    """TASK-62#2: 빈 coverageCommand는 설정되지 않은 것과 같다(옛 설정 이름도 읽는다)."""
    backlog_project(tmp_path)
    (tmp_path / "pom.xml").write_text("")
    (tmp_path / ".claude-rails.json").write_text(json.dumps({"coverageCommand": ""}))
    run_main(monkeypatch, bash(tmp_path, DONE))
    assert decision(capsys.readouterr().out)["permissionDecision"] == "deny"


def test_task62_2_no_language_no_command_passes(tmp_path, monkeypatch, capsys):
    """TASK-62#2: 감지된 언어가 없고 coverageCommand도 없으면 통과(opt-in 유지)."""
    backlog_project(tmp_path)
    assert run_main(monkeypatch, bash(tmp_path, DONE)) == 0
    assert capsys.readouterr().out == ""


def test_task62_2_not_a_backlog_project_passes(tmp_path, monkeypatch, capsys):
    """TASK-62#2: backlog.md 프로젝트가 아니면 통과."""
    (tmp_path / "pyproject.toml").write_text("")
    assert run_main(monkeypatch, bash(tmp_path, DONE)) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        {"tool_name": "Edit", "tool_input": {"file_path": "x"}},
        {"tool_name": "Bash", "tool_input": "oops"},
        {"tool_name": "Bash"},
    ],
)
def test_task62_2_ignores_non_bash_or_malformed_input(monkeypatch, capsys, payload):
    """TASK-62#2: Bash가 아니거나 입력이 깨졌으면 통과."""
    assert run_main(monkeypatch, payload) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("command", ["ls", "git push", "backlog task view A-1", ""])
def test_task62_2_non_done_line_exits_before_any_check(tmp_path, monkeypatch, capsys, command):
    """TASK-62#2: Done 이동이 아닌 줄은 설정 · 언어 감지 · 서브프로세스 전에 끝난다."""
    backlog_project(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run before a Done move is detected")

    monkeypatch.setattr(rcd, "detect_languages", forbidden)
    monkeypatch.setattr(rcd, "configured_coverage_command", forbidden)
    monkeypatch.setattr(rcd.subprocess, "run", forbidden)
    assert run_main(monkeypatch, bash(tmp_path, command)) == 0
    assert capsys.readouterr().out == ""


# --- TASK-62#3: -s Done에서도 coverageCommand를 실행하고 리포트를 확인한다 ---


def done_with(tmp_path, monkeypatch, capsys, manifests, config):
    backlog_project(tmp_path)
    for name in manifests:
        (tmp_path / name).write_text("")
    (tmp_path / ".claude-code-agile-hooks.json").write_text(json.dumps(config))
    assert run_main(monkeypatch, bash(tmp_path, DONE)) == 0
    return json.loads(capsys.readouterr().out)


def test_task62_3_done_passes_with_fresh_report(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 명령 성공 + 이번 실행의 리포트 -> 통과(권한 결정 없이 리포트만 보여 줌)."""
    out = done_with(tmp_path, monkeypatch, capsys, ["pyproject.toml"],
                    {"coverageCommand": "echo TOTAL-100 && echo r > coverage.xml"})
    assert "hookSpecificOutput" not in out
    assert "TOTAL-100" in out["systemMessage"]


def test_task62_3_done_denies_failing_command(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 명령이 실패하면(100% 미달) -s Done을 deny하고 출력을 보여 준다."""
    out = done_with(tmp_path, monkeypatch, capsys, ["pom.xml"],
                    {"coverageCommand": "echo 'LINE 0.93' && exit 1"})
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "미달" in hso["permissionDecisionReason"]
    assert "LINE 0.93" in hso["permissionDecisionReason"]


def test_task62_3_done_denies_missing_report(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 명령은 성공했지만 리포트가 없으면 -s Done을 deny한다."""
    out = done_with(tmp_path, monkeypatch, capsys, ["CMakeLists.txt"],
                    {"coverageCommand": "true"})
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "coverage" in hso["permissionDecisionReason"]


def test_task62_3_done_denies_malformed_report_dir(tmp_path, monkeypatch, capsys):
    """TASK-62#3: coverageReportDir 형식이 틀리면 -s Done을 deny한다."""
    out = done_with(tmp_path, monkeypatch, capsys, ["package.json"],
                    {"coverageCommand": "true", "coverageReportDir": ["x"]})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_task62_3_done_without_language_runs_command_only(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 언어가 없어도 coverageCommand가 있으면 돌리고, 종료 코드만 본다."""
    out = done_with(tmp_path, monkeypatch, capsys, [], {"coverageCommand": "exit 3"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# The helpers below are copies of pre_push_coverage_check.py's (REGISTRY keeps
# them identical); these cases cover this file's own copies.


def test_task62_2_helper_edges():
    """TASK-62#2: 빈 cwd는 backlog 프로젝트도 아니고 언어도 없다; 래퍼 뒤의 backlog도 센다."""
    assert rcd.is_backlog_project("") is False
    assert rcd.detect_languages("") == []
    assert rcd.done_targets("sudo -E backlog task edit A-1 -s Done") == ["A-1"]


def test_task62_3_helper_edges(tmp_path):
    """TASK-62#3: 설정 없음 -> coverageReportDir 없음; 문자열 · 맵 덮어쓰기; 깨진 링크는 건너뜀."""
    assert rcd.configured_report_dir(str(tmp_path)) is None
    assert rcd.report_paths(["java", "cpp"], "cov") == {"java": ("cov",), "cpp": ("cov",)}
    assert rcd.report_paths(["java", "cpp"], {"cpp": "c"}) == {
        "java": ("target/site/jacoco", "build/reports/jacoco"),
        "cpp": ("c",),
    }
    (tmp_path / "coverage").mkdir()
    (tmp_path / "coverage" / "dangling").symlink_to(tmp_path / "nowhere")
    assert rcd.fresh_report(str(tmp_path), "coverage", 0) is False
    (tmp_path / "coverage" / "index.html").write_text("x")
    assert rcd.fresh_report(str(tmp_path), "coverage", 0) is True
    assert rcd.fresh_report(str(tmp_path), "coverage", 10**12) is False  # stale


def test_task62_4_readme_documents_coverage_gate():
    """TASK-62#4: README에 언어별 100% 설정 예 · 리포트 위치 · 새 훅이 있다."""
    import os

    readme = os.path.join(os.path.dirname(__file__), os.pardir, "README.md")
    with open(readme) as f:
        text = f.read()
    for needle in (
        "--cov-fail-under=100",
        "coverageThreshold",
        "thresholds: { 100: true }",
        "minimum",
        "--fail-under-line 100 --fail-under-branch 100",
        "htmlcov/",
        "coverage.xml",
        "target/site/jacoco/",
        "build/reports/jacoco/",
        "coverageReportDir",
        "require_coverage_on_done.py",
    ):
        assert needle in text, needle
    for language, paths in rcd.default_report_paths().items():
        for path in paths:
            assert path in text, (language, path)
