# ---
# title: test_workflow_guide_owner
# description: 워크플로 안내문과 README에 저장소별 담당 규칙(workspace owner로 확인, claude 담당이 아니면 편집 · 커밋하지 않음)이 담당 표 복사 없이 있는지 검증하는 테스트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# task: TASK-78
# created_date: '2026-11-26'
# updated_date: '2026-11-26'
# ---
# TASK-78: 워크플로 안내문에 저장소별 담당 규칙 한 줄 — Claude 담당이 아닌 저장소는 편집하지 않는다
#
# The owner table lives in dev-toolchain workspace/repos.tsv (decision-25).
# The guide and README only point at the lookup command, so these tests check
# the rule's wording and that no repository row was copied into the guide.
import os

import session_start as ss

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HOOKS_DIR)
GUIDE = os.path.join(HOOKS_DIR, "workflow_guide.md")
README = os.path.join(REPO_ROOT, "README.md")
MAX_GUIDE_LINES = 30

OWNER_COMMAND = "`dev-toolchain workspace owner <경로>`"
# Stems shared by the guide (한다) and README (합니다).
OWNER_RULE_PHRASES = (
    "저장소마다 담당 에이전트",
    "`claude`",
    "편집 · 커밋하지 않",
    "읽기 · 보고만",
    "`unknown`",
)
# Repositories owned by someone other than this Claude session - if any of
# them shows up in the guide, the table was copied instead of pointed at.
OTHER_OWNERS_REPOS = (
    "central-docs-collector",
    "omnivim",
    "freeride",
    "handcrafted-python",
    "doctree",
    "ebpf-wire-to-code-tracer",
    "toy-project",
)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def guide_body():
    return ss.strip_frontmatter(read(GUIDE))


# == AC/DoD ==


def test_guide_states_the_owner_rule():
    """TASK-78#1: the guide names the lookup command, says a repo not owned by
    claude is only read and reported on, and that unknown means asking."""
    body = guide_body()
    assert OWNER_COMMAND in body
    for phrase in OWNER_RULE_PHRASES:
        assert phrase in body, phrase
    line = next(l for l in body.splitlines() if OWNER_COMMAND in l)
    assert "유저에게 묻" in line


def test_guide_points_at_the_command_not_the_table():
    """TASK-78#1 TASK-78#B1: no repository of another owner and no repos.tsv
    row is copied into the guide - repos.tsv stays the single source."""
    body = guide_body()
    for repo in OTHER_OWNERS_REPOS:
        assert repo not in body, repo
    assert "\tantigravity" not in body
    assert "\tclaude-other" not in body


def test_guide_keeps_its_line_cap():
    """TASK-78#1 TASK-78#B2: the new line does not push the guide over 30 lines."""
    assert 0 < len(guide_body().splitlines()) <= MAX_GUIDE_LINES


def test_readme_carries_the_same_owner_rule():
    """TASK-78#2: README (the SSOT) has the same command and rule, plus where
    the owner table lives."""
    readme = read(README)
    assert OWNER_COMMAND in readme
    for phrase in OWNER_RULE_PHRASES:
        assert phrase in readme, phrase
    assert "repos.tsv" in readme
    assert "decision-25" in readme


# == Coverage ==
