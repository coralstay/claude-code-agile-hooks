---
id: TASK-6
title: 복붙된 훅 로직 drift 자동 차단 훅 신설 (dedup_drift_guard)
status: Done
assignee: []
created_date: '2026-09-18 16:18'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - 삽질기록.md
  - hooks/pre_commit_check.py
  - backlog/drafts/draft-1 - is_backlog_project-중복-버그-수정-drift-방지-테스트.md
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
27개 훅은 "완전 독립형(공용 import 없음)" 설계라 동일 로직이 여러 파일에 복붙돼 있다. 삽질기록.md에 기록된 교훈(서브폴더 존재만으로 backlog 프로젝트 오판 금지)이 require_active_task.py 1곳에만 반영되고 나머지 4곳엔 반영 안 된 사례(DRAFT-1)가 실제로 지금 이 저장소에 존재했다 — 이 클래스의 버그(한 곳만 고치고 복붙된 나머지는 안 고침)가 테스트 하나로는 재발을 막기 부족하다(테스트는 "누군가 돌려야" 잡힌다). pre_commit_check.py와 동일한 패턴(matcher Bash, if Bash(git *))으로, 커밋 시점에 등록된 복붙 함수들이 모든 사본에서 실제로 동일한지 비교해서 다르면 커밋을 물리적으로 막는 새 훅을 만든다. 이 저장소 자신의 hooks/ 디렉토리에만 적용되고 다른 프로젝트에서는 조용히 통과해야 한다(self-guard).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 hooks/dedup_drift_guard.py 신설: 스크립트 내부에 REGISTRY(함수명 -> 동일해야 하는 파일 목록) 명시, 최초 항목은 is_backlog_project -> [require_active_task.py, pre_commit_check.py, pre_push_check.py, block_stop_if_dirty.py, session_start.py]
- [x] #2 matcher Bash, if Bash(git *) — git commit 실행 전에 REGISTRY의 각 함수 소스를 파일별로 추출해 비교, 하나라도 다르거나 누락되면 어느 파일이 다른지 구체적으로 보여주며 exit code 2로 커밋 차단
- [x] #3 cwd/hooks/ 밑에 REGISTRY가 가리키는 파일들이 없으면(claude-rails 저장소 자신이 아니면) 즉시 통과 — self-guard
- [x] #4 test_dedup_drift_guard.py 추가: 전부 동일할 때 통과 / 하나라도 다를 때 차단 / 함수가 일부 파일에서만 누락됐을 때도 차단, 세 케이스 커버
- [x] #5 settings.hooks.json에 새 훅 등록 (pre_commit_check.py와 같은 이벤트/matcher/if 블록에 추가)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
hooks/dedup_drift_guard.py 신설: REGISTRY(is_backlog_project -> 5개 훅 파일)를 ast 비교로 검증, 커밋 시점에 드리프트 발견 시 exit 2로 차단, self-guard로 다른 프로젝트에서는 무해. hooks/test_dedup_drift_guard.py 13개 테스트로 동일/불일치/함수누락 3케이스 및 기존 dedup_registry 회귀 커버. settings.hooks.json에 pre_commit_check.py와 동일 PreToolUse/Bash/if Bash(git *) 블록으로 등록. 전체 hooks/ pytest 397 passed. 새 훅이 이 저장소 자신의 5개 파일을 검사해도 현재 동일 상태라 커밋을 막지 않음을 실커밋으로 확인.
<!-- SECTION:FINAL_SUMMARY:END -->
