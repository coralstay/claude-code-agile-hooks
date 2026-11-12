#!/usr/bin/env python3
# ---
# title: reserved_tag_guard
# description: 어시스턴트 최종 메시지에 하네스 예약 태그가 있으면 턴 종료를 막는 Stop 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
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

RESERVED_TAGS = (  # ---- 1
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

_TAG_RE = re.compile(  # ---- 2
    r"<\s*/?\s*("
    + "|".join(re.escape(t) for t in RESERVED_TAGS)
    + r")(?=[\s/>])[^<>]*>",
    re.IGNORECASE,
)

# Opening fence: optional indentation, 3+ backticks or tildes, then an
# optional info string. (A backtick fence's info string may not contain
# backticks, per CommonMark.)
_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def strip_fenced_blocks(text):  # ---- 3
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


def strip_inline_code(text):  # ---- 4
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

    if data.get("stop_hook_active"):  # ---- 5
        sys.exit(0)

    message = data.get("last_assistant_message")  # ---- 6
    if not isinstance(message, str):
        sys.exit(0)

    tags = find_reserved_tags(message)
    if not tags:
        sys.exit(0)

    # Backticked so the feedback itself never shows a bare reserved tag.
    listed = ", ".join(f"`<{t}>`" for t in tags)  # ---- 7
    deny(
        f"[claude-code-agile-hooks] 직전 응답에 하네스 예약 태그가 들어 있습니다: {listed}\n"
        "이 태그들은 하네스가 사용자가 직접 실행한 명령·출력이나 시스템 주입 메시지를 "
        "표시할 때만 쓰는 형식이라, 어시스턴트가 만들어 내면 '사용자가 실행했다'는 "
        "기록을 위조하는 셈이 됩니다.\n"
        "직전 메시지를 정정하세요: 사용자는 아무것도 실행하지 않았다는 점을 분명히 밝히고, "
        "제안하려던 명령은 펜스 코드블록(```bash)으로 다시 제시하세요. "
        "태그를 설명해야 한다면 인라인 코드나 코드블록 안에만 쓰세요."
    )


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 하네스 예약 태그 목록
#   설명: 이 태그들은 트랜스크립트에서 '사용자가 실행했다'를 나타내는 유일한 표식이다. 어시스턴트가 직접 내보내면(제안 명령을 그리려는 선의라도) 다른 가드와 사람 검토자가 믿는 신뢰 경계가 위조된다.
#   관련: TASK-30
#   개념: 신뢰 경계: 누가 실행했는지에 대한 기록을 믿을 수 있는 선
# 2 태그 모양 매칭
#   설명: `<tag>`·`</tag>`·`< tag attr="x" >`·`<tag/>`를 대소문자 무관하게 잡는다. 뒤따르는 lookahead가 `<bash-inputs>`나 `<command-name-x>` 같은 비슷한 이름을 걸러 낸다.
# 3 펜스 코드블록은 무시
#   설명: ``` 또는 ~~~ 펜스 안은 검사 대상에서 뺀다. 닫히지 않은 펜스는 글 끝까지 이어진다. 백틱 펜스의 정보 문자열에 백틱이 있으면 펜스가 아니다(CommonMark).
#   개념: CommonMark 펜스 코드블록
# 4 인라인 코드 스팬은 무시
#   설명: N개의 백틱 열이 정확히 N개의 백틱 열로 닫힐 때까지가 코드 스팬이다. 짝이 없는 열은 일반 글자로 둔다. 그래서 태그를 코드로 감싸 설명하는 것은 허용된다.
# 5 교정 턴은 반복 차단하지 않는다
#   설명: stop_hook_active이면 통과시켜 교정 턴이 무한히 거부되는 루프를 막는다. block_stop_if_dirty와 달리 여기서는 교정이 어시스턴트 메시지에 달려 있어 루프 위험이 실제로 있다.
#   관련: hooks/block_stop_if_dirty.py
# 6 마지막 메시지만 검사
#   설명: Stop 페이로드의 last_assistant_message만 본다. 트랜스크립트는 파싱하지 않아 싸고, 모든 프로젝트에 적용된다(backlog 프로젝트 한정이 아님).
# 7 피드백에도 맨 태그를 쓰지 않는다
#   설명: 거부 메시지 자체가 예약 태그를 맨 모양으로 내보내면 같은 위조가 되므로 백틱으로 감싸 보여 준다.
