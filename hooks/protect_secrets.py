#!/usr/bin/env python3
# ---
# title: protect_secrets
# description: .env·SSH 키·클라우드 자격 증명 같은 비밀 파일의 읽기·수정·유출을 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Read|Edit|Write|Bash)
Prevent reading, modifying, or exfiltrating secret files (.env, SSH keys,
cloud credentials, keystores). Ported from karanb192/claude-code-hooks'
protect-secrets plugin (MIT license), originally ported 2025-ish from an
older snapshot of that upstream.

Covers the Bash-level bypass (grep/cat/cp on a protected file, not just the
Read/Edit/Write tools directly) since that's the documented real-world gap
this plugin fixed upstream.

2026-09-19: re-synced with upstream main (karanb192/claude-code-hooks,
plugins/protect-secrets/protect-secrets.js) to add delegation-sink
detection — secret files/vars handed to an external model CLI (gemini,
codex, llm, sgpt, aichat, openai, mods, fabric) or POSTed to a known model
API host (api.openai.com, api.anthropic.com, etc). Simplified from
upstream's SINK_CLI/SINK_HOST/SECRET_VAR regex machinery (no SAFETY_LEVEL
tiers, no ask-mode) to fit this file's existing token/substring-matching
style rather than a 1:1 port.

HOOK_SAFETY_LEVEL: critical|high|strict (default: high).

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import sys

PROTECTED_PATTERNS = [  # ---- 1
    r"(^|/)\.env(\.[a-zA-Z0-9_.-]+)?$",
    r"(^|/)\.aws/credentials$",
    r"(^|/)\.ssh/id_[a-zA-Z0-9]+$",
    r"\.pem$",
    r"(^|/)\.npmrc$",
    r"(^|/)\.netrc$",
    r"\.pfx$",
    r"\.keystore$",
    r"(^|/)secrets?\.ya?ml$",
]

PROTECTED_RE = re.compile("|".join(f"(?:{p})" for p in PROTECTED_PATTERNS))

# --- delegation-sink detection (ported from upstream SINK_CLI/SINK_HOST/SECRET_VAR) ---

_SINK_CLI = r"(?:gemini(?:-cli)?|codex|llm|sgpt|aichat|openai|mods|fabric)"  # ---- 2
SINK_CLI_RE = re.compile(  # ---- 3
    r"(?:^|[\s|;&(`\"'!])" + _SINK_CLI + r"(?=[\s<]|$)",
    re.IGNORECASE,
)

SINK_HOST_RE = re.compile(  # ---- 4
    r"(?:generativelanguage\.googleapis\.com|aiplatform\.googleapis\.com|"
    r"api\.openai\.com|[\w.-]+\.openai\.azure\.com|api\.anthropic\.com|"
    r"openrouter\.ai|api\.mistral\.ai|api\.groq\.com|api\.together\.xyz|"
    r"api\.deepseek\.com|api\.x\.ai|api\.cohere\.com|api\.perplexity\.ai|"
    r"api\.fireworks\.ai|api\.cerebras\.ai|router\.huggingface\.co|"
    r"bedrock-runtime(?:-fips)?\.[\w-]+\.amazonaws\.com|"
    r"integrate\.api\.nvidia\.com|api\.deepinfra\.com)",
    re.IGNORECASE,
)

SECRET_VAR_RE = re.compile(  # ---- 5
    r"\$\{?[A-Z0-9_]*(?:SECRETS?|KEY|TOKEN|PASSWORD|PASSWD|PASSPHRASE|PASS|"
    r"CREDENTIALS?|API_KEY|APIKEY|PAT)[A-Z0-9_]*\}?",
    re.IGNORECASE,
)


def is_protected_path(path):
    if not path:
        return False
    normalized = path.replace("\\", "/")
    return bool(PROTECTED_RE.search(normalized))


def bash_targets_protected_file(command):
    """Best-effort: does any whitespace-delimited token in this shell command
    look like a protected file path (covers `grep -r . .env`, `cat .env`,
    `cp .env /tmp`, etc.). Token-based rather than a single substring search
    so the `$`-anchored patterns in PROTECTED_PATTERNS still work correctly
    against a multi-argument command line."""
    if not command:
        return False
    tokens = re.split(r"\s+", command)  # ---- 6
    return any(is_protected_path(tok) for tok in tokens)


