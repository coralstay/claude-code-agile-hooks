---
id: DRAFT-11
title: >-
  수동 검증 Done 게이트: [수동 검증] 항목은 증거 줄 + 사람 서명 Manual-Verified(Card-Digest)로 통과, 승인
  시점 대비 변경 · 브랜치 무관 Done 차단
status: Draft
assignee: []
created_date: '2026-11-05T18:56:00Z'
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

## AC 후보
1. [수동 검증] AC · DoD는 증거 줄이 있으면 표식 없이 통과, 없으면 빠진 증거를 나열해 거부
2. 근거 없는 증거 줄(표식만 · 설명만)은 증거로 치지 않는다
3. 수동 AC에 묶인 규칙은 증거 줄로, 자동 AC에 묶인 규칙은 테스트 표식으로 판정
4. 수동 항목이 있는 카드는 사람 서명 Manual-Verified와 일치하는 Card-Digest가 없으면 거부(AI 서명 · digest 불일치 · 다른 카드 ID 구분 메시지)
5. Plan-Approved 시점 대비 수동 표기 추가 · 규칙 재연결 · 항목 삭제 · 문구 변경을 거부
6. 수동 전용 카드의 sourceGlobs 변경을 거부
7. 지금 브랜치의 카드가 아닌 카드의 -s Done도 검사
8. card_gate.py CLI가 훅과 같은 판정을 내고 종료 코드로 알린다
9. README · CLAUDE.md.snippet 반영, 커버리지 100%
<!-- SECTION:DESCRIPTION:END -->
