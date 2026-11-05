# TASK-74: hooks/conftest.py가 테스트의 git 하위 프로세스를 사용자 전역 · 시스템 · 환경 변수 git 설정에서 격리한다
#
# The outer test pollutes the environment the way a real signing setup does
# (commit.gpgsign=true, gpg.format=ssh, a user.signingkey) through all four
# channels git reads: the global file, the system file, GIT_CONFIG_COUNT/KEY_n/
# VALUE_n and GIT_CONFIG_PARAMETERS. It then runs an inner pytest session with
# pytester. With the real conftest copied in, the inner git commit succeeds and
# `git config --get` sees none of the polluted values; without it (control),
# the very same inner test fails, so the pass is the fixture's doing.
import os
import subprocess
from pathlib import Path

pytest_plugins = ["pytester"]

CONFTEST = Path(__file__).with_name("conftest.py")
MISSING_KEY = "/nonexistent/signing-key"

POLLUTED_CONFIG = f"""\
[commit]
\tgpgsign = true
[tag]
\tgpgsign = true
[gpg]
\tformat = ssh
[user]
\tsigningkey = {MISSING_KEY}
"""

INNER_TEST = '''
import os
import subprocess


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )


def test_commit_is_unsigned_and_config_is_clean(tmp_path):
    assert git(tmp_path, "init", "-q").returncode == 0
    git(tmp_path, "config", "user.name", "Tester")
    git(tmp_path, "config", "user.email", "tester@example.com")
    commit = git(tmp_path, "commit", "-q", "--allow-empty", "-m", "x")
    assert commit.returncode == 0, commit.stderr
    for key in ("commit.gpgsign", "tag.gpgsign", "gpg.format", "user.signingkey"):
        got = git(tmp_path, "config", "--get", key)
        assert got.returncode == 1 and got.stdout == "", (key, got.stdout)
    leaked = [n for n in os.environ if n.startswith("GIT_CONFIG_") and n not in (
        "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_SYSTEM")]
    assert leaked == []
'''


def pollute(monkeypatch, tmp_path):
    """Turn signing on through the global file, the system file,
    GIT_CONFIG_COUNT/KEY_n/VALUE_n and GIT_CONFIG_PARAMETERS at once."""
    polluted = tmp_path / "polluted-gitconfig"
    polluted.write_text(POLLUTED_CONFIG)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(polluted))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(polluted))
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)
    env_config = {
        "commit.gpgsign": "true",
        "gpg.format": "ssh",
        "user.signingkey": MISSING_KEY,
    }
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(env_config)))
    for n, (key, value) in enumerate(env_config.items()):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{n}", key)
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{n}", value)
    monkeypatch.setenv(
        "GIT_CONFIG_PARAMETERS",
        f"'commit.gpgsign'='true' 'user.signingkey'='{MISSING_KEY}'",
    )
    # Never reach a real signing agent (Secretive / Touch ID), even in the
    # control run that is expected to fail.
    monkeypatch.setenv("SSH_AUTH_SOCK", str(tmp_path / "no-agent.sock"))


def run_inner(pytester):
    pytester.makepyfile(test_inner=INNER_TEST)
    return pytester.runpytest_subprocess("-p", "no:cacheprovider", "-p", "no:xdist")


# == AC/DoD ==


def test_conftest_isolates_git_from_polluted_config(pytester, monkeypatch, tmp_path):
    """TASK-74#2 TASK-74#1 TASK-74#B1: under a fully polluted git config the
    real conftest still gives the inner test an unsigned, clean git."""
    pollute(monkeypatch, tmp_path)
    pytester.makeconftest(CONFTEST.read_text())
    result = run_inner(pytester)
    result.assert_outcomes(passed=1)


def test_polluted_config_breaks_git_without_conftest(pytester, monkeypatch, tmp_path):
    """TASK-74#2 control: the same inner test fails without the conftest, so
    the pollution is real and the passing case proves the fixture works."""
    pollute(monkeypatch, tmp_path)
    result = run_inner(pytester)
    result.assert_outcomes(failed=1)


def test_outer_suite_git_sees_no_user_config(tmp_path):
    """TASK-74#1 TASK-74#B1 TASK-74#3 TASK-74#B2: this suite itself runs under
    the autouse fixture, so the user's signing settings are invisible here and
    a signing test only gets the keys and config it sets itself."""
    assert os.environ["GIT_CONFIG_NOSYSTEM"] == "1"
    assert Path(os.environ["GIT_CONFIG_GLOBAL"]).read_text() == ""
    for name in os.environ:
        assert not name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
    assert "GIT_CONFIG_COUNT" not in os.environ
    assert "GIT_CONFIG_PARAMETERS" not in os.environ
    got = subprocess.run(
        ["git", "config", "--get", "user.signingkey"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert got.returncode == 1 and got.stdout == ""


# == Coverage ==
