"""TASK-63: require_design_propagation.py - a top-level design/ change must
be propagated to the affected component design/ before the top-level task
moves to Done (decision-15).

DOC_SECTION is a verbatim copy of the '## 문서 계층' section of the
top-level design/00-문서-정보.md (coralstay-software-factory, 2026-10-22),
parse rules and 장 대응표 included, so the parser is tested against the
real input format."""

import io
import json
import os
import subprocess

import pytest

import require_design_propagation as rdp

DOC_SECTION = """\
## 문서 계층

설계 문서는 최상위 한 곳(이 저장소의 `design/`)과 컴포넌트 세 곳(각 컴포넌트 저장소의 `design/`)에 나뉜다.

- 컴포넌트는 `components/<이름>`에 두는 독립 git 저장소다. 최상위 `.gitignore`가 `components/`를 제외하고, 최상위는 컴포넌트 파일을 하나도 추적하지 않는다. 서브모듈이 아니다(`.gitmodules` 없음).
- 최상위는 목표 `G-n`(1.03) · 원칙(1.02) · 요구사항 ID(2.03 · 2.04)를 소유한다. 요구사항 ID는 최상위에서만 부여한다.
- 컴포넌트 `design/`은 최상위를 상위 문서로 둔다. 원칙을 상속하고, 요구사항을 같은 ID로 이어받아 패키지 · 클래스 · 결정 · 테스트로 내린다. 최상위 결정을 어겨야 하면 최상위 결정을 먼저 고친다.
- 명세를 저장소마다 두는 이유는 3.05 ADR-025에 있다. 명세와 코드가 같은 저장소에 있어야 SDD(명세를 먼저 고친다)가 같은 PR 안에서 성립하고, 에이전트가 그 저장소의 `design/`을 조상 문서로 읽는다(ORC-019).
- 최상위를 고치면 아래 장 대응표로 영향받는 컴포넌트 `design/`을 같이 고친다(편집 규칙, RAIL-024).

### 장 대응표

최상위 장을 고치면 같은 행의 컴포넌트 장이 영향받는 장이다. claude-code-agile-hooks의 전파 강제 훅이 이 표를 읽는다(RAIL-024). 형식 규칙은 다음과 같다.

- `최상위 장`: `00`은 `design/00-문서-정보.md`, `N.MM`은 `design/N-*/MM-*.md`, `부록 <이름>`은 이름의 공백을 `-`로 바꾼 `design/부록-<이름>.md`다.
- `범위`: `전체`는 장 전체다. `§n`은 제목이 `## §n`으로 시작하는 절, 영역 접두어(`ORC` · `RAIL` · `TRL` · `BL`)는 2.03에서 제목이 그 접두어로 시작하는 절이다. 절 밖(장 머리 · `## 원천`)을 고치면 그 장의 모든 행에 해당한다.
- 컴포넌트 열 머리는 `components/<이름>`의 디렉토리 이름과 같다. 칸에는 그 컴포넌트 `design/`의 장을 같은 표기로 ` · `로 나눠 적고, 대응 장이 없으면 `—`를 적는다.
- 행을 더하거나 칸을 고칠 때 훅은 고치지 않는다. 열 구성이나 칸 표기를 바꾸려면 claude-code-agile-hooks DRAFT-13의 훅을 먼저 맞춘다.

| 최상위 장 | 범위 | agent-orchestrator | claude-code-agile-hooks | coding-agent-git-commit-tool |
| --- | --- | --- | --- | --- |
| 00 | 전체 | 00 | 00 | 00 |
| 1.01 | 전체 | 1.01 | 1.01 | 1.01 |
| 1.02 | 전체 | 1.02 | 1.02 | 1.02 |
| 1.03 | 전체 | 1.03 | 1.03 | 1.03 |
| 1.04 | 전체 | 1.04 | 1.04 | 1.04 |
| 2.01 | 전체 | 2.01 | 2.01 | 2.01 |
| 2.02 | 전체 | 2.02 | 2.02 | 2.02 |
| 2.03 | ORC | 2.03 | — | — |
| 2.03 | RAIL | — | 2.03 | — |
| 2.03 | TRL | — | — | 2.03 |
| 2.03 | BL | 2.03 | 2.03 | — |
| 2.04 | 전체 | 2.04 | 2.04 | 2.04 |
| 3.01 | 전체 | 3.01 | 3.01 | 3.01 |
| 3.02 | 전체 | 3.02 | 3.02 | 3.02 |
| 3.03 | §1 | 3.01 · 3.03 | — | — |
| 3.03 | §2 | — | 3.03 | — |
| 3.03 | §3 | — | — | 3.03 |
| 3.03 | §4 | 3.03 | 3.03 | — |
| 3.04 | §1 | 3.04 | 3.04 | — |
| 3.04 | §2 | 3.04 | — | 3.04 |
| 3.04 | §3 | 3.04 | 3.04 | — |
| 3.04 | §4 | 3.04 | — | — |
| 3.04 | §5 | 3.04 | — | — |
| 3.04 | §6 | 3.04 | — | — |
| 3.04 | §7 | — | 3.04 | — |
| 3.04 | §8 | 3.04 | — | — |
| 3.04 | §9 | — | 3.04 | — |
| 3.05 | 전체 | 3.05 | 3.05 | 3.05 |
| 4.01 | 전체 | 4.01 | 4.01 | 4.01 |
| 4.02 | 전체 | 4.02 | 4.02 | 4.02 |
| 4.03 | 전체 | 4.03 | 4.03 | 4.03 |
| 5.01 | 전체 | 5.01 | 5.01 | 5.01 |
| 5.02 | 전체 | 5.02 | 5.02 | 5.02 |
| 5.03 | 전체 | 5.03 | 5.03 | 5.03 |
| 5.04 | 전체 | 5.04 | 5.04 | 5.04 |
| 부록 참고 문헌 | 전체 | 부록 참고 문헌 | 부록 참고 문헌 | 부록 참고 문헌 |
| 부록 용어집 | 전체 | 부록 용어집 | 부록 용어집 | 부록 용어집 |
"""

