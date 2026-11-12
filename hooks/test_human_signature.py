# ---
# title: test_human_signature
# description: 사람 서명 판정이 키 지문에 고정되는지 실제 git 저장소와 ssh 키로 검증하는 테스트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
# TASK-72: 사람 서명 판정을 사람 키 지문으로 고정한다(allowed_signers · humanSigners · 로컬 allowedSignersFile 우회 차단)
#
# Real git repos and throwaway ssh-keygen keys. Each test gets its own $HOME
# (with ~/.ssh/allowed_signers) and its own "installed hook directory": the
# module's __file__ is pointed at a tmp dir so fingerprint_path() resolves the
# human-signers file there through the real realpath(__file__) logic. The
# AC #6 tests also copy the hook file itself into a tmp dir and run it as a
# subprocess, through a symlink, to show the file is found next to the hook.
import io
import json
import os
import shutil
import subprocess
import sys

import pytest

import require_implementation_plan as rip

SOAP_PLAN = """### Subjective
요청.

### Objective
사실.

### Assessment
판단.

### Plan
1. 순서.
"""

CARD = f"""---
id: TASK-58
title: 제목
status: To Do
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 기능
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 테스트 통과 로그
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
{SOAP_PLAN}<!-- SECTION:PLAN:END -->
"""

START = 'backlog task edit TASK-58 -s "In Progress"'
APPROVAL_COMMAND = 'git commit --allow-empty -S -m "Plan-Approved: TASK-58"'


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout


def fingerprint(pub):
    """What `ssh-keygen -lf key.pub` prints as its second field."""
    out = subprocess.run(
        ["ssh-keygen", "-lf", str(pub)], capture_output=True, text=True, check=True
    ).stdout
    return out.split()[1]


@pytest.fixture(scope="session")
def keys(tmp_path_factory):
    """Human and AI ssh signing keys: path, public key text, fingerprint."""
    directory = tmp_path_factory.mktemp("keys")
    found = {}
    for name in ("human", "ai"):
        key = directory / name
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)],
            check=True,
        )
        pub = key.with_suffix(".pub")
        found[name] = {
            "key": key,
            "pub": " ".join(pub.read_text().split()[:2]),
            "fp": fingerprint(pub),
        }
    return found


@pytest.fixture
def env(tmp_path, monkeypatch, keys):
    """$HOME with ~/.ssh/allowed_signers (`human` and `ai-claude-code`), an
    installed hook directory whose human-signers lists the human key, and a
    backlog repo holding TASK-58 with `humanSigners: ["human"]`."""
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    hookdir = tmp_path / "installed"
    hookdir.mkdir()
    monkeypatch.setattr(rip, "__file__", str(hookdir / "require_implementation_plan.py"))
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Tester")
    git(root, "config", "user.email", "tester@example.com")
    git(root, "config", "gpg.format", "ssh")
    (root / ".claude-code-agile-hooks.json").write_text(
        json.dumps({"humanSigners": ["human"]})
    )
    (root / "backlog" / "tasks").mkdir(parents=True)
    (root / "backlog" / "config.yml").write_text("project_name: x\n")
    (root / "backlog" / "tasks" / "task-58 - 제목.md").write_text(CARD)
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")

    class Env:
        path = root
        hooks = hookdir
        signers_file = hookdir / "human-signers"
        allowed = home / ".ssh" / "allowed_signers"

        def allow(self, *pairs):
            """Rewrite ~/.ssh/allowed_signers with (principal, key name)."""
            self.allowed.write_text(
                "".join(f"{p} {keys[k]['pub']}\n" for p, k in pairs)
            )

        def pin(self, text):
            self.signers_file.write_text(text)

        def config(self, data):
            (root / ".claude-code-agile-hooks.json").write_text(
                data if isinstance(data, str) else json.dumps(data)
            )

        def approve(self, key="human", sign=True):
            args = ["-c", f"user.signingkey={keys[key]['key']}", "commit", "-q"]
            args += ["--allow-empty", "-S" if sign else "--no-gpg-sign"]
            git(root, *args, "-m", "Plan-Approved: TASK-58")

        def verdict(self):
            """%G?|%GK|%GS of HEAD as git sees it with ~/.ssh/allowed_signers."""
            return git(
                root,
                "-c",
                f"gpg.ssh.allowedSignersFile={self.allowed}",
                "log",
                "-1",
                "--format=%G?|%GK|%GS",
            ).strip()

    e = Env()
    e.allow(("human", "human"), ("ai-claude-code", "ai"))
    e.pin(keys["human"]["fp"] + "\n")
    return e


