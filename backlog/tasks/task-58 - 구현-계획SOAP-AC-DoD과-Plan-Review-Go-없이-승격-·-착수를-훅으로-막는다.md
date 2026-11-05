---
id: TASK-58
title: 구현 계획(SOAP + AC + DoD)과 Plan-Review-Go 없이 승격 · 착수를 훅으로 막는다
status: Done
assignee: []
created_date: '2026-10-12 02:24'
updated_date: '2026-10-21 09:05'
labels:
  - hooks
dependencies: []
references:
  - decision-1
  - decision-12
  - decision-13
  - decision-14
documentation:
  - >-
    https://github.com/coralstay/coralstay-software-factory/blob/main/design/3-아키텍처-설계서/05-설계-결정.md#adr-022-구현-계획은-soap--ac--dod-착수-전-plan-review-go
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): Claude가 backlog.md CLI로 일할 때 구현 계획(Implementation Plan) 없이 태스크를 만든다. 이를 훅으로 강제한다.

지금 require_draft_first.py는 task create만 막고(draft 경유 강제), 계획이 있는지는 아무도 보지 않는다. backlog draft create에는 --plan 옵션이 없으므로 draft edit --plan으로 계획을 적은 뒤에야 승격할 수 있게 한다.

유저 결정(2026-10-12):
- 구현 계획은 SOAP 노트 형식 + AC + DoD로 쓴다. backlog.md의 Implementation Plan 항목(--plan)은 항상 SOAP 네 절로 채운다. 카드에는 AC와 DoD가 있어야 한다.
- 각 절에는 항상 제목을 단다. 제목은 프로그래밍 언어의 키워드처럼 고정된 예약어다. 훅은 이 제목으로 절을 찾고, 절이 작성됐는지 검사한다.
- Plan-Review-Go: 태스크가 In Progress로 가기 전에 구현 계획이 작성되고, 사람이 리뷰하고, 승인(go)해야 한다. 그 뒤에만 In Progress로 옮길 수 있다.

## SOAP 예약 제목

Implementation Plan은 아래 네 제목을 이 순서로, 철자 그대로 쓴다(대소문자 · 띄어쓰기 변형은 인정하지 않는다).

| 예약 제목 | 뜻 | 쓰는 내용 |
| --- | --- | --- |
| ### Subjective | 주관적 정보 | 요청 · 배경: 유저가 무엇을 왜 원하는가 |
| ### Objective | 객관적 정보 | 확인한 사실: 코드 · 측정값 · 현재 동작 |
| ### Assessment | 평가 | 판단: 문제가 무엇이고 어떤 접근을 고르는가 |
| ### Plan | 계획 | 구현 순서 |

작성됨 = 제목이 있고, 다음 제목 전까지 공백이 아닌 본문이 있다. 제목이 없거나, 순서가 다르거나, 같은 제목이 두 번 나오거나, 본문이 비어 있으면 작성되지 않은 것으로 본다.

미결(착수 시 결정): 훅은 사람과 Claude를 구분하지 못한다. 그래서 go를 어떻게 기록할지(예: 사람만 붙이는 라벨이나 필드, 사람이 만든 리뷰 파일이나 커밋)는 착수할 때 정한다.

