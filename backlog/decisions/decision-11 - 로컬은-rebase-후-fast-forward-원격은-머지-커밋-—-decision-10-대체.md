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

**로컬: 트렁크 기반 개발이다.** 기준은 항상 `main`이고, task 브랜치는 `main`의 최신 내용
위에 작업을 덧붙이는 것이다. 그래서 task 브랜치는 `main`을 따라잡을 때 머지가 아니라 rebase로
따라간다. 그러면 task 브랜치는 언제나 `main` 끝에서 갈라진 선형 이력이 되고, 로컬 통합은
fast-forward 한 번으로 끝난다.

즉 다시 쓰면 안 되는 것은 `main`의 이력이다. task 브랜치는 `main`을 따라가기 위해 다시
쓰이는 것이 정상이다.

## Decision

**로컬에서 task 브랜치는 항상 `main`에 rebase해서 따라간다(트렁크 기반).** 통합은
rebase 후 fast-forward로 한다.

```
git rebase main            # task 브랜치에서
git checkout main
git merge --ff-only task/<ID>
```

로컬에서는 머지 커밋을 만들지 않는다.

**원격(GitHub PR) 병합은 머지 커밋으로 한다** — `gh pr merge --merge`(또는 GitHub UI의
"Create a merge commit"). rebase merge와 squash merge는 쓰지 않는다.

**금지선은 `main`의 이력이다.** `main`의 커밋은 rebase·amend로 다시 쓰지 않고, `main`에
force push하지 않는다.

decision-10을 이 decision이 대체한다. decision-4의 "push·원격 병합은 사람이 최종 승인"과
"로컬 fast-forward까지만 자동화"는 그대로 유효하다 — 로컬 rebase와 `--ff-only` 병합은
자동으로 하고, push와 PR 병합 앞에서는 멈춘다.

## Consequences

- 원격 병합이 기존 커밋 객체를 보존하므로, 원격 병합 후 로컬 `main`은
  `git pull --ff-only`로 맞춘다. decision-5 Consequences의
  `git fetch` + `git reset --hard origin/<branch>` 동기화는 더 이상 필요 없다.
- 로컬 `main`의 task 단위 이력은 선형이고, 원격 `main`에는 PR마다 머지 커밋이 하나씩 생긴다.
  PR 단위로 보려면 `git log --first-parent`를 쓴다.
- task 브랜치는 `main`이 앞서 나가면 언제든 `main`에 rebase해서 따라간다. `main`을
  task 브랜치로 머지해 들이지 않는다.
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
