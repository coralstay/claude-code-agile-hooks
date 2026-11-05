# TASK-61: 테스트 파일 구조(헤더 → AC/DoD → Coverage)를 강제하는 require_test_layout.py
import io
import json
import os
import re

import pytest

import dedup_drift_guard as ddg
import require_test_layout as rtl

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def project(tmp_path):
    """A fake backlog.md project (no testFirst config)."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "backlog").mkdir()
    (tmp_path / "backlog" / "config.yml").write_text("x")
    return tmp_path


def put(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def write(root, rel, content):
    return {
        "cwd": str(root),
        "tool_name": "Write",
        "tool_input": {"file_path": os.path.join(str(root), rel), "content": content},
    }


def edit(root, rel, old, new, replace_all=False):
    tool_input = {
        "file_path": os.path.join(str(root), rel),
        "old_string": old,
        "new_string": new,
    }
    if replace_all:
        tool_input["replace_all"] = True
    return {"cwd": str(root), "tool_name": "Edit", "tool_input": tool_input}


def run(monkeypatch, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rtl.main()
    return exc_info.value.code


def py(*lines):
    return "\n".join(lines) + "\n"


SECTIONS_PY = ["# == AC/DoD ==", "def test_a(): pass", "# == Coverage ==", "def test_b(): pass"]
SECTIONS_C = ["// == AC/DoD ==", "test('a', () => {});", "// == Coverage ==", "test('b', () => {});"]

# == AC/DoD ==

# --- TASK-61#1: the first comment block names the task(s) ---


@pytest.mark.parametrize(
    "rel, header",
    [
        ("tests/test_router.py", "# TASK-61: 라우터 테스트"),
        ("tests/router_test.py", "# TASK-61: 라우터 테스트"),
        ("web/router.test.ts", "// TASK-61: 라우터 테스트"),
        ("web/router.spec.jsx", "// TASK-61: 라우터 테스트"),
        ("web/router.test.mjs", "// TASK-61: 라우터 테스트"),
        ("src/test/java/RouterTest.java", "// TASK-61: 라우터 테스트"),
        ("src/test/java/RouterTests.java", "// TASK-61: 라우터 테스트"),
        ("cpp/router_test.cc", "// TASK-61: 라우터 테스트"),
        ("cpp/test_router.cpp", "// TASK-61: 라우터 테스트"),
    ],
)
def test_task61_1_new_test_file_with_header_is_allowed(project, monkeypatch, rel, header):
    """TASK-61#1: a new test file in each of the five languages passes with
    its header."""
    body = SECTIONS_PY if rel.endswith(".py") else SECTIONS_C
    assert run(monkeypatch, write(project, rel, py(header, *body))) == 0


@pytest.mark.parametrize(
    "rel, content",
    [
        ("tests/test_router.py", py("import os", *SECTIONS_PY)),
        ("tests/test_router.py", py("# 라우터 테스트", *SECTIONS_PY)),
        ("tests/test_router.py", py('"""TASK-61: docstring is not a comment"""', *SECTIONS_PY)),
        ("tests/test_router.py", py("# TASK-61:", *SECTIONS_PY)),
        ("tests/test_router.py", py("import os", "# TASK-61: too late", *SECTIONS_PY)),
        ("web/router.test.ts", py("import x from 'y';", *SECTIONS_C)),
        ("web/router.test.ts", py("# TASK-61: wrong comment syntax", *SECTIONS_C)),
        ("src/test/java/RouterTest.java", py("package a;", *SECTIONS_C)),
        ("cpp/router_test.cpp", py("#include <x>", *SECTIONS_C)),
    ],
)
def test_task61_1_new_test_file_without_header_is_denied(
    project, monkeypatch, capsys, rel, content
):
    """TASK-61#1: no `<ID>: <summary>` line in the first comment block ->
    deny, with the expected layout in the message."""
    assert run(monkeypatch, write(project, rel, content)) == 2
    err = capsys.readouterr().err
    assert err.startswith("[claude-code-agile-hooks]")
    assert "<ID>: <한 줄 요약>" in err
    assert "== AC/DoD ==" in err


def test_task61_1_one_header_line_per_task_and_extra_comment_lines(project, monkeypatch):
    """TASK-61#1: several tasks each get a line; other comment lines in the
    block are allowed."""
    content = py("#!/usr/bin/env python3", "# TASK-56: 테스트 먼저", "# TASK-61: 구조", "# 메모", *SECTIONS_PY)
    assert run(monkeypatch, write(project, "test_x.py", content)) == 0


def test_task61_1_block_comment_header_for_c_family(project, monkeypatch):
    """TASK-61#1: JS/TS/Java/C++ may use one leading /* ... */ block."""
    for header in (
        ["/*", " * TASK-61: 블록 주석 헤더", " */"],
        ["/* TASK-61: 한 줄 블록 */"],
        ["#!/usr/bin/env node", "/**", " * 메모", " * TASK-61: 셔뱅 뒤 */"],
    ):
        assert run(monkeypatch, write(project, "a.test.js", py(*header, *SECTIONS_C))) == 0
    bad = py("/*", " * 요약만 있고 ID 없음", " */", *SECTIONS_C)
    assert run(monkeypatch, write(project, "a.test.js", bad)) == 2


