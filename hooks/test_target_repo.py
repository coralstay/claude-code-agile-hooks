# ---
# title: test_target_repo
# description: 게이트가 세션 cwd가 아니라 명령 · 파일의 대상 저장소로 판정하는지 훅 사본마다 검증하는 테스트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-18'
# updated_date: '2026-11-18'
# ---
# TASK-75: 게이트를 세션 cwd가 아니라 명령 · 파일의 대상 저장소로 판정한다(cd · git -C · BACKLOG_CWD · 하위 디렉터리 · 워크트리, 모르면 거부)
#
# The shared helpers (project_root / is_backlog_project, command_target_dir /
# target_roots, edit_target_root) are copied byte-for-byte into several
# self-contained hooks and registered in dedup_drift_guard.REGISTRY. Helper
# tests run against every registered copy, so each copy is exercised by the
# same cases. Hook tests use real git repos in tmp_path: a "session" repo and
# a "target" repo, the payload's cwd being the session one.
import importlib
import os
import subprocess

import pytest

import dedup_drift_guard

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_HOOKS = [
    "pre_commit_check.py",
    "pre_push_check.py",
    "require_draft_first.py",
    "require_implementation_plan.py",
    "require_test_first.py",
    "require_work_order.py",
    "require_stage_committed.py",
    "require_coverage_on_done.py",
    "backlog_commit_scope.py",
]
EDIT_HOOKS = ["require_active_task.py", "require_test_first.py", "require_test_layout.py"]


def copies(name):
    files = dedup_drift_guard.REGISTRY.get(name) or ["<unregistered>.py"]
    return [f[: -len(".py")] for f in files]


def load(module_name):
    return importlib.import_module(module_name)


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def make_repo(path, backlog=True):
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main", cwd=path)
    if backlog:
        (path / "backlog").mkdir(exist_ok=True)
        (path / "backlog" / "config.yml").write_text("project_name: x\n")
    return path


def commit_all(path, message="init"):
    git("add", "-A", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message, cwd=path)


# == AC/DoD ==

# --- AC #8: one implementation, registered ---------------------------------


def test_registry_lists_project_root():
    """TASK-75#8: project_root is a REGISTRY entry wherever
    is_backlog_project is (is_backlog_project calls it), and every copy of
    both is the same implementation."""
    registry = dedup_drift_guard.REGISTRY
    assert sorted(registry["project_root"]) == sorted(registry["is_backlog_project"])
    names = ["project_root", "is_backlog_project"]
    assert dedup_drift_guard.find_drift(HOOKS_DIR, {n: registry[n] for n in names}) == []


# --- AC #1: project_root / is_backlog_project ------------------------------


@pytest.mark.parametrize("module_name", copies("project_root"))
def test_project_root_is_git_toplevel_from_subdirectory(module_name, tmp_path):
    """TASK-75#1 TASK-75#B1: a subdirectory (existing or not) and a file
    path resolve to the repository top-level."""
    m = load(module_name)
    repo = make_repo(tmp_path / "repo")
    (repo / "src" / "deep").mkdir(parents=True)
    assert m.project_root(str(repo)) == str(repo)
    assert m.project_root(str(repo / "src" / "deep")) == str(repo)
    assert m.project_root(str(repo / "src" / "new.py")) == str(repo)
    assert m.project_root(str(repo / "not" / "yet")) == str(repo)


@pytest.mark.parametrize("module_name", copies("project_root"))
def test_project_root_none_outside_repo(module_name, tmp_path):
    """TASK-75#1"""
    m = load(module_name)
    assert m.project_root(str(tmp_path)) is None
    assert m.project_root("") is None
    assert m.project_root(None) is None


@pytest.mark.parametrize("module_name", copies("is_backlog_project"))
def test_is_backlog_project_from_subdirectory(module_name, tmp_path):
    """TASK-75#1 TASK-75#B1: a session cwd in a subdirectory of a backlog
    project no longer switches the gates off."""
    m = load(module_name)
    repo = make_repo(tmp_path / "repo")
    (repo / "hooks").mkdir()
    assert m.is_backlog_project(str(repo)) is True
    assert m.is_backlog_project(str(repo / "hooks")) is True


@pytest.mark.parametrize("module_name", copies("is_backlog_project"))
def test_is_backlog_project_in_linked_worktree(module_name, tmp_path):
    """TASK-75#1 TASK-75#B1: a linked worktree (`.git` is a file) of a
    backlog project is that project too."""
    m = load(module_name)
    repo = make_repo(tmp_path / "repo")
    commit_all(repo)
    worktree = tmp_path / "wt"
    git("worktree", "add", "-q", "-b", "task/X-1", str(worktree), cwd=repo)
    assert (worktree / ".git").is_file()
    assert m.project_root(str(worktree / "backlog")) == str(worktree)
    assert m.is_backlog_project(str(worktree)) is True
    assert m.is_backlog_project(str(worktree / "backlog")) is True


