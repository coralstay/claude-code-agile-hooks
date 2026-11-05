---
id: TASK-69
title: testFirst Done 게이트에서 '(수동)'으로 끝나는 AC · DoD는 테스트 표식을 요구하지 않는다(비즈니스 규칙은 예외 없음)
status: To Do
assignee: []
created_date: '2026-10-29T12:21:00Z'
updated_date: '2026-10-29T23:50:00Z'
labels:
  - hooks
dependencies: []
documentation:
  - >-
    https://github.com/coralstay/coralstay-software-factory/tree/task/task-19/design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 결정(2026-10-29, 최상위 TASK-19 A6 · A6 보완): 텍스트가 `(수동)`으로 끝나는 AC와 DoD 항목은 testFirst Done 게이트(require_test_first.py)가 테스트 표식(AC `<ID>#<n>`, DoD `<ID>#D<n>`)을 요구하지 않는다. 표시가 카드에 그대로 드러나므로 '정말 테스트할 수 없는 항목인가'는 계획 리뷰 · 승인 때 사람이 함께 판단한다. 비즈니스 규칙 `<ID>#B<k>`는 예외가 없다. 예외 항목의 예: '각 커밋에 TASK ID', 'README 반영' 같은 절차 항목. 문서만 바꾸는 카드(agent-orchestrator AO-29)가 testFirst Done 게이트에 막힌 일이 계기다. 그래서 DoD뿐 아니라 AC에도 이 예외를 둔다. require_test_layout.py는 표식이 놓인 자리만 검사하므로 바꿀 것이 없다.

이 카드는 최상위 coralstay-software-factory TASK-19의 결정을 구현한다. 커밋 본문에 'Refs: coralstay-software-factory TASK-19'를 적는다.

## 비즈니스 규칙
- B1 (AC #1) 텍스트가 `(수동)`으로 끝나는 AC는 `<ID>#<n>` 표식 없이도 Done 게이트를 통과한다
- B2 (AC #1) `(수동)`이 중간에 있거나 철자 · 괄호가 다르면 예외가 아니다(끝의 공백만 무시한다)
- B3 (AC #2) 텍스트가 `(수동)`으로 끝나는 DoD는 `<ID>#D<n>` 표식 없이도 Done 게이트를 통과한다
- B4 (AC #3) 비즈니스 규칙 `<ID>#B<k>` 표식은 묶인 AC가 `(수동)`이어도 언제나 요구한다
- B5 (AC #4) 소스 편집 게이트에서 체크 안 된 첫 AC가 `(수동)`이면 그 AC 표식은 요구하지 않고, 그 AC에 묶인 규칙 표식만 요구한다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 check_done: 텍스트가 (수동)으로 끝나는 AC는 <ID>#<n> 표식을 요구하지 않는다(끝의 공백만 무시, 중간의 (수동)이나 다른 표기는 예외 아님)
- [ ] #2 check_done: 텍스트가 (수동)으로 끝나는 DoD는 <ID>#D<n> 표식을 요구하지 않는다
- [ ] #3 비즈니스 규칙 <ID>#B<k> 표식은 묶인 AC가 (수동)이어도 Done 게이트에서 언제나 요구한다
- [ ] #4 check_edit: 체크 안 된 첫 AC가 (수동)이면 그 AC 표식은 요구하지 않고 그 AC에 묶인 규칙 표식만 요구한다
- [ ] #5 Done 거부 메시지에 '(수동)으로 끝나는 AC · DoD는 표식 예외'를 안내한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 README(testFirst 설명) · CLAUDE.md.snippet에 (수동) 예외와 규칙은 예외 없음을 반영한다 (수동)
- [ ] #3 각 커밋에 TASK ID와 본문 'Refs: coralstay-software-factory TASK-19', push 전 Done + final summary (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-10-29 '(수동)'이 붙은 DoD는 Done 게이트의 테스트 표식 요구에서 빼기로 했다(A6). 문서 전용 카드가 막히는 일을 겪은 뒤 이 예외를 AC에도 넓혔다(A6 보완). 비즈니스 규칙은 예외로 두지 않는다.

### Objective
- require_test_first.py:504-523 check_done은 card["acs"] · card["rules"] · card["dod"] 전부에 대해 표식 라벨을 만들고, 하나라도 테스트에 없으면 거부한다. 예외 경로가 없다.
- require_test_first.py:389-431 parse_card는 AC · DoD를 (번호, 체크 여부, 텍스트)로 읽는다(AC_RE L80). 텍스트는 그대로 남아 있어 끝의 `(수동)`을 판정할 수 있다.
- require_test_first.py:482-501 check_edit는 체크 안 된 첫 AC의 표식과 그 AC에 묶인 규칙 표식을 요구한다. `(수동)` AC가 먼저 오면 소스 편집이 그 AC에서 막힌다.
- README.md:215-219(testFirst 설명) · 229(표식 위치), CLAUDE.md.snippet:57-60이 'AC · 규칙 · DoD 표식이 모두 있어야 Done'이라고 적는다.
- require_test_layout.py는 표식의 위치(== AC/DoD == 섹션)만 검사한다.
- 이 저장소 .claude-code-agile-hooks.json에는 testFirst가 없다. 그래서 이 저장소의 카드에는 게이트가 걸리지 않고, 테스트는 임시 저장소 픽스처로 한다.

### Assessment
parse_card가 항목마다 manual 플래그(텍스트 끝이 `(수동)`인가)를 같이 반환하게 한다. 그러면 check_done · check_edit가 그 플래그로 라벨을 거른다. 규칙(rules)은 거르지 않는다. 다른 표기(전각 괄호 · '(manual)')는 받지 않는다. 오타로 예외가 생기는 것보다 거부되는 편이 안전하다. 바꿀 훅이 require_test_first 하나뿐이고 공유 함수(REGISTRY)는 건드리지 않는다.

### Plan
1. AC #1 · #2 · #3: check_done 테스트 먼저((수동) AC · DoD 통과, 중간 (수동) 거부, 규칙 예외 없음), 그다음 구현.
2. AC #4: check_edit 테스트 먼저, 구현.
3. 거부 메시지에 (수동) 예외 안내, README · CLAUDE.md.snippet, coverageCommand 100%.
<!-- SECTION:PLAN:END -->
