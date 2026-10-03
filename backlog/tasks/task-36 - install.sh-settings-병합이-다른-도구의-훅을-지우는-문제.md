---
id: TASK-36
title: 'install.sh: settings 병합이 다른 도구의 훅을 지우는 문제'
status: To Do
assignee: []
created_date: '2026-10-03 07:58'
updated_date: '2026-10-03 08:02'
labels:
  - hooks
  - install
dependencies: []
references:
  - decision-3
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
install.sh는 jq -s '.[0] * .[1]'로 settings.hooks.json을 ~/.claude/settings.json에 병합한다. jq의 객체 병합은 배열을 합치지 않고 통째로 교체하므로, 같은 이벤트(PreToolUse, Stop 등)에 다른 도구의 훅이 있으면 사라진다. 2026-10-03 실측: 설치된 settings에 claude-rails가 아닌 훅 11개(iTerm 상태 표시 10개, WebFetch 가드 1개)가 있어 install.sh를 쓰면 모두 지워진다. 스크립트도 경고만 출력하고 그대로 진행한다. 같은 날 일괄 설치는 추가 전용 병합 스크립트로 대신했다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 settings 병합이 추가 전용이 된다 — 기존 항목(다른 도구 훅 포함)은 그대로 두고 빠진 claude-rails 항목만 (이벤트, matcher) 그룹에 추가한다
- [ ] #2 이미 있는 항목은 중복 추가하지 않아 재실행해도 결과가 같다
- [ ] #3 병합 로직을 테스트로 검증한다(다른 도구 훅 보존, 중복 없음, 새 이벤트 추가)
<!-- AC:END -->