DOC = "# 0. 문서 정보\n\n머리말.\n\n" + DOC_SECTION + "\n## 편집 규칙\n\n- 규칙.\n"
COMPONENTS = [
    "agent-orchestrator",
    "claude-code-agile-hooks",
    "coding-agent-git-commit-tool",
]


def replace_table_line(doc, old, new):
    assert old in doc
    return doc.replace(old, new, 1)


# --- AC #1: the 장 대응표 is read from design/00-문서-정보.md, not hardcoded ---


def test_parses_real_table_columns_and_rows():
    """TASK-63#1: components come from the header, rows from the body."""
    table = rdp.parse_table(DOC)
    assert table["components"] == COMPONENTS
    assert len(table["rows"]) == 37
    first = table["rows"][0]
    assert (first["chapter"], first["scope"]) == ("00", "전체")
    assert first["cells"] == {c: ["00"] for c in COMPONENTS}


def test_parses_joined_cells_and_dash():
    """TASK-63#1: ` · ` joins chapters, `—` means none."""
    rows = rdp.parse_table(DOC)["rows"]
    row = next(r for r in rows if (r["chapter"], r["scope"]) == ("3.03", "§1"))
    assert row["cells"] == {
        "agent-orchestrator": ["3.01", "3.03"],
        "claude-code-agile-hooks": [],
        "coding-agent-git-commit-tool": [],
    }
    appendix = rows[-1]
    assert appendix["chapter"] == "부록 용어집"
    assert appendix["cells"]["agent-orchestrator"] == ["부록 용어집"]