def run_main(monkeypatch, cwd, command=START):
    payload = {"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc_info:
        rip.main()
    return exc_info.value.code


# == AC/DoD ==


def test_ai_key_listed_as_human_principal_is_denied(env, monkeypatch, capsys, keys):
    """TASK-72#1 TASK-72#B1 (A1): the AI key put into allowed_signers under
    the `human` principal gives %G? = G and %GS = human - still denied,
    because its fingerprint is not pinned."""
    env.allow(("human", "human"), ("human", "ai"))
    env.approve(key="ai")
    assert env.verdict() == f"G|{keys['ai']['fp']}|human"
    assert run_main(monkeypatch, env.path) == 2
    err = capsys.readouterr().err
    assert "사람 키가 아닌 키의 서명" in err
    assert f"%GK = {keys['ai']['fp']}" in err


def test_human_key_with_pinned_fingerprint_passes(env, monkeypatch):
    """TASK-72#1 TASK-72#B1 TASK-72#4"""
    env.approve()
    assert run_main(monkeypatch, env.path) == 0


def test_human_key_under_any_principal_passes(env, monkeypatch, keys):
    """TASK-72#1 TASK-72#B1 TASK-72#B2: the principal name doesn't matter -
    a pinned key passes under a principal humanSigners doesn't list."""
    env.allow(("someone", "human"))
    env.approve()
    assert env.verdict() == f"G|{keys['human']['fp']}|someone"
    assert run_main(monkeypatch, env.path) == 0


def test_ai_principal_in_human_signers_is_denied(env, monkeypatch, capsys, keys):
    """TASK-72#2 TASK-72#B2 (A2): humanSigners naming the AI principal does
    not make an unpinned key human."""
    env.config({"humanSigners": ["human", "ai-claude-code"]})
    env.approve(key="ai")
    assert env.verdict() == f"G|{keys['ai']['fp']}|ai-claude-code"
    assert run_main(monkeypatch, env.path) == 2
    err = capsys.readouterr().err
    assert f"%GK = {keys['ai']['fp']}" in err
    assert "humanSigners는 더 이상 판정에 쓰지 않습니다" in err


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"humanSigners": []},
        {"humanSigners": ["someone-else"]},
        {"humanSigners": "human"},
        ["human"],
        "not json",
        None,
    ],
    ids=["missing", "empty", "other", "string", "not-object", "bad-json", "no-file"],
)
def test_human_signers_config_does_not_affect_the_verdict(env, monkeypatch, config):
    """TASK-72#2 TASK-72#B2: whatever humanSigners holds (or no config at
    all), a pinned human key passes."""
    if config is None:
        (env.path / ".claude-code-agile-hooks.json").unlink()
    else:
        env.config(config)
    env.approve()
    assert run_main(monkeypatch, env.path) == 0


def test_deny_messages_tell_missing_invalid_and_not_human_apart(env, monkeypatch, capsys, keys):
    """TASK-72#4: missing, invalid (%G? != G) and not_human (fingerprint not
    pinned, shown) each get their own message."""
    assert run_main(monkeypatch, env.path) == 2
    missing = capsys.readouterr().err
    assert "'Plan-Approved: TASK-58'인 커밋이 없습니다" in missing
    env.approve(sign=False)
    assert run_main(monkeypatch, env.path) == 2
    invalid = capsys.readouterr().err
    assert "서명이 유효하지 않습니다(%G? = N" in invalid
    git(env.path, "reset", "-q", "--hard", "HEAD~1")
    env.approve(key="ai")
    assert run_main(monkeypatch, env.path) == 2
    not_human = capsys.readouterr().err
    assert f"%GK = {keys['ai']['fp']}" in not_human
    assert str(env.signers_file) in not_human
    for err in (missing, invalid, not_human):
        assert APPROVAL_COMMAND in err
    assert "인 커밋이 없습니다" not in invalid + not_human
    assert "유효하지 않습니다" not in missing + not_human
    assert "%GK =" not in missing + invalid


def test_approval_status_kinds(env, keys):
    """TASK-72#4"""
    pinned = {keys["human"]["fp"]}
    cwd = str(env.path)
    assert rip.approval_status(cwd, "TASK-58", pinned) == ("missing", None)
    env.approve(key="ai")
    assert rip.approval_status(cwd, "TASK-58", pinned) == ("not_human", keys["ai"]["fp"])
    env.approve(sign=False)
    assert rip.approval_status(cwd, "TASK-58", pinned) == ("invalid", "N")
    env.approve()
    assert rip.approval_status(cwd, "TASK-58", pinned) == ("approved", keys["human"]["fp"])