@pytest.mark.parametrize("module_name", copies("is_backlog_project"))
def test_is_backlog_project_false_without_repo_or_config(module_name, tmp_path):
    """TASK-75#1: backlog/config.yml without a repository, or a repository
    without backlog/config.yml, is not a backlog project."""
    m = load(module_name)
    loose = tmp_path / "loose"
    (loose / "backlog").mkdir(parents=True)
    (loose / "backlog" / "config.yml").write_text("x: 1\n")
    plain = make_repo(tmp_path / "plain", backlog=False)
    assert m.is_backlog_project(str(loose)) is False
    assert m.is_backlog_project(str(plain)) is False
    assert m.is_backlog_project("") is False


# --- AC #2 · #4 · #6 · #8: command_target_dir ------------------------------


def test_registry_lists_command_target_helpers():
    """TASK-75#8: command_target_dir and target_roots are REGISTRY entries
    listing every Bash gate converted to the target repository, each of
    them also carries command_head (command_target_dir calls it), and every
    copy is the same implementation."""
    registry = dedup_drift_guard.REGISTRY
    assert sorted(registry["command_target_dir"]) == sorted(TARGET_HOOKS)
    assert sorted(registry["target_roots"]) == sorted(TARGET_HOOKS)
    assert set(TARGET_HOOKS) <= set(registry["command_head"])
    assert set(TARGET_HOOKS) <= set(registry["project_root"])
    names = ["command_target_dir", "target_roots", "command_head"]
    assert dedup_drift_guard.find_drift(HOOKS_DIR, {n: registry[n] for n in names}) == []


@pytest.fixture
def dirs(tmp_path):
    """session/, b/ (with b/sub/ and b/rel/), c/ and a home/ directory."""
    for name in ("session", "b/sub", "b/rel", "c", "home"):
        (tmp_path / name).mkdir(parents=True)
    return tmp_path


def targets(module_name, command, cwd):
    """The target directory of each segment, keyed by its first words."""
    m = load(module_name)
    return [(" ".join(seg[:2]) if seg else None, d) for seg, d in m.command_target_dir(command, cwd)]


def target_of(module_name, command, cwd, prefix):
    """The target of the last segment whose text starts with `prefix`."""
    m = load(module_name)
    found = [d for seg, d in m.command_target_dir(command, cwd) if " ".join(seg).startswith(prefix)]
    assert found, (command, prefix)
    return found[-1]


TARGET_CASES = [
    # (command, prefix of the judged segment, expected relative to tmp_path)
    ("git commit -m x", "git commit", "session"),
    ("cd {b} && git commit -m x", "git commit", "b"),
    ("cd {b}; cd sub && git commit", "git commit", "b/sub"),
    ("cd {b} && cd .. && cd c && git commit", "git commit", "c"),
    ("git -C {b} commit", "git -C", "b"),
    ("cd {b} && git -C ../c commit", "git -C", "c"),
    ("git -C {b} -C sub -c a=b commit", "git -C", "b/sub"),
    ("git --no-pager -C {b} push", "git --no-pager", "b"),
    ("/usr/bin/git -C {b} push", "/usr/bin/git -C", "b"),
    ("cd -P -- {b} && git commit", "git commit", "b"),
    ("cd {b} >/dev/null 2>&1 && git commit", "git commit", "b"),
    ("{{ cd {b}; }}; git commit", "git commit", "b"),
    ("cd {b} || exit 1; git commit", "git commit", "b"),
    ("cd {b} || return; git commit", "git commit", "b"),
    ("x && cd {b} && git commit", "git commit", "b"),
    ("pushd {b} && git commit", "git commit", "b"),
    ("(cd {b} && git status); git commit", "git commit", "session"),
    ("(cd {b} && git commit)", "git commit", "b"),
    ("echo $(cd {b}) && git commit", "git commit", "session"),
    ("cd {b} | cat; git commit", "git commit", "session"),
    ("echo | cd {b}; git commit", "git commit", "session"),
    ("cd {b} && make & git commit", "git commit", "session"),
    ("cd {b}\ngit commit", "git commit", "b"),
    ("cd {b} && \\\n git commit", "git commit", "b"),
    ("cd {b} <<EOF\ncd {c}\nEOF\ngit commit", "git commit", "b"),
    ("cd ~ && git commit", "git commit", "home"),
    ("cd && git commit", "git commit", "home"),
    ("cd ~/ && git commit", "git commit", "home"),
]


@pytest.mark.parametrize("module_name", copies("command_target_dir"))
@pytest.mark.parametrize("command,prefix,expected", TARGET_CASES)
def test_command_target_dir_follows_cd_and_git_C(module_name, command, prefix, expected, dirs, monkeypatch):
    """TASK-75#2 TASK-75#B2: earlier `cd <dir>` (`&&`, `;`, newline) and
    `git -C <dir>` set the target, relative paths resolve against the
    directory before them, and a cd bash doesn't keep (subshell,
    pipeline, background) doesn't count."""
    monkeypatch.setenv("HOME", str(dirs / "home"))
    monkeypatch.delenv("CDPATH", raising=False)
    cmd = command.format(b=dirs / "b", c=dirs / "c")
    assert target_of(module_name, cmd, str(dirs / "session"), prefix) == str(dirs / expected)


