"""Tests for scripts/work_order.py (TASK-60#1).

The script reads incomplete tasks' `dependencies` from backlog/tasks/*.md
frontmatter, sorts them into levels (same level = parallel, levels =
sequential) and writes backlog/work-order.md headed by the input hash.
"""

import os
import subprocess
import sys

import pytest

import work_order as wo

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work_order.py")


def write_task(root, task_id, title="t", status="To Do", deps=None, raw_deps=None):
    tasks = root / "backlog" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    if raw_deps is None:
        if deps:
            raw_deps = "dependencies:\n" + "".join(f"  - {d}\n" for d in deps)
        else:
            raw_deps = "dependencies: []\n"
    (tasks / f"{task_id.lower()} - {title}.md").write_text(
        "---\n"
        f"id: {task_id}\n"
        f"title: {title}\n"
        f"status: {status}\n"
        "labels: []\n"
        f"{raw_deps}"
        "---\n\n## Description\n\nbody\n"
    )


@pytest.fixture
def project(tmp_path):
    os.mkdir(tmp_path / ".git")
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("project_name: x\n")
    (tmp_path / "backlog" / "tasks").mkdir()
    return tmp_path


def work_order_text(project):
    return (project / "backlog" / "work-order.md").read_text()


# --- frontmatter parsing ---------------------------------------------------


def test_parse_frontmatter_block_and_inline_lists_task_60_1():
    """TASK-60#1: dependencies as a YAML block list, inline list or empty list."""
    fm = wo.parse_frontmatter(
        "---\nid: TASK-3\ntitle: 'It''s C'\ndependencies:\n  - TASK-1\n  - task-2\n"
        "labels: [a, \"b\"]\nempty: []\n---\nbody: not frontmatter\n"
    )
    assert fm["id"] == "TASK-3"
    assert fm["title"] == "It's C"
    assert fm["dependencies"] == ["TASK-1", "task-2"]
    assert fm["labels"] == ["a", "b"]
    assert fm["empty"] == []
    assert "body" not in fm


def test_parse_frontmatter_folded_scalar_and_junk_task_60_1():
    fm = wo.parse_frontmatter(
        "---\n  stray indented line\ntitle: >-\n  long\n  title\nrefs:\n  - >-\n"
        "    folded item\n-\n---\n"
    )
    assert fm["title"] == "long title"
    assert fm["refs"] == [">-", ""]


def test_parse_frontmatter_without_frontmatter_task_60_1():
    assert wo.parse_frontmatter("# just markdown\n") == {}
    assert wo.parse_frontmatter("") == {}


def test_parse_frontmatter_unclosed_block_reads_to_end_task_60_1():
    assert wo.parse_frontmatter("---\nid: TASK-1") == {"id": "TASK-1"}


def test_parse_task_normalizes_ids_and_deps_task_60_1():
    task = wo.parse_task(
        "---\nid: task-7\ntitle: Seven\nstatus: In Progress\n"
        "dependencies: [task-2, TASK-1, TASK-2]\n---\n"
    )
    assert task == {
        "id": "TASK-7",
        "title": "Seven",
        "status": "In Progress",
        "deps": ["TASK-1", "TASK-2"],
    }


def test_parse_task_single_string_dep_and_missing_fields_task_60_1():
    task = wo.parse_task("---\nid: TASK-1\ndependencies: TASK-9\n---\n")
    assert task == {"id": "TASK-1", "title": "", "status": "", "deps": ["TASK-9"]}
    assert wo.parse_task("---\ntitle: no id\n---\n") is None


def test_natural_key_orders_numbers_numerically_task_60_1():
    ids = ["TASK-10", "TASK-2", "TASK-1", "OTHER-3", "TASK-2.1"]
    assert sorted(ids, key=wo.natural_key) == [
        "OTHER-3",
        "TASK-1",
        "TASK-2",
        "TASK-2.1",
        "TASK-10",
    ]


# --- reading tasks / hash ----------------------------------------------------


