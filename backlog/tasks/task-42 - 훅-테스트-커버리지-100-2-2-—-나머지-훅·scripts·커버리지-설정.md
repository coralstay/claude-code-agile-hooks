---
id: TASK-42
title: 훅 테스트 커버리지 100% (2/2) — 나머지 훅·scripts·커버리지 설정
status: Done
assignee: []
created_date: '2026-10-03 12:38'
updated_date: '2026-10-03 18:04'
labels:
  - tests
  - coverage
dependencies:
  - TASK-41
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
(1/2) 이후 남은 훅과 scripts/merge_settings.py의 미커버를 채운다. if __name__ == '__main__' 진입점은 coverage 설정에서 제외하고(표준 관행), merge_settings.py CLI는 subprocess 대신 main()을 직접 호출하는 테스트로 측정되게 한다. 커버리지 설정 파일(.coveragerc 또는 pyproject.toml)에 측정 대상·제외 규칙·fail_under=100을 둔다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 저장소 루트에서 hooks·scripts 전체의 줄·분기 커버리지가 100%다
- [x] #2 커버리지 설정 파일에 측정 대상·제외 규칙·fail_under=100이 있다
- [x] #3 추가한 테스트는 각각 해당 분기의 기대 동작을 단언한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
hooks/·scripts/ 전체 줄·분기 커버리지 100%(3330문, 1354분기, 미커버 0). pyproject.toml에 pytest testpaths(hooks, scripts)와 coverage 설정(source hooks·scripts, 테스트 파일 omit, branch, fail_under=100, show_missing, exclude_also는 __main__ 진입점만)을 두었다 — 루트에서 uvx --with pytest-cov pytest -q --cov 한 줄이 게이트가 된다. pragma 없음. 추가 테스트는 모두 기대 동작을 단언, 기존 테스트 기대값·삭제 없음, 보안 훅 차단 코드 제거 없음. 제거: context_flags.write_flags와 merge_settings.main의 'if os.path.exists(tmp)' 도달 불가 분기 → contextlib.suppress(FileNotFoundError)로 동작 동일. merge_settings.main()은 in-process 테스트로 측정. 1368 passed, cd hooks 단독 실행·동시 2회 실행 모두 통과. 참고: PostToolUse 포매터(ruff format)가 저장소 전체 스타일과 달라 Edit 한 번에 파일 전체를 재작성 — TASK-43에서 일괄 포맷 또는 포매터 범위 정리 검토. nerf_receipts의 chmod 0 테스트는 root로 실행하면 실패(CI는 비root 러너 필요).
<!-- SECTION:FINAL_SUMMARY:END -->
