---
id: TASK-38
title: pre_git_safety_check.py — 신규 저장소 최초 push가 main 가드에 막히는 문제와 우회 경로 기록
status: Done
assignee: []
created_date: '2026-09-25 19:52'
updated_date: '2026-10-03 13:13'
labels: []
dependencies:
  - TASK-37
references:
  - decision-4
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
2026-09-26 coralstay-software-factory 저장소를 GitHub에 처음 올리는 과정에서 발견. `gh repo create --public --source=. --remote=origin` 까지는 통과했으나, 이어지는 `git push -u origin main` 이 pre_git_safety_check.py 의 check_push() 에 걸려 차단됐다.

## 문제

check_push() 는 refspec 에 등장하는 대상 브랜치가 PROTECTED_BRANCHES(main/master) 이면 무조건 deny 한다. 그런데 "신규 저장소의 최초 push"는 의미상 보호할 대상(원격 main)이 아직 존재하지 않는 케이스다. 즉 덮어쓸 이력도, 되돌릴 리뷰 절차도 없는데 가드가 걸린다. 결과적으로 `gh repo create` 로 원격만 만들어 두고 내용은 못 올리는 반쪽 상태가 된다.

## 확인된 우회 경로 (의도된 escape 가 아니라 구현상의 빈틈)

check_push() 는 주석에 명시된 대로 refspec 이 명시된 형태만 검사한다:

- `git push origin main` / `git push origin main:main` → 차단됨
- `git push` (refspec 없음) → **검사되지 않음**. 훅이 git 을 실행하지 않고는 현재 브랜치를 알 수 없기 때문에 의도적으로 미검사로 남겨둔 구간이다.

따라서 `git config branch.main.remote origin` + `git config branch.main.merge refs/heads/main` 으로 upstream 을 먼저 박아두고 bare `git push` 를 때리면 가드를 통과한다. 이건 sanctioned override 가 아니라 known gap 이므로, 에이전트가 임의로 쓰면 안 된다.

이번 세션에서는 우회하지 않고 사용자가 프롬프트에서 `! git push -u origin main` 으로 직접 실행하는 방식을 택했다 (훅은 Claude 의 Bash 도구 호출에만 걸리고 사용자 직접 실행에는 걸리지 않는다).

## 검토할 선택지

1. 최초 push 예외: `git ls-remote --exit-code --heads <remote> <branch>` 로 원격 브랜치 부재를 확인했을 때만 허용. 훅이 git 을 실행해야 하므로 self-contained 원칙과 레이턴시를 따져봐야 함.
2. bare `git push` 갭 자체를 메우기 (현재 브랜치 확인 후 동일 규칙 적용) — 갭을 닫으면 위 우회 경로도 사라지므로 1번과 같이 가야 함.
3. 현상 유지 + 문서화: 최초 push 는 사람이 직접 실행하는 것을 정식 절차로 README 에 명시.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 원격에 대상 브랜치가 없을 때(git ls-remote로 확인)의 최초 push는 main 가드를 통과한다 — 원격 확인 실패 시에는 막는다
- [x] #2 refspec 없는 bare push도 현재 브랜치를 확인해 같은 규칙을 적용해 알려진 우회 경로를 닫는다
- [x] #3 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
pre_git_safety_check.py에 최초 push 예외와 bare push 판정을 넣었다. main/master 대상 push는 git ls-remote --exit-code --heads가 2(원격 브랜치 없음)일 때만 허용하고, 0이면 차단, 그 밖(원격 없음·타임아웃·git 없음·pushInsteadOf 설정)은 fail-closed로 차단. 대상 판정은 src:dst, refs/heads/ 제거, HEAD/@ 해석, --all/--mirror/matching을 반영해 HEAD:refs/heads/main, --all 같은 기존 우회도 막는다. refspec 없는 push는 git 규칙(remote.<r>.mirror → remote.<r>.push → push.default, pushRemote 등)으로 대상 브랜치를 구해 같은 규칙을 적용 — upstream 설정 후 bare push 우회를 닫았다. 최초 push라도 force/delete는 차단. 훅 자신의 git 호출에 git -c/GIT_* 접두는 넘기지 않는다(승인 전 사용자 설정 실행 방지). push가 아닌 명령은 subprocess 0회. 테스트는 사용자 git 설정·네트워크와 격리, 임시 bare 원격으로 실측. 912 passed, 파일 커버리지 100%(__main__ 줄 제외). 알려진 한계: 실행 시점 refspec(xargs/find -exec), 앞 명령의 export GIT_DIR, bash -c/eval. 후속 검토: git -C로 지정된 저장소가 악성 설정(core.sshCommand 등)을 가지면 훅의 ls-remote가 승인 전에 실행한다. AC #3 설치는 일괄.
<!-- SECTION:FINAL_SUMMARY:END -->