def test_table_changes_are_picked_up_without_code_changes():
    """TASK-63#1: a new column or row in the doc shows up as data."""
    doc = DOC.replace(
        "| coding-agent-git-commit-tool |\n| --- | --- | --- | --- | --- |",
        "| coding-agent-git-commit-tool | new-component |\n"
        "| --- | --- | --- | --- | --- | --- |",
    )
    doc = "\n".join(
        line + " — |" if line.startswith("| ") and "| ---" not in line
        and "최상위 장" not in line else line
        for line in doc.split("\n")
    )
    doc = replace_table_line(
        doc,
        "| 부록 용어집 | 전체 | 부록 용어집 | 부록 용어집 | 부록 용어집 | — |",
        "| 부록 용어집 | 전체 | 부록 용어집 | 부록 용어집 | 부록 용어집 | — |\n"
        "| 6.01 | 전체 | — | — | — | 6.01 |",
    )
    table = rdp.parse_table(doc)
    assert table["components"] == COMPONENTS + ["new-component"]
    assert table["rows"][-1]["cells"]["new-component"] == ["6.01"]


def test_no_table_heading_means_no_table():
    """TASK-63#1: a component repo's 00 doc has no 장 대응표 -> None."""
    assert rdp.parse_table("# 0. 문서 정보\n\n## 문서 계층\n\n본문\n") is None
    assert rdp.parse_table("# 0\n\n### 장 대응표\n\n| a | b |\n") is None
    assert rdp.parse_table("") is None


def test_headings_inside_code_fences_are_ignored():
    """TASK-63#1"""
    fenced = "# 0\n\n```\n## 문서 계층\n### 장 대응표\n| 최상위 장 | 범위 | a |\n```\n"
    assert rdp.parse_table(fenced) is None


def test_table_under_heading_ends_at_next_heading():
    """TASK-63#1: rows after the next heading don't belong to the table."""
    doc = DOC.replace("## 편집 규칙", "### 다른 표\n\n| x | y |\n\n## 편집 규칙")
    assert len(rdp.parse_table(doc)["rows"]) == 37


@pytest.mark.parametrize(
    "old, new, needle",
    [
        ("| 최상위 장 | 범위 |", "| 장 | 범위 |", "머리"),
        ("| 최상위 장 | 범위 | agent-orchestrator |", "| 최상위 장 | 범위 | |", "머리"),
        ("| --- | --- | --- | --- | --- |", "| 00 | 전체 | 00 | 00 | 00 |", "구분"),
        ("| 1.01 | 전체 | 1.01 | 1.01 | 1.01 |", "| 1.01 | 전체 | 1.01 | 1.01 |", "칸 수"),
        ("| 1.02 | 전체 |", "| 1.02 | 절반 |", "범위"),
        ("| 1.03 | 전체 |", "| 1.3.x | 전체 |", "최상위 장"),
        ("| 1.04 | 전체 | 1.04 |", "| 1.04 | 전체 | |", "빈 칸"),
    ],
)
def test_malformed_table_raises(old, new, needle):
    """TASK-63#1: a broken table is an error, not silently no table."""
    with pytest.raises(rdp.TableError) as exc_info:
        rdp.parse_table(replace_table_line(DOC, old, new))
    assert needle in str(exc_info.value)


def test_heading_without_table_raises():
    """TASK-63#1"""
    doc = "# 0\n\n## 문서 계층\n\n### 장 대응표\n\n표 없음\n"
    with pytest.raises(rdp.TableError):
        rdp.parse_table(doc)


def test_header_only_table_raises():
    """TASK-63#1"""
    doc = "## 문서 계층\n\n### 장 대응표\n\n| 최상위 장 | 범위 | a |\n"
    with pytest.raises(rdp.TableError):
        rdp.parse_table(doc)


@pytest.mark.parametrize(
    "chapter, path, expected",
    [
        ("00", "design/00-문서-정보.md", True),
        ("00", "design/00-다른.md", False),
        ("3.03", "design/3-아키텍처-설계서/03-컴포넌트-명세.md", True),
        ("3.03", "design/3-아키텍처-설계서/04-인터페이스.md", False),
        ("3.03", "design/3-아키텍처-설계서/x/03-a.md", False),
        ("1.01", "design/1-제안서/01-배경.md", True),
        ("1.01", "design/10-x/01-y.md", False),
        ("부록 참고 문헌", "design/부록-참고-문헌.md", True),
        ("부록 참고 문헌", "design/부록-용어집.md", False),
        ("3.03", "design/diagrams/a.dot", False),
    ],
)
def test_chapter_path_rules(chapter, path, expected):
    """TASK-63#1: 00 / N.MM / 부록 <이름> name files as the doc's rules say."""
    assert rdp.chapter_matches(chapter, path) is expected