관련: require_draft_first.py(명령 파싱 규칙), decision-1(커맨드 문자열 매칭의 한계), decision-12(테스트 먼저). 설계 문서 반영은 coralstay-software-factory 쪽 후속 draft에서 한다(BL-015 · BL-017 · RAIL-020 예정).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backlog draft promote <ID>는 draft에 비어 있지 않은 Implementation Plan 절이 없으면 deny하고 backlog draft edit <ID> --plan을 안내한다
- [x] #2 backlog task edit <ID> -s "In Progress"는 그 태스크에 구현 계획이 없으면 deny한다(MCP · 웹 UI로 만든 카드에 대한 2차 방어선)
- [x] #3 draft promote와 -s "In Progress"는 Implementation Plan에 SOAP 예약 제목(### Subjective · ### Objective · ### Assessment · ### Plan)이 이 순서로 한 번씩 있고 각 절 본문이 비어 있지 않은지 검사해, 어긋나면 deny하고 빠지거나 비어 있는 제목을 안내한다
- [x] #4 draft promote와 -s "In Progress"는 카드에 AC나 DoD가 없으면 deny한다
- [x] #5 backlog task edit <ID> -s "In Progress"는 그 태스크에 Plan-Review-Go 승인(go)이 기록돼 있지 않으면 deny한다(기록 방식은 미결 항목에서 정한다)
- [x] #6 명령 위치(command position) 파싱은 require_draft_first.py와 같은 규칙을 쓰고, 인용문 · heredoc 안의 문자열은 통과시킨다
- [x] #7 settings.hooks.json 등록 + 테스트, README · CLAUDE.md.snippet에 SOAP 예약 제목 템플릿과 Plan-Review-Go를 반영한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 전체 테스트 통과 · 커버리지 100%(coverageCommand)
- [x] #2 settings.hooks.json 등록 · dedup REGISTRY · 등록 계약 테스트 반영
- [x] #3 push 전 커밋 정리, 각 커밋에 TASK-58
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저는 Claude가 구현 계획 없이 태스크를 만들고 착수하는 것을 막고 싶어 한다. 구현 계획은 SOAP 노트 형식 + AC + DoD로 항상 채우고, 착수 전에 사람이 리뷰하고 go를 줘야 한다(2026-10-12).

### Objective
- require_draft_first.py는 task create만 막는다. 계획 유무 · 형식은 아무 훅도 보지 않는다.
- backlog draft create에는 --plan이 없다. draft edit · task edit의 --plan으로 Implementation Plan 섹션(SECTION:PLAN 마커 사이)을 채운다.
- AC · DoD는 카드 파일의 각 마커 사이에 있고, task view --plain에도 나온다.

### Assessment
새 독립형 훅(hooks/require_implementation_plan.py, decision-3) 하나로 promote · In Progress 두 시점을 막는다. 제목은 예약어로 고정해 문자열 일치로 판정한다. 모호한 자연어 판정을 피하기 위해서다. go 기록 방식은 사람과 Claude를 구분할 수 있는 방식이어야 하므로 착수 시 유저와 정한다.

### Plan
1. go 기록 방식을 유저와 정한다.
2. 훅 파일을 만들고 PreToolUse(Bash)에 등록한다. require_draft_first.py의 command_head · 세그먼트 분할을 복사하고 dedup_drift_guard REGISTRY에 등록한다.
3. promote: backlog/drafts/의 파일에서 SECTION:PLAN 사이를 꺼내 예약 제목 4개(순서 · 중복 · 본문)를 검사한다.
4. 같은 파일에서 AC · DoD 항목이 하나 이상 있는지 검사한다.
5. In Progress: 태스크 파일에 3 · 4를 똑같이 적용하고, go 기록을 확인한다.
6. AC 순서대로 RGR(테스트 먼저)로 구현한 뒤 settings.hooks.json · README · CLAUDE.md.snippet에 SOAP 템플릿을 반영한다.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
착수 시 결정(유저, 2026-10-21) — decision-13: go는 사람이 남기는 빈 서명 커밋(git commit --allow-empty -S -m "Go: <ID>"), 제목이 정확히 'Go: <ID>'. 훅은 그 커밋이 있고 git log --format=%G? 결과가 G(유효한 서명)인지만 본다 — 서명 키 주체는 가리지 않는다(최상위 TASK-17에서 서명 키 전제 삭제). 구현 계획 Plan 1단계는 이것으로 끝남.

