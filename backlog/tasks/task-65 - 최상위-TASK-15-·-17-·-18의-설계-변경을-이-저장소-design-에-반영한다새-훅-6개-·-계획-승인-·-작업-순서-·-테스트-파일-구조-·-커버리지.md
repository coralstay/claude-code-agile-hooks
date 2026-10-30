---
id: TASK-65
title: 설계 문서로 이 저장소의 현행 동작 방식을 정의한다(코드 기준 있는 그대로) — 최상위 TASK-15 · 17 · 18 · 19 전파 포함
status: To Do
assignee: []
created_date: 2026-10-22 05:52
updated_date: '2026-10-30T11:32:00Z'
labels:
  - design
dependencies: []
references:
  - decision-15
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 지시(2026-10-30): claude-code-agile-hooks를 다시 읽고 이 프로젝트의 동작 방식을 설계 문서부터 정의한다. 코드에만 있고 설계 문서에 빠진 것도 확인해 넣는다. 다음 단계(절차마다 갈래를 골라 쓰는 사람 전용 설정, 별도 카드)의 바탕이 된다 — 이 카드는 갈래를 넣지 않고 지금 main 코드의 동작을 있는 그대로 적는다.

현황(2026-10-30 조사): design/ 21개 장 중 5개(00 · 1.01 · 1.02 · 3.01 · 4.03)만 내용이 있고 TASK-56 무렵(훅 33개, RAIL-019)에서 멈췄다. main(22b5eaf)은 훅 39개 · 등록 58건이고 최상위 2.03은 RAIL-001~025 · BL-001~017을 정의한다. 실제 동작 설명은 README(L296-453) · CLAUDE.md.snippet에만 있다. 훅 수가 문서마다 33 · 32 · 34로 다르고, 사람 판단 지점이 '둘'과 '셋'으로 다르다. decision-13~15 본문이 비어 있고 decision-5 · 13 상태가 실제(superseded)와 다르다.

코드에는 있는데 설계에 없거나 다른 것(4.03에 Q로 등록): ① 새 훅 6개(require_implementation_plan · stage_committed · work_order · test_layout · coverage_on_done · design_propagation) ② 설정 키 humanSigners · coverageReportDir ③ 세션 cwd로 저장소를 판정하는 결함(pre_commit · pre_push · pre_push_coverage · backlog_commit_scope · backlog 명령 훅 8개, 참고 구현 pre_git_safety_check.after_cd) ④ require_active_task는 아무 카드나 In Progress면 통과, 'task view' 검사는 transcript 문자열 ⑤ require_test_first Done 검사는 현재 브랜치 카드에만 ⑥ pre_commit_check 브랜치 규칙은 task/ 접두어만 ⑦ pre_push_coverage_check는 backlog 프로젝트 확인 없이 모든 저장소에 적용, 통과 시 push 자동 허용 ⑧ 설정 JSON 오류 처리가 훅마다 다름 ⑨ config_guard가 .claude-code-agile-hooks.json · allowed_signers · git 서명 설정을 보호하지 않음 ⑩ protect_secrets 문서와 코드 불일치(HOOK_SAFETY_LEVEL) ⑪ auto_stage와 단계 커밋 게이트의 상호작용 미기록 ⑫ 사람 판단 지점 수 불일치.

최상위 TASK-19 결정(A1 · A2 · A5 · A6 · C2 · squash)은 구현 카드 TASK-67~70이 보류 중이라 아직 코드에 없다 — '결정됨 · 미구현'으로 표시해 적는다.

