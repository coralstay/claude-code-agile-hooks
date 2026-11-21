# ---
# title: test_workflow_guide
# description: 워크플로 안내문의 내용·길이·README 대응과 session_start 배달, install.sh가 CLAUDE.md를 건드리지 않음을 검증하는 테스트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-21'
# updated_date: '2026-11-21'
# ---
# TASK-76: 워크플로 안내문을 훅과 함께 배달한다(session_start가 매 세션 출력, CLAUDE.md 블록 대신)
#
# The guide (hooks/workflow_guide.md) is installed next to the hooks and
# printed by session_start.py on every session. These tests read the repo's
# guide and README, run session_start.py in-process (its __file__ pointed at a
# tmp dir to move or remove the guide) and as a subprocess, and run install.sh
# against a tmp $HOME - never the real ~/.claude.
import io
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import session_start as ss

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HOOKS_DIR)
GUIDE = os.path.join(HOOKS_DIR, "workflow_guide.md")
INSTALL_SH = os.path.join(REPO_ROOT, "install.sh")
MAX_GUIDE_LINES = 30
OLD_MARKER = "<!-- CLAUDE-CODE-AGILE-HOOKS:BEGIN -->"

# Rules the guide states in words: each phrase (a stem, since the guide
# says 한다 and README says 합니다) must be in the guide and in README
# (README is the SSOT). Inline code spans are checked separately.
GUIDE_RULE_PHRASES = (
    "메시지대로 따르고 우회하지 않",
    "plan mode",
    "SOAP",
    "사람이 자기 키로 서명",
    "Claude는 만들지 않",
    "승인 전에는 실행하지 않",
    "단계마다 커밋",
    "커밋하지 않은 채 턴을 끝내지 않",
    "유저에게 먼저 묻",
    "명령 · 파일이 겨누는 저장소",
    "리터럴 경로",
    "push는 Done 뒤에만",
    "PR 병합은 사람이",
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def guide_body():
    return ss.strip_frontmatter(read(GUIDE))


def backlog_stub(tmp_path):
    """A `backlog` on PATH that echoes which subcommand ran."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "backlog"
    script.write_text('#!/bin/sh\necho "STUB $1 $2"\n')
    script.chmod(0o755)
    return str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def backlog_project(path):
    (path / ".git").mkdir(parents=True)
    (path / "backlog").mkdir()
    (path / "backlog" / "config.yml").write_text("x: 1\n")
    return path


def run_main(monkeypatch, cwd):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": str(cwd)})))
    with pytest.raises(SystemExit) as exc_info:
        ss.main()
    return exc_info.value.code


def output(capsys):
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out else None


def hook_dir_with(tmp_path, guide):
    """A fake installed hook dir: session_start's __file__ lives there and
    the guide is `guide` (text), a directory ('DIR') or absent (None)."""
    hooks = tmp_path / "installed"
    hooks.mkdir()
    if guide == "DIR":
        (hooks / "workflow_guide.md").mkdir()
    elif guide is not None:
        (hooks / "workflow_guide.md").write_bytes(guide)
    return hooks


def run_install(home, tmp_path):
    return subprocess.run(
        ["bash", INSTALL_SH],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )


# == AC/DoD ==


def test_guide_carries_the_approved_items():
    """TASK-76#1: briefing, plan → draft → promote, the human signature,
    execution order, stage commits, scope questions, target repository and
    literal paths, completion · push · merge and README as the SSOT."""
    body = guide_body()
    for phrase in (
        *GUIDE_RULE_PHRASES,
        "`backlog overview`",
        "`backlog search`",
        "`backlog draft create`",
        "AC · DoD",
        "`backlog draft promote <ID>`",
        "`--add-ref`",
        "`--doc`",
        "`Plan-Approved: <ID>`",
        "`backlog task view <ID> --plain`",
        '`-s "In Progress"`',
        "`task/<ID>`",
        "`<ID>#<n>`",
        "`<ID>#B<k>`",
        "AC 밖",
        "`git -C <dir>`",
        "`--final-summary`",
        "README.md",
        "SSOT",
    ):
        assert phrase in body, phrase


def test_guide_has_no_backlogging_skill_or_porting_note():
    """TASK-76#1: no /backlogging skill and no old .sh → .py porting note."""
    text = read(GUIDE)
    assert "/backlogging" not in text
    assert "백로깅" not in text
    assert "포팅" not in text
    assert ".sh" not in text


def test_guide_stays_short():
    """TASK-76#1 TASK-76#B4: the guide Claude sees has a line cap."""
    lines = guide_body().splitlines()
    assert 0 < len(lines) <= MAX_GUIDE_LINES, len(lines)


def test_every_guide_rule_is_in_readme():
    """TASK-76#1 TASK-76#B1: README is the SSOT - every inline code span of
    the guide and every rule phrase is also in README."""
    body = guide_body()
    readme = read(os.path.join(REPO_ROOT, "README.md"))
    spans = re.findall(r"`([^`]+)`", body)
    assert len(spans) >= 10
    missing = [s for s in spans if s not in readme]
    missing += [p for p in GUIDE_RULE_PHRASES if p not in readme]
    assert missing == []


def test_session_start_prints_the_guide_outside_any_project(monkeypatch, capsys, tmp_path):
    """TASK-76#2 TASK-76#B2: a non-project cwd (with or without the backlog
    CLI) still gets the guide as additionalContext and no systemMessage."""
    for has_backlog in (True, False):
        monkeypatch.setattr(ss, "has_command", lambda name, v=has_backlog: v)
        assert run_main(monkeypatch, tmp_path) == 0
        hso = output(capsys)
        assert hso["hookEventName"] == "SessionStart"
        assert hso["additionalContext"] == guide_body()
        assert "systemMessage" not in hso


def test_session_start_appends_overview_after_the_guide_in_a_project(tmp_path):
    """TASK-76#2 TASK-76#B2: inside a backlog project (here a subdirectory,
    run as a real subprocess with a stub backlog) the guide comes first, then
    the overview; backlog doctor stays in systemMessage."""
    project = backlog_project(tmp_path / "proj")
    (project / "sub").mkdir()
    result = subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, "session_start.py")],
        input=json.dumps({"cwd": str(project / "sub")}),
        env={**os.environ, "PATH": backlog_stub(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    hso = json.loads(result.stdout)["hookSpecificOutput"]
    assert hso["additionalContext"] == guide_body() + "\n\nSTUB instructions overview\n"
    assert hso["systemMessage"] == "backlog doctor:\nSTUB doctor \n"


@pytest.mark.parametrize("guide", [None, "DIR", b"\xff\xfe broken"], ids=["missing", "directory", "not-utf8"])
def test_session_start_without_a_readable_guide_never_fails(monkeypatch, capsys, tmp_path, guide):
    """TASK-76#2 TASK-76#B2: no guide or an unreadable one - no crash, no
    guide; outside a project nothing is printed, inside one the overview
    alone is."""
    hooks = hook_dir_with(tmp_path, guide)
    monkeypatch.setattr(ss, "__file__", str(hooks / "session_start.py"))
    monkeypatch.setattr(ss, "has_command", lambda name: True)
    monkeypatch.setattr(ss, "run", lambda cwd, cmd: "OVERVIEW" if cmd[1] == "instructions" else "ok")

    assert run_main(monkeypatch, tmp_path / "elsewhere") == 0
    assert capsys.readouterr().out == ""

    project = backlog_project(tmp_path / "proj")
    assert run_main(monkeypatch, project) == 0
    hso = output(capsys)
    assert hso["additionalContext"] == "OVERVIEW"
    assert hso["systemMessage"] == "backlog doctor:\nok"


def test_session_start_reads_the_guide_next_to_the_installed_hook(tmp_path):
    """TASK-76#2: installed layout - the guide beside a copied hook is the
    one printed, without its frontmatter."""
    hooks = hook_dir_with(tmp_path, "---\ntitle: x\n---\n안내 본문\n".encode())
    shutil.copy(os.path.join(HOOKS_DIR, "session_start.py"), hooks)
    result = subprocess.run(
        [sys.executable, str(hooks / "session_start.py")],
        input=json.dumps({"cwd": str(tmp_path)}),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"] == "안내 본문"


def test_snippet_is_gone():
    """TASK-76#3: CLAUDE.md.snippet no longer exists."""
    assert not os.path.exists(os.path.join(REPO_ROOT, "CLAUDE.md.snippet"))


@pytest.mark.parametrize("existing", [None, "", "# mine\n", "# mine\n" + OLD_MARKER + "\nold\n<!-- CLAUDE-CODE-AGILE-HOOKS:END -->\n"],
                         ids=["absent", "empty", "own-rules", "old-block"])
def test_install_never_writes_claude_md_and_copies_the_guide(tmp_path, existing):
    """TASK-76#3 TASK-76#B3: install.sh leaves ~/.claude/CLAUDE.md exactly as
    it was (not created, not appended), notes an old marker block only, and
    puts the guide next to the hooks."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    claude_md = home / ".claude" / "CLAUDE.md"
    if existing is not None:
        claude_md.write_text(existing)
    result = run_install(home, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    if existing is None:
        assert not claude_md.exists()
    else:
        assert claude_md.read_text() == existing
    noticed = "CLAUDE-CODE-AGILE-HOOKS:BEGIN" in result.stdout
    assert noticed == (existing is not None and OLD_MARKER in existing)
    if noticed:
        assert "session_start" in result.stdout
        assert "자동으로 고치지 않음" in result.stdout
    installed = home / ".claude" / "hooks" / "claude-code-agile-hooks" / "workflow_guide.md"
    assert installed.read_text(encoding="utf-8") == read(GUIDE)


def test_install_help_no_longer_mentions_the_snippet():
    """TASK-76#3: the usage text describes the guide copy, not CLAUDE.md."""
    result = subprocess.run(["bash", INSTALL_SH, "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "CLAUDE.md.snippet" not in result.stdout
    assert "workflow_guide.md" in result.stdout
    assert "건드리지 않음" in result.stdout


def test_readme_describes_the_new_delivery():
    """TASK-76#4: README explains the guide file + session_start delivery
    and no longer the snippet."""
    readme = read(os.path.join(REPO_ROOT, "README.md"))
    assert "CLAUDE.md.snippet" not in readme
    assert "[`hooks/workflow_guide.md`](hooks/workflow_guide.md)" in readme
    assert "additionalContext" in readme
    assert "CLAUDE-CODE-AGILE-HOOKS:BEGIN" in readme


# == Coverage ==


@pytest.mark.parametrize(
    "text, expected",
    [
        ("---\na: 1\n---\nbody\n", "body"),
        ("no frontmatter\n", "no frontmatter"),
        ("---\nunterminated\n", "---\nunterminated"),
        ("\n\n", ""),
    ],
)
def test_strip_frontmatter(text, expected):
    assert ss.strip_frontmatter(text) == expected


def test_empty_guide_and_empty_overview_print_nothing(monkeypatch, capsys, tmp_path):
    hooks = hook_dir_with(tmp_path, b"---\ntitle: x\n---\n\n")
    monkeypatch.setattr(ss, "__file__", str(hooks / "session_start.py"))
    monkeypatch.setattr(ss, "has_command", lambda name: True)
    monkeypatch.setattr(ss, "run", lambda cwd, cmd: "")
    assert run_main(monkeypatch, tmp_path / "elsewhere") == 0
    assert capsys.readouterr().out == ""
    project = backlog_project(tmp_path / "proj")
    assert run_main(monkeypatch, project) == 0
    hso = output(capsys)
    assert hso["additionalContext"] == ""
    assert hso["systemMessage"] == "backlog doctor:\n"
