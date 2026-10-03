---
id: decision-10
title: 병합은 머지 커밋으로 — decision-5(항상 rebase merge) 대체
date: '2026-09-26 13:16'
status: superseded
---
> **2026-10-03: decision-11로 대체됨.** 로컬 통합은 rebase 후 fast-forward, 원격(GitHub PR)
> 병합은 머지 커밋으로 한다. 금지선은 공개(push)된 이력이다.

## Context

decision-5(2026-09-19)는 "이후 모든 PR은 rebase merge로 병합한다"고 정했고, 그 정책을
`hooks/pre_merge_check.py`가 fast-forward 전용 강제로 뒷받침했다.

**decision-5의 관찰은 정확했지만 결론이 뒤집혀 있었다.** 그 Context는 이렇게 적고 있다:

> GitHub가 PR을 병합하면서 커밋 메시지는 동일하지만 committer 정보가 바뀐 새 커밋 객체를
> 만들었기 때문(author는 `cpu-once` 유지, committer는 `coralstay`로 재작성됨)

문제로 본 것이 맞다 — 병합이 커밋을 다시 만들어 committer가 바뀌는 것이다. 그런데
**rebase merge는 그 재작성을 없애지 않고 오히려 모든 커밋에 적용한다.** merge commit은
커밋 하나를 새로 얹을 뿐 기존 커밋 객체를 건드리지 않는다.

2026-09-26에 git-format에서 그 결과가 드러났다(실측): `main`의 커밋들이
`Signed-off-by: cpu-once`를 달고 있는데 실제 committer는 `coralstay`다. `post-commit`이
로컬 커밋 시점의 커미터로 트레일러를 쓴 뒤 GitHub이 rebase로 커밋을 다시 만들어서다.
`%G?`도 전부 `N`이다 — 서명도 무효가 됐다. **트레일러가 자기가 앉아 있는 커밋에 대해
거짓을 말한다.**

외부 근거: Linux 커널 메인테이너 문서는 "공개된 이력은 바꾸지 말 것", "reparenting은 그때의
검증을 무효화한다", "커널 커뮤니티는 merge commit을 두려워하지 않는다"고 적는다. 서명은
rebase로 부모가 바뀌면 깨진다. force-push 1.6억 건 규모의 provenance 연구(arXiv 2607.02774)는
이력 재작성이 저자 귀속 분석을 무효화한다고 보고한다.

## Decision

**병합은 머지 커밋으로 한다.** rebase merge와 squash merge를 쓰지 않는다.
decision-5를 이 decision이 대체한다.

근거 정책은 git-format의 decision-24(append-only)다 — 커밋이 만들어진 뒤에는 그 객체를
다시 만들지 않고, 금지선은 공개(push)된 이력에 둔다.

**`hooks/pre_merge_check.py`를 제거한다**(TASK-24). 그 훅은 주석 그대로
"no merge commits, no squash"를 강제해 이 decision의 정반대를 강제한다. 실제로 조사 중
정상 작업을 두 번 막았고, 금지 옵션명이 무관한 heredoc 안에 있을 때도 막았다(명령 문자열
전체를 부분 문자열로 매칭한다).

`git config merge.ff`는 전역·로컬 모두 설정돼 있지 않아 되돌릴 것이 없다(확인).

**선형 이력이 필요하면 `git log --first-parent`를 쓴다.** 병합 방식을 바꿔서 얻는 것이 아니다.

## Consequences

- 트레일러가 자기 커밋에 대해 참인 상태가 유지된다. `Signed-off-by`가 실제 committer와,
  서명이 서명한 객체와 맞물린다.
- 원본 커밋 객체가 보존되므로 실제 분기 구조가 남는다.
- `git log`가 머지 커밋으로 덜 선형이 된다. `--first-parent`로 완화한다.
- **이미 어긋난 과거 커밋은 고치지 않는다.** 고치는 것 자체가 이력 재작성이고, 그때의
  결정에는 그때의 이유가 있었다.
- decision-4("로컬 fast-forward까지만 자동화")의 그 문구가 어긋난다. 그 decision의 핵심은
  "push·원격 병합은 사람이 최종 승인"이고 그 부분은 유효하다 — fast-forward 한정 문구만
  이 decision이 대체한다.
- 원격 쪽 강제는 GitHub 설정으로 한다. github.com에는 `pre-receive` 훅을 설치할 수 없다
  (Enterprise 전용). git-format 저장소에는 2026-09-26에 적용했다 — `allow_rebase_merge`와
  `allow_squash_merge`를 끄고, ruleset으로 force push와 브랜치 삭제를 막았다. 이 저장소에도
  같은 설정이 필요한지는 별도 판단 사항이다.
