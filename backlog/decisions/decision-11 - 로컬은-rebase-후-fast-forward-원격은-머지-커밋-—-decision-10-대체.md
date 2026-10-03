---
id: decision-11
title: '로컬은 rebase 후 fast-forward, 원격은 머지 커밋 — decision-10 대체'
date: '2026-10-03 03:26'
status: accepted
---
## Context

decision-5(항상 rebase merge)와 decision-10(항상 머지 커밋)은 둘 다 로컬 통합과 원격(GitHub
PR) 병합을 한 규칙으로 묶었다. 그런데 두 지점에서 커밋 객체에 일어나는 일이 다르다.

**원격 병합: GitHub이 커밋을 다시 만든다.** 이 저장소에서 실측했다(decision-5 Context) —
PR #5를 병합하자 커밋 메시지는 그대로인데 author는 `cpu-once`로 남고 committer는
`coralstay`로 재작성된 새 커밋 객체가 생겼고, 해시가 바뀌어 로컬 `main`과 `origin/main`이
갈라졌다. rebase merge는 이 재작성을 없애지 않고 PR의 **모든** 커밋에 적용한다. 머지 커밋은
커밋 하나를 새로 얹을 뿐 기존 커밋 객체를 그대로 보존한다.

**로컬 통합: 아직 공개되지 않은 커밋이다.** task 브랜치의 커밋은 push 전이라 rebase로 다시
써도 공개된 이력은 바뀌지 않는다 — 그 커밋 객체를 참조하는 사람이 아직 없다. 그리고 task
브랜치를 `main` 위로 선형으로 올려 두면 검토(커밋 단위 diff)와 `git bisect`가 쉬워진다.

즉 재작성의 문제는 "rebase냐 머지 커밋이냐"가 아니라 "공개된 이력을 다시 쓰느냐"다. 로컬과
원격을 나눠 보면 두 요구를 함께 만족할 수 있다.

외부 근거: Linux 커널 메인테이너 문서는 공개된 이력은 다시 쓰지 말고, 아직 공개하지 않은
자기 브랜치는 정리해도 된다고 적는다(Documentation/maintainer/rebasing-and-merging.rst).

## Decision

**로컬 통합은 rebase 후 fast-forward로 한다.**

```
git rebase main            # task 브랜치에서
git checkout main
git merge --ff-only task/<ID>
```

로컬에서는 머지 커밋을 만들지 않는다.

**원격(GitHub PR) 병합은 머지 커밋으로 한다** — `gh pr merge --merge`(또는 GitHub UI의
"Create a merge commit"). rebase merge와 squash merge는 쓰지 않는다.

**금지선은 공개(push)된 이력이다.** 이미 push된 커밋은 rebase·amend로 다시 쓰지 않고,
force push는 하지 않는다.

decision-10을 이 decision이 대체한다. decision-4의 "push·원격 병합은 사람이 최종 승인"과
"로컬 fast-forward까지만 자동화"는 그대로 유효하다 — 로컬 rebase와 `--ff-only` 병합은
자동으로 하고, push와 PR 병합 앞에서는 멈춘다.

## Consequences

- 원격 병합이 기존 커밋 객체를 보존하므로, 원격 병합 후 로컬 `main`은
  `git pull --ff-only`로 맞춘다. decision-5 Consequences의
  `git fetch` + `git reset --hard origin/<branch>` 동기화는 더 이상 필요 없다.
- 로컬 `main`의 task 단위 이력은 선형이고, 원격 `main`에는 PR마다 머지 커밋이 하나씩 생긴다.
  PR 단위로 보려면 `git log --first-parent`를 쓴다.
- task 브랜치를 push한 뒤에는 그 브랜치도 공개된 이력이다 — 그 뒤로는 rebase하지 않는다.
  로컬 rebase는 push 전까지만 한다.
- **decision-4와의 정합성**: decision-4의 Decision·Consequences 본문(로컬은
  `git merge --ff-only`까지만 자동, push·원격 병합은 사람이 승인)은 이 decision과 일치한다.
  어긋나는 것은 decision-4 상단에 decision-10 시점에 붙은 주석("'로컬 fast-forward까지만
  자동화' 문구만 대체됐다 — 병합은 머지 커밋으로 한다")뿐이다. 이 decision 이후로 그 주석은
  유효하지 않다 — 로컬은 다시 fast-forward이고, 머지 커밋은 원격 병합에만 해당한다.
  decision-4 본문은 이력이므로 고치지 않는다.
- 같은 이유로 decision-5 상단의 "병합은 머지 커밋으로 한다" 주석도 원격 병합에 한해 유효하다.
- 원격 쪽 방식을 GitHub 저장소 설정(`allow_rebase_merge`/`allow_squash_merge` 끄기, force
  push 차단 ruleset 등)으로 강제할지는 별도 판단 사항이다. github.com에는 `pre-receive`
  훅을 설치할 수 없다.
