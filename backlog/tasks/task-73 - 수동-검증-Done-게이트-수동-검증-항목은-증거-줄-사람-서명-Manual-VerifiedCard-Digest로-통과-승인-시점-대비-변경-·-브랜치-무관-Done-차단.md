---
id: TASK-73
title: >-
  수동 검증 Done 게이트: [수동 검증] 항목은 증거 줄 + 사람 서명 Manual-Verified(Card-Digest)로 통과, 승인
  시점 대비 변경 · 브랜치 무관 Done 차단
status: To Do
assignee: []
created_date: '2026-11-05T18:56:00Z'
updated_date: '2026-11-05T20:12:00Z'
labels:
  - security
  - workflow
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## 배경
유저 결정(2026-11-06, 계획 ~/.claude/plans/giggly-kindling-snowglobe.md 2절 B). TASK-69('(수동)' 끝 표기 예외, 규칙은 예외 없음)와 source-header DRAFT-2('[수동 검증]' 증거 줄)를 대체한다 — 승격하면 TASK-69는 이 카드로 대체됐다고 적고 보관한다.
계기: source-header TASK-20(보관 · 재초기화, 운영 카드)이 Done 게이트에서 테스트 표식을 요구받아 막혔다. 반대로 TASK-3 · 16은 지금 브랜치(task/TASK-20)의 카드가 아니어서 검사 없이 Done이 됐다.
유저 결정: 수동 항목 표기는 '[수동 검증]' 접두어, 수동 카드 Done에는 사람 서명 필수, 수동 AC에 묶인 비즈니스 규칙도 증거 + 사람 서명으로 통과(b), 우회 경로는 모두 막는다.
선행: 사람 서명 지문 고정 draft(DRAFT-10). 대상 저장소 해석은 TASK-67과 맞춘다.