UNKNOWN_CASES = [
    'cd "$X" && git commit',
    "cd $(git rev-parse --show-toplevel) && git commit",
    "cd `pwd` && git commit",
    "cd - && git commit",
    "popd && git commit",
    "pushd && git commit",
    "pushd +1 && git commit",
    "cd {b} {c} && git commit",
    "cd {b}/missing && git commit",
    "cd {b}/* && git commit",
    "cd ~nosuchuser-x && git commit",
    "false || cd {b}; git commit",
    "x && cd {b}; git commit",
    "cd {b} || echo no; git commit",
    "if true; then cd {b}; fi; git commit",
    'git -C "$D" commit',
    "git -C commit",
    "git -C",
    "cd {b} && git -C missing commit",
    "git --git-dir=x commit",
    "git --work-tree x commit",
    "GIT_DIR=x git commit",
    "export GIT_DIR={b}/.git; git commit",
    "GIT_WORK_TREE={b}; git commit",
]


@pytest.mark.parametrize("module_name", copies("command_target_dir"))
@pytest.mark.parametrize("command", UNKNOWN_CASES)
def test_command_target_dir_unknown_is_none(module_name, command, dirs, monkeypatch):
    """TASK-75#6 TASK-75#B6: a directory that can't be known statically
    (variables, command substitution, `cd -`, globs, missing directories,
    a cd that may not have run, another git dir) is None."""
    monkeypatch.delenv("CDPATH", raising=False)
    cmd = command.format(b=dirs / "b", c=dirs / "c")
    m = load(module_name)
    pairs = m.command_target_dir(cmd, str(dirs / "session"))
    assert pairs[-1][1] is None or [d for s, d in pairs if s and s[0].endswith("git")] == [None]


@pytest.mark.parametrize("module_name", copies("command_target_dir"))
def test_command_target_dir_cdpath_and_relative_without_cwd(module_name, dirs, monkeypatch):
    """TASK-75#6 TASK-75#B6: with CDPATH set a relative cd may go anywhere;
    a relative cd from an unknown session cwd is unknown too."""
    m = load(module_name)
    monkeypatch.setenv("CDPATH", str(dirs))
    session = str(dirs / "b")
    assert m.command_target_dir("cd sub && git commit", session)[-1][1] is None
    assert m.command_target_dir("cd ./sub && git commit", session)[-1][1] == str(dirs / "b/sub")
    assert m.command_target_dir("cd .. && git commit", session)[-1][1] == str(dirs)
    monkeypatch.delenv("CDPATH")
    assert m.command_target_dir("cd sub && git commit", "")[-1][1] is None
    assert m.command_target_dir("git commit", "")[-1][1] == ""


@pytest.mark.parametrize("module_name", copies("command_target_dir"))
def test_command_target_dir_unparsable_line(module_name, dirs):
    """TASK-75#6 TASK-75#B6: an untokenizable line keeps the session cwd
    only when its text changes no directory."""
    m = load(module_name)
    session = str(dirs / "session")
    assert m.command_target_dir('git commit -m "x', session) == [(None, session)]
    assert m.command_target_dir(f'cd {dirs / "b"} && git commit -m "x', session) == [(None, None)]
    assert m.command_target_dir('BACKLOG_CWD=x backlog task edit 1 -s "Done', session) == [(None, None)]
    assert m.command_target_dir(None, session) == []


BACKLOG_CASES = [
    ("BACKLOG_CWD={b} backlog task edit 1 -s Done", "backlog", "b"),
    ("env BACKLOG_CWD={b} backlog task edit 1 -s Done", "backlog", "b"),
    ("env -i BACKLOG_CWD={b} /opt/bin/backlog.md draft promote 1", "backlog", "b"),
    ("export BACKLOG_CWD={b}; backlog draft promote 1", "backlog", "b"),
    ("export BACKLOG_CWD=rel && cd {b} && backlog draft promote 1", "backlog", "b/rel"),
    ("cd {b} && BACKLOG_CWD=sub backlog draft promote 1", "backlog", "b/sub"),
    ("export BACKLOG_CWD={b}; unset BACKLOG_CWD; backlog draft promote 1", "backlog", "session"),
    ("(export BACKLOG_CWD={b}); backlog draft promote 1", "backlog", "session"),
    ("BACKLOG_CWD={b} git commit", "git", "session"),
]


