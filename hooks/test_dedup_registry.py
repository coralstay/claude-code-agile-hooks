"""Drift-prevention test for `is_backlog_project()`.

The hooks below (originally five) are each fully self-contained (no shared imports, by
design — see require_active_task.py's module docstring), so the
`is_backlog_project()` check is hand-copied into every one of them. That's
exactly how the 2026-09-18 bug happened: the `.git`-existence check landed in
require_active_task.py but never propagated to the other four copies.

This test extracts the `is_backlog_project` function's AST from every hook
module, normalizes away location metadata, and asserts all copies are
identical. If someone patches only one copy in the future, this test fails.
"""

import ast
import os

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))

MODULES = [
    "require_active_task.py",
    "pre_commit_check.py",
    "pre_push_check.py",
    "block_stop_if_dirty.py",
    "session_start.py",
    "require_draft_first.py",
]


def _function_ast_dump(path, function_name):
    with open(path) as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.dump(node, annotate_fields=False, include_attributes=False)
    raise AssertionError(f"{function_name}() not found in {path}")


def test_is_backlog_project_identical_across_all_hooks():
    dumps = {}
    for module in MODULES:
        path = os.path.join(HOOKS_DIR, module)
        dumps[module] = _function_ast_dump(path, "is_backlog_project")

    baseline_module = MODULES[0]
    baseline = dumps[baseline_module]

    mismatched = [module for module, dump in dumps.items() if dump != baseline]

    assert not mismatched, (
        "is_backlog_project() has drifted out of sync across hooks. "
        f"{baseline_module} disagrees with: {mismatched}. "
        "Every self-contained hook copy must apply the same fix together "
        "(see decision-2 in this repo's backlog for the 2026-09-10 story)."
    )