## 제안 규칙
- 표기: AC · DoD 본문이 '[수동 검증]'으로 시작. '(수동)' 끝 표기는 쓰지 않고 쓰던 카드는 바꾼다
- 증거: 수동 AC · DoD와 그 AC에 묶인 규칙은 테스트 표식 대신 Notes의 '- 증거: <ID>#n|#B<k>|#D<n> — …' 줄. 줄마다 재확인 가능한 근거 1개 이상(백틱 명령 · 7자리 이상 해시 · '/' 포함 경로 · URL)
- 사람 서명: 수동 항목이 있는 카드의 Done은 HEAD에서 닿는, 제목이 정확히 'Manual-Verified: <ID>'이고 사람 서명(DRAFT-10 판정)인 커밋이 필요. 본문 'Card-Digest: <sha256>'이 지금 카드(정규화한 AC · DoD · 규칙 · 증거 줄)의 digest와 같아야 한다. 거부 메시지가 수동 항목 · 증거 요약과 서명 명령을 보여 준다
- 승인 시점 비교: Plan-Approved 커밋 시점의 카드와 비교해 [수동 검증] 신규 부착, 규칙-AC 연결 변경, AC · DoD · 규칙 삭제 · 문구 변경이 있으면 거부(다시 Plan-Approved)
- 수동 전용 카드: AC가 모두 수동인데 브랜치가 merge-base 이후 sourceGlobs 파일을 바꿨으면 거부
- 브랜치 무관: -s Done은 지금 브랜치의 카드가 아니어도 그 프로젝트의 카드면 검사
- 검사 CLI: scripts/card_gate.py(work_order.py처럼 설치본 옆). commit-tool pre-push 플러그인과 upkeep CI가 쓴다. 훅은 self-contained를 지키고 card_gate.py와 결과가 같은지 테스트한다
## 비즈니스 규칙
- B1 (AC #1) AC · DoD 본문이 '[수동 검증]'으로 시작할 때만 수동 항목이다(앞 공백만 무시, 다른 표기 · 중간 위치는 수동 아님)
- B2 (AC #2) 증거 줄은 Notes의 '- 증거: <표식…> — <설명>' 줄이고, 설명에 근거(백틱 명령 · 7자 이상 16진 해시 · '/' 포함 경로 · URL) 1개 이상이 있어야 한다
- B3 (AC #3) 수동 AC에 묶인 규칙은 증거 줄로, 자동 AC에 묶인 규칙은 테스트 표식으로 판정한다
- B4 (AC #4) 수동 항목이 있는 카드의 Done은 HEAD에서 닿고 제목이 정확히 'Manual-Verified: <ID>'이며 사람 서명(DRAFT-10 판정)인 커밋이 있어야 한다
- B5 (AC #4) 그 커밋 본문의 'Card-Digest: <sha256>'이 지금 카드의 digest(정규화한 AC · DoD · 규칙 줄과 체크 상태, 증거 줄)와 같아야 한다
- B6 (AC #5) HEAD에서 닿는 가장 최근의 사람 서명 Plan-Approved 커밋 시점 카드와 비교해 [수동 검증] 신규 부착 · 규칙-AC 연결 변경 · AC · DoD · 규칙 삭제나 문구 변경이 있으면 거부하고, 수동 항목이 있는데 그런 승인 커밋이 없어도 거부한다
- B7 (AC #6) AC가 모두 수동인 카드는 브랜치가 기본 브랜치와의 merge-base 이후 sourceGlobs 파일을 바꿨으면 거부한다
- B8 (AC #7) -s Done 검사는 지금 브랜치의 카드가 아니어도 그 프로젝트의 카드면 걸린다
- B9 (AC #8) card_gate.py는 훅과 같은 입력에 같은 판정을 내고, 통과 0 · 거부 1 · 설정 오류 2로 끝난다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 require_test_first: [수동 검증] AC · DoD는 테스트 표식 대신 증거 줄이 있으면 통과하고, 없으면 빠진 증거를 나열해 거부한다
- [ ] #2 근거 없는 증거 줄(표식만 · 설명만 · 근거 없는 설명)은 증거로 치지 않는다
- [ ] #3 수동 AC에 묶인 규칙은 증거 줄로, 자동 AC에 묶인 규칙은 지금처럼 테스트 표식으로 판정한다
- [ ] #4 새 훅 require_manual_verified: 수동 항목이 있는 카드의 Done은 사람 서명 Manual-Verified와 일치하는 Card-Digest가 없으면 거부하고(없음 · AI 서명 · digest 불일치를 구별), 거부 메시지에 수동 항목 · 증거 요약과 서명 명령을 보여 준다
- [ ] #5 Plan-Approved 시점 대비 수동 표기 추가 · 규칙 재연결 · 항목 삭제 · 문구 변경, 승인 커밋 없음을 거부한다
- [ ] #6 AC가 모두 수동인 카드의 브랜치가 sourceGlobs 파일을 바꿨으면 거부한다
- [ ] #7 -s Done은 지금 브랜치의 카드가 아니어도 검사한다(require_test_first · require_manual_verified 둘 다)
- [ ] #8 scripts/card_gate.py CLI가 훅과 같은 판정을 내고 종료 코드로 알리며, 훅과의 판정 일치를 테스트로 고정한다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 [수동 검증] README · CLAUDE.md.snippet · settings.hooks.json(새 훅 등록) · install.sh(card_gate.py 복사)에 반영한다
- [ ] #3 [수동 검증] 설치 후 upkeep TASK-4(운영 카드)로 실제 Done 전환과 거부 시나리오를 확인한다
- [ ] #4 [수동 검증] TASK-69를 이 카드로 대체됐다고 적고 보관한다
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-11-06 운영 카드 Done 규칙을 정했다: 수동 항목은 '[수동 검증]' 접두어, 수동 카드 Done에는 사람 서명 필수, 수동 AC에 묶인 규칙도 증거 + 사람 서명(b), 논의한 우회 경로(B1~B4 카드 변경, C1~C3 서명 재사용 · 빈 증거, 브랜치 무관)를 모두 막는다(계획 ~/.claude/plans/giggly-kindling-snowglobe.md 2절 B).

### Objective
- hooks/require_test_first.py: parse_card(L389)가 AC · DoD · 규칙을 읽고, check_done(L504)이 모든 표식을 요구한다. main()(L524)은 task/<ID> 브랜치의 카드가 In Progress일 때만 검사하고 다른 카드의 -s Done은 건너뛴다(실제로 source-header TASK-3 · 16이 이렇게 통과).
- testFirst 설정이 없는 프로젝트에서는 require_test_first가 아예 걸리지 않는다.
- require_implementation_plan.py의 approval_status가 Plan-Approved 커밋을 찾는다(DRAFT-10이 지문 판정으로 바꾼다).
- 훅은 self-contained(외부 import 없음), 복제 함수는 dedup_drift_guard.REGISTRY로 동일성 검사. work_order.py가 설치본 옆 CLI의 선례.

### Assessment
표식 예외(테스트 쪽)는 require_test_first에, 사람 확인(서명 · digest · 승인 시점 비교 · 수동 전용 카드의 소스 변경)은 새 훅 require_manual_verified에 둔다. 새 훅은 testFirst와 무관하게 backlog 프로젝트면 걸린다 — 사람 확인은 테스트 설정 여부와 상관없어야 한다. digest는 체크 상태까지 묶어 '사람이 본 최종 상태'에 서명하게 한다. 승인 시점 카드는 승인 커밋 트리에서 frontmatter id로 찾는다(제목 변경 대응). 기본 브랜치는 origin/HEAD → main 순으로 정한다. card_gate.py는 두 훅의 판정을 하나로 묶은 CLI로 commit-tool pre-push(DRAFT-22)와 upkeep CI가 쓴다. TASK-69('(수동)' 끝 표기)는 이 카드로 대체한다.

### Plan
1. AC #1~#3: require_test_first 테스트 먼저([수동 검증] AC · DoD · 규칙 증거 판정, 근거 없는 증거 거부, 자동 항목 불변) → 구현.
2. AC #7: 브랜치 무관 Done 검사 테스트 → main()의 브랜치 조건을 '프로젝트의 카드'로 넓힌다.
3. AC #4 · #5 · #6: require_manual_verified 테스트 먼저(임시 저장소 + 사람 · AI 테스트 키, digest 일치 · 불일치, 승인 뒤 카드 변경, 수동 전용 카드의 소스 변경) → 구현, settings.hooks.json 등록.
4. AC #8: scripts/card_gate.py와 훅 판정 일치 테스트 → 구현, install.sh 복사.
5. README · CLAUDE.md.snippet, coverageCommand 100%. 설치 후 upkeep TASK-4로 실전 확인.
<!-- SECTION:PLAN:END -->