커밋 본문에 'Refs: coralstay-software-factory TASK-15 · TASK-17 · TASK-18 · TASK-19' 중 해당하는 것을 적는다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 3.02 동작 명세: 카드 생애주기 전체(draft 작성 → 커밋 → 승격 → 커밋 → 의존 · 작업 순서 → 커밋 → 계획 승인 → 브랜치 · In Progress → AC 루프 → Done → push)를 단계마다 '어떤 훅이 무엇을 막는지' 표로 적고, 흐름은 DOT, 시퀀스는 mermaid로 그린다 (수동)
- [ ] #2 3.01 시스템 구성: 훅 39개 · 등록 58건과 세 가지 성격 분류를 main에 맞추고 diagrams/01-three-natures.dot을 갱신해 build-diagrams.py로 재렌더한다. 문서 안 훅 수 · 등록 수가 settings.hooks.json과 일치한다
- [ ] #3 3.03 훅별 명세: 훅마다 이벤트 · matcher, 검사 내용, 설정 키 · 환경변수, RAIL ID, 실패 시 동작을 적는다 — 모든 훅이 RAIL ID를 갖는다(00 추적 규칙, ID가 없으면 RAIL-???로 최상위에 요청) (수동)
- [ ] #4 3.04 인터페이스: 훅 입력 payload · 출력(deny · additionalContext · exit code), .claude-code-agile-hooks.json 키 전체(testCommand · coverageCommand · coverageReportDir · testFirst · humanSigners), 환경변수(HOOK_SAFETY_LEVEL · HOOK_AUDIT_* · CONFIG_GUARD_ALLOW · CONFIG_WATCH_BLOCK · CC_* 등), install.sh · merge_settings 동작을 적는다 (수동)
- [ ] #5 2.02 · 2.03: 도메인 모델(카드 · 착수 · 단계 커밋 · 작업 순서 · 승인)과 최상위 RAIL-001~025 · BL-001~017을 훅에 대응시키는 표를 최상위와 같은 ID로 적는다 (수동)
- [ ] #6 3.05 설계 결정: decision-1~15를 ADR로 옮기고 decision-13~15 본문을 채우며 decision-5 · 13 상태를 superseded로 바로잡는다 (수동)
- [ ] #7 4.03 미결 사항: 설명의 ①~⑫(코드에 있으나 설계에 없거나 다른 것 · 알려진 결함)를 Q로 등록하고, 최상위 TASK-19 결정을 '결정됨 · 미구현(TASK-67~70)'으로 적는다 (수동)
- [ ] #8 README · CLAUDE.md.snippet: 동작 설명은 design/의 해당 장을 가리키게 줄이고 README에는 요약 · 설치만 남긴다. 사람 판단 지점 수 등 문서 간 불일치를 없앤다 (수동)
- [ ] #9 각 커밋 본문에 해당 최상위 태스크의 'Refs: coralstay-software-factory TASK-n'을 적는다 (수동)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 design/ 상대 링크 검사에서 깨진 링크가 없다 (수동)
- [ ] #2 문서에 적힌 훅 수 · 등록 수를 settings.hooks.json에서 센 값과 대조한 결과를 노트에 남긴다 (수동)
- [ ] #3 파일 하나에 커밋 하나, 각 커밋에 TASK-65, push 전 Done + final summary (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저는 hooks를 '절차 묶음 + 절차마다 고를 수 있는 갈래 + 사람만 바꾸는 설정'으로 만들기 전에, 이 프로젝트를 다시 읽고 동작 방식을 설계 문서부터 정의하라고 했다(2026-10-30). 코드에만 있는 것도 확인해 넣으라고 했다.

### Objective
- 2026-10-30 읽기 전용 조사 3건: design/는 21개 장 중 5개만 내용이 있고 TASK-56 무렵에서 멈췄다. main은 훅 39개 · 등록 58건이다. 동작 설명은 README · snippet에만 있다.
- 코드 조사 표(훅 · 이벤트 · 절차 · 설정 키 · 결함)가 있다. 설명의 ①~⑫가 그 결과다.
- 최상위 00(문서 계층 · 장 대응표)은 이 저장소 design/가 1~5장과 부록을 모두 갖추고 최상위 ID를 그대로 쓰라고 한다.

### Assessment
갈래 설계(다음 카드)는 '지금 무엇이 어떻게 동작하는가'가 문서로 고정돼야 할 수 있다. 그래서 이 카드는 판단을 섞지 않고 코드를 있는 그대로 적고, 결함 · 불일치는 고치지 않고 Q로 남긴다. README의 중복 설명은 design/로 옮겨 출처를 하나로 만든다.

### Plan
1. 3.02 동작 명세(중심) → 3.01 · 다이어그램 → 3.03 → 3.04 → 2.02 · 2.03 → 3.05 → 4.03 → README · snippet 순으로, 파일 하나에 커밋 하나.
2. 훅 수 · 등록 수 대조, RAIL ID grep, 상대 링크 검사, 다이어그램 재렌더.
3. 서브에이전트에 장 단위로 맡기고 결과를 대조 검증한다.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
착수 조건(유저, 2026-10-22): TASK-58 ~ 63(PR #54 ~ #59) 머지 후. Refs: coralstay-software-factory TASK-15 · TASK-17 · TASK-18

결정 반영(유저, 2026-10-29): 최상위 TASK-19(충돌 A1 ~ A6 · C2 결정)의 전파를 AC #4로 더했다. 기존 AC #1 ~ #3은 그대로다. TASK-19 몫의 커밋에는 본문에 'Refs: coralstay-software-factory TASK-19'를 적는다(TASK-15 · 17 · 18 몫은 AC #3대로). 구현 카드 DRAFT-8 ~ 11(승격 뒤 ID)이 끝난 뒤 실제 동작과 맞춰 반영한다.
<!-- SECTION:NOTES:END -->