# --- temp git repos: a top-level repo and its components/<name> repos ---

GIT_ISOLATION = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")
COMPONENTS_DOC = (
    "# 3.03 컴포넌트 명세\n\n머리말.\n\n"
    "## §1 오케스트레이터\n\na1\n\n"
    "## §2 훅\n\nb1\n\n"
    "## §3 커밋 도구\n\nc1\nc2\n\n"
    "## §4 backlog\n\nd1\n\n"
    "```\n## §2 펜스 안\n```\nf1\n\n"
    "## 원천\n\ne1\n"
)
REQUIREMENTS_DOC = (
    "# 2.03 기능 요구사항\n\n머리말.\n\n"
    "## ORC 오케스트레이터\n\no1\n\n"
    "## RAIL 훅\n\nr1\n\n"
    "## TRL 트레일러\n\nt1\n\n"
    "## BL backlog\n\nl1\n"
)
FILES = {
    "design/00-문서-정보.md": DOC,
    "design/3-아키텍처-설계서/03-컴포넌트-명세.md": COMPONENTS_DOC,
    "design/2-요구사항-명세서/03-기능-요구사항.md": REQUIREMENTS_DOC,
    "design/부록-용어집.md": "# 부록 용어집\n\n- 용어\n",
    "design/diagrams/a.dot": "digraph { a -> b }\n",
}
ARCH = "design/3-아키텍처-설계서/03-컴포넌트-명세.md"
REQ = "design/2-요구사항-명세서/03-기능-요구사항.md"
DONE = "backlog task edit TASK-16 -s Done"