def test_local_allowed_signers_file_is_ignored_for_ai_key(env, monkeypatch, capsys, tmp_path, keys):
    """TASK-72#3 TASK-72#B3 (A3): a repo-local gpg.ssh.allowedSignersFile
    pointing at a fake file that vouches for the AI key as `human` changes
    nothing - ~/.ssh/allowed_signers (human key only) is used, so the AI
    signature is not even valid."""
    env.allow(("human", "human"))
    fake = tmp_path / "fake_allowed_signers"
    fake.write_text(f"human {keys['ai']['pub']}\n")
    git(env.path, "config", "gpg.ssh.allowedSignersFile", str(fake))
    env.approve(key="ai")
    assert git(env.path, "log", "-1", "--format=%G?|%GS").strip() == "G|human"
    assert run_main(monkeypatch, env.path) == 2
    assert "서명이 유효하지 않습니다(%G? = U" in capsys.readouterr().err


@pytest.mark.parametrize("channel", ["local", "global", "env"])
def test_allowed_signers_file_from_config_does_not_change_verdict(env, monkeypatch, tmp_path, channel):
    """TASK-72#3 TASK-72#B3: pointing allowedSignersFile at a missing file
    through repo-local, global or environment-variable config leaves the
    verdict on a human approval unchanged (plain git says U there)."""
    missing = str(tmp_path / "nowhere")
    if channel == "local":
        git(env.path, "config", "gpg.ssh.allowedSignersFile", missing)
    elif channel == "global":
        global_config = tmp_path / "global-gitconfig"
        global_config.write_text(f"[gpg \"ssh\"]\n\tallowedSignersFile = {missing}\n")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    else:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "gpg.ssh.allowedSignersFile")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", missing)
    env.approve()
    assert git(env.path, "log", "-1", "--format=%G?").strip() == "U"
    assert run_main(monkeypatch, env.path) == 0


GUIDANCE = ("ssh-keygen -lf", "SHA256:", APPROVAL_COMMAND)


@pytest.mark.parametrize(
    "content, reason",
    [
        (None, "없습니다"),
        ("", "비어 있습니다"),
        ("\n  \n# 사람 키\n", "비어 있습니다"),
        ("SHA256:abc\n", "2"),
        ("human SHA256:{fp}\n", "2"),
        ("{fp} human\n", "2"),
        ("{fp}=\n", "2"),
        ("MD5:{fp}\n", "2"),
        ("sha256:{tail}\n", "2"),
        ("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI\n", "2"),
    ],
    ids=[
        "missing", "empty", "comments-only", "short", "principal-prefix",
        "trailing-word", "padding", "md5", "lowercase", "public-key",
    ],
)
def test_bad_fingerprint_file_fails_closed(env, monkeypatch, capsys, keys, content, reason):
    """TASK-72#5 TASK-72#B4: missing, empty or malformed human-signers denies
    with setup guidance even when a pinned human key signed the approval.
    A malformed line anywhere (here line 2, after a good one) is enough."""
    fp = keys["human"]["fp"]
    if content is None:
        env.signers_file.unlink()
    elif reason == "2":
        env.pin(fp + "\n" + content.format(fp=fp, tail=fp[len("SHA256:"):]))
        reason = "2번째 줄"
    else:
        env.pin(content)
    env.approve()
    assert run_main(monkeypatch, env.path) == 2
    err = capsys.readouterr().err
    assert str(env.signers_file) in err
    assert reason in err
    for text in GUIDANCE:
        assert text in err


def test_unreadable_fingerprint_file_fails_closed(env, monkeypatch, capsys):
    """TASK-72#5 TASK-72#B4: a human-signers that can't be read (here a
    directory) denies too."""
    env.signers_file.unlink()
    env.signers_file.mkdir()
    env.approve()
    assert run_main(monkeypatch, env.path) == 2
    err = capsys.readouterr().err
    assert "읽을 수 없습니다" in err and "ssh-keygen -lf" in err


def test_comments_blank_lines_and_several_fingerprints_are_allowed(env, monkeypatch, keys):
    """TASK-72#5: `#` comments, blank lines and surrounding whitespace are
    fine; any listed fingerprint counts."""
    env.pin(f"# 사람 키\n\n  {keys['ai']['fp']}  \n# 노트북\n{keys['human']['fp']}\n")
    assert rip.human_fingerprints()[0] == {keys["ai"]["fp"], keys["human"]["fp"]}
    env.approve()
    assert run_main(monkeypatch, env.path) == 0


