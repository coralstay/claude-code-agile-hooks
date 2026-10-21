import io
import json
import os

import pytest

import pre_push_coverage_check as ppc

PUSH_INPUT = {"command": "git push"}


def run_main(monkeypatch, stdin_data):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        ppc.main()
    return exc_info.value.code


def test_no_op_when_command_is_not_a_push(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": "git status"}}
    )
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl").exists()


def test_no_op_when_no_config_file(tmp_path, monkeypatch, capsys):
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl").exists()


def test_no_op_when_coverage_command_key_missing(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(json.dumps({}))
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl").exists()


def test_allows_and_reports_when_command_succeeds(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "echo 'TOTAL 100%' && exit 0"})
    )
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"
    assert "TOTAL 100%" in hso["systemMessage"]

    log_file = tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    lines = log_file.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["passed"] is True
    assert record["exit_code"] == 0
    assert "TOTAL 100%" in record["output"]
    assert "timestamp" in record


def test_denies_and_reports_when_command_fails(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "echo 'TOTAL 42%' && exit 1"})
    )
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0  # blocking happens via JSON permissionDecision, not exit code
    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "미달" in hso["permissionDecisionReason"]
    assert "TOTAL 42%" in hso["systemMessage"]

    log_file = tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    record = json.loads(log_file.read_text().splitlines()[0])
    assert record["passed"] is False
    assert record["exit_code"] == 1


def test_fires_on_dash_c_push(tmp_path, monkeypatch, capsys):
    # Regression: `git -C <path> push ...` must still be recognized, not
    # just a literal `git push` prefix.
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "echo ran && exit 0"})
    )
    code = run_main(
        monkeypatch,
        {
            "cwd": str(tmp_path),
            "tool_input": {"command": f"git -C {tmp_path} push -u origin x"},
        },
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"


def _init_git_repo(cwd, branch):
    import subprocess

    subprocess.run(
        ["git", "init", "-q", "-b", branch], cwd=cwd, check=True, capture_output=True
    )
    (cwd / "f.txt").write_text("hi")
    subprocess.run(["git", "add", "f.txt"], cwd=cwd, check=True, capture_output=True)
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
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_log_includes_session_project_branch_task_id(tmp_path, monkeypatch):
    _init_git_repo(tmp_path, "task/TASK-42")
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 0"})
    )
    run_main(
        monkeypatch,
        {"cwd": str(tmp_path), "session_id": "sess-abc123", "tool_input": PUSH_INPUT},
    )

    log_file = tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    record = json.loads(log_file.read_text().splitlines()[0])
    assert record["session_id"] == "sess-abc123"
    assert record["project"] == tmp_path.name
    assert record["branch"] == "task/TASK-42"
    assert record["task_id"] == "TASK-42"


def test_log_task_id_is_none_off_task_branch(tmp_path, monkeypatch):
    _init_git_repo(tmp_path, "main")
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 0"})
    )
    run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})

    log_file = tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    record = json.loads(log_file.read_text().splitlines()[0])
    assert record["branch"] == "main"
    assert record["task_id"] is None


def test_task_id_from_branch():
    assert ppc.task_id_from_branch("task/TASK-7") == "TASK-7"
    assert ppc.task_id_from_branch("main") is None
    assert ppc.task_id_from_branch("") is None


def test_log_appends_across_multiple_push_attempts(tmp_path, monkeypatch):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 0"})
    )
    run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})

    log_file = tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    lines = log_file.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["passed"] is False
    assert json.loads(lines[1])["passed"] is True


def test_append_log_creates_directory(tmp_path):
    ppc.append_log(str(tmp_path), {"a": 1})
    log_file = tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    assert json.loads(log_file.read_text().strip()) == {"a": 1}


def test_log_path(tmp_path):
    assert ppc.log_path(str(tmp_path)) == str(
        tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    )


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    with pytest.raises(SystemExit) as exc_info:
        ppc.main()
    assert exc_info.value.code == 0
    assert capsys.readouterr().out == ""


def test_configured_coverage_command_reads_file(tmp_path):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "pytest --cov"})
    )
    assert ppc.configured_coverage_command(str(tmp_path)) == "pytest --cov"


def test_configured_coverage_command_none_without_file(tmp_path):
    assert ppc.configured_coverage_command(str(tmp_path)) is None