def git(cwd, *args):
    result = subprocess.run(
        [
            "git",
            "-c", "user.name=t",
            "-c", "user.email=t@example.com",
            "-c", "commit.gpgsign=false",
            "-c", "tag.gpgsign=false",
            "-c", "core.hooksPath=/dev/null",
            "-C", str(cwd),
            *args,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


class Repo:
    def __init__(self, path, files=None, branch="main"):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        git(path, "init", "-q", "-b", branch)
        for rel, text in (files or {}).items():
            self.write(rel, text)
        self.commit("init", allow_empty=True)

    def write(self, rel, text):
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def read(self, rel):
        return (self.path / rel).read_text()

    def replace(self, rel, old, new):
        text = self.read(rel)
        assert old in text
        self.write(rel, text.replace(old, new, 1))

    def commit(self, *messages, allow_empty=False):
        git(self.path, "add", "-A")
        args = ["commit", "-q"]
        if allow_empty:
            args.append("--allow-empty")
        for m in messages:
            args += ["-m", m]
        git(self.path, *args)
        return git(self.path, "rev-parse", "HEAD").strip()

    def checkout(self, *args):
        git(self.path, "checkout", "-q", *args)


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch):
    for name in GIT_ISOLATION:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def top(tmp_path):
    """Top-level repo on task/task-16, branched from main after the design
    docs were committed."""
    repo = Repo(tmp_path / "top", dict(FILES, **{".gitignore": "components/\n"}))
    repo.checkout("-b", "task/task-16")
    return repo


def component(top, name, *messages, branch=None):
    repo = Repo(top.path / "components" / name, {"design/00.md": "x\n"})
    if branch:
        repo.checkout("-b", branch)
    if messages:
        repo.commit(*messages, allow_empty=True)
    return repo


def all_components(top, task="TASK-16"):
    for name in COMPONENTS:
        component(top, name, f"X-1: 전파", f"Refs: coralstay-software-factory {task}")


def run_hook(monkeypatch, cwd, command=DONE, tool="Bash"):
    payload = {"cwd": str(cwd), "tool_name": tool, "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rdp.main()
    return exc_info.value.code


def denied(monkeypatch, capsys, cwd, command=DONE):
    code = run_hook(monkeypatch, cwd, command)
    err = capsys.readouterr().err
    assert code == 2, err
    return err


def missing_in(err):
    """Component names listed as missing in a deny message."""
    return sorted(
        name for name in COMPONENTS if f"  - {name} " in err or f"  - {name}\n" in err
    )


# --- AC #4: Done of the top-level task needs propagation per component ---


def test_section_change_denies_only_the_mapped_component(top, monkeypatch, capsys):
    """TASK-63#4: 3.03 §2 -> claude-code-agile-hooks only; the message names
    the chapter, the missing repo and both ways out."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    err = denied(monkeypatch, capsys, top.path)
    assert err.startswith("[claude-code-agile-hooks]")
    assert missing_in(err) == ["claude-code-agile-hooks"]
    assert "3.03 §2" in err
    assert "components/claude-code-agile-hooks 저장소가 없습니다" in err
    assert "Refs: coralstay-software-factory TASK-16" in err
    assert "Propagation-None: claude-code-agile-hooks: <사유>" in err
    assert "--allow-empty" in err


def test_refs_commit_on_any_component_branch_passes(top, monkeypatch):
    """TASK-63#4: a 'Refs: coralstay-software-factory <ID>' commit on any
    branch of components/<name> counts."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    repo = component(
        top,
        "claude-code-agile-hooks",
        "TASK-70: 3.03 반영",
        "Refs: coralstay-software-factory TASK-16",
        branch="task/TASK-70",
    )
    repo.checkout("main")
    assert run_hook(monkeypatch, top.path) == 0


@pytest.mark.parametrize(
    "refs, ok",
    [
        ("Refs: coralstay-software-factory task-16", True),
        ("refs: Coralstay-Software-Factory TASK-16.", True),
        ("Refs: coralstay-software-factory TASK-15, TASK-16", True),
        ("Refs: coralstay-software-factory TASK-1", False),
        ("Refs: coralstay-software-factory TASK-160", False),
        ("Refs: coralstay-software-factory TASK-16.1", False),
        ("Refs: coralstay-software-factory XTASK-16", False),
        ("Refs: other-repo TASK-16", False),
        ("본문에 coralstay-software-factory TASK-16을 적었을 뿐", False),
    ],
)
def test_refs_line_matching(top, monkeypatch, refs, ok):
    """TASK-63#4: the ID matches case-insensitively and word-bounded."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    component(top, "claude-code-agile-hooks", "X-1: 반영", refs)
    assert (run_hook(monkeypatch, top.path) == 0) is ok


def test_propagation_none_trailer_passes(top, monkeypatch):
    """TASK-63#4: an empty commit with the trailer is enough."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    top.commit(
        "TASK-16: 전파 영향 없음 기록",
        "Propagation-None: claude-code-agile-hooks: 문구만 고쳤다",
        allow_empty=True,
    )
    assert run_hook(monkeypatch, top.path) == 0


@pytest.mark.parametrize(
    "trailer",
    [
        "Propagation-None: claude-code-agile-hooks:",
        "Propagation-None: claude-code-agile-hooks",
        "Propagation-None: agent-orchestrator: 영향 없음",
    ],
)
def test_trailer_needs_the_component_and_a_reason(top, monkeypatch, capsys, trailer):
    """TASK-63#4"""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    top.commit("TASK-16: 기록", trailer, allow_empty=True)
    assert missing_in(denied(monkeypatch, capsys, top.path)) == [
        "claude-code-agile-hooks"
    ]


def test_trailer_must_be_a_trailer_not_body_text(top, monkeypatch, capsys):
    """TASK-63#4: git's trailer parser decides - a line in the middle of the
    body is not a trailer."""
    top.replace(ARCH, "b1", "b2")
    top.commit(
        "TASK-16: §2 수정",
        "Propagation-None: claude-code-agile-hooks: 이유\n본문이 이어진다",
        "마지막 문단",
    )
    assert missing_in(denied(monkeypatch, capsys, top.path)) == [
        "claude-code-agile-hooks"
    ]


