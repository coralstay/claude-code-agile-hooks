---
id: DRAFT-11
title: 'decision-11: 로컬은 rebase merge, 원격은 머지 커밋 — decision-10 대체'
status: Draft
assignee: []
created_date: '2026-10-03 03:23'
updated_date: '2026-10-03 03:23'
labels:
  - policy
  - git
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-10("병합은 머지 커밋으로, rebase merge 금지")를 대체하는 decision-11을 만든다.

## 왜

decision-5(항상 rebase)와 decision-10(항상 머지 커밋)은 둘 다 로컬과 원격을 한 규칙으로 묶었다. 그런데 두 지점에서 커밋 객체에 일어나는 일이 다르다.

- 원격(GitHub PR) 병합: GitHub이 커밋을 다시 만든다. 이 저장소에서 실측했다(decision-5 Context) — author는 cpu-once로 남지만 committer는 coralstay로 재작성되고 해시가 바뀐다. rebase merge는 이 재작성을 PR의 모든 커밋에 적용하고, 머지 커밋은 기존 커밋 객체를 보존한다.
- 로컬 통합: 아직 push되지 않은 커밋이라 rebase로 다시 써도 공개된 이력은 바뀌지 않는다. task 브랜치를 main 위로 선형으로 올리면 검토와 bisect가 쉬워진다.

또 decision-10은 근거를 다른 저장소의 decision에 두고 있다. claude-rails의 규칙과 근거는 이 저장소 안에서 완결해야 한다(외부 프로젝트 결합 금지). decision-11은 이 저장소의 실측만 근거로 쓴다.

## decision-11 본문 요지

- 로컬: git rebase main 후 git merge --ff-only. 로컬에서는 머지 커밋을 만들지 않는다.
- 원격: gh pr merge --merge. rebase/squash merge 금지.
- 금지선은 공개(push)된 이력이다. force push 금지.
- decision-10 대체. decision-4의 "로컬 fast-forward까지만 자동화"와 "push·원격 병합은 사람이 최종 승인"은 유효.
- 결과: 원격 병합 후 로컬 main은 git pull --ff-only로 맞춘다(reset --hard 동기화 불필요). GitHub 설정으로 원격을 강제할지는 별도 판단.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 backlog decision create로 decision-11을 만든다 — 본문은 이 저장소의 실측만 근거로 쓰고 다른 저장소를 참조하지 않는다
- [ ] #2 decision-10의 status를 superseded로 바꾸고 decision-11을 가리키게 한다
- [ ] #3 decision-4가 decision-11과 일치하는지 확인하고, 어긋나는 문구가 있으면 decision-11 Consequences에 명시한다
- [ ] #4 README.md와 backlog/docs에서 병합 방식 서술을 찾아 decision-11과 맞춘다
<!-- AC:END -->