def test_read_tasks_skips_non_md_and_unparsable_task_60_1(project):
    write_task(project, "TASK-1")
    (project / "backlog" / "tasks" / "notes.txt").write_text("x")
    (project / "backlog" / "tasks" / "broken.md").write_text("no frontmatter")
    assert list(wo.read_tasks(str(project))) == ["TASK-1"]


def test_read_tasks_without_tasks_dir_task_60_1(tmp_path):
    assert wo.read_tasks(str(tmp_path)) == {}


def test_incomplete_tasks_excludes_done_case_insensitively_task_60_1():
    tasks = {
        "TASK-1": {"id": "TASK-1", "title": "", "status": "Done", "deps": []},
        "TASK-2": {"id": "TASK-2", "title": "", "status": " done ", "deps": []},
        "TASK-3": {"id": "TASK-3", "title": "", "status": "To Do", "deps": []},
    }
    assert list(wo.incomplete_tasks(tasks)) == ["TASK-3"]


def test_input_hash_depends_on_id_set_and_deps_only_task_60_1():
    """TASK-60#1: the hash covers the incomplete task ID set + their deps -
    not titles, not order, not timestamps."""
    a = {"TASK-1": {"id": "TASK-1", "title": "A", "status": "To Do", "deps": []}}
    b = {"TASK-1": {"id": "TASK-1", "title": "renamed", "status": "In Progress", "deps": []}}
    c = {"TASK-1": {"id": "TASK-1", "title": "A", "status": "To Do", "deps": ["TASK-9"]}}
    d = dict(a, **{"TASK-2": {"id": "TASK-2", "title": "", "status": "", "deps": []}})
    assert wo.input_hash(a) == wo.input_hash(b)
    assert wo.input_hash(a) != wo.input_hash(c)
    assert wo.input_hash(a) != wo.input_hash(d)
    assert len(wo.input_hash({})) == 64


# --- levels / cycles -----------------------------------------------------------


def node(task_id, deps=(), title="t"):
    return {"id": task_id, "title": title, "status": "To Do", "deps": list(deps)}


def test_compute_levels_parallel_and_sequential_task_60_1():
    tasks = {
        t["id"]: t
        for t in [
            node("TASK-1"),
            node("TASK-10"),
            node("TASK-2", ["TASK-1"]),
            node("TASK-3", ["TASK-1", "TASK-2"]),
            node("TASK-4", ["TASK-10"]),
        ]
    }
    assert wo.compute_levels(tasks) == [
        ["TASK-1", "TASK-10"],
        ["TASK-2", "TASK-4"],
        ["TASK-3"],
    ]


def test_compute_levels_deps_outside_the_set_are_satisfied_task_60_1():
    """TASK-60#1: deps on Done or absent tasks don't hold anything back."""
    tasks = {"TASK-5": node("TASK-5", ["TASK-1", "TASK-404"])}
    assert wo.compute_levels(tasks) == [["TASK-5"]]


def test_compute_levels_empty_task_60_1():
    assert wo.compute_levels({}) == []


def test_compute_levels_raises_on_cycle_with_cycle_listed_task_60_1():
    tasks = {
        t["id"]: t
        for t in [
            node("TASK-1"),
            node("TASK-2", ["TASK-4"]),
            node("TASK-3", ["TASK-2"]),
            node("TASK-4", ["TASK-3"]),
            node("TASK-5", ["TASK-4"]),
        ]
    }
    with pytest.raises(wo.CycleError) as exc_info:
        wo.compute_levels(tasks)
    assert exc_info.value.cycle == ["TASK-2", "TASK-4", "TASK-3", "TASK-2"]


def test_compute_levels_self_dependency_is_a_cycle_task_60_1():
    with pytest.raises(wo.CycleError) as exc_info:
        wo.compute_levels({"TASK-1": node("TASK-1", ["TASK-1"])})
    assert exc_info.value.cycle == ["TASK-1", "TASK-1"]


# --- rendering -------------------------------------------------------------------


