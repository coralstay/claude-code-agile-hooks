---
id: TASK-38
title: pre_git_safety_check.py — 신규 저장소 최초 push가 main 가드에 막히는 문제와 우회 경로 기록
status: In Progress
assignee: []
created_date: '2026-09-25 19:52'
updated_date: '2026-10-03 12:56'
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
- [ ] #3 테스트를 추가하고 전체 스위트가 통과하며 설치본을 갱신한다
<!-- AC:END -->
