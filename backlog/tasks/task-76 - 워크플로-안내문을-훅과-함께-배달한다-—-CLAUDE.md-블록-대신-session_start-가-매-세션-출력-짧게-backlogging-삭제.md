---
id: TASK-76
title: >-
  워크플로 안내문을 훅과 함께 배달한다 — CLAUDE.md 블록 대신 session_start 가 매 세션 출력, 짧게,
  /backlogging 삭제
status: Done
assignee: []
created_date: '2026-11-21T04:23:00Z'
updated_date: '2026-11-22T11:00:00Z'
labels:
  - workflow
  - docs
dependencies: []
references:
  - TASK-75
documentation:
  - /Users/flynn_macpro/.claude/plans/agile-hooks-workflow-guide-delivery.md
  - README.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
유저(2026-11-18): 훅(강제)과 ~/.claude/CLAUDE.md 의 워크플로 안내문이 어긋나 있다. 안내문은 짧게 두고 상세 규칙은 README 와 훅 차단 메시지가 맡는다(반대 관점). /backlogging 언급은 지운다. 배달 방식은 'session_start 훅이 항상 출력'.
- 원인: install.sh 는 훅(hooks/*.py)은 매번 덮어쓰지만 안내문(CLAUDE.md.snippet)은 ~/.claude/CLAUDE.md 마커 블록에 처음 한 번만 붙인다 → 블록이 2026-10-11 판(39줄 + 유저 수정)에서 멈췄고 저장소 원본은 101줄로 늘었다. 이번 세션에서 SOAP·단계 커밋·작업 순서·서명·테스트 파일 구조·설계 전파 규칙을 모두 훅에 막힌 뒤에야 알았다.
- 이미 있는 것: hooks/session_start.py 가 backlog 프로젝트 안에서 시작한 세션에만 backlog instructions overview 를 additionalContext 로 넣는다.
계획: ~/.claude/plans/agile-hooks-workflow-guide-delivery.md (승인됨)

## 범위
- hooks/workflow_guide.md(새, 약 20줄): 훅이 막으면 메시지대로·우회 금지, 브리핑 → plan mode → draft(SOAP·AC·DoD) → 승격·ref·doc, Plan-Approved 는 사람 키(Claude 는 안 만듦), 실행 순서·단계 커밋·범위 밖은 묻기, 대상 저장소·리터럴 경로, 완료·push·병합은 사람, 상세는 README. /backlogging·포팅 메모 없음
- session_start.py: 세션 위치와 무관하게 항상 안내문 출력, 프로젝트면 overview·무결성 경고를 이어 붙임, 안내문 없으면 조용히 건너뜀
- CLAUDE.md.snippet 삭제, install.sh 3단계 삭제 → 옛 마커 블록이 남아 있으면 지우라는 안내만
- README: 안내문 배달 방식 절, 빠지는 상세 규칙이 README 에 다 있는지 대조
- 테스트: snippet 문구 단언 4곳을 README·안내문 대상으로

## 비즈니스 규칙
- B1 (AC #1) 안내문은 README 에 없는 규칙을 두지 않는다(README 가 SSOT)
- B2 (AC #2) 안내문은 세션 위치와 무관하게 매 세션 출력되고 실패해도 세션을 막지 않는다
- B3 (AC #3) install 은 사용자의 ~/.claude/CLAUDE.md 를 쓰거나 지우지 않는다(안내만)
- B4 (AC #1) 안내문은 짧게 유지한다(줄 수 상한 테스트)

## 유저가 할 일(병합 후)
install.sh 재실행 → ~/.claude/CLAUDE.md 1~39행(마커 블록) 삭제(백업은 미리). 서브에이전트·다이어그램 원칙은 그대로.

## 하지 않는 것
README 상세 규칙 재작성, 블록 밖 유저 원칙
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 hooks/workflow_guide.md 가 승인된 계획의 항목(훅 메시지대로·우회 금지, 계획 → draft → 승격, 사람 서명, 실행·단계 커밋·범위 밖 질문, 대상 저장소·리터럴 경로, 완료·push·병합, 상세는 README)을 짧게(줄 수 상한) 담고 /backlogging 이 없다. 안내문의 규칙은 모두 README 에 있다(B1·B4)
- [x] #2 session_start.py 가 세션 위치와 무관하게 매번 안내문을 additionalContext 로 내고, backlog 프로젝트 안이면 기존 overview·무결성 경고를 이어 붙이며, 안내문이 없거나 읽기에 실패해도 세션을 막지 않는다(B2)
- [x] #3 CLAUDE.md.snippet 을 지우고 install.sh 는 ~/.claude/CLAUDE.md 를 쓰지 않는다. 옛 마커 블록이 남아 있으면 지우라는 안내만 출력한다(B3)
- [x] #4 README 의 안내문 배달 설명을 고치고, snippet 문구를 단언하던 테스트 4곳을 README·안내문 대상으로 바꾼다
- [x] #5 설계 문서·상세 레퍼런스에서 CLAUDE.md.snippet 언급(design/3-아키텍처-설계서/01-시스템-구성.md, 02-동작-명세.md, design/4-구현-계획서/03-미결-사항.md, backlog/docs/doc-2)을 새 배달 방식(hooks/workflow_guide.md + session_start)으로 고친다(유저 결정 2026-11-21: 이번 카드에서 마무리)
- [x] #6 안내문 첫 문장이 실제 동작과 맞다: 카드 워크플로 강제는 backlog 프로젝트(저장소 루트에 backlog/config.yml)를 대상으로 하는 작업에만, 그 밖에서는 범용(안전) 훅만 작동한다고 적는다(유저 결정 2026-11-22)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 coverageCommand 통과·커버리지 100%(line + branch) 출력을 Notes 에 첨부
- [x] #2 [수동 검증] 설치 후 새 세션(비프로젝트 cwd·프로젝트 cwd 각각)에서 안내문이 보이는지 확인
- [x] #3 source-header lint --strict 0
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저(2026-11-18)가 훅과 CLAUDE.md 워크플로 안내문의 불일치를 풀자고 했다. 안내문은 짧게, 상세는 README·훅 메시지(반대 관점), /backlogging 삭제, 배달은 session_start 훅이 항상 출력.

### Objective
- install.sh: hooks/*.py 는 매번 cp, CLAUDE.md.snippet 은 마커가 없을 때만 ~/.claude/CLAUDE.md 에 덧붙임(install.sh:54-58). 설치된 블록은 2026-10-11 판, 저장소 원본은 101줄.
- session_start.py: is_backlog_project(cwd) 일 때만 backlog instructions overview 를 additionalContext 로 낸다.
- snippet 문구를 단언하는 테스트: test_require_stage_committed.py:251, test_require_implementation_plan.py:713, test_require_design_propagation.py:809, test_require_test_layout.py:285.

### Assessment
안내문을 훅과 같은 폴더에 두고 session_start 가 매 세션 출력하면 설치 경로가 하나가 되어 구조적으로 어긋날 수 없다. 사용자의 CLAUDE.md 는 install 이 건드리지 않는다(안내만). 짧은 안내문 + README SSOT + 차단 메시지로 역할을 나눈다.

### Plan
1. 테스트 먼저: 안내문 내용·길이·/backlogging 없음, session_start 비프로젝트/프로젝트/파일 없음, install 이 CLAUDE.md 를 쓰지 않음, 문서 단언 4곳 이동 — 실패 확인.
2. workflow_guide.md 작성, session_start.py 수정, install.sh 3단계 교체, snippet 삭제, README.
3. coverageCommand 100%, lint.
4. 유저 설치 → 새 세션 두 곳에서 확인 → Done·PR.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## 2026-11-21 구현·검증 (서브에이전트 구현, 아래는 내가 직접 다시 돌린 결과)
- 커밋: 0d9f7ca(테스트) → 3e461ba(workflow_guide.md·session_start) → bb35a62(install.sh·snippet 삭제) → c88e892(README)
- 테스트 먼저(서브에이전트 기록): 전체 22 failed(새 테스트 20 + README·install 단언) → 구현 후 통과
- coverageCommand: 3293 passed, TOTAL 7426 stmts·3514 branches 100%. source-header lint --strict rc=0
- 손 실행: echo '{"cwd":"/private/tmp"}' | python3 hooks/session_start.py → 비프로젝트 위치에서도 안내문 19줄 출력, /backlogging 없음
- 안내문은 프론트매터를 떼고 출력, 없거나 못 읽으면 조용히 건너뜀. 프로젝트면 overview 를 뒤에 붙임
- install.sh: CLAUDE.md 를 쓰지 않음, 안내문 복사, 옛 마커 블록이 있으면 안내만. 유저는 2026-11-21 이미 ~/.claude/CLAUDE.md 1~39행 블록을 지움(백업 ~/githubs-backup/2026-11-21-CLAUDE.md.bak)
- snippet 에서 README 로 옮긴 규칙: 브리핑 명령, plan mode 먼저, 승격 직후 ref·doc, 승인 전 실행 금지, task view 선행, AC 단위 반복, testCommand, 미커밋 턴 종료 금지, 범위 밖 질문, 완료 순서, Done 뒤 push, 병합은 사람, 훅 메시지대로·우회 금지
- 남은 낡은 언급(범위 밖, 유저 판단): design/3-아키텍처-설계서/01-시스템-구성.md:21, 02-동작-명세.md:28, design/4-구현-계획서/03-미결-사항.md:35, backlog/docs/doc-2 …:815 가 CLAUDE.md.snippet 을 언급
- 남은 것: DoD #2(설치 후 새 세션 두 곳에서 안내문 확인) — 유저

## 2026-11-21 AC #5
- design/3-아키텍처-설계서/01-시스템-구성.md: '지침 블록 CLAUDE.md.snippet' 행을 '워크플로 안내문 hooks/workflow_guide.md'(session_start 가 매 세션 주입, 훅과 함께 설치) 행으로, 설치 행에 'CLAUDE.md 는 쓰지 않음'
- 02-동작-명세.md 원천: hooks/workflow_guide.md(TASK-76 전에는 CLAUDE.md.snippet)
- 03-미결-사항.md Q-1 ⑤: 안내문 첫 문단으로 반영했다고 기록(안내는 강제가 아니라 ①~④는 남음)
- doc-2: backlog doc update 로 파일 구성 트리에서 snippet 을 빼고 hooks/workflow_guide.md 추가(CLI 가 파일 이름을 제목에 맞춰 claude-code-agile-hooks-상세-레퍼런스.md 로 바꿈, 내용 변경은 그 두 줄과 프론트매터 날짜뿐)
- 저장소에 남은 CLAUDE.md.snippet 언급은 '없어야 한다'고 단언하는 테스트 3곳과 이력 설명뿐. 테스트 3293 passed, lint rc=0

## 2026-11-22 설치 후 새 세션 확인 (DoD #2)
- 유저가 install.sh 실행(2026-11-21 14:18 KST, ~/.claude/hooks/…/workflow_guide.md·session_start.py 가 저장소와 cmp 동일, ~/.claude/CLAUDE.md 에 옛 마커 블록 0건)
- 설치된 훅 직접 실행(SessionStart 페이로드): ~/githubs → 안내문 19줄, ~/githubs/dev-tools/dev-toolchain → 안내문 + backlog overview 61줄
- 실제 새 세션: 'cd ~/githubs && claude -p …'(헤드리스 새 세션)에게 시작 맥락을 물었더니 '## Backlog.md 워크플로 (claude-code-agile-hooks)'와 '1. **브리핑**: …' 줄을 그대로 옮겨 적음
- 유저가 '새 터미널에서 안내문이 안 보인다'고 한 것: SessionStart additionalContext 는 터미널 화면에 표시되지 않고 Claude 맥락으로만 들어간다. 그리고 그때 연 세션(~ , 첫 기록 2026-11-21T04:19Z)은 설치(05:18Z) 전에 시작된 세션을 이어 연 것이었다(설치 후 새로 시작된 세션 기록 없음)
- 부수 발견: 다른 SessionStart 훅(standup-autopilot 등) 출력이 32KB 를 넘어 잘려 파일로 저장된다. 안내문은 별도 블록이라 온전히 들어왔다

## 2026-11-22 AC #6
- 안내문이 모든 세션에 들어가게 되면서 첫 문장('이 환경은 … 강제한다')이 비프로젝트 위치에서는 실제보다 강했다. 'backlog 프로젝트(저장소 루트에 backlog/config.yml)를 대상으로 하는 작업은 카드 워크플로를 훅이 강제하고, 그 밖에서는 안전 훅만 작동한다'로 고침
- 테스트 먼저: test_guide_opening_states_where_the_card_gates_apply 실패 확인 → 수정 후 통과. 전체 3294 passed, 100%, lint rc=0
- 설치본 갱신은 유저의 install.sh 재실행 필요
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
워크플로 안내문을 ~/.claude/CLAUDE.md 에 한 번 붙이던 방식(CLAUDE.md.snippet)을 없애고, 훅 폴더의 hooks/workflow_guide.md(19줄)를 session_start 훅이 세션 위치와 무관하게 매 세션 맥락으로 넣게 했다. 안내문이 훅과 함께 설치되므로 훅과 판이 어긋나지 않는다. 안내문은 짧게 두고(30줄 상한 테스트) 상세 규칙은 README 가 SSOT, /backlogging·낡은 포팅 메모는 뺐다. install.sh 는 사용자의 CLAUDE.md 를 쓰지 않고 옛 블록이 있으면 안내만 한다. 설계 문서·상세 레퍼런스의 snippet 언급도 고쳤다. 테스트 3293·커버리지 100%, 실제 새 세션이 안내문을 받는 것을 확인했다.
<!-- SECTION:FINAL_SUMMARY:END -->
