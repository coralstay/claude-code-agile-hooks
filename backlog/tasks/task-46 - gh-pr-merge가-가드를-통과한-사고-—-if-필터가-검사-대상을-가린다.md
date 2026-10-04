---
id: TASK-46
title: gh pr merge가 가드를 통과한 사고 — if 필터가 검사 대상을 가린다
status: Done
assignee: []
created_date: '2026-10-03 17:13'
updated_date: '2026-10-04 01:14'
labels:
  - hooks
  - bug
dependencies:
  - TASK-45
references:
  - TASK-37
  - TASK-39
  - TASK-45
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-10-03 21:22(KST) coding-agent-git-commit-tool(당시 git-trail) 세션에서 `cd <repo> && gh pr merge 46 --merge 2>&1 | tail -3; gh pr view 46 ...`가 막히지 않고 실행돼 PR #46이 병합됐다. 같은 세션의 PR #47 병합 명령(13:16Z)은 "gh pr merge 계열 명령은 금지"로 막혔다.

원인: 그 시점 설치본의 pre_git_safety_check.py가 `if: Bash(git *)` 필터로 등록돼 있었다. check_gh_destructive()는 gh 명령을 검사하는데, 필터가 git 하위 명령이 있는 Bash 호출에서만 훅을 띄우므로 git이 없는 `cd … && gh pr merge …`에서는 훅 자체가 실행되지 않았다. TASK-37(1478694, 21:44 커밋, 22:12 설치)이 /usr/bin/git 경로 호출 때문에 이 필터를 없애면서 우연히 함께 막혔다. 지금 설치본에 같은 명령을 넣으면 exit 2로 차단된다(재현 확인).

남은 위험: 다른 claude-rails 훅 5개가 여전히 `if: Bash(git *)`로 등록돼 있다 — pre_commit_check, pre_push_check, pre_push_coverage_check, backlog_commit_scope, dedup_drift_guard. TASK-37이 지적한 것과 같은 이유로 /usr/bin/git 같은 경로 호출에서는 이 훅들이 실행되지 않을 수 있고, 훅이 검사하는 명령과 등록 필터가 어긋나도 그걸 잡는 장치가 없다(이번 사고가 그 경우).

AC 후보:
1. 각 훅이 검사하는 명령 범위와 settings.hooks.json의 if 필터가 맞는지 대조하는 계약 테스트가 있다 — 검사 대상이 필터 밖이면 실패한다
2. 위 5개 훅에 대해 경로 호출(/usr/bin/git commit·push)과 git 아닌 명령으로 시작하는 복합 명령(cd … && git push)에서 실제로 실행되는지 실측하고, 실행되지 않는 보안 훅은 필터를 없애거나 대체한다
3. 이번 사고 재현(`cd x && gh pr merge 1`이 차단됨)을 회귀 테스트로 남긴다

참고: TASK-37(필터 제거 선례), TASK-45(gh 검사 오탐·미탐 — 판정 로직, 이 건은 등록 범위), TASK-43(훅 계약 테스트)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 각 훅이 검사하는 명령 범위와 settings.hooks.json의 if 필터가 맞는지 대조하는 계약 테스트가 있다 — 검사 대상이 필터 밖이면 실패한다
- [x] #2 if 필터가 남은 훅(pre_push_check, pre_push_coverage_check, dedup_drift_guard 등)이 경로 호출과 git 아닌 명령으로 시작하는 복합 명령에서 실행되는지 실측하고, 실행되지 않는 게이트·보안 훅은 필터를 없애거나 대체한다
- [x] #3 cd x && gh pr merge 1이 차단되는 회귀 테스트를 남긴다
- [x] #4 전체 스위트를 통과하고 설치본을 갱신한다
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-04 실측(메인 세션, Claude Code 설치본, pre_push_check.py를 if: Bash(git *)로 등록한 상태 — Done 아니면 push 차단):
- git push --dry-run nonexistent-remote-x some-branch → 훅 실행(차단)
- true && git push --dry-run nonexistent-remote-x some-branch → 훅 실행(if 규칙이 복합 명령의 하위 명령마다 맞춤)
- /usr/bin/git push --dry-run nonexistent-remote-x some-branch → 훅 실행 안 됨(명령이 실행됨, 원격 부재로만 실패)
결론: if: Bash(git *)는 하위 명령별 텍스트 접두사 매칭, 경로 정규화 없음 → 경로 호출은 우회, git 하위 명령 없는 줄(cd x && gh pr merge)은 아예 안 걸림.
결정: pre_push_check·pre_push_coverage_check 필터 제거(게이트, 비 push 줄은 subprocess 없이 종료 — 테스트 추가). dedup_drift_guard 유지(drift 감지기, test_dedup_registry.py가 스위트에서 동일 검출 — 계약 테스트 hidden_ok). pr_provenance_stamp 유지(표시용 도장 — hidden_ok). 계약 테스트: hooks/test_hook_registration_contract.py.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
if 필터 매칭을 실측했다(2026-10-04, 설치본 pre_push_check): 하위 명령별 텍스트 접두사 매칭이며 복합 명령·파이프 뒤 명령·env 할당 접두는 매칭되지만 /usr/bin/git 같은 경로 호출과 git 하위 명령이 없는 줄(cd x && gh pr merge)은 매칭되지 않는다. 이 의미를 흉내 내는 시뮬레이터와 계약 테스트(test_hook_registration_contract.py)를 추가: 훅마다 검사 대상 대표 명령을 훅 자신의 판정 함수로 확인한 뒤 필터를 통과하는지 대조하고, 가려지는 명령은 사유가 적힌 hidden_ok만 허용, 낡은 예외·계약 없는 필터·미분류 Bash 훅을 거부한다. 게이트인 pre_push_check·pre_push_coverage_check의 if 필터 제거(push 아닌 줄은 subprocess 없이 즉시 종료 — 테스트로 고정). dedup_drift_guard(드리프트 감지)·pr_provenance_stamp(장식)는 필터 유지 + 경로 호출 hidden_ok. pre_git_safety_check에 필터가 없음과 사고 줄 차단을 계약으로 고정. 옛 필터를 되살리면 9개 테스트가 실패함을 확인. 1241 passed. 래퍼(sudo) 매칭은 미실측 — 보수적 가정. AC #4 설치는 일괄.
<!-- SECTION:FINAL_SUMMARY:END -->
