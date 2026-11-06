# ---
# title: conftest
# description: 테스트의 git 하위 프로세스를 사용자 전역·시스템·환경 변수 git 설정에서 격리하는 pytest 설정
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""TASK-74: keep every git child process of the test suite away from the
user's git configuration.

Tests here create throwaway repos and run `git commit` in them. Without this,
those git processes inherit the user's global ~/.gitconfig (commit.gpgsign=true,
gpg.format=ssh) and the environment-variable config Claude Code injects
(GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n with an AI
user.signingkey), so every test commit asks a real signing agent for a
signature: random exit-128 failures under parallel load and a Touch ID prompt
per commit in a human terminal. Test commits have no reason to be signed.

Environment-variable config applies on top of GIT_CONFIG_GLOBAL, so pointing
the global file at an empty one is not enough: GIT_CONFIG_COUNT/KEY_n/VALUE_n
and GIT_CONFIG_PARAMETERS are removed too. Everything goes through
monkeypatch, so it is undone after each test. Tests that already isolate
themselves set the same variables again, which is harmless. Hook scripts are
not touched: at runtime they must keep reading the user's real config.

Same convention as coding-agent-git-commit-tool tests/isolated_repo.py
child_env() (GF-125)."""

import os
import re

import pytest

ENV_CONFIG_ENTRY = re.compile(r"GIT_CONFIG_(KEY|VALUE)_\d+")


def isolate_git_config(monkeypatch, global_config):
    """Point git at an empty global config, no system config and no
    environment-variable config."""
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    entries = [name for name in os.environ if ENV_CONFIG_ENTRY.fullmatch(name)]
    for name in ["GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", *entries]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def isolated_git_config(monkeypatch, tmp_path_factory):
    isolate_git_config(
        monkeypatch, tmp_path_factory.mktemp("git-isolation") / "gitconfig"
    )
