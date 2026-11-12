#!/usr/bin/env python3
# ---
# title: case_insensitive_guard
# description: 대소문자 비구분 파일시스템에서 rm -rf가 다른 대소문자 경로까지 지우는 것을 막는 훅
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# upstream: https://github.com/karanb192/claude-code-hooks
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""PreToolUse (matcher: Bash)
Stop `rm -rf content` from destroying `Content` on a case-insensitive
filesystem (APFS default on macOS, exFAT, NTFS). Ported from
karanb192/claude-code-hooks' case-insensitive-guard plugin (MIT license).

The real hazard: a command deletes path X, but a differently-cased path Y
also exists on disk and the filesystem treats them as the same entry. Since
this hook can't rely on the actual filesystem case-sensitivity setting
(sandboxed here, and we don't want to shell out per invocation for a rare
case), it flags any `rm -rf`-style deletion of a target whose current working
directory contains a sibling entry differing only by case - a cheap, real
check using os.listdir(), not a guess.

Fully self-contained: no imports from any other file in this repo."""

import json
import os
import re
import shlex
import sys

RM_RE = re.compile(r"\brm\b")


def find_case_collision(target, cwd):
    """If `target` (relative to cwd) has a sibling in the same directory that
    matches case-insensitively but not case-sensitively, return that sibling
    name. Otherwise None."""
    if not target or target.startswith("-"):
        return None

    directory, _, name = target.rpartition("/")
    search_dir = os.path.join(cwd, directory) if directory else cwd

    try:
        entries = os.listdir(search_dir)
    except OSError:
        return None

    for entry in entries:
        if entry != name and entry.lower() == name.lower():  # ---- 1
            return entry
    return None


def deny(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    command = (data.get("tool_input") or {}).get("command", "")
    cwd = data.get("cwd", ".")

    if not command or not RM_RE.search(command):
        sys.exit(0)

    try:
        tokens = shlex.split(command)
    except ValueError:  # ---- 2
        sys.exit(0)

    basenames = [os.path.basename(t) for t in tokens]
    if "rm" not in basenames:  # ---- 3
        sys.exit(0)

    rm_index = basenames.index("rm")
    targets = [t for t in tokens[rm_index + 1 :] if not t.startswith("-")]
    for target in targets:
        collision = find_case_collision(target, cwd)
        if collision:
            deny(  # ---- 4
                f"[case-insensitive-guard] '{target}'와(과) 대소문자만 다른 '{collision}'이(가) "
                f"같은 디렉토리에 있습니다. 대소문자 구분 안 하는 파일시스템(APFS/exFAT/NTFS)에서는 "
                f"'{target}' 삭제가 '{collision}'도 함께 지울 수 있습니다: {command}"
            )

    sys.exit(0)


if __name__ == "__main__":
    main()


# ======== 노트 ========
# 1 대소문자만 다른 형제 항목 탐지
#   설명: 파일시스템 설정을 추측하지 않고 실제 os.listdir() 결과에서 이름이 대소문자만 다른 항목을 찾는 값싼 실측이다. 샌드박스에서 파일시스템 대소문자 여부를 알 수 없고 호출마다 외부 명령을 띄우고 싶지도 않아서 이 방식을 쓴다.
#   개념: 대소문자 비구분 파일시스템: APFS 기본값(macOS), exFAT, NTFS
# 2 따옴표가 깨진 명령은 통과
#   설명: shlex가 해석하지 못하는 명령은 판단 근거가 없으므로 막지 않고 통과시킨다. 이 훅은 차단 확신이 있을 때만 거부한다.
# 3 basename으로 rm 판정
#   설명: `/bin/rm`처럼 절대 경로로 부른 `rm`도 같은 이름으로 취급하려고 토큰의 basename을 비교한다.
#   관련: decision-1 (basename 정규화까지만 하고 syscall 수준 강제는 범위 밖)
# 4 충돌이 있으면 삭제 전에 거부
#   설명: 대상과 대소문자만 다른 형제가 같은 디렉터리에 있을 때만 exit 2로 거부한다. 일반 `rm`은 건드리지 않는다.