def test_chapter_head_change_counts_for_every_row(top, monkeypatch, capsys):
    """TASK-63#4: outside every listed section -> all rows of the chapter."""
    top.replace(ARCH, "머리말.", "머리말 고침.")
    top.commit("TASK-16: 머리 수정")
    assert missing_in(denied(monkeypatch, capsys, top.path)) == COMPONENTS


def test_unlisted_section_counts_for_every_row(top, monkeypatch, capsys):
    """TASK-63#4: `## 원천` is outside the §n rows."""
    top.replace(ARCH, "e1", "e2")
    top.commit("TASK-16: 원천 수정")
    assert missing_in(denied(monkeypatch, capsys, top.path)) == COMPONENTS


def test_heading_inside_fence_is_not_a_section(top, monkeypatch, capsys):
    """TASK-63#4: f1 sits after a fenced '## §2' but inside §4."""
    top.replace(ARCH, "f1", "f2")
    top.commit("TASK-16: §4 수정")
    assert missing_in(denied(monkeypatch, capsys, top.path)) == [
        "agent-orchestrator",
        "claude-code-agile-hooks",
    ]


@pytest.mark.parametrize(
    "old, new, expected",
    [
        ("r1", "r2", ["claude-code-agile-hooks"]),
        ("t1", "t2", ["coding-agent-git-commit-tool"]),
        ("l1", "l2", ["agent-orchestrator", "claude-code-agile-hooks"]),
        ("o1", "o2", ["agent-orchestrator"]),
    ],
)
def test_area_prefix_sections(top, monkeypatch, capsys, old, new, expected):
    """TASK-63#4: 2.03 sections map by area prefix."""
    top.replace(REQ, old, new)
    top.commit("TASK-16: 2.03 수정")
    assert missing_in(denied(monkeypatch, capsys, top.path)) == expected


def test_deletion_maps_through_the_old_file(top, monkeypatch, capsys):
    """TASK-63#4: removed lines are placed by the parent's headings."""
    top.replace(ARCH, "c1\nc2\n", "")
    top.commit("TASK-16: §3 줄 삭제")
    assert missing_in(denied(monkeypatch, capsys, top.path)) == [
        "coding-agent-git-commit-tool"
    ]


def test_deleted_file_counts_every_row_of_its_sections(top, monkeypatch, capsys):
    """TASK-63#4"""
    os.remove(top.path / "design/부록-용어집.md")
    top.commit("TASK-16: 용어집 삭제")
    assert missing_in(denied(monkeypatch, capsys, top.path)) == COMPONENTS


def test_whole_chapter_row_and_new_file(top, monkeypatch, capsys):
    """TASK-63#4: a 전체 row; a new chapter file is mapped too."""
    top.write("design/5-구현-결과-보고서/01-개요.md", "# 5.01\n\n## §1 x\n\ny\n")
    top.commit("TASK-16: 5.01 추가")
    err = denied(monkeypatch, capsys, top.path)
    assert missing_in(err) == COMPONENTS
    assert "5.01" in err


def test_all_components_propagated_passes(top, monkeypatch):
    """TASK-63#4"""
    top.replace(ARCH, "머리말.", "머리말 고침.")
    top.commit("TASK-16: 머리 수정")
    all_components(top)
    assert run_hook(monkeypatch, top.path) == 0


def test_mixed_refs_and_trailer(top, monkeypatch, capsys):
    """TASK-63#4: each component is satisfied on its own."""
    top.replace(ARCH, "머리말.", "머리말 고침.")
    top.commit(
        "TASK-16: 머리 수정",
        "Propagation-None: coding-agent-git-commit-tool: 해당 없음",
    )
    component(top, "agent-orchestrator", "AO-1: 반영", "Refs: coralstay-software-factory TASK-16")
    err = denied(monkeypatch, capsys, top.path)
    assert missing_in(err) == ["claude-code-agile-hooks"]