def test_run_shell_captures_combined_output():
    code, output = ppc.run_shell(".", "echo out; echo err >&2; exit 5")
    assert code == 5
    assert "out" in output and "err" in output


# --- TASK-39: only a `git push` in command position counts ------------------

PUSH_TEXT_ONLY = [
    "echo git push",
    "echo /usr/bin/git",
    'echo "git push origin task/x"',
    "git commit -m 'then git push'",
    "backlog task edit TASK-1 --notes 'git push after review'",
    "cat <<'EOF' > notes.md\ngit push\nEOF",
    "cat <<EOF\n  git -C /p push\nEOF\necho done",
    "git -C /p status",
    "git log --grep push",
    "git --no-pager",
    "",
]

PUSH_REAL = [
    "git push",
    "/usr/bin/git push",
    "./git push",
    "git -C /p push",
    "git -c push.default=current push",
    "git --git-dir=.git push",
    "git -q push",
    "FOO=1 git push",
    "env FOO=1 git push origin task/x",
    "sudo -E git push",
    "cd /p && git push",
    "git commit -m x; git push",
    "false || git push",
    "(git push)",
    "git \\\npush",
    "cat <<'EOF' > f\nbody\nEOF\ngit push",
    'git push "unterminated',
]


@pytest.mark.parametrize("command", PUSH_TEXT_ONLY)
def test_command_runs_git_ignores_text(command):
    assert ppc.command_runs_git(command, "push") is False


@pytest.mark.parametrize("command", PUSH_REAL)
def test_command_runs_git_detects_real_push(command):
    assert ppc.command_runs_git(command, "push") is True


def test_command_runs_git_unparsable_falls_back_to_substring():
    assert ppc.command_runs_git('git commit -m "x', "push") is False
    assert ppc.command_runs_git('git push "x', "push") is True


@pytest.mark.parametrize("command", PUSH_TEXT_ONLY)
def test_text_mentioning_push_runs_no_coverage(tmp_path, monkeypatch, capsys, command):
    # Regression (TASK-39): `echo git push` and heredoc bodies used to run the
    # coverage command and log an attempt.
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": command}}
    )
    assert code == 0
    assert capsys.readouterr().out == ""
    assert not (tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl").exists()


def test_fires_on_prefixed_absolute_push_in_chain(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )
    command = "git commit -m x && FOO=1 /usr/bin/git push"
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": command}}
    )
    assert code == 0
    hso = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"


# --- TASK-46: no `if` filter any more, so this runs on every Bash call ---


@pytest.mark.parametrize(
    "command",
    ["ls -la", "git status", "cd x && gh pr view 1", "echo git push", ""],
)
def test_non_push_line_exits_before_config_or_subprocess(
    tmp_path, monkeypatch, capsys, command
):
    """A line without a push must stay cheap: no config read, no
    subprocess, no output."""
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "exit 1"})
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("must not run before a push is detected")

    monkeypatch.setattr(ppc.subprocess, "run", forbidden)
    monkeypatch.setattr(ppc, "configured_coverage_command", forbidden)
    code = run_main(
        monkeypatch, {"cwd": str(tmp_path), "tool_input": {"command": command}}
    )
    assert code == 0
    assert capsys.readouterr().out == ""


def test_segment_of_only_assignments_is_not_a_push():
    assert ppc.command_runs_git("FOO=1 BAR=2", "push") is False
    assert ppc.command_runs_git("FOO=1 BAR=2; git push", "push") is True


# TASK-54: .claude-code-agile-hooks.json 우선, 옛 .claude-rails.json fallback.
# 로그는 옛 설정만 쓰고 .claude-code-agile-hooks/가 아직 없을 때만 .claude-rails/에 남는다.
def test_config_only_new_name_logs_to_new_dir(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "echo new && exit 0"})
    )
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT}) == 0
    assert "new" in capsys.readouterr().out
    assert (tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl").exists()
    assert not (tmp_path / ".claude-rails").exists()


def test_config_only_legacy_name_logs_to_legacy_dir(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-rails.json").write_text(
        json.dumps({"coverageCommand": "echo old && exit 0"})
    )
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT}) == 0
    assert "old" in capsys.readouterr().out
    assert (tmp_path / ".claude-rails" / "coverage-log.jsonl").exists()
    assert not (tmp_path / ".claude-code-agile-hooks").exists()


