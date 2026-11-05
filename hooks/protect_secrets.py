#!/usr/bin/env python3
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

PROTECTED_PATTERNS = [
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

# External model CLIs a secret could be handed off to instead of a real
# exfiltration channel (upstream: SINK_CLI).
_SINK_CLI = r"(?:gemini(?:-cli)?|codex|llm|sgpt|aichat|openai|mods|fabric)"
# Matched as a command word (start of string, or after a shell separator/
# wrapper-ish punctuation), not as an arbitrary substring — so "openai" in
# prose doesn't trip it, but "cat .env | gemini" or "; codex ..." do
# (upstream: SINK_PREFIX/SINK_END, simplified).
SINK_CLI_RE = re.compile(
    r"(?:^|[\s|;&(`\"'!])" + _SINK_CLI + r"(?=[\s<]|$)",
    re.IGNORECASE,
)

# Known hosted-LLM API hosts a secret could be POSTed to (upstream: SINK_HOST).
SINK_HOST_RE = re.compile(
    r"(?:generativelanguage\.googleapis\.com|aiplatform\.googleapis\.com|"
    r"api\.openai\.com|[\w.-]+\.openai\.azure\.com|api\.anthropic\.com|"
    r"openrouter\.ai|api\.mistral\.ai|api\.groq\.com|api\.together\.xyz|"
    r"api\.deepseek\.com|api\.x\.ai|api\.cohere\.com|api\.perplexity\.ai|"
    r"api\.fireworks\.ai|api\.cerebras\.ai|router\.huggingface\.co|"
    r"bedrock-runtime(?:-fips)?\.[\w-]+\.amazonaws\.com|"
    r"integrate\.api\.nvidia\.com|api\.deepinfra\.com)",
    re.IGNORECASE,
)

# Env var names that look like secrets (upstream: SECRET_WORD/SECRET_VAR),
# e.g. $OPENAI_API_KEY, ${DB_PASSWORD}, $GH_TOKEN.
SECRET_VAR_RE = re.compile(
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
    tokens = re.split(r"\s+", command)
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
    return bool(SINK_CLI_RE.search(command)) or bool(SINK_HOST_RE.search(command))


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
        if bash_targets_delegation_sink(command):
            deny(
                f"[protect-secrets] 시크릿이 외부 모델 CLI/API로 흘러가는 명령으로 보여 차단되었습니다: {command}"
            )

    sys.exit(0)


if __name__ == "__main__":
    main()