def test_task61_1_edit_result_is_checked(project, monkeypatch):
    """TASK-61#1: Edit is judged on the file after the replacement."""
    put(project, "test_x.py", py("# TASK-61: 구조", *SECTIONS_PY))
    assert run(monkeypatch, edit(project, "test_x.py", "# TASK-61: 구조\n", "")) == 2
    assert run(monkeypatch, edit(project, "test_x.py", "구조", "새 요약")) == 0


# --- TASK-61#2: the AC/DoD section marker comes before the Coverage one ---


@pytest.mark.parametrize(
    "body, problem",
    [
        (["# == Coverage ==", "# == AC/DoD =="], "앞에"),
        (["# == AC/DoD ==", "def test_a(): pass"], "'# == Coverage ==' 섹션 표식이 없습니다"),
        (["def test_a(): pass", "# == Coverage =="], "'# == AC/DoD ==' 섹션 표식이 없습니다"),
        (["def test_a(): pass"], "'# == AC/DoD ==' 섹션 표식이 없습니다"),
        (["# == AC/DoD ==", "# == Coverage ==", "# == AC/DoD =="], "한 번"),
        (["# == AC/DoD ==", "# == Coverage ==", "# == Coverage =="], "한 번"),
    ],
)
def test_task61_2_missing_or_misordered_sections_are_denied(
    project, monkeypatch, capsys, body, problem
):
    """TASK-61#2: each section marker exactly once, AC/DoD before Coverage."""
    content = py("# TASK-61: 섹션", *body)
    assert run(monkeypatch, write(project, "test_x.py", content)) == 2
    err = capsys.readouterr().err
    assert problem in err
    assert "<ID>: <한 줄 요약>" not in err


@pytest.mark.parametrize(
    "rel, lines",
    [
        ("a.test.ts", ["// TASK-61: 섹션", "// == AC/DoD ==", "// == Coverage =="]),
        ("ATest.java", ["// TASK-61: 섹션", "/* == AC/DoD == */", "/* == Coverage == */"]),
        ("a_test.cc", ["/* TASK-61: 섹션 */", "  // == AC/DoD ==", "  // == Coverage =="]),
        ("test_a.py", ["# TASK-61: 섹션", "# == AC/DoD ==", "    # == Coverage =="]),
    ],
)
def test_task61_2_section_markers_in_each_comment_syntax(project, monkeypatch, rel, lines):
    """TASK-61#2: the markers are full-line comments in the file's syntax."""
    assert run(monkeypatch, write(project, rel, py(*lines))) == 0


def test_task61_2_markers_in_the_wrong_syntax_do_not_count(project, monkeypatch, capsys):
    """TASK-61#2: `# == AC/DoD ==` is not a comment in TypeScript, and a
    marker trailing code is not a section marker."""
    content = py("// TASK-61: 섹션", "# == AC/DoD ==", "// == Coverage ==")
    assert run(monkeypatch, write(project, "a.test.ts", content)) == 2
    assert "'// == AC/DoD ==' 섹션 표식이 없습니다" in capsys.readouterr().err
    content = py("# TASK-61: 섹션", "x = 1  # == AC/DoD ==", "# == Coverage ==")
    assert run(monkeypatch, write(project, "test_a.py", content)) == 2
    assert "'# == AC/DoD ==' 섹션 표식이 없습니다" in capsys.readouterr().err