@pytest.mark.parametrize("module_name", copies("command_target_dir"))
@pytest.mark.parametrize("command,prefix,expected", BACKLOG_CASES)
def test_command_target_dir_backlog_cwd(module_name, command, prefix, expected, dirs):
    """TASK-75#4 TASK-75#B4: BACKLOG_CWD=<dir> in front of the command
    (also behind `env`) or exported earlier on the line is the target of a
    backlog command, relative to the segment's directory; it doesn't move
    git."""
    cmd = command.format(b=dirs / "b")
    m = load(module_name)
    found = [
        d for seg, d in m.command_target_dir(cmd, str(dirs / "session"))
        if any(t.endswith(prefix) or t.endswith(prefix + ".md") for t in seg)
    ]
    assert found[-1] == str(dirs / expected)


BACKLOG_UNKNOWN = [
    "BACKLOG_CWD=$Y backlog draft promote 1",
    "BACKLOG_CWD={b}; backlog draft promote 1",
    "true && export BACKLOG_CWD={b}; backlog draft promote 1",
    "export BACKLOG_CWD; backlog draft promote 1",
    "export BACKLOG_CWD=$(pwd); backlog draft promote 1",
]


@pytest.mark.parametrize("module_name", copies("command_target_dir"))
@pytest.mark.parametrize("command", BACKLOG_UNKNOWN)
def test_command_target_dir_backlog_cwd_unknown(module_name, command, dirs):
    """TASK-75#4 TASK-75#6 TASK-75#B6: a BACKLOG_CWD that can't be known
    statically (a variable, an assignment that may not be exported, an
    export that may not have run) makes the backlog target unknown."""
    m = load(module_name)
    pairs = m.command_target_dir(command.format(b=dirs / "b"), str(dirs / "session"))
    assert pairs[-1][1] is None


# --- AC #2 · #6 · #7: pre_commit_check / pre_push_check ----------------------


def run_hook(module_name, monkeypatch, payload):
    import io
    import json

    m = load(module_name)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc:
        m.main()
    return exc.value.code


def bash(cwd, command):
    return {"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": command}}


@pytest.fixture
def two_repos(tmp_path):
    """a/: backlog project whose testCommand fails, on branch main with an
    active task; b/: plain git repo (no backlog); p/: backlog project whose
    testCommand passes; home/: no repository."""
    a = make_repo(tmp_path / "a")
    (a / ".claude-code-agile-hooks.json").write_text('{"testCommand": "echo A-TESTS && exit 1"}')
    b = make_repo(tmp_path / "b", backlog=False)
    p = make_repo(tmp_path / "p")
    (p / ".claude-code-agile-hooks.json").write_text('{"testCommand": "exit 0"}')
    (b / "README").write_text("b\n")
    for repo in (a, b, p):
        commit_all(repo)
    home = tmp_path / "home"
    home.mkdir()
    return a, b, p, home


def test_pre_commit_check_runs_target_repo_tests_not_session(two_repos, monkeypatch, capsys):
    """TASK-75#2 TASK-75#B2: 'A 세션에서 cd B && git commit이 A의 testCommand를
    돌림' - the commit is judged on B (here a passing backlog project P),
    and a non-project session's `cd A && git commit` runs A's tests."""
    a, b, p, home = two_repos
    import pre_commit_check as pcc

    monkeypatch.setattr(pcc, "has_command", lambda name: True)
    monkeypatch.setattr(pcc, "has_active_task", lambda cwd: False)
    assert run_hook("pre_commit_check", monkeypatch, bash(a, f"cd {p} && git commit -m x")) == 0
    assert run_hook("pre_commit_check", monkeypatch, bash(home, f"cd {a} && git commit -m x")) == 2
    assert "A-TESTS" in capsys.readouterr().err
    assert run_hook("pre_commit_check", monkeypatch, bash(home, f"git -C {a} commit -m x")) == 2


def test_pre_commit_check_branch_of_target_repo(two_repos, monkeypatch, capsys):
    """TASK-75#2 TASK-75#B2: the task-branch check reads the target repo's
    active task and branch."""
    a, b, p, home = two_repos
    import pre_commit_check as pcc

    monkeypatch.setattr(pcc, "has_command", lambda name: True)
    monkeypatch.setattr(pcc, "has_active_task", lambda cwd: cwd == str(p))
    assert run_hook("pre_commit_check", monkeypatch, bash(home, f"cd {p} && git commit -m x")) == 2
    assert "태스크 브랜치" in capsys.readouterr().err


def test_pre_commit_check_non_project_target_not_gated(two_repos, monkeypatch):
    """TASK-75#7 TASK-75#B7: a commit aimed at a repo that isn't a backlog
    project passes even though the session cwd's tests fail."""
    a, b, p, home = two_repos
    import pre_commit_check as pcc

    monkeypatch.setattr(pcc, "has_command", lambda name: True)
    monkeypatch.setattr(pcc, "has_active_task", lambda cwd: True)
    assert run_hook("pre_commit_check", monkeypatch, bash(a, f"cd {b} && git commit -m x")) == 0
    assert run_hook("pre_commit_check", monkeypatch, bash(a, f"git -C {b} commit -m x")) == 0


