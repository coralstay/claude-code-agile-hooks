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