def test_config_both_names_new_wins(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageCommand": "echo new && exit 0"})
    )
    (tmp_path / ".claude-rails.json").write_text(
        json.dumps({"coverageCommand": "echo old && exit 1"})
    )
    assert ppc.configured_coverage_command(str(tmp_path)) == "echo new && exit 0"
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT}) == 0
    out = capsys.readouterr().out
    assert "new" in out and "old" not in out
    assert (tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl").exists()
    assert not (tmp_path / ".claude-rails").exists()


def test_legacy_config_with_existing_new_dir_logs_to_new_dir(tmp_path):
    (tmp_path / ".claude-rails.json").write_text(json.dumps({}))
    (tmp_path / ".claude-code-agile-hooks").mkdir()
    assert ppc.log_path(str(tmp_path)) == str(
        tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl"
    )


def test_project_config_path_none(tmp_path):
    assert ppc.project_config_path(str(tmp_path)) is None


# --- TASK-62: 매니페스트로 5개 언어 감지, 감지되면 coverageCommand 필수 ---


@pytest.mark.parametrize(
    "manifest, language",
    [
        ("package.json", "javascript"),
        ("tsconfig.json", "typescript"),
        ("pom.xml", "java"),
        ("build.gradle", "java"),
        ("build.gradle.kts", "java"),
        ("pyproject.toml", "python"),
        ("setup.cfg", "python"),
        ("pytest.ini", "python"),
        ("CMakeLists.txt", "cpp"),
    ],
)
def test_task62_1_detects_language_by_manifest(tmp_path, manifest, language):
    """TASK-62#1: 프로젝트 루트의 매니페스트 하나로 언어를 감지한다."""
    (tmp_path / manifest).write_text("")
    assert ppc.detect_languages(str(tmp_path)) == [language]


def test_task62_1_detects_several_languages_in_fixed_order(tmp_path):
    """TASK-62#1: 여러 매니페스트 -> 고정 순서의 언어 목록(중복 없음)."""
    for name in ("CMakeLists.txt", "pytest.ini", "pyproject.toml", "tsconfig.json",
                 "package.json", "pom.xml", "build.gradle"):
        (tmp_path / name).write_text("")
    assert ppc.detect_languages(str(tmp_path)) == [
        "javascript", "typescript", "java", "python", "cpp",
    ]


def test_task62_1_no_manifest_detects_nothing(tmp_path):
    """TASK-62#1: 매니페스트가 없거나 하위 디렉토리에만 있으면 감지하지 않는다."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "package.json").write_text("")
    (tmp_path / "README.md").write_text("")
    assert ppc.detect_languages(str(tmp_path)) == []
    assert ppc.detect_languages("") == []


def test_task62_1_manifest_must_be_a_file(tmp_path):
    """TASK-62#1: 같은 이름의 디렉토리는 매니페스트가 아니다."""
    (tmp_path / "pom.xml").mkdir()
    assert ppc.detect_languages(str(tmp_path)) == []


@pytest.mark.parametrize("config", [None, {}, {"coverageCommand": ""}])
def test_task62_2_language_without_coverage_command_denies_push(
    tmp_path, monkeypatch, capsys, config
):
    """TASK-62#2: 언어가 감지됐는데 coverageCommand가 없으면 push를 deny한다
    (opt-in -> 필수)."""
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    if config is not None:
        (tmp_path / ".claude-code-agile-hooks.json").write_text(json.dumps(config))
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    hso = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    reason = hso["permissionDecisionReason"]
    assert "coverageCommand" in reason
    assert "javascript" in reason and "python" in reason


def test_task62_2_no_language_keeps_opt_in(tmp_path, monkeypatch, capsys):
    """TASK-62#2: 감지된 언어가 없으면 지금처럼 opt-in(설정 없으면 조용히 통과)."""
    (tmp_path / "Makefile").write_text("")
    code = run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT})
    assert code == 0
    assert capsys.readouterr().out == ""


# --- TASK-62#3: 명령 실패 또는 이번 실행의 리포트가 없으면 deny (툴체인은 셸 스텁) ---