@pytest.mark.parametrize(
    "command",
    ['cd "$X" && git commit -m x', 'git -C "$(pwd)" commit -m x', "cd - && git commit"],
)
def test_pre_commit_check_unknown_target_denied(two_repos, monkeypatch, capsys, command):
    """TASK-75#6 TASK-75#B6: an unknown target is denied with the reason,
    even from a session cwd that isn't a backlog project."""
    a, b, p, home = two_repos
    import pre_commit_check as pcc

    monkeypatch.setattr(pcc, "has_command", lambda name: True)
    assert run_hook("pre_commit_check", monkeypatch, bash(home, command)) == 2
    assert "정적으로 알 수 없어" in capsys.readouterr().err


def push_view(status):
    return lambda cwd, task_id: {"task": {"status": status, "finalSummary": ""}}


def test_pre_push_check_other_repo_branch_delete_not_blocked(two_repos, monkeypatch):
    """TASK-75#2 TASK-75#7 TASK-75#B7: 'A의 task 브랜치 때문에 B push가 막힘' -
    session A sits on task/X-1 with an unfinished card, `cd B && git push
    origin --delete <branch>` is judged on B (not a backlog project)."""
    a, b, p, home = two_repos
    git("checkout", "-q", "-b", "task/X-1", cwd=a)
    import pre_push_check as ppc

    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(ppc, "task_view", push_view("In Progress"))
    assert run_hook("pre_push_check", monkeypatch, bash(a, "git push")) == 2
    assert run_hook("pre_push_check", monkeypatch, bash(a, f"cd {b} && git push origin --delete x")) == 0
    assert run_hook("pre_push_check", monkeypatch, bash(a, f"git -C {b} push origin --delete x")) == 0


def test_pre_push_check_judges_target_repo_card(two_repos, monkeypatch, capsys):
    """TASK-75#2 TASK-75#B2: from a session outside any project,
    `cd P && git push` is judged on P's branch and card."""
    a, b, p, home = two_repos
    git("checkout", "-q", "-b", "task/X-2", cwd=p)
    import pre_push_check as ppc

    seen = []
    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    monkeypatch.setattr(
        ppc, "task_view", lambda cwd, task_id: seen.append((cwd, task_id)) or push_view("To Do")(cwd, task_id)
    )
    assert run_hook("pre_push_check", monkeypatch, bash(home, f"cd {p} && git push")) == 2
    assert seen == [(str(p), "X-2")]
    assert "X-2" in capsys.readouterr().err


def test_pre_push_check_unknown_target_denied(two_repos, monkeypatch, capsys):
    """TASK-75#6 TASK-75#B6"""
    a, b, p, home = two_repos
    import pre_push_check as ppc

    monkeypatch.setattr(ppc, "has_command", lambda name: True)
    assert run_hook("pre_push_check", monkeypatch, bash(home, 'git -C "$D" push')) == 2
    assert "정적으로 알 수 없어" in capsys.readouterr().err


# --- AC #3 · #4 · #6 · #7: backlog command gates -----------------------------

PLANLESS_DRAFT = "---\nid: DRAFT-1\ntitle: x\nstatus: Draft\n---\n\n## Description\n\nx\n"
COMPLETE_DRAFT = (
    "---\nid: DRAFT-1\ntitle: x\nstatus: Draft\n---\n\n"
    "## Acceptance Criteria\n<!-- AC:BEGIN -->\n- [ ] #1 a\n<!-- AC:END -->\n\n"
    "## Definition of Done\n<!-- DOD:BEGIN -->\n- [ ] #1 d\n<!-- DOD:END -->\n\n"
    "## Implementation Plan\n\n<!-- SECTION:PLAN:BEGIN -->\n"
    "### Subjective\ns\n### Objective\no\n### Assessment\na\n### Plan\np\n"
    "<!-- SECTION:PLAN:END -->\n"
)