def write_fake(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def fakes(tmp_path, keys):
    """Fake verification programs that fabricate 'good signature by the
    human key' for whatever they are handed: one speaking ssh-keygen -Y,
    one speaking gpg/gpgsm --status-fd."""
    fp = keys["human"]["fp"]
    ssh = write_fake(
        tmp_path / "fake-ssh-keygen",
        'case "$*" in *find-principals*) echo human; exit 0;; esac\n'
        "cat >/dev/null\n"
        f"echo 'Good \"git\" signature for human with ED25519 key {fp}'\n",
    )
    gpg = write_fake(
        tmp_path / "fake-gpg",
        "cat >/dev/null\n"
        f"printf '[GNUPG:] NEWSIG\\n[GNUPG:] GOODSIG {fp} human\\n"
        f"[GNUPG:] VALIDSIG {fp}\\n[GNUPG:] TRUST_ULTIMATE\\n'\n",
    )
    return {"ssh": ssh, "gpg": gpg}


def forge_approval(env, armor):
    """An AI-made Plan-Approved commit carrying a junk signature block with
    `armor` (git picks the verifier by the armor, not by gpg.format), put
    on HEAD the way `hash-object` + `update-ref` lets anyone do."""
    tree = git(env.path, "rev-parse", "HEAD^{tree}").strip()
    parent = git(env.path, "rev-parse", "HEAD").strip()
    body = (
        f"tree {tree}\nparent {parent}\n"
        "author t <t@e> 1 +0000\ncommitter t <t@e> 1 +0000\n"
        f"gpgsig -----BEGIN {armor}-----\n \n AAAA\n -----END {armor}-----\n"
        "\nPlan-Approved: TASK-58\n"
    )
    sha = subprocess.run(
        ["git", "-C", str(env.path), "hash-object", "-t", "commit", "-w", "--stdin"],
        input=body, capture_output=True, text=True, check=True,
    ).stdout.strip()
    git(env.path, "update-ref", "HEAD", sha)


def inject(env, monkeypatch, tmp_path, channel, pairs):
    """Set git config `pairs` through one channel git reads."""
    if channel == "local":
        for key, value in pairs:
            git(env.path, "config", key, value)
    elif channel == "global":
        path = tmp_path / "attacker-gitconfig"
        for key, value in pairs:
            git(env.path, "config", "--file", str(path), key, value)
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(path))
    elif channel == "env-count":
        monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(pairs)))
        for n, (key, value) in enumerate(pairs):
            monkeypatch.setenv(f"GIT_CONFIG_KEY_{n}", key)
            monkeypatch.setenv(f"GIT_CONFIG_VALUE_{n}", value)
    else:
        monkeypatch.setenv(
            "GIT_CONFIG_PARAMETERS", " ".join(f"'{k}'='{v}'" for k, v in pairs)
        )


CHANNELS = ["local", "global", "env-count", "env-parameters"]
# (program key, fake, gpg.format set alongside, how the AI approval is made)
FAKE_PROGRAMS = [
    ("gpg.ssh.program", "ssh", None, "ai-ssh-key"),
    ("gpg.program", "gpg", "openpgp", "PGP SIGNATURE"),
    ("gpg.openpgp.program", "gpg", "openpgp", "PGP SIGNATURE"),
    ("gpg.x509.program", "gpg", "x509", "SIGNED MESSAGE"),
]


@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize(
    "key, fake, fmt, made", FAKE_PROGRAMS, ids=[p[0] for p in FAKE_PROGRAMS]
)
def test_fake_verification_program_cannot_make_ai_approval_human(
    env, monkeypatch, tmp_path, keys, fakes, channel, key, fake, fmt, made
):
    """TASK-72#7 TASK-72#B6: a fake verification program injected through
    repo-local, global or environment-variable config makes plain git report
    'G + pinned human fingerprint + human' for an AI-made approval (checked
    first), yet the hook still denies - it pins the programs itself."""
    if made == "ai-ssh-key":
        env.approve(key="ai")
    else:
        forge_approval(env, made)
    pairs = [(key, fakes[fake])] + ([("gpg.format", fmt)] if fmt else [])
    inject(env, monkeypatch, tmp_path, channel, pairs)
    assert env.verdict() == f"G|{keys['human']['fp']}|human"
    assert run_main(monkeypatch, env.path) == 2


