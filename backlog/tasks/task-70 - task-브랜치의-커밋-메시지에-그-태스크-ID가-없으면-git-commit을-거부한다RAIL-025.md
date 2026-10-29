---
id: TASK-70
title: task 브랜치의 커밋 메시지에 그 태스크 ID가 없으면 git commit을 거부한다(RAIL-025)
status: To Do
assignee: []
created_date: '2026-10-29T12:23:00Z'
updated_date: '2026-10-29T12:24:00Z'
labels:
  - hooks
dependencies:
  - DRAFT-8
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 결정(2026-10-29, 최상위 TASK-19 C2, 최상위 설계 RAIL-025): `task/<ID>` 브랜치에서는 메시지(제목 · 본문 · 트레일러)에 그 ID가 단어로 들어 있지 않은 `git commit`을 거부한다. 대소문자는 기존 매처처럼 무시한다. 계기: 최상위 TASK-14의 design/ 커밋 5개(1ea925d ~ 7ea2884)에 태스크 ID가 없었다. 그 상태로 쌓인 브랜치(task-14→15→17→18)에 올라가 어느 태스크의 변경인지 알 수 없게 됐다. 그 이력은 고치지 않는다(TASK-66 AC #3의 안내로 처리). 이 카드는 다시 생기지 않게 막는다.

메시지를 읽어야 하는 경로: `-m`(여러 개), `-F <파일>`, `-F - <<EOF` heredoc, Claude Code가 흔히 쓰는 `-m "$(cat <<'EOF' ... EOF)"`, `--trailer`, 메시지 없이 쓴 `--amend`(기존 메시지가 남으므로 그 메시지로 판정), `-C/--reuse-message`, `--fixup/--squash`. 주의: 공유 파서 strip_heredoc_bodies는 토큰으로 나누기 전에 heredoc 본문을 지운다. 그래서 heredoc 메시지는 원래 명령 텍스트에서 따로 읽어야 한다. 에디터 경로(메시지 옵션 없음)는 메시지를 미리 볼 수 없으니 거부한다. 같은 판단이 coding-agent-git-commit-tool decision-18(에디터 경로 거부)에도 있지만, 그 도구는 이 저장소에 설치돼 있지 않다. `git merge`가 직접 만드는 머지 커밋은 범위 밖이다(README에 한계로 적는다).

ID 매처는 TASK-63의 `has_refs_commit`이 쓰는 단어 경계 정규식(require_design_propagation.py:519-522)을 공유 함수로 뽑는다. 그 함수를 dedup REGISTRY로 TASK-66과 함께 쓴다. TASK-66은 이 카드에 의존하게 된다. 승격 뒤 `backlog task edit TASK-66 --dep <이 카드 ID>`로 건다(아직 TASK-66은 고치지 않았다). 선행: DRAFT-8(명령의 대상 저장소 해석 — `cd <dir> && git commit`, `git -C`). 이 카드는 최상위 coralstay-software-factory TASK-19의 결정을 구현한다. 커밋 본문에 'Refs: coralstay-software-factory TASK-19'를 적는다.

## 비즈니스 규칙
- B1 (AC #1) task/<ID> 브랜치에서 메시지 어디에도 그 ID가 없으면 커밋을 거부한다
- B2 (AC #1) 다른 태스크 ID만 있으면 거부한다
- B3 (AC #1) 단어 경계로 찾는다 — TASK-6은 TASK-60 · TASK-6.1에 매치되지 않고, task-64는 브랜치 task/TASK-64에 매치된다
- B4 (AC #1) `Refs: <다른 저장소> <ID>` 줄의 ID는 이 저장소 태스크 ID로 세지 않는다
- B5 (AC #2) `-m`이 여러 개면 합친 메시지에서 찾고, `-F <파일>` · `-F -` heredoc · `-m "$(cat <<'EOF' ...)"` 본문 · `--trailer` 값도 메시지로 본다
- B6 (AC #3) 메시지 없이 `--amend`(또는 `--amend --no-edit`)를 쓰면 기존 HEAD 메시지로, `-C` · `--fixup` · `--squash`는 그 대상 커밋 메시지로 판정한다
- B7 (AC #4) 에디터 경로(메시지 옵션 없음 · `-c` · `-e` · `-t`만 있음)는 거부한다
- B8 (AC #4) 메시지를 정적으로 알 수 없으면(파이프로 넣는 `-F -`, 변수 · heredoc이 아닌 명령 치환) 거부한다
- B9 (AC #6) 대상 저장소의 현재 브랜치가 task/<ID>가 아니면 이 검사를 하지 않는다
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pre_commit_check: 대상 저장소의 현재 브랜치가 task/<ID>면 커밋 메시지(제목 · 본문 · 트레일러)에 그 ID가 단어 경계 · 대소문자 무시로 있어야 하고, 없거나 다른 ID만 있으면 거부한다. 'Refs: <다른 저장소> <ID>' 줄은 세지 않는다
- [ ] #2 메시지 복원: -m/--message 여러 개, -F/--file <파일>(대상 저장소 기준 경로), -F - <<EOF heredoc, -m "$(cat <<'EOF' ... EOF)", --trailer 값을 strip_heredoc_bodies와 별도로 원래 명령 텍스트에서 읽는다
- [ ] #3 메시지를 재사용하는 커밋: 메시지 옵션 없는 --amend(--no-edit 포함)는 HEAD 메시지로, -C/--reuse-message · --fixup · --squash는 대상 커밋 메시지로, 머지 마무리 commit --no-edit은 .git/MERGE_MSG로 판정한다
- [ ] #4 에디터 경로(메시지 옵션 없음, -c · -e · -t만 있음)와 정적으로 알 수 없는 메시지(파이프로 넣는 -F -, 변수 · heredoc이 아닌 명령 치환)는 -m 또는 -F <파일>을 쓰라는 안내와 함께 거부한다
- [ ] #5 ID 매처 mentions_task_id를 require_design_propagation.has_refs_commit에서 꺼내 dedup REGISTRY 공유 함수로 등록하고, has_refs_commit이 그것을 쓰게 바꾼다(TASK-66이 같은 함수를 재사용)
- [ ] #6 대상 저장소 · 브랜치는 DRAFT-8의 command_target_dir로 정하고, ID 검사는 testCommand 실행보다 먼저 한다. task 브랜치가 아니면 검사하지 않는다
- [ ] #7 git merge가 직접 만드는 머지 커밋은 검사 범위 밖이라는 한계를 README에 적는다 (수동)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 coverageCommand 통과 · 커버리지 100%(line + branch)
- [ ] #2 바뀐 훅이 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트와 맞는다
- [ ] #3 README(RAIL-025) · CLAUDE.md.snippet 반영 (수동)
- [ ] #4 승격 뒤 backlog task edit TASK-66 --dep <이 카드 ID>를 걸고 작업 순서를 다시 계산한다 (수동)
- [ ] #5 각 커밋에 TASK ID와 본문 'Refs: coralstay-software-factory TASK-19', push 전 Done + final summary (수동)
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저가 2026-10-29 C2에서 '이력은 고치지 않고, 재발은 훅으로 막는다'를 골랐다. task 브랜치의 커밋 메시지에 그 태스크 ID가 없으면 거부한다. TASK-66(ID로 커밋 고르기)과 같은 매처를 쓰자고 했다.

### Objective
- pre_commit_check.py:205-238 main은 `git commit`을 감지하고, In Progress 카드가 있을 때 task 브랜치 여부와 testCommand만 본다. 메시지는 읽지 않는다.
- 명령 파싱은 strip_heredoc_bodies(pre_commit_check.py:54-66)가 heredoc 본문을 먼저 지우고 tokenize · split_segments로 나눈다. 그래서 `-m "$(cat <<'EOF'` 뒤의 본문은 토큰에 남지 않는다.
- backlog_commit_scope.py:97-111(COMMIT_SHORT_WITH_ARG = "mFcCt", COMMIT_LONG_WITH_ARG)과 commit_stages_all(L321-344)이 이미 git commit 옵션 중 인자를 받는 것들을 구분한다.
- require_design_propagation.py:512-523 has_refs_commit 안에 단어 경계 ID 정규식 `(?<![A-Za-z0-9-])ID(?![A-Za-z0-9]|\.\d)`(IGNORECASE)가 지역 변수로 있다. REGISTRY에는 없다.
- coding-agent-git-commit-tool hooks/prepare-commit-msg:179-190 reject_editor_path는 에디터 경로를 거부하지만, 이 저장소에는 core.hooksPath가 없다(설치 안 됨).
- 이 저장소의 머지 커밋 메시지는 이미 '(TASK-63)'처럼 ID를 단다(git log 22b5eaf ~ 9a8995c).

### Assessment
검사는 pre_commit_check에 넣고 testCommand보다 먼저 돌린다. 어차피 거부될 커밋에 긴 테스트를 돌리지 않기 위해서다. 새 훅 파일은 만들지 않는다. 메시지 복원 함수 `commit_message_sources(command, target_dir)`는 원래 명령 텍스트를 받는다. 이 함수는 heredoc 본문을 직접 짝지은 뒤 옵션을 해석한다. 결과는 '알려진 메시지 텍스트' 또는 '알 수 없음' 또는 '에디터'다. 매처 `mentions_task_id(text, task_id)`는 require_design_propagation에서 꺼내 REGISTRY에 등록하고 has_refs_commit도 그것을 쓰게 바꾼다. `Refs: <저장소>` 줄은 매칭 전에 뺀다. 머지 마무리 `git commit`(MERGE_HEAD 있음, 메시지 옵션 없음, `--no-edit`)은 .git/MERGE_MSG로 판정한다. 나머지 머지는 범위 밖이다. 대상 저장소 · 브랜치는 DRAFT-8의 command_target_dir로 정한다.

### Plan
1. AC #5: mentions_task_id 추출 테스트 먼저(경계 · 대소문자 · Refs 줄 제외), REGISTRY 등록, has_refs_commit 전환(회귀 테스트 그대로 통과).
2. AC #2 · #3 · #4: 메시지 복원 테스트 표(-m 여럿, -F 파일, -F - heredoc, $(cat <<'EOF'), --trailer, --amend, -C, --fixup, 에디터, 파이프) 먼저, 구현.
3. AC #1 · #6: pre_commit_check 통합 테스트 먼저(임시 저장소 task 브랜치), 구현 — testCommand 전에 거부.
4. README(RAIL-025 · 한계) · CLAUDE.md.snippet, coverageCommand 100%. 승격 뒤 TASK-66에 --dep.
<!-- SECTION:PLAN:END -->