# hook -> the gated command whose rule the prepared project breaks
GATED = {
    "require_draft_first": "backlog task create x",
    "require_implementation_plan": "backlog draft promote DRAFT-1",
    "require_work_order": "backlog draft promote DRAFT-1",
    "require_stage_committed": "backlog draft create x",
    "require_test_first": "backlog task edit X-1 -s Done",
    "require_coverage_on_done": "backlog task edit X-1 -s Done",
    "backlog_commit_scope": "git commit -m x",
}
BACKLOG_GATED = [h for h, c in GATED.items() if c.startswith("backlog")]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def breaking_project(hook, path, monkeypatch):
    """A backlog project in which GATED[hook] breaks that hook's rule."""
    repo = make_repo(path)
    if hook == "require_implementation_plan":
        write(repo / "backlog" / "drafts" / "draft-1 - x.md", PLANLESS_DRAFT)
    elif hook == "require_work_order":
        write(repo / "backlog" / "tasks" / "task-1 - x.md", "---\nid: TASK-1\nstatus: To Do\n---\n")
    elif hook == "require_test_first":
        from test_require_test_first import make_card

        write(repo / ".claude-code-agile-hooks.json",
              '{"testFirst": {"sourceGlobs": ["src/**"], "testGlobs": ["tests/**"]}}')
        commit_all(repo)
        git("checkout", "-q", "-b", "task/X-1", cwd=repo)
        m = load(hook)
        monkeypatch.setattr(m, "has_command", lambda name: True)
        monkeypatch.setattr(
            m, "task_view",
            lambda cwd, task_id: make_card([(True, "a")], task_id="X-1") if cwd == str(repo) else None,
        )
    elif hook == "require_coverage_on_done":
        write(repo / ".claude-code-agile-hooks.json", '{"coverageCommand": "echo LOW && exit 1"}')
    elif hook == "backlog_commit_scope":
        commit_all(repo)
        write(repo / "backlog" / "drafts" / "draft-1 - x.md", PLANLESS_DRAFT)
        write(repo / "src.py", "x = 1\n")
        git("add", "-A", cwd=repo)
    return repo


def verdict(hook, monkeypatch, capsys, payload):
    """"deny" (exit 2, or a PreToolUse deny decision on stdout) or "pass"."""
    import json

    capsys.readouterr()
    code = run_hook(hook, monkeypatch, payload)
    out, err = capsys.readouterr()
    if code == 2:
        return "deny", err
    if '"permissionDecision": "deny"' in out:
        return "deny", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    return "pass", out + err


@pytest.fixture
def places(tmp_path):
    """home/ (no repository) and b/ (a git repo that isn't a backlog project)."""
    home = tmp_path / "home"
    home.mkdir()
    b = make_repo(tmp_path / "b", backlog=False)
    return home, b


@pytest.mark.parametrize("hook", list(GATED))
def test_cd_into_project_from_non_project_session_is_gated(hook, places, tmp_path, monkeypatch, capsys):
    """TASK-75#3 TASK-75#B3: 'backlog 프로젝트가 아닌 세션 cwd에서 cd <프로젝트> &&
    backlog …' is judged by that project's rule (here: denied)."""
    home, b = places
    p = breaking_project(hook, tmp_path / "p", monkeypatch)
    kind, why = verdict(hook, monkeypatch, capsys, bash(home, f"cd {p} && {GATED[hook]}"))
    assert kind == "deny", why
    assert "정적으로 알 수 없어" not in why
    kind, why = verdict(hook, monkeypatch, capsys, bash(p / "backlog", GATED[hook]))
    assert kind == "deny", why


@pytest.mark.parametrize("hook", list(GATED))
def test_non_project_target_is_not_gated_from_project_session(hook, places, tmp_path, monkeypatch, capsys):
    """TASK-75#7 TASK-75#B7 TASK-75#3: the same command aimed at a repo that
    isn't a backlog project passes, though the session cwd breaks the rule."""
    home, b = places
    p = breaking_project(hook, tmp_path / "p", monkeypatch)
    kind, why = verdict(hook, monkeypatch, capsys, bash(p, GATED[hook]))
    assert kind == "deny", why
    kind, why = verdict(hook, monkeypatch, capsys, bash(p, f"cd {b} && {GATED[hook]}"))
    assert kind == "pass", why


@pytest.mark.parametrize("hook", list(GATED))
def test_unknown_target_of_backlog_gate_is_denied(hook, places, monkeypatch, capsys):
    """TASK-75#6 TASK-75#B6 TASK-75#3: `cd "$X" && <gated command>` is denied
    with the reason, even from a session cwd that isn't a project."""
    home, b = places
    if hook == "require_test_first":
        monkeypatch.setattr(load(hook), "has_command", lambda name: True)
    kind, why = verdict(hook, monkeypatch, capsys, bash(home, f'cd "$X" && {GATED[hook]}'))
    assert kind == "deny" and "정적으로 알 수 없어" in why


@pytest.mark.parametrize("hook", BACKLOG_GATED)
@pytest.mark.parametrize(
    "prefix", ["BACKLOG_CWD={p} ", "env BACKLOG_CWD={p} ", "export BACKLOG_CWD={p}; "]
)
def test_backlog_cwd_names_the_target_project(hook, prefix, places, tmp_path, monkeypatch, capsys):
    """TASK-75#4 TASK-75#B4: BACKLOG_CWD=<dir> (in front, behind env, or
    exported earlier) makes <dir> the backlog command's target."""
    home, b = places
    p = breaking_project(hook, tmp_path / "p", monkeypatch)
    kind, why = verdict(hook, monkeypatch, capsys, bash(home, prefix.format(p=p) + GATED[hook]))
    assert kind == "deny", why
    kind, why = verdict(hook, monkeypatch, capsys, bash(p, f"BACKLOG_CWD={b} " + GATED[hook]))
    assert kind == "pass", why