@pytest.mark.parametrize("channel", CHANNELS)
def test_real_human_approval_passes_despite_fake_programs(
    env, monkeypatch, tmp_path, fakes, channel
):
    """TASK-72#7 TASK-72#B6: with a rejecting fake ssh program and the gpg
    fakes injected, plain git no longer says G for a real human signature,
    but the hook's pinned real ssh-keygen still verifies it."""
    env.approve()
    pairs = [
        ("gpg.ssh.program", write_fake(tmp_path / "reject", "exit 1\n")),
        ("gpg.program", fakes["gpg"]),
        ("gpg.x509.program", fakes["gpg"]),
    ]
    inject(env, monkeypatch, tmp_path, channel, pairs)
    assert not env.verdict().startswith("G|")
    assert run_main(monkeypatch, env.path) == 0


def run_hook_file(hook, cwd):
    """Run a copy of the hook as the harness would, `python3 <path>`."""
    payload = {"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": START}}
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def test_fingerprint_file_is_read_next_to_the_real_hook_file(env, tmp_path, keys):
    """TASK-72#6 TASK-72#B5: the hook file copied to `real/` is run through a
    symlink in `link/`. Only real/human-signers counts: decoys pinning the AI
    key next to the symlink, in the repo root and named by the project config
    are all ignored."""
    real = tmp_path / "real"
    link = tmp_path / "link"
    real.mkdir()
    link.mkdir()
    shutil.copy(rip.__spec__.origin, real / "require_implementation_plan.py")
    (link / "require_implementation_plan.py").symlink_to(real / "require_implementation_plan.py")
    (real / "human-signers").write_text(keys["human"]["fp"] + "\n")
    decoy = keys["ai"]["fp"] + "\n"
    (link / "human-signers").write_text(decoy)
    (env.path / "human-signers").write_text(decoy)
    env.config({"humanSigners": ["ai-claude-code"], "humanSignersFile": str(link / "human-signers")})
    hook = link / "require_implementation_plan.py"
    pinned = os.path.join(os.path.realpath(real), "human-signers")

    env.approve(key="ai")
    denied = run_hook_file(hook, env.path)
    assert denied.returncode == 2
    assert f"%GK = {keys['ai']['fp']}" in denied.stderr
    assert pinned in denied.stderr

    env.approve()
    assert run_hook_file(hook, env.path).returncode == 0

    (real / "human-signers").unlink()
    missing = run_hook_file(hook, env.path)
    assert missing.returncode == 2
    assert f"{pinned}이(가) 없습니다" in missing.stderr


def test_fingerprint_path_has_no_override(env, monkeypatch, tmp_path):
    """TASK-72#6 TASK-72#B5: environment variables don't move the file."""
    expected = os.path.join(os.path.realpath(env.hooks), "human-signers")
    for name in ("HUMAN_SIGNERS", "HUMAN_SIGNERS_FILE", "CLAUDE_CODE_AGILE_HOOKS_HUMAN_SIGNERS"):
        monkeypatch.setenv(name, str(tmp_path / "elsewhere"))
    assert rip.fingerprint_path() == expected


# == Coverage ==


INSTALL_SH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "install.sh"
)


@pytest.mark.parametrize("existing", [None, "", "SHA256:x\n"], ids=["none", "empty", "filled"])
def test_install_script_explains_but_never_writes_the_fingerprint_file(tmp_path, existing):
    """install.sh (run against a tmp $HOME) tells how to make human-signers
    while it is missing or empty, says nothing once it has content, and
    never creates or changes it."""
    home = tmp_path / "home"
    signers = home / ".claude" / "hooks" / "claude-code-agile-hooks" / "human-signers"
    signers.parent.mkdir(parents=True)
    if existing is not None:
        signers.write_text(existing)
    result = subprocess.run(
        ["bash", INSTALL_SH],
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if existing:
        assert "human-signers" not in result.stdout
        assert signers.read_text() == existing
    else:
        assert f"{signers} 이 없거나 비어 있습니다" in result.stdout
        assert "ssh-keygen -lf" in result.stdout
        assert '-s "In Progress"가 막힙니다' in result.stdout
        assert signers.exists() == (existing is not None)


def test_legacy_note_only_when_config_has_human_signers(env, monkeypatch, capsys):
    """No humanSigners key in the config: no 'no longer used' note."""
    env.config({"testCommand": "true"})
    env.approve(key="ai")
    assert run_main(monkeypatch, env.path) == 2
    assert "humanSigners" not in capsys.readouterr().err