후속 결정(유저, 2026-10-21) — 미반영: (1) 용어: go · go 판정 · Plan-Review-Go를 '계획 승인'(plan approval) · '승인 게이트'(approval gate) · '계획 → 리뷰 → 계획 승인'으로 바꾸고, 커밋 제목은 'Plan-Approved: <ID>'. 훅 · 테스트 · README · CLAUDE.md.snippet · decision-13 · 최상위 design/ 전부 대상. (2) 서명: 지금은 사람과 Claude가 같은 키(github_signature)를 쓰고 allowedSignersFile이 없어 모든 커밋이 %G?=N — 이대로면 훅이 사람의 승인 커밋도 막는다. 유저 의도는 'AI가 쓴 건 AI, 사람이 쓴 건 사람'. 두 키 분리(AI 전용 키 + allowed_signers principal 구분 + 사람 키를 Claude가 못 쓰게) 방식 선택 대기. Done 전에 DoD 추가 필요(카드에 DoD 없음).

decision-14(유저, 2026-10-21): 용어 go → 계획 승인, go 판정 → 승인 게이트, Plan-Review-Go → 계획 → 리뷰 → 계획 승인, 커밋 제목 'Plan-Approved: <ID>'. 서명은 두 키로 나눈다 — Claude는 AI 전용 키, 사람은 기존 키(ssh-agent에서 내려 암호 입력 필요). allowed_signers에 principal을 나눠 올리고, 승인 게이트는 %G?=G이고 %GS가 프로젝트 설정 humanSigners 목록에 있을 때만 통과. decision-13을 대체한다.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
구현 계획(SOAP + AC + DoD)과 계획 승인 없이 draft 승격 · 착수하는 것을 막는 독립 훅 hooks/require_implementation_plan.py를 추가했다.

- draft promote: Implementation Plan이 없거나 비면 deny, draft edit --plan 안내(AC #1). task edit -s "In Progress"도 같은 검사(AC #2, MCP · 웹 UI 카드의 2차 방어선)
- SOAP 예약 제목 ### Subjective · ### Objective · ### Assessment · ### Plan — 철자 · 순서 · 중복 · 빈 본문 검사, 템플릿 안내(AC #3). AC · DoD 항목이 없으면 deny(AC #4)
- 승인 게이트(AC #5, decision-14 — decision-13 대체): HEAD에서 닿는 커밋 중 제목이 정확히 'Plan-Approved: <ID>'이고 %G? = G, 서명자 %GS가 프로젝트 설정 humanSigners에 있어야 In Progress 허용. 승인 커밋 없음 · 서명 무효 · 사람이 아닌 서명자를 구분해 안내하고, Claude는 승인 커밋을 만들지 않는다고 명시. humanSigners가 없거나 잘못되면 설정 안내와 함께 deny
- 명령 위치 파싱(require_draft_first.py 규칙 복사, REGISTRY 등록), 인용문 · heredoc 통과, 짝 안 맞는 따옴표는 정규식 대체 판정(AC #6)
- settings.hooks.json 등록, 등록 계약 테스트, README · CLAUDE.md.snippet에 SOAP 템플릿 · 계획 → 리뷰 → 계획 승인 · 두 키 구성 · humanSigners · 남은 위험(로컬 파일 보호 필요) 반영(AC #7)
- 용어: go → 계획 승인, go 판정 → 승인 게이트(유저 결정, 업계 관행 plan approval · approval gate)

검증: uvx … pytest --cov → 1931 passed, TOTAL 4179 stmts · 1710 branches 100%. 실제 ssh 키 3개(human · ai-claude-code · stranger)로 서명 상태별 통합 테스트.
유저 설정 필요: ~/.ssh/allowed_signers(human · ai-claude-code principal), gpg.ssh.allowedSignersFile, Claude Code env의 AI 서명 키, 사람 키 ssh-agent 제외, 프로젝트별 "humanSigners": ["human"]. 설정 전에는 이 훅을 설치하면 모든 In Progress 전이가 막힌다.
<!-- SECTION:FINAL_SUMMARY:END -->