def test_task61_2_existing_adopted_file_edit_that_breaks_order_is_denied(project, monkeypatch):
    """TASK-61#2: an Edit that leaves the sections out of order is denied."""
    put(project, "test_x.py", py("# TASK-61: 섹션", *SECTIONS_PY))
    assert run(monkeypatch, edit(project, "test_x.py", "# == Coverage ==\n", "")) == 2
    payload = edit(project, "test_x.py", "def test_b(): pass", "def test_b(): assert 1")
    assert run(monkeypatch, payload) == 0


# --- TASK-61#3: AC/rule/DoD markers only inside the AC/DoD section ---


@pytest.mark.parametrize(
    "lines, marker",
    [
        (["# TASK-61: 요약 TASK-61#1", "# == AC/DoD ==", "# == Coverage =="], "TASK-61#1"),
        (["# TASK-61: 요약", "X = 'TASK-61#B2'", "# == AC/DoD ==", "# == Coverage =="], "TASK-61#B2"),
        (["# TASK-61: 요약", "# == AC/DoD ==", "# == Coverage ==", "def test_e(): pass  # TASK-61#D3"], "TASK-61#D3"),
        (["# TASK-61: 요약", "# == AC/DoD ==", "# == Coverage ==", "# AO-7#12"], "AO-7#12"),
    ],
)
def test_task61_3_marker_outside_the_ac_dod_section_is_denied(
    project, monkeypatch, capsys, lines, marker
):
    """TASK-61#3: `<ID>#<n>`, `<ID>#B<k>` and `<ID>#D<n>` outside the
    section deny, naming the marker and its line."""
    assert run(monkeypatch, write(project, "test_x.py", py(*lines))) == 2
    err = capsys.readouterr().err
    line_no = next(i for i, line in enumerate(lines, start=1) if marker in line)
    assert f"{line_no}번째 줄: {marker}" in err


def test_task61_3_markers_inside_the_section_are_allowed(project, monkeypatch):
    """TASK-61#3: markers of every kind (and of several tasks) inside the
    section pass; text that only looks similar outside it passes too."""
    content = py(
        "# TASK-56: 테스트 먼저",
        "# TASK-61: 구조",
        "# issue #12, TASK-61: 요약, TASK-61#x",
        "# == AC/DoD ==",
        "def test_a():  # TASK-61#1 TASK-61#B2 TASK-61#D3 TASK-56#4",
        "    pass",
        "# == Coverage ==",
        "def test_e(): pass  # see TASK-61 and #4",
    )
    assert run(monkeypatch, write(project, "test_x.py", content)) == 0


def test_task61_3_c_family_markers(project, monkeypatch):
    """TASK-61#3: the same rule in JS/TS/Java/C++ files."""
    inside = py("// TASK-61: 구조", "// == AC/DoD ==", '@DisplayName("TASK-61#1")', "// == Coverage ==")
    assert run(monkeypatch, write(project, "ATest.java", inside)) == 0
    outside = py("// TASK-61: 구조", "// == AC/DoD ==", "// == Coverage ==", 'it("TASK-61#2", () => {});')
    assert run(monkeypatch, write(project, "a.spec.ts", outside)) == 2


def test_task61_3_edit_moving_a_marker_into_coverage_is_denied(project, monkeypatch):
    """TASK-61#3: judged on the Edit result too."""
    put(project, "test_x.py", py("# TASK-61: 구조", *SECTIONS_PY))
    payload = edit(project, "test_x.py", "def test_b(): pass", "def test_b(): pass  # TASK-61#2")
    assert run(monkeypatch, payload) == 2
    payload = edit(project, "test_x.py", "def test_a(): pass", "def test_a(): pass  # TASK-61#2")
    assert run(monkeypatch, payload) == 0



# --- TASK-61#5: convention and per-language examples in the docs ---


def read_repo(name):
    with open(os.path.join(REPO_ROOT, name)) as f:
        return f.read()


def test_task61_5_readme_has_a_passing_example_per_language():
    """TASK-61#5: README carries a Python, TS, Java and C++ example, each
    with a marker, and every one passes the hook's own layout check."""
    blocks = re.findall(r"```(python|ts|java|cpp)\n(.*?)```", read_repo("README.md"), re.S)
    assert sorted({lang for lang, _ in blocks}) == ["cpp", "java", "python", "ts"]
    for lang, body in blocks:
        syntax = rtl.HASH if lang == "python" else rtl.SLASH
        assert rtl.layout_problems(body, syntax) == [], lang
        assert rtl.MARKER_RE.search(body), lang


