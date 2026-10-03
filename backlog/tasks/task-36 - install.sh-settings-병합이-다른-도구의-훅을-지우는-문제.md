---
id: TASK-36
title: 'install.sh: settings 병합이 다른 도구의 훅을 지우는 문제'
status: Done
assignee: []
created_date: '2026-10-03 07:58'
updated_date: '2026-10-03 12:28'
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
- [x] #1 settings 병합이 추가 전용이 된다 — 기존 항목(다른 도구 훅 포함)은 그대로 두고 빠진 claude-rails 항목만 (이벤트, matcher) 그룹에 추가한다
- [x] #2 이미 있는 항목은 중복 추가하지 않아 재실행해도 결과가 같다
- [x] #3 병합 로직을 테스트로 검증한다(다른 도구 훅 보존, 중복 없음, 새 이벤트 추가)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
install.sh의 jq 객체 병합(같은 이벤트 배열을 통째로 교체해 다른 도구 훅을 지움)을 scripts/merge_settings.py의 추가 전용 병합으로 교체했다. merge_hooks는 순수 함수로, (이벤트, matcher, command)로 항목을 식별해 없으면 같은 matcher 그룹에 추가하고, 같은 command가 있는데 if/timeout 등이 다르면 그 자리에서 갱신한다. 삭제는 하지 않는다. CLI는 바뀐 것이 있을 때만 백업 → 임시 파일 → JSON 재검증 → 원자적 교체. jq 의존성 제거. 테스트 16개(다른 도구 훅 보존, 재실행 멱등, 새 이벤트, 그룹 재사용, hooks 키 없음, 비훅 키 보존, 임시 HOME에서 install.sh 두 번 실행 E2E — 옛 install.sh에선 E2E가 실패함을 확인). 테스트 실행: 저장소 루트에서 uvx pytest -q hooks scripts → 776 passed(hooks만은 760). README·doc-2 설치 절 반영. 한계: 저장소에서 훅의 matcher/이벤트가 바뀌면 옛 항목이 남는다(삭제하지 않으므로).
<!-- SECTION:FINAL_SUMMARY:END -->
