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

ENV_CONFIG_ENTRY = re.compile(r"GIT_CONFIG_(KEY|VALUE)_\d+")  # ---- 1


def isolate_git_config(monkeypatch, global_config):
    """Point git at an empty global config, no system config and no
    environment-variable config."""
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))  # ---- 2
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    entries = [name for name in os.environ if ENV_CONFIG_ENTRY.fullmatch(name)]
    for name in ["GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", *entries]:
        monkeypatch.delenv(name, raising=False)  # ---- 3


@pytest.fixture(autouse=True)  # ---- 4
def isolated_git_config(monkeypatch, tmp_path_factory):
    isolate_git_config(
        monkeypatch, tmp_path_factory.mktemp("git-isolation") / "gitconfig"
    )

# ======== 노트 ========
# 1 환경 변수 config 항목 패턴
#   설명: Claude Code가 주입하는 GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n 이름을 fullmatch로 골라내기 위한 정규식이다. n의 개수를 미리 알 수 없어서 환경을 훑어 찾아야 한다.
#   관련: isolate_git_config의 entries 수집
# 2 전역 설정 파일을 빈 파일로 교체
#   설명: 사용자 ~/.gitconfig의 commit.gpgsign=true, gpg.format=ssh를 테스트 git 프로세스가 상속하지 않게 한다. 안 그러면 테스트 커밋마다 실제 서명 에이전트를 호출해 병렬 부하에서 exit 128이 무작위로 난다.
#   개념: GIT_CONFIG_GLOBAL
# 3 환경 변수 config 제거
#   설명: GIT_CONFIG_COUNT/KEY_n/VALUE_n/PARAMETERS는 GIT_CONFIG_GLOBAL 위에 덮어 적용되므로 전역 파일을 비우는 것만으로는 AI 서명 키가 남는다. 그래서 따로 지운다. monkeypatch라 테스트가 끝나면 원복된다.
# 4 모든 테스트에 자동 적용되는 격리 픽스처
#   설명: autouse=True라 테스트가 따로 요청하지 않아도 이 디렉터리의 모든 테스트가 격리된 git 설정에서 돈다. 훅 스크립트 자체는 건드리지 않으므로 런타임에는 실제 사용자 설정을 그대로 읽는다.
