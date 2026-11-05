#!/usr/bin/env python3
"""ConfigChange (matcher: user_settings|project_settings|local_settings|policy_settings|skills)
Make every mid-session config change loudly visible (default) or block it
outright with CONFIG_WATCH_BLOCK=true. Catches out-of-band settings.json
writes made by something other than the agent itself (config_guard.py
covers the agent's own edits; this covers everything else - e.g. the
CHAINDROP npm worm's persistence trick of rewriting settings.json from a
malicious dependency's postinstall script). Ported from
karanb192/claude-code-hooks' config-watch plugin (MIT license).

The ConfigChange payload schema isn't fully documented upstream, so this
parses defensively: known fields are used if present, and the whole raw
event is always logged regardless.

policy_settings changes are never blocked (managed/enterprise settings are
outside what this session should be overriding) - only warned about.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = os.path.expanduser("~/.claude/hooks-logs/config-watch.jsonl")


def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    config_type = data.get("source") or data.get("config_type") or "unknown"
    file_path = data.get("file_path") or data.get("file") or "unknown"

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config_type": config_type,
        "file_path": file_path,
        "raw": data,
    }
    append_log(record)

    should_block = os.environ.get("CONFIG_WATCH_BLOCK") == "true" and config_type != "policy_settings"

    if should_block:
        deny(f"[config-watch] 세션 중 설정 변경이 감지되어 차단되었습니다: {config_type} ({file_path})")

    print(f"[config-watch] 설정 변경 감지: {config_type} ({file_path})", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