def bash_targets_delegation_sink(command):
    """Does this command look like it hands a secret file or secret-named
    env var off to an external model CLI or a known model API host? Covers
    both directions upstream tracks: `gemini -p "..." < .env`,
    `cat .env | codex`, `llm "$OPENAI_API_KEY"`, and
    `curl https://api.openai.com/... -d "key=$STRIPE_SECRET_KEY"`.

    This is a coarse whole-command heuristic (secret reference anywhere +
    sink reference anywhere), not a data-flow analysis — see README known
    limitations for what it structurally can't catch."""
    if not command:
        return False
    has_secret = bash_targets_protected_file(command) or bool(
        SECRET_VAR_RE.search(command)
    )
    if not has_secret:
        return False
    return bool(SINK_CLI_RE.search(command)) or bool(SINK_HOST_RE.search(command))  # ---- 7


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}

    if tool_name in ("Read", "Edit", "Write"):
        path = tool_input.get("file_path", "")
        if is_protected_path(path):
            deny(f"[protect-secrets] 보호된 파일입니다, 접근이 차단되었습니다: {path}")

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if bash_targets_protected_file(command):
            deny(
                f"[protect-secrets] 보호된 파일을 건드리는 명령으로 보여 차단되었습니다: {command}"
            )
        if bash_targets_delegation_sink(command):  # ---- 8
            deny(
                f"[protect-secrets] 시크릿이 외부 모델 CLI/API로 흘러가는 명령으로 보여 차단되었습니다: {command}"
            )

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 보호 대상 파일 패턴
#   설명: dotenv 계열, `~/.aws/credentials`, `~/.ssh/id_*`, `*.pem`, `.npmrc`, `.netrc`, `*.pfx`, `*.keystore`, `secrets.y(a)ml`. 모두 경로 끝(`$`)에 고정해 둔 패턴이다.
# 2 외부 모델 CLI 목록
#   설명: 비밀이 진짜 유출 경로 대신 넘어갈 수 있는 외부 모델 CLI(업스트림의 SINK_CLI).
#   관련: THIRD_PARTY_NOTICES.md (karanb192/claude-code-hooks protect-secrets)
#   개념: delegation sink: 비밀을 외부 모델에 맡기는 도착점
# 3 CLI는 명령어 단어로만 매칭
#   설명: 문자열의 처음이나 셸 구분자·따옴표 뒤의 단어로만 잡는다. 그래서 글 안의 'openai'는 걸리지 않고 파이프로 CLI에 넘기거나 `; codex ...`처럼 부르는 경우는 걸린다(업스트림 SINK_PREFIX/SINK_END를 단순화).
# 4 모델 API 호스트 목록
#   설명: 비밀을 POST할 수 있는 호스팅 LLM API 호스트(업스트림의 SINK_HOST). 새 호스트는 이 정규식에 직접 더해야 한다.
# 5 비밀처럼 보이는 환경 변수 이름
#   설명: `$OPENAI_API_KEY`, `${DB_PASSWORD}`, `$GH_TOKEN` 같은 이름(업스트림 SECRET_WORD/SECRET_VAR).
# 6 토큰 단위로 경로 검사
#   설명: 단일 부분 문자열 검색 대신 공백으로 나눈 토큰마다 검사해야 `$`로 끝을 고정한 PROTECTED_PATTERNS가 여러 인자가 붙은 명령줄에서도 맞게 동작한다. cat·grep -r·cp 같은 Bash 경로의 접근을 잡는다.
# 7 비밀 참조와 도착점이 함께 있으면 차단
#   설명: 명령 어디에든 비밀 참조가 있고 어디에든 싱크 참조가 있으면 차단하는 거친 휴리스틱이다. 데이터 흐름 분석이 아니므로 구조적으로 못 잡는 경우가 있다(README의 알려진 한계 참고).
#   관련: README.md
# 8 Bash 우회까지 막는다
#   설명: Read/Edit/Write 도구뿐 아니라 grep·cat·cp 같은 Bash 경로로 보호 파일을 건드리는 것도 막는다. 업스트림이 고친 현실의 구멍이 바로 이것이다.
