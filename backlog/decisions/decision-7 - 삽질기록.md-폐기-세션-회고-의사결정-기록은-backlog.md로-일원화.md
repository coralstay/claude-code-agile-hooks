---
id: decision-7
title: 삽질기록.md 폐기, 세션 회고/의사결정 기록은 backlog.md로 일원화
date: '2026-09-19 05:10'
status: accepted
---
## Context

`삽질기록.md`(파일 기반 수기 기록)와 backlog.md의 `doc`/`decision`(구조화된 CLI 기반
기록)이 사실상 같은 목적(사고/교훈/판단 기록)으로 중복 운영되고 있었다. 사용자가 명시적으로
"필요없는 내용"이라고 판단해 삭제를 지시했다.

## Decision

`삽질기록.md`를 삭제하고, 앞으로 세션 회고와 의사결정은 전부 `backlog doc`/
`backlog decision`으로만 남긴다. 살아있는 문서(README, doc-2, 활성 코드 주석)의
`삽질기록.md` 링크는 제거하되, 이미 작성된 회고성 언급(doc-1, decision-2의 "삽질기록.md
2026-09-10 교훈이...")은 당시 사실을 기록한 것이라 그대로 둔다.

## Consequences

- 삽질기록.md의 유일한 항목(2026-09-10 is_backlog_project 사례)은 decision-2에 이미
  인용돼 있어 정보 손실은 없다.
- 앞으로 "사고/교훈"이 생기면 파일에 수기로 적지 않고 `backlog decision create`로
  구조화해서 남긴다 — CLI 기반 기록이 검색/조회(`backlog search`, `decision list`)가
  되기 때문에 더 낫다는 판단.