def push_with(tmp_path, monkeypatch, capsys, manifests, config):
    for name in manifests:
        (tmp_path / name).write_text("")
    (tmp_path / ".claude-code-agile-hooks.json").write_text(json.dumps(config))
    assert run_main(monkeypatch, {"cwd": str(tmp_path), "tool_input": PUSH_INPUT}) == 0
    return json.loads(capsys.readouterr().out)["hookSpecificOutput"]


def writes(*paths):
    """Shell stub of a coverage tool that writes report files and exits 0."""
    parts = []
    for p in paths:
        parent = os.path.dirname(p)
        if parent:
            parts.append(f"mkdir -p {parent}")
        parts.append(f"echo report > {p}")
    return " && ".join(parts) or "true"



@pytest.mark.parametrize(
    "manifests, report",
    [
        (["pyproject.toml"], "coverage.xml"),
        (["setup.cfg"], "htmlcov/index.html"),
        (["package.json"], "coverage/lcov.info"),
        (["tsconfig.json"], "coverage/index.html"),
        (["pom.xml"], "target/site/jacoco/index.html"),
        (["build.gradle.kts"], "build/reports/jacoco/test/html/index.html"),
        (["CMakeLists.txt"], "coverage/index.html"),
        (["package.json", "tsconfig.json"], "coverage/coverage-final.json"),
    ],
)
def test_task62_3_fresh_report_in_default_location_allows(
    tmp_path, monkeypatch, capsys, manifests, report
):
    """TASK-62#3: 명령이 성공하고 언어별 기본 위치에 이번 실행의 리포트가 있으면 통과."""
    hso = push_with(tmp_path, monkeypatch, capsys, manifests,
                    {"coverageCommand": writes(report)})
    assert hso["permissionDecision"] == "allow", hso["permissionDecisionReason"]