@pytest.mark.parametrize("name", ["README.md", "CLAUDE.md.snippet"])
def test_task61_5_convention_is_documented(name):
    """TASK-61#5: header line, both section markers and the DoD marker."""
    text = read_repo(name)
    for phrase in ("<ID>: <한 줄 요약>", "== AC/DoD ==", "== Coverage ==", "<ID>#D<n>"):
        assert phrase in text, (name, phrase)


def test_task61_5_readme_lists_the_default_target_names():
    """TASK-61#5: the documented defaults are the ones the hook uses."""
    text = read_repo("README.md")
    for pattern in ("test_*.py", "*_test.py", "*.test.*", "*.spec.*", "*Test.java", "*Tests.java", "*_test.cc", "test_*.cpp"):
        assert pattern in text, pattern


# --- TASK-61#D2: registration, REGISTRY and the registration contract ---


def test_task61_d2_registered_for_every_edit_and_write():
    """TASK-61#D2: settings.hooks.json runs the hook on PreToolUse
    Edit|Write with no `if` filter, and its copied helpers are in the dedup
    REGISTRY without drift."""
    settings = json.loads(read_repo("settings.hooks.json"))
    found = [
        (group.get("matcher"), hook.get("if"))
        for group in settings["hooks"]["PreToolUse"]
        for hook in group["hooks"]
        if hook["command"].endswith("/require_test_layout.py")
    ]
    assert found == [("Edit|Write", None)]
    for name in (
        "is_backlog_project",
        "project_config_path",
        "is_outside_project",
        "is_glob_list",
        "glob_regex",
        "glob_matches",
        "matches_any",
    ):
        assert "require_test_layout.py" in ddg.REGISTRY[name], name
    assert ddg.find_drift(os.path.join(REPO_ROOT, "hooks")) == []


def test_task61_1_2_3_this_file_follows_its_own_layout():
    """TASK-61#1 TASK-61#2 TASK-61#3: self-application - this test file is
    a new test file in this backlog project, so it must pass the hook."""
    with open(__file__) as f:
        assert rtl.layout_problems(f.read(), rtl.HASH) == []


# == Coverage ==


def test_marker_check_waits_for_valid_sections(project, monkeypatch, capsys):
    content = py("# TASK-61: 구조", "# == Coverage ==", "# == AC/DoD ==", "x = 1")
    assert run(monkeypatch, write(project, "test_x.py", content)) == 2
    assert "번째 줄:" not in capsys.readouterr().err


def test_header_after_section_marker_does_not_count(project, monkeypatch):
    content = py("# == AC/DoD ==", "# TASK-61: 너무 늦음", "# == Coverage ==")
    assert run(monkeypatch, write(project, "test_x.py", content)) == 2


def test_blank_line_ends_the_first_comment_block(project, monkeypatch):
    content = py("", "# 메모", "", "# TASK-61: 다른 블록", *SECTIONS_PY)
    assert run(monkeypatch, write(project, "test_x.py", content)) == 2
    content = py("", "", "# TASK-61: 앞의 빈 줄은 건너뜀", *SECTIONS_PY)
    assert run(monkeypatch, write(project, "test_x.py", content)) == 0


def test_empty_or_blank_new_file_is_denied(project, monkeypatch):
    assert run(monkeypatch, write(project, "test_x.py", "")) == 2
    assert run(monkeypatch, write(project, "a.test.ts", "\n\n")) == 2
    assert run(monkeypatch, write(project, "a.test.ts", "#!/usr/bin/env node\n")) == 2


def test_unterminated_block_comment_is_read_to_the_end(project, monkeypatch):
    content = py("/*", " * TASK-61: 닫히지 않은 블록")
    assert rtl.has_header(content.split("\n"), rtl.SLASH)


def test_comment_text_per_language():
    assert rtl.comment_text("  /* 한 줄 */", rtl.SLASH) == "한 줄"
    assert rtl.comment_text(" * 이어지는 줄", rtl.SLASH) == "이어지는 줄"
    assert rtl.comment_text("// a", rtl.SLASH) == "a"
    assert rtl.comment_text("# a", rtl.SLASH) is None
    assert rtl.comment_text("// a", rtl.HASH) is None
    assert rtl.comment_text("x = 1  # a", rtl.HASH) is None