def test_component_dir_that_is_not_a_repo_is_missing(top, monkeypatch, capsys):
    """TASK-63#4: components/<name> must be its own git repo (else git would
    read the top-level repo)."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정", "Refs: coralstay-software-factory TASK-16")
    (top.path / "components" / "claude-code-agile-hooks").mkdir(parents=True)
    err = denied(monkeypatch, capsys, top.path)
    assert "components/claude-code-agile-hooks 저장소가 없습니다" in err


def test_unmapped_design_files_are_ignored(top, monkeypatch):
    """TASK-63#4: diagrams and other files outside the map don't trigger."""
    top.write("design/diagrams/a.dot", "digraph { a -> c }\n")
    top.write("design/9-없는-문서/01-x.md", "# x\n")
    top.commit("TASK-16: 다이어그램")
    assert run_hook(monkeypatch, top.path) == 0


def test_no_design_change_passes(top, monkeypatch):
    """TASK-63#4"""
    top.write("src/a.py", "x = 1\n")
    top.commit("TASK-16: 코드")
    assert run_hook(monkeypatch, top.path) == 0


def test_commits_already_on_main_are_not_counted(top, monkeypatch):
    """TASK-63#4: only commits on the task branch since the base count."""
    top.checkout("main")
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-15: §2 수정")
    top.checkout("task/task-16")
    git(top.path, "merge", "-q", "--no-edit", "main")
    assert run_hook(monkeypatch, top.path) == 0


def test_uncommitted_design_changes_are_not_counted(top, monkeypatch):
    """TASK-63#4: committed changes only (stage commits come first)."""
    top.replace(ARCH, "b1", "b2")
    git(top.path, "add", "-A")
    top.replace(ARCH, "c1", "c9")
    assert run_hook(monkeypatch, top.path) == 0


def test_origin_head_is_a_base(top, monkeypatch):
    """TASK-63#4: with no local main/master, the remote default branch is
    the base."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    main_sha = git(top.path, "rev-parse", "main").strip()
    git(top.path, "update-ref", "refs/remotes/origin/trunk", main_sha)
    git(top.path, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    git(top.path, "branch", "-q", "-D", "main")
    assert rdp.base_refs(str(top.path)) == ["refs/remotes/origin/trunk"]
    assert run_hook(monkeypatch, top.path) == 2


def test_master_is_a_base(tmp_path, monkeypatch, capsys):
    """TASK-63#4"""
    repo = Repo(tmp_path / "top", FILES, branch="master")
    repo.checkout("-b", "task/task-16")
    repo.replace(ARCH, "b1", "b2")
    repo.commit("TASK-16: §2 수정")
    assert missing_in(denied(monkeypatch, capsys, repo.path)) == [
        "claude-code-agile-hooks"
    ]


def test_no_base_branch_passes(tmp_path, monkeypatch):
    """TASK-63#4: no main/master/origin HEAD -> the range is unknown, pass."""
    repo = Repo(tmp_path / "top", FILES, branch="task/task-16")
    repo.replace(ARCH, "b1", "b2")
    repo.commit("TASK-16: §2 수정")
    assert run_hook(monkeypatch, repo.path) == 0


def test_numeric_and_lowercase_targets(top, monkeypatch):
    """TASK-63#4: `16`, `task-16` and `TASK-16` name the branch's task."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    for target in ("16", "task-16", "TASK-16"):
        assert run_hook(monkeypatch, top.path, f"backlog task edit {target} -s Done") == 2


def test_done_from_another_branch_finds_the_task_branch(top, monkeypatch, capsys):
    """TASK-63#4: on main, the local task/<ID> branch is checked."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    top.checkout("main")
    assert missing_in(denied(monkeypatch, capsys, top.path)) == [
        "claude-code-agile-hooks"
    ]


