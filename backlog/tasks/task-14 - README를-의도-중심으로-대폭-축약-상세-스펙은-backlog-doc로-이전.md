---
id: TASK-14
title: 'README를 의도 중심으로 대폭 축약, 상세 스펙은 backlog doc로 이전'
status: Done
assignee: []
created_date: '2026-09-19 04:45'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-1
dependencies: []
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README.md를 60줄 안팎으로 축약 — 의도 문장, 왜/어떻게 요약, 훅 구성 개요, 설치 명령, 상세 자료 포인터만 남김
- [x] #2 기존 README의 0/2~12장 상세 내용(운영-개인 레포 맥락, 설치 메커니즘, Phase 명세, HIL 표, 훅 스펙 표, 설정 예시, 알려진 한계, 설치/삭제, 파일 구성)을 backlog doc로 이전해 정보 손실 없이 보존
- [x] #3 README에서 새 backlog doc, 삽질기록.md, doc-1, decision-1~5, draft-1/2로 가는 포인터 정리
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
README.md를 677줄에서 33줄로 축약 — 의도 문장, 왜(기계적 강제 vs 사람 판단 한 문단 요약), 뭐가 있나(28개 훅 개요), 설치 명령, 포인터 5개만 남김. 기존 README의 0/2~12장(운영-개인 레포 맥락, Phase 명세, HIL 표, 훅 28개 스펙, 설정 예시, 알려진 한계, 설치/삭제, 파일 구성)은 손실 없이 backlog doc-2(claude-rails 상세 레퍼런스)로 이전. README에서 doc-2/삽질기록.md/doc-1/decision-1~5/draft-1~2로 가는 포인터 정리.
<!-- SECTION:FINAL_SUMMARY:END -->