@pytest.mark.parametrize("hook", BACKLOG_GATED)
def test_unknown_backlog_cwd_is_denied(hook, places, monkeypatch, capsys):
    """TASK-75#4 TASK-75#6 TASK-75#B6"""
    home, b = places
    if hook == "require_test_first":
        monkeypatch.setattr(load(hook), "has_command", lambda name: True)
    kind, why = verdict(hook, monkeypatch, capsys, bash(home, "BACKLOG_CWD=$Y " + GATED[hook]))
    assert kind == "deny" and "정적으로 알 수 없어" in why


def test_work_order_judged_on_target_not_session(tmp_path, monkeypatch, capsys):
    """TASK-75#3 TASK-75#B3: 2026-11-17 - require_work_order checked the
    session repo's work-order.md instead of the repo `cd <B> && backlog task
    edit ...` targets. B has nothing to order, so it passes."""
    a = breaking_project("require_work_order", tmp_path / "a", monkeypatch)
    b = make_repo(tmp_path / "b")
    command = f'cd {b} && backlog task edit TASK-9 -s "In Progress"'
    assert verdict("require_work_order", monkeypatch, capsys, bash(a, command))[0] == "pass"


def test_promote_judged_on_target_draft_not_session(tmp_path, monkeypatch, capsys):
    """TASK-75#3 TASK-75#B3: 2026-11-17 - require_implementation_plan refused
    `cd <scratch> && backlog draft promote DRAFT-1` because it read the
    session project's DRAFT-1. The scratch project's DRAFT-1 is complete."""
    a = breaking_project("require_implementation_plan", tmp_path / "a", monkeypatch)
    scratch = make_repo(tmp_path / "scratch")
    write(scratch / "backlog" / "drafts" / "draft-1 - x.md", COMPLETE_DRAFT)
    command = f"cd {scratch} && backlog draft promote DRAFT-1"
    assert verdict("require_implementation_plan", monkeypatch, capsys, bash(a, command))[0] == "pass"
    assert verdict("require_implementation_plan", monkeypatch, capsys, bash(a, "backlog draft promote DRAFT-1"))[0] == "deny"



# --- AC #5 · #8: Edit/Write gates judge the edited file's repository --------


def test_registry_lists_edit_target_root():
    """TASK-75#8 TASK-75#5: edit_target_root is a REGISTRY entry for every
    Edit/Write gate and every copy is the same implementation."""
    registry = dedup_drift_guard.REGISTRY
    assert sorted(registry["edit_target_root"]) == sorted(EDIT_HOOKS)
    assert set(EDIT_HOOKS) <= set(registry["project_root"])
    names = ["edit_target_root"]
    assert dedup_drift_guard.find_drift(HOOKS_DIR, {n: registry[n] for n in names}) == []


@pytest.mark.parametrize("module_name", copies("edit_target_root"))
def test_edit_target_root_is_the_files_repository(module_name, tmp_path):
    """TASK-75#5 TASK-75#B5: the edited file's git top-level, whatever the
    session cwd; relative paths resolve against the session cwd; a symlink
    into a repository counts as that repository."""
    m = load(module_name)
    p = make_repo(tmp_path / "p")
    (p / "src").mkdir()
    q = make_repo(tmp_path / "q", backlog=False)
    home = tmp_path / "home"
    home.mkdir()
    (home / "link").symlink_to(p / "src")
    assert m.edit_target_root(str(p / "src" / "new.py"), str(home)) == str(p)
    assert m.edit_target_root("src/new.py", str(p)) == str(p)
    assert m.edit_target_root("x.py", str(p / "src")) == str(p)
    assert m.edit_target_root(str(q / "a.py"), str(p)) == str(q)
    assert m.edit_target_root(str(home / "link" / "a.py"), str(home)) == str(p)


@pytest.mark.parametrize("module_name", copies("edit_target_root"))
def test_edit_target_root_outside_any_repo_falls_back_to_session(module_name, tmp_path):
    """TASK-75#5: a file in no repository (a plan, a scratch file), or no
    usable path, judges at the session cwd's top-level (or the cwd itself);
    the gates' outside-project check then lets such a file through."""
    m = load(module_name)
    p = make_repo(tmp_path / "p")
    loose = tmp_path / "loose"
    loose.mkdir()
    assert m.edit_target_root(str(loose / "plan.md"), str(p / "backlog")) == str(p)
    assert m.edit_target_root(str(loose / "plan.md"), str(loose)) == str(loose)
    assert m.edit_target_root("", str(p / "backlog")) == str(p)
    assert m.edit_target_root(None, str(loose)) == str(loose)
    assert m.edit_target_root("rel.py", "") == ""


def edit_payload(cwd, path, content="x = 1\n"):
    return {
        "cwd": str(cwd),
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": content},
        "transcript_path": "",
    }