def test_done_of_a_task_without_branch_passes(top, monkeypatch):
    """TASK-63#4: no task/<ID> branch -> nothing to check."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    assert run_hook(monkeypatch, top.path, "backlog task edit TASK-99 -s Done") == 0


def test_merge_commits_are_skipped(top, monkeypatch):
    """TASK-63#4: a merge of a side branch is not diffed itself."""
    top.checkout("-b", "side")
    top.write("notes.txt", "n\n")
    top.commit("side")
    top.checkout("task/task-16")
    top.write("other.txt", "o\n")
    top.commit("TASK-16: other")
    git(top.path, "merge", "-q", "--no-ff", "--no-edit", "side")
    git(top.path, "branch", "-q", "-D", "side")
    assert run_hook(monkeypatch, top.path) == 0


def test_malformed_table_denies_the_done_move(top, monkeypatch, capsys):
    """TASK-63#4: a broken map is reported, not skipped."""
    top.replace("design/00-문서-정보.md", "| 1.02 | 전체 |", "| 1.02 | 절반 |")
    top.commit("TASK-16: 표 깨짐")
    err = denied(monkeypatch, capsys, top.path)
    assert "장 대응표" in err
    assert "범위" in err


def test_subdirectory_cwd_uses_the_repo_root(top, monkeypatch, capsys):
    """TASK-63#4"""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    assert missing_in(denied(monkeypatch, capsys, top.path / "design")) == [
        "claude-code-agile-hooks"
    ]


@pytest.mark.parametrize(
    "command",
    [
        "backlog task edit TASK-16 -s 'In Progress'",
        "echo backlog task edit TASK-16 -s Done",
        "git commit -m 'backlog task edit TASK-16 -s Done'",
        "ls",
    ],
)
def test_other_commands_pass(top, monkeypatch, command):
    """TASK-63#4: only a command-position Done move triggers."""
    top.replace(ARCH, "b1", "b2")
    top.commit("TASK-16: §2 수정")
    assert run_hook(monkeypatch, top.path, command) == 0


def test_other_tools_and_bad_input_pass(top, monkeypatch):
    """TASK-63#4"""
    assert run_hook(monkeypatch, top.path, tool="Edit") == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        rdp.main()
    assert exc_info.value.code == 0
    payload = {"cwd": str(top.path), "tool_name": "Bash", "tool_input": "x"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rdp.main()
    assert exc_info.value.code == 0


def test_origin_head_pointing_at_main_is_listed_once(top):
    """TASK-63#4"""
    main_sha = git(top.path, "rev-parse", "main").strip()
    git(top.path, "update-ref", "refs/remotes/origin/main", main_sha)
    git(top.path, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    assert rdp.base_refs(str(top.path)) == ["refs/remotes/origin/main", "refs/heads/main"]


# --- copied Done detection (REGISTRY keeps it identical to require_test_first) ---


@pytest.mark.parametrize(
    "command, expected",
    [
        ("backlog task edit TASK-16 -s Done", ["TASK-16"]),
        ("backlog task edit TASK-16 --status=done", ["TASK-16"]),
        ("sudo -E backlog tasks edit 16 --status DONE", ["16"]),
        ("X=1 backlog task edit TASK-16 --plain -s Done", ["TASK-16"]),
        ("backlog task edit TASK-16 -s", []),
        ("backlog task edit -s Done", []),
        ("backlog task view TASK-16", []),
        ("backlog", []),
        ("sudo -E", []),
        ("", []),
        ("cat <<EOF\nbacklog task edit TASK-16 -s Done\nEOF\nls", []),
        ("cat <<EOF\nx\nEOF\nbacklog task edit TASK-16 -s Done", ["TASK-16"]),
        ("backlog task edit TASK-16 -s Done 'unbalanced", ["TASK-16"]),
    ],
)
def test_done_targets(command, expected):
    """TASK-63#4: only a command-position Done move is a trigger."""
    assert rdp.done_targets(command) == expected


def test_same_task():
    """TASK-63#4"""
    assert rdp.same_task("task-16", "TASK-16")
    assert rdp.same_task("16", "task-16")
    assert not rdp.same_task("1", "task-16")
    assert not rdp.same_task("TASK-1", "TASK-16")