def test_task62_3_success_without_report_denies(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 명령은 성공했지만 리포트가 없으면 deny하고 위치를 알려 준다."""
    hso = push_with(tmp_path, monkeypatch, capsys, ["pyproject.toml"],
                    {"coverageCommand": "echo 'TOTAL 100%'"})
    assert hso["permissionDecision"] == "deny"
    reason = hso["permissionDecisionReason"]
    assert "python" in reason and "htmlcov" in reason and "coverage.xml" in reason
    record = json.loads(
        (tmp_path / ".claude-code-agile-hooks" / "coverage-log.jsonl").read_text()
    )
    assert record["passed"] is False and record["exit_code"] == 0
    assert record["languages"] == ["python"]


def test_task62_3_stale_report_denies(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 실행 전부터 있던(mtime이 실행 시작보다 이른) 리포트는 세지 않는다."""
    (tmp_path / "htmlcov").mkdir()
    old = tmp_path / "htmlcov" / "index.html"
    old.write_text("old")
    os.utime(old, (1_000_000, 1_000_000))
    (tmp_path / "coverage.xml").write_text("old")
    os.utime(tmp_path / "coverage.xml", (1_000_000, 1_000_000))
    hso = push_with(tmp_path, monkeypatch, capsys, ["pytest.ini"],
                    {"coverageCommand": "true"})
    assert hso["permissionDecision"] == "deny"


def test_task62_3_failing_command_denies_even_with_report(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 100% 미달(명령 실패)이면 리포트가 있어도 deny."""
    hso = push_with(tmp_path, monkeypatch, capsys, ["pyproject.toml"],
                    {"coverageCommand": writes("coverage.xml") + " && exit 2"})
    assert hso["permissionDecision"] == "deny"
    assert "미달" in hso["permissionDecisionReason"]


def test_task62_3_every_detected_language_needs_its_report(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 감지된 언어마다 리포트가 있어야 한다(JS 리포트로 Python을 대신하지 못함)."""
    hso = push_with(tmp_path, monkeypatch, capsys, ["package.json", "pyproject.toml"],
                    {"coverageCommand": writes("coverage/lcov.info")})
    assert hso["permissionDecision"] == "deny"
    reason = hso["permissionDecisionReason"]
    assert "python" in reason and "javascript" not in reason


def test_task62_3_no_language_checks_only_exit_code(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 감지된 언어가 없으면 리포트를 요구하지 않는다(opt-in 그대로)."""
    hso = push_with(tmp_path, monkeypatch, capsys, [], {"coverageCommand": "true"})
    assert hso["permissionDecision"] == "allow"


def test_task62_3_report_dir_string_overrides_every_language(tmp_path, monkeypatch, capsys):
    """TASK-62#3: coverageReportDir 문자열은 감지된 모든 언어의 위치를 바꾼다."""
    config = {"coverageCommand": writes("reports/cov/index.html"),
              "coverageReportDir": "reports/cov"}
    hso = push_with(tmp_path, monkeypatch, capsys, ["pyproject.toml", "pom.xml"], config)
    assert hso["permissionDecision"] == "allow"


def test_task62_3_report_dir_string_replaces_default(tmp_path, monkeypatch, capsys):
    """TASK-62#3: 위치를 바꾸면 기본 위치의 리포트는 세지 않는다."""
    config = {"coverageCommand": writes("coverage.xml"), "coverageReportDir": "out"}
    hso = push_with(tmp_path, monkeypatch, capsys, ["pyproject.toml"], config)
    assert hso["permissionDecision"] == "deny"
    assert "out" in hso["permissionDecisionReason"]


def test_task62_3_report_dir_map_overrides_per_language(tmp_path, monkeypatch, capsys):
    """TASK-62#3: coverageReportDir 맵은 적힌 언어만 바꾸고 나머지는 기본 위치."""
    config = {"coverageCommand": writes("out/cov.xml", "coverage/lcov.info"),
              "coverageReportDir": {"python": "out/cov.xml", "cpp": "x"}}
    hso = push_with(tmp_path, monkeypatch, capsys, ["pyproject.toml", "package.json"], config)
    assert hso["permissionDecision"] == "allow"


@pytest.mark.parametrize(
    "report_dir", ["", ["coverage"], {"ruby": "cov"}, {"python": ""}, {"python": 3}, 7]
)
def test_task62_3_malformed_report_dir_denies_without_running(
    tmp_path, monkeypatch, capsys, report_dir
):
    """TASK-62#3: coverageReportDir 형식이 틀리면 명령을 돌리지 않고 deny."""
    config = {"coverageCommand": "touch ran", "coverageReportDir": report_dir}
    hso = push_with(tmp_path, monkeypatch, capsys, ["pyproject.toml"], config)
    assert hso["permissionDecision"] == "deny"
    assert "coverageReportDir" in hso["permissionDecisionReason"]
    assert not (tmp_path / "ran").exists()


def test_task62_3_fresh_report_skips_unreadable_entries(tmp_path):
    """TASK-62#3: 깨진 심볼릭 링크 같은 읽을 수 없는 항목은 건너뛴다."""
    (tmp_path / "coverage").mkdir()
    (tmp_path / "coverage" / "dangling").symlink_to(tmp_path / "nowhere")
    assert ppc.fresh_report(str(tmp_path), "coverage", 0) is False
    (tmp_path / "coverage" / "index.html").write_text("x")
    assert ppc.fresh_report(str(tmp_path), "coverage", 0) is True
    assert ppc.fresh_report(str(tmp_path), "missing", 0) is False


def test_task62_3_run_start_is_floored_to_the_second(tmp_path, monkeypatch):
    """TASK-62#3: 실행 시작 시각은 초 단위로 내림 — mtime 해상도가 1초인
    파일 시스템에서 같은 초에 쓴 리포트도 이번 실행으로 센다."""
    monkeypatch.setattr(ppc.time, "time", lambda: 2_000_000.9)
    report = tmp_path / "coverage.xml"

    def fake_run(cwd, command):
        report.write_text("x")
        os.utime(report, (2_000_000, 2_000_000))
        return 0, ""

    monkeypatch.setattr(ppc, "run_shell", fake_run)
    exit_code, _, problem = ppc.coverage_verdict(str(tmp_path), "x", ["python"], None)
    assert exit_code == 0 and problem is None


def test_task62_3_configured_report_dir_reads_config(tmp_path):
    """TASK-62#3: coverageReportDir는 설정에서 읽고, 설정이 없으면 None."""
    assert ppc.configured_report_dir(str(tmp_path)) is None
    (tmp_path / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"coverageReportDir": {"python": "cov.xml"}})
    )
    assert ppc.configured_report_dir(str(tmp_path)) == {"python": "cov.xml"}