def test_render_header_hash_and_level_table_task_60_1():
    tasks = {
        "TASK-1": node("TASK-1", title="A | pipe"),
        "TASK-2": node("TASK-2", ["TASK-1"], title="B"),
        "TASK-3": node("TASK-3", ["TASK-1", "TASK-77"], title="C"),
    }
    all_ids = set(tasks)
    text = wo.render(tasks, all_ids)
    lines = text.splitlines()
    assert lines[0] == f"<!-- work-order-hash: {wo.input_hash(tasks)} -->"
    assert "| 단계 | ID | 제목 |" in lines
    rows = [line for line in lines if line.startswith("| ") and "TASK-" in line]
    assert rows == [
        "| 1 | TASK-1 | A \\| pipe |",
        "| 2 | TASK-2 | B |",
        "| 2 | TASK-3 | C |",
    ]
    assert "TASK-77" in text  # absent dependency is reported
    assert text.endswith("\n")


def test_render_without_incomplete_tasks_task_60_1():
    text = wo.render({}, set())
    assert text.splitlines()[0] == f"<!-- work-order-hash: {wo.input_hash({})} -->"
    assert "미완료 태스크가 없습니다" in text
    assert "충족으로 간주" not in text


def test_hash_header_regex_reads_back_rendered_hash_task_60_1():
    tasks = {"TASK-1": node("TASK-1")}
    m = wo.HASH_RE.search(wo.render(tasks, set(tasks)))
    assert m and m.group(1) == wo.input_hash(tasks)


# --- CLI ------------------------------------------------------------------------


def test_main_writes_deterministic_work_order_task_60_1(project, capsys):
    write_task(project, "TASK-1", "A", status="Done")
    write_task(project, "TASK-2", "B", deps=["TASK-1"])
    write_task(project, "TASK-3", "C", deps=["TASK-2"])
    write_task(project, "TASK-4", "D")
    assert wo.main([str(project)]) == 0
    first = work_order_text(project)
    assert "| 1 | TASK-2 | B |" in first
    assert "| 1 | TASK-4 | D |" in first
    assert "| 2 | TASK-3 | C |" in first
    assert "TASK-1 |" not in first  # Done tasks are not listed
    assert "work-order.md" in capsys.readouterr().out
    assert wo.main([str(project)]) == 0
    assert work_order_text(project) == first


def test_main_defaults_to_cwd_task_60_1(project, monkeypatch):
    write_task(project, "TASK-1")
    monkeypatch.chdir(project)
    assert wo.main([]) == 0
    assert "| 1 | TASK-1 | t |" in work_order_text(project)


def test_main_cycle_fails_and_writes_nothing_task_60_1(project, capsys):
    write_task(project, "TASK-1", deps=["TASK-2"])
    write_task(project, "TASK-2", deps=["TASK-1"])
    assert wo.main([str(project)]) == 1
    err = capsys.readouterr().err
    assert "TASK-1 -> TASK-2 -> TASK-1" in err
    assert not (project / "backlog" / "work-order.md").exists()


def test_main_cycle_keeps_existing_file_untouched_task_60_1(project):
    (project / "backlog" / "work-order.md").write_text("old\n")
    write_task(project, "TASK-1", deps=["TASK-1"])
    assert wo.main([str(project)]) == 1
    assert work_order_text(project) == "old\n"


def test_main_rejects_non_backlog_dir_task_60_1(tmp_path, capsys):
    assert wo.main([str(tmp_path)]) == 1
    assert "backlog" in capsys.readouterr().err


def test_main_rejects_extra_args_task_60_1(project, capsys):
    assert wo.main([str(project), "extra"]) == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_script_runs_as_cli_task_60_1(project):
    write_task(project, "TASK-1")
    result = subprocess.run(
        [sys.executable, SCRIPT, str(project)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert (project / "backlog" / "work-order.md").is_file()


@pytest.mark.parametrize("flag", ["-h", "--help", "help"])
def test_main_help_prints_usage_and_returns_zero_task_71_1(flag, capsys):
    """TASK-71#1: -h · --help · help print the usage to stdout and exit 0."""
    assert wo.main([flag]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("사용법 (Usage): work-order [project_dir]\n")
    assert "backlog/work-order.md" in captured.out
    assert captured.err == ""
