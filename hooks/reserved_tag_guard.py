#!/usr/bin/env python3
"""Stop
TASK-30: block the turn from ending when the assistant's own final message
contains harness-reserved tags (the ones Claude Code uses to mark output the
*user* produced, e.g. a `!`-prefixed command and its stdout, or messages the
harness injected).

Why: those tags are the transcript's only marker of "the user ran this". If the
assistant emits them itself - even innocently, to render a suggested command -
the transcript forges a trust boundary that other guards and human reviewers
rely on ("the user executed it, not Claude").

Occurrences inside fenced code blocks (``` / ~~~) and inline code spans are
ignored, so explaining the tags in code is fine. Mentioning a tag name in plain
prose without angle brackets is fine too.

Cheap by design: only `last_assistant_message` from the Stop payload is
checked; the transcript is never parsed. `stop_hook_active` -> exit 0 so the
correction turn can never loop.

Applies to every project (not backlog-only).

Fully self-contained: no imports from any other file in this repo."""

import json
import re
import sys

RESERVED_TAGS = (
    "bash-input",
    "bash-stdout",
    "bash-stderr",
    "system-reminder",
    "local-command-stdout",
    "local-command-stderr",
    "command-name",
    "command-message",
    "command-args",
    "persisted-output",
    "task-notification",
    "user-prompt-submit-hook",
)

# <tag>, </tag>, < tag attr="x" >, <tag/>, case-insensitive. The lookahead
# keeps `<bash-inputs>` / `<command-name-x>` from matching.
_TAG_RE = re.compile(
    r"<\s*/?\s*("
    + "|".join(re.escape(t) for t in RESERVED_TAGS)
    + r")(?=[\s/>])[^<>]*>",
    re.IGNORECASE,
)

# Opening fence: optional indentation, 3+ backticks or tildes, then an
# optional info string. (A backtick fence's info string may not contain
# backticks, per CommonMark.)
_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def strip_fenced_blocks(text):
    """Drop every line inside a fenced code block (fence lines included).
    An unclosed fence runs to the end of the text."""
    kept = []
    fence_char = None
    fence_len = 0
    for line in text.split("\n"):
        if fence_char is None:
            m = _FENCE_OPEN_RE.match(line)
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                continue
            kept.append(line)
        else:
            stripped = line.strip()
            if (
                stripped
                and set(stripped) == {fence_char}
                and len(stripped) >= fence_len
            ):
                fence_char = None
        # lines inside a fence are dropped
    return "\n".join(kept)


def strip_inline_code(text):
    """Remove inline code spans: a run of N backticks closed by the next run
    of exactly N backticks. An unmatched run is literal text."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "`":
            out.append(text[i])
            i += 1
            continue
        j = i
        while j < n and text[j] == "`":
            j += 1
        run = j - i
        k = j
        close = -1
        while k < n:
            if text[k] == "`":
                m = k
                while m < n and text[m] == "`":
                    m += 1
                if m - k == run:
                    close = m
                    break
                k = m
            else:
                k += 1
        if close == -1:
            out.append(text[i:j])
            i = j
        else:
            out.append(" ")
            i = close
    return "".join(out)


def find_reserved_tags(text):
    """Return reserved tag names (lowercase, first-seen order, deduplicated)
    appearing outside code in `text`."""
    visible = strip_inline_code(strip_fenced_blocks(text))
    found = []
    for m in _TAG_RE.finditer(visible):
        name = m.group(1).lower()
        if name not in found:
            found.append(name)
    return found


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)

    if data.get("stop_hook_active"):
        sys.exit(0)

    message = data.get("last_assistant_message")
    if not isinstance(message, str):
        sys.exit(0)

    tags = find_reserved_tags(message)
    if not tags:
        sys.exit(0)

    # Backticked so the feedback itself never shows a bare reserved tag.
    listed = ", ".join(f"`<{t}>`" for t in tags)
    deny(
        f"[claude-rails] 직전 응답에 하네스 예약 태그가 들어 있습니다: {listed}\n"
        "이 태그들은 하네스가 사용자가 직접 실행한 명령·출력이나 시스템 주입 메시지를 "
        "표시할 때만 쓰는 형식이라, 어시스턴트가 만들어 내면 '사용자가 실행했다'는 "
        "기록을 위조하는 셈이 됩니다.\n"
        "직전 메시지를 정정하세요: 사용자는 아무것도 실행하지 않았다는 점을 분명히 밝히고, "
        "제안하려던 명령은 펜스 코드블록(```bash)으로 다시 제시하세요. "
        "태그를 설명해야 한다면 인라인 코드나 코드블록 안에만 쓰세요."
    )


if __name__ == "__main__":
    main()