@pytest.fixture
def edit_places(tmp_path):
    """home/ (no repository), p/ (backlog project, opted into testFirst, on
    task/X-1) and b/ (a git repo that isn't a backlog project)."""
    home = tmp_path / "home"
    home.mkdir()
    p = make_repo(tmp_path / "p")
    write(p / ".claude-code-agile-hooks.json",
          '{"testFirst": {"sourceGlobs": ["src/**"], "testGlobs": ["tests/**"]}}')
    write(p / "src" / "app.py", "x = 0\n")
    commit_all(p)
    git("checkout", "-q", "-b", "task/X-1", cwd=p)
    b = make_repo(tmp_path / "b", backlog=False)
    (b / "src").mkdir()
    return home, p, b


def test_require_active_task_judges_the_edited_files_project(edit_places, monkeypatch, capsys):
    """TASK-75#5 TASK-75#B5: an edit of a file in a backlog project without
    an In Progress task is denied from a non-project session or a
    subdirectory; an edit in another repository passes from a project
    session that has no active task either."""
    home, p, b = edit_places
    m = load("require_active_task")
    monkeypatch.setattr(m, "has_command", lambda name: True)
    seen = []
    monkeypatch.setattr(m, "has_active_task", lambda cwd: seen.append(cwd) or False)
    assert run_hook("require_active_task", monkeypatch, edit_payload(home, p / "src" / "app.py")) == 2
    assert "In Progress" in capsys.readouterr().err
    assert run_hook("require_active_task", monkeypatch, edit_payload(p / "src", "app.py")) == 2
    assert seen == [str(p), str(p)]
    assert run_hook("require_active_task", monkeypatch, edit_payload(p, b / "src" / "a.py")) == 0


def test_require_test_first_edit_judges_the_edited_files_project(edit_places, monkeypatch, capsys):
    """TASK-75#5 TASK-75#B5: the next-AC marker check runs on the edited
    file's project (its config, branch, card and tests), not the session's."""
    from test_require_test_first import make_card

    home, p, b = edit_places
    m = load("require_test_first")
    monkeypatch.setattr(m, "has_command", lambda name: True)
    monkeypatch.setattr(
        m, "task_view",
        lambda cwd, task_id: make_card([(False, "a")], task_id="X-1") if cwd == str(p) else None,
    )
    payload = edit_payload(home, p / "src" / "app.py")
    payload["tool_name"] = "Edit"
    assert run_hook("require_test_first", monkeypatch, payload) == 2
    assert "X-1#1" in capsys.readouterr().err
    assert run_hook("require_test_first", monkeypatch, edit_payload(p / "src", "app.py")) == 2
    assert run_hook("require_test_first", monkeypatch, edit_payload(p, b / "src" / "a.py")) == 0


def test_require_test_layout_judges_the_edited_files_project(edit_places, monkeypatch, capsys):
    """TASK-75#5 TASK-75#B5: a new test file without the layout is denied in
    a backlog project from any session cwd, and not gated in a repository
    that isn't one."""
    home, p, b = edit_places
    assert run_hook("require_test_layout", monkeypatch, edit_payload(home, p / "tests" / "test_a.py")) == 2
    assert "구조 규약" in capsys.readouterr().err
    assert run_hook("require_test_layout", monkeypatch, edit_payload(p / "src", "../tests/test_b.py")) == 2
    assert run_hook("require_test_layout", monkeypatch, edit_payload(p, b / "test_c.py")) == 0


# == Coverage ==


@pytest.mark.parametrize("module_name", copies("command_target_dir"))
def test_command_target_dir_stray_paren_and_or_before_subshell(module_name, dirs):
    """An unmatched `)` is ignored; `cd b || (exit)` has no segment after
    `||` to recognize as exit, so the target becomes unknown."""
    m = load(module_name)
    b, session = str(dirs / "b"), str(dirs / "session")
    assert m.command_target_dir(f"cd {b}) && git commit", session)[-1][1] == b
    assert m.command_target_dir(f"cd {b} || (exit 1); git commit", session)[-1][1] is None


@pytest.mark.parametrize("module_name", copies("target_roots"))
def test_target_roots_groups_by_repo_and_uses_fallback(module_name, tmp_path):
    """Two gated segments in one repo form one group; an untokenizable
    line counts the hook's fallback results against the session cwd."""
    m = load(module_name)
    p = make_repo(tmp_path / "p")
    q = make_repo(tmp_path / "q")
    (p / "sub").mkdir()
    match = lambda seg: seg[-1] if seg[0] == "go" else None  # noqa: E731
    command = f"go 1; cd sub && go 2; cd {q} && go 3; echo x"
    assert m.target_roots(command, str(p), match, []) == [(str(p), ["1", "2"]), (str(q), ["3"])]
    assert m.target_roots('go "1', str(p / "sub"), match, ["f"]) == [(str(p), ["f"])]
    assert m.target_roots('go "1', str(p), match, []) == []
    assert m.target_roots(f"cd {tmp_path} && go 1", str(p), match, []) == []