def test_file_of_only_comments_without_trailing_newline():
    assert rtl.has_header(["# TASK-61: 주석뿐"], rtl.HASH)
    assert rtl.has_header(["// TASK-61: 주석뿐"], rtl.SLASH)


def test_slash_files_ignore_star_lines_outside_a_leading_block(project, monkeypatch):
    # a leading `// ...` block stops at a `*` line: only `//` lines join it
    lines = ["// 메모", "* TASK-61: not part of the // block"]
    assert not rtl.has_header(lines, rtl.SLASH)


# --- scope: existing files ---


def test_grandfathered_file_passes_with_a_hint(project, monkeypatch, capsys):
    put(project, "test_old.py", py("import os", "def test_a(): pass"))
    payload = edit(project, "test_old.py", "def test_a(): pass", "def test_a(): assert 1")
    assert run(monkeypatch, payload) == 0
    out = json.loads(capsys.readouterr().out)
    assert "== AC/DoD ==" in out["systemMessage"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["additionalContext"] == out["systemMessage"]


def test_grandfathered_file_rewritten_with_write_passes_with_a_hint(project, monkeypatch, capsys):
    put(project, "a.test.ts", "test('a', () => {});\n")
    assert run(monkeypatch, write(project, "a.test.ts", "test('b', () => {});\n")) == 0
    assert "// == AC/DoD ==" in json.loads(capsys.readouterr().out)["systemMessage"]


def test_existing_file_that_adopts_the_layout_is_checked(project, monkeypatch):
    put(project, "test_old.py", py("import os", "def test_a(): pass"))
    # adding a section marker opts the file in, so the missing header denies
    payload = edit(project, "test_old.py", "import os", "import os\n# == AC/DoD ==")
    assert run(monkeypatch, payload) == 2
    payload = edit(project, "test_old.py", "import os", py("# TASK-61: 도입", "import os", *SECTIONS_PY))
    assert run(monkeypatch, payload) == 0


def test_existing_file_with_layout_cannot_drop_it(project, monkeypatch):
    put(project, "test_x.py", py("# TASK-61: 구조", *SECTIONS_PY))
    assert run(monkeypatch, write(project, "test_x.py", py("def test_a(): pass"))) == 2


def test_section_marker_alone_marks_an_existing_file_as_adopted():
    assert rtl.adopted(py("x", "# == Coverage =="), rtl.HASH)
    assert rtl.adopted(py("x", "# == AC/DoD =="), rtl.HASH)
    assert not rtl.adopted(py("x", "# 메모"), rtl.HASH)


# --- Edit simulation ---


def test_edit_replace_all_replaces_every_occurrence(project, monkeypatch):
    put(project, "test_x.py", py("# TASK-61: 구조", *SECTIONS_PY, "# TASK-61: 구조"))
    payload = edit(project, "test_x.py", "# TASK-61: 구조", "# 요약 없음", replace_all=True)
    assert run(monkeypatch, payload) == 2
    payload = edit(project, "test_x.py", "# TASK-61: 구조", "# 요약 없음")
    # only the first one changes: the trailing copy is not in the first block
    assert run(monkeypatch, payload) == 2


@pytest.mark.parametrize(
    "tool_input",
    [
        {"old_string": "not there", "new_string": "x"},
        {"old_string": "", "new_string": "x"},
        {"old_string": 1, "new_string": "x"},
        {"old_string": "import", "new_string": None},
    ],
)
def test_edit_that_would_fail_passes(project, monkeypatch, tool_input):
    put(project, "test_x.py", py("import os"))
    payload = edit(project, "test_x.py", "a", "b")
    payload["tool_input"].update(tool_input)
    assert run(monkeypatch, payload) == 0


def test_edit_of_missing_file_passes(project, monkeypatch):
    assert run(monkeypatch, edit(project, "test_missing.py", "a", "b")) == 0


def test_write_without_string_content_passes(project, monkeypatch):
    payload = write(project, "test_x.py", "x")
    payload["tool_input"]["content"] = None
    assert run(monkeypatch, payload) == 0


def test_unreadable_existing_path_counts_as_missing(project):
    assert rtl.read_file(str(project / "nope.py")) is None


def test_directory_named_like_a_test_is_not_an_existing_file(project, monkeypatch):
    (project / "test_dir.py").mkdir()
    assert run(monkeypatch, edit(project, "test_dir.py", "a", "b")) == 0


# --- target paths ---


@pytest.mark.parametrize(
    "rel",
    [
        "src/router.py",
        "tests/conftest.py",
        "web/router.ts",
        "web/router.test.vue",
        "src/main/java/Router.java",
        "src/test/java/RouterTestUtil.java",
        "cpp/router.cpp",
        "cpp/test_router.cc",
        "README.md",
        "tests/test_data.json",
    ],
)
def test_non_test_files_are_ignored(project, monkeypatch, rel):
    assert run(monkeypatch, write(project, rel, "no header\n")) == 0


def test_test_globs_replace_the_defaults(project, monkeypatch):
    put(project, ".claude-code-agile-hooks.json", json.dumps(
        {"testFirst": {"sourceGlobs": ["src/main/**"], "testGlobs": ["src/test/**"]}}
    ))
    assert run(monkeypatch, write(project, "src/test/java/a/Helper.java", "x\n")) == 2
    assert run(monkeypatch, write(project, "src/test/resources/a.json", "x\n")) == 0
    # default names outside testGlobs are no longer targets
    assert run(monkeypatch, write(project, "tools/test_x.py", "x\n")) == 0


def test_legacy_config_name_is_read(project, monkeypatch):
    put(project, ".claude-rails.json", json.dumps({"testFirst": {"testGlobs": ["t/**"]}}))
    assert run(monkeypatch, write(project, "t/helper.py", "x\n")) == 2


@pytest.mark.parametrize(
    "config",
    [
        "{not json",
        json.dumps(["x"]),
        json.dumps({"testCommand": "pytest"}),
        json.dumps({"testFirst": ["t/**"]}),
        json.dumps({"testFirst": {"testGlobs": []}}),
        json.dumps({"testFirst": {"testGlobs": "t/**"}}),
    ],
)
def test_unusable_test_globs_fall_back_to_defaults(project, monkeypatch, config):
    put(project, ".claude-code-agile-hooks.json", config)
    assert run(monkeypatch, write(project, "t/helper.py", "x\n")) == 0
    assert run(monkeypatch, write(project, "t/test_x.py", "x\n")) == 2


def test_unreadable_config_falls_back_to_defaults(project, monkeypatch):
    put(project, ".claude-code-agile-hooks.json", json.dumps({"testFirst": {"testGlobs": ["t/**"]}}))

    def refuse(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(rtl, "open", refuse, raising=False)
    assert rtl.load_test_globs(str(project)) is None


def test_relative_file_path_is_resolved_against_cwd(project, monkeypatch):
    payload = write(project, "test_x.py", "x\n")
    payload["tool_input"]["file_path"] = "test_x.py"
    assert run(monkeypatch, payload) == 2


# --- applicability ---


def test_outside_project_passes(project, monkeypatch, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    payload = write(project, "test_x.py", "x\n")
    payload["tool_input"]["file_path"] = str(other / "test_x.py")
    assert run(monkeypatch, payload) == 0


def test_non_backlog_project_passes(tmp_path, monkeypatch):
    assert run(monkeypatch, write(tmp_path, "test_x.py", "x\n")) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Read", "tool_input": {"file_path": "test_x.py"}},
        {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        {"tool_name": "Write", "tool_input": "not a dict"},
        {"tool_name": "Write", "tool_input": {}},
        {"tool_name": "Write", "tool_input": {"file_path": 3, "content": "x"}},
        {},
    ],
)
def test_other_payloads_pass(project, monkeypatch, payload):
    payload = dict(payload, cwd=str(project))
    assert run(monkeypatch, payload) == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        rtl.main()
    assert exc_info.value.code == 0


# --- copied helpers (REGISTRY keeps them identical to their originals) ---


def test_copied_helpers(tmp_path):
    assert not rtl.is_backlog_project("")
    assert not rtl.is_backlog_project(str(tmp_path))
    assert rtl.project_config_path(str(tmp_path)) is None
    assert not rtl.is_outside_project("", str(tmp_path))
    assert rtl.is_outside_project("../x", str(tmp_path))
    assert rtl.glob_matches("**/test_*.py", "a/b/test_x.py")
    assert rtl.glob_matches("hooks/?.py", "hooks/a.py")
    assert not rtl.glob_matches("hooks/?.py", "hooks/ab.py")
    assert rtl.glob_matches("lib**", "lib/a/b")
