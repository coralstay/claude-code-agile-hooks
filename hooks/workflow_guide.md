---
title: workflow_guide
description: session_start 훅이 매 세션 Claude에게 보여 주는 짧은 워크플로 안내문
authors: [coralstay]
license: AGPL-3.0-only
status: draft
created_date: '2026-11-21'
updated_date: '2026-11-26'
---
## Backlog.md 워크플로 (claude-code-agile-hooks)

backlog 프로젝트(저장소 루트에 `backlog/config.yml`이 있는 곳)를 대상으로 하는 작업은 카드 중심 워크플로를 훅이 강제하고,
그 밖에서는 안전 훅(위험 명령 · 비밀값 · 설정 보호 등)만 작동한다. 훅이 막으면 메시지대로 따르고 우회하지 않는다.

1. **브리핑**: 새 요청을 받으면 `backlog overview` · `backlog search`로 현황부터 본다.
2. **계획**: plan mode로 계획을 먼저 보여 주고, 승인되면 `backlog draft create`로 draft에 담는다(SOAP 계획 · AC · DoD).
   유저가 draft를 승인하면 `backlog draft promote <ID>`로 승격하고, 결정은 `--add-ref`, 문서는 `--doc`으로 카드에 잇는다.
3. **계획 승인**: `Plan-Approved: <ID>` 커밋은 사람이 자기 키로 서명해 만든다. Claude는 만들지 않고 유저에게 승인을 요청한다.
   승인 전에는 실행하지 않는다.
4. **실행**: `backlog task view <ID> --plain` → `-s "In Progress"` → `task/<ID>` 브랜치 →
   AC마다 테스트(`<ID>#<n>` · `<ID>#B<k>` 표식) → 구현 → 커밋.
   - 단계마다 커밋한다. 커밋하지 않은 채 턴을 끝내지 않는다.
   - AC 밖의 일이 보이면 범위를 넓히지 말고 유저에게 먼저 묻는다.
5. **대상 저장소**: 훅은 세션 위치가 아니라 명령 · 파일이 겨누는 저장소로 판정한다. 다른 저장소는 리터럴 경로로
   다룬다(`cd <dir> && …`, `git -C <dir>`). 변수로 쓴 경로(`cd "$X"`)는 막힌다.
   - 저장소마다 담당 에이전트가 있다(`dev-toolchain workspace owner <경로>`). `claude`가 아니면 편집 · 커밋하지 않고 읽기 · 보고만 하며, `unknown`이면 유저에게 묻는다.
6. **완료**: 테스트 통과 같은 증거를 본 뒤 AC · DoD를 체크하고 `--final-summary`를 쓰고 Done으로 옮긴다.
   push는 Done 뒤에만 하고, PR 병합은 사람이 한다.

상세 규칙은 claude-code-agile-hooks 저장소의 README.md가 기준(SSOT)이다.
