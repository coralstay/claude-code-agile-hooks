---
id: DRAFT-10
title: 계획 수립부터 승격까지 작업 파이프라인 전체를 훅으로 강제한다
status: Draft
assignee: []
created_date: '2026-09-26 08:08'
updated_date: '2026-10-03 03:39'
labels:
  - backlog
  - workflow
  - hooks
dependencies: []
documentation:
  - backlog/drafts/draft-9 - backlog-드래프트→승격-단계-분리를-훅으로-강제한다.md
  - backlog/drafts/draft-2 - 커맨드-문자열-매칭의-구조적-한계를-보완할-syscall-레벨-샌드박스-레이어-검토.md
  - backlog/drafts/draft-5 - 훅-시스템의-구조적-문제-5가지-—-1차-완화책은-컨텍스트-플래그-우선순위-높음.md
  - >-
    backlog/drafts/draft-8 -
    어시스턴트가-하네스-예약-태그bash-input를-출력해-사용자-직접-실행을-사칭할-수-있는-문제-—-신뢰-경계-위조.md
  - >-
    backlog/decisions/decision-1 -
    커맨드-문자열-매칭-훅은-basename-정규화까지만-—-syscall-레벨-강제는-범위-밖.md
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저가 2026-09-26에 명시한 "작업 파이프라인" 전체를 훅으로 강제할 수 있는지 검토한다.
DRAFT-9는 이 파이프라인의 4/6/7단계(드래프트 경유 + 생성/승격 각각 별도 커밋)만 다룬다 —
이 드래프트는 파이프라인 전체를 규격으로 놓고, 단계별로 훅이 관측 가능한지/강제 가능한지를
구분한다.

## 파이프라인 규격

1. **Claude plan mode로 계획 작성** — 에이전트가 plan mode에서 계획을 작성한다
2. **사람이 검토하고 계획을 구상** — 유저가 그 계획을 읽고 형태를 잡는다 (실행 전 게이트)
3. **오토모드로 전환** — 승인 후에야 실행 모드로 넘어간다
4. **backlog.md CLI로 드래프트 작성** — 계획이 `backlog draft create`가 된다
   (`backlog task create`로 바로 태스크를 만들지 않는다)
5. **검증 단계** — 순차검증, 병렬검증, 설계오류 검증, 그리고 그 결과로 작업 정렬
   (의존성 순서 결정)과 작업순서 문서화
6. **커밋**
7. **승격(`backlog draft promote`) 후 다시 커밋**

## 왜 훅이 필요한가

지금은 CLAUDE.md 서술로만 존재해서 실제로 어겨진다. 4단계 위반 사례는 DRAFT-9에 기록돼
있다(`backlog task create`로 드래프트를 건너뛴 GF-135 → 아카이브 → DRAFT-18 재작성). 1~3
단계는 더 조용히 어겨진다 — plan mode를 건너뛰고 바로 구현에 들어가도 아무 흔적이 남지
않는다. 5단계는 아예 강제 장치가 없고, 빠뜨려도 나중에 "왜 이 순서로 작업했는지"를 읽을
곳이 없다.

## 훅이 실제로 볼 수 있는 것 (실측, Claude Code 2.1.267)

임시 settings(`--settings`)에 stdin 덤프 훅을 붙이고 `claude -p`를 돌려 페이로드를 직접
확인했다.

- **`permission_mode` 필드가 실제로 온다.** `--permission-mode plan`으로 띄운 세션에서
  `UserPromptSubmit` 페이로드 키는
  `[cwd, hook_event_name, permission_mode, prompt, prompt_id, session_id, transcript_path]`,
  `PreToolUse`는 `[cwd, hook_event_name, permission_mode, prompt_id, session_id, tool_input,
  tool_name, tool_use_id, transcript_path]`였고 두 경우 다 `permission_mode == "plan"`.
  `Stop`도 `permission_mode`를 싣는다(`[background_tasks, cwd, hook_event_name,
  last_assistant_message, permission_mode, prompt_id, session_crons, session_id,
  stop_hook_active, transcript_path]`).
- **`SessionStart`에는 `permission_mode`가 없다.** 키는 `[cwd, hook_event_name, session_id,
  source, transcript_path]`뿐이다. 세션 시작 시점에 모드를 근거로 판단하려는 훅은 못 쓴다.
- **훅은 "현재 모드"만 본다. "모드가 바뀌었다"는 이벤트는 없다.** 전환 자체를 알리는 훅
  이벤트는 없고, 직전 값과 비교하려면 훅이 스스로 상태를 저장해야 한다.
- **전환 이력은 트랜스크립트에 남는다.** 모든 훅이 받는 `transcript_path`의 JSONL에
  `{"type": "permission-mode", "permissionMode": "auto"|"plan"|"default", "sessionId": ...}`
  전용 레코드가 있고, 실제 세션에서 `auto → plan → default` 순서가 그대로 읽혔다.
  `type: "user"` 프롬프트 레코드에도 `permissionMode`가 박혀 있다(실측 집계: `permission-mode`
  레코드 3705건, `user` 레코드 1338건). 즉 "이 세션이 plan mode를 거쳤는가"는 훅이
  트랜스크립트를 읽어 사후 판정할 수 있다. 다만 이 레코드에는 timestamp가 없어서 다른
  이벤트와의 정확한 시간 정렬은 인접 레코드 순서에 의존한다.
- **`ExitPlanMode`는 실제 도구 호출이다.** 트랜스크립트에
  `{"name":"ExitPlanMode","input":{"plan":"..."}}` 형태의 `tool_use`가 남고, 승인되면
  `tool_result`가 `{"type":"tool_reference","tool_name":"ExitPlanMode"}`로 돌아온다.
  따라서 계획 본문과 "승인됨" 신호를 둘 다 훅에서 잡을 수 있는 자리가 존재한다.
  (미확인: `PreToolUse`/`PostToolUse` 매처가 `ExitPlanMode`에 실제로 걸리는지는 직접
  확인하지 못했다 — `claude -p` 헤드리스 세션에는 그 도구가 노출되지 않아 재현에 실패했다.
  대화형 세션에서 매처 `ExitPlanMode`로 한 번 찍어보는 게 첫 실측 과제다.)

## 단계별 강제 가능성

**1~3단계 (plan mode → 사람 검토 → 오토모드).** 가장 어려운 구간이지만 관측 자체는 가능하다.
가능한 강제 지점:
- `PreToolUse(Edit|Write)` / `PreToolUse(Bash)`에서 `permission_mode`를 보고, 이 세션
  트랜스크립트에 `permission-mode: plan` 레코드나 승인된 `ExitPlanMode` 호출이 하나도 없으면
  구현을 막는다 — "계획 없이 바로 코드부터 손대는 것"을 차단하는 형태.
- 또는 `PostToolUse(ExitPlanMode)`에서 계획 본문을 세션 상태로 떨어뜨려 두고, 이후 4단계
  드래프트가 그 계획과 연결됐는지를 검사한다.
- 2단계(사람의 검토)는 훅이 직접 볼 수 없다. 관측 가능한 대리 신호는 "`ExitPlanMode`가
  승인되어 `tool_result`가 돌아왔다"와 "모드가 plan에서 벗어났다" 두 가지뿐이다. 이 대리
  신호를 승인의 증거로 인정할지가 정책 결정이다 — DRAFT-8이 지적한 "표식은 위조 가능하다"는
  문제와 같은 성질의 결정이다.
- 주의: require_active_task.py가 이미 plan mode와 충돌한 사례가 있다(계획 파일 저장이
  In Progress 태스크 없다는 이유로 차단됨). 1~3단계를 강제하는 훅을 추가할 때 기존
  Edit/Write 게이트와 데드락을 만들지 않는지 먼저 따져야 한다.

**4단계 (드래프트 경유).** DRAFT-9 그대로. `PreToolUse(Bash)`에서 `backlog task create`
차단 + 커밋 스테이징 검사. 여기서 다시 설계하지 않는다.

**5단계 (검증·정렬·문서화).** 아래 별도 절.

**6~7단계 (커밋 분리).** DRAFT-9의 B안(스테이징 내용으로 단계 혼합 차단) 그대로.

## 5단계: 훅이 검사할 수 있는 것과 없는 것

이 단계가 가장 기계화하기 어렵다. "순차검증/병렬검증/설계오류 검증을 제대로 했는가"는
판단의 품질이고, 훅은 판단의 품질을 볼 수 없다. 훅이 볼 수 있는 건 **산출물의 존재와 모양**
뿐이다. 이 경계를 흐리면 "형식만 채우고 통과하는" 의식(ritual)이 되므로 처음부터 분리해
적는다.

**훅이 검사할 수 있는 것 (산출물 기반, 구체안):**
- **승격 시점 의존성 검사**: 드래프트 2건 이상을 연달아 승격하는데 그중 어느 태스크에도
  `dependencies`가 비어 있으면 승격(또는 승격 커밋)을 거부한다. `backlog task edit --dep`,
  `--depends-on`, `--ordinal`이 CLI에 있으므로 정렬 결과를 기록할 자리는 이미 있다.
  (단일 태스크 승격에는 적용하지 않는다 — 의존성이 없는 게 정상이다.)
- **작업순서 문서 존재 검사**: `backlog/docs/`에 이번에 승격되는 태스크 ID들을 본문에서
  참조하는 문서가 있는지 확인한다. 없으면 거부하고 `backlog doc create`를 안내한다.
- **역참조 검사**: 승격된 태스크가 그 작업순서 문서를 `--doc`으로 걸고 있는지 확인한다
  (한쪽만 가리키면 `task view` 한 번으로 컨텍스트가 안 모인다 — CLAUDE.md의 취지).
- **정렬 일관성 검사**: `dependencies` 그래프에 순환이 있으면 거부. 문서에 적힌 순서와
  `--ordinal`/의존성 그래프의 위상 순서가 모순되면 경고. 이건 "판단"이 아니라 순수한
  일관성 검사라 훅이 확실히 할 수 있다.
- **검증 흔적 검사(가장 약한 것)**: 드래프트 본문에 순차/병렬/설계오류 세 축에 해당하는
  섹션이 채워져 있는지. 섹션 제목만 보는 검사는 우회가 자유로우므로, 넣더라도 차단이 아니라
  경고로 둬야 한다.

**훅이 검사할 수 없는 것 (명시적으로 포기할 것):**
- 병렬로 돌릴 수 있다고 판단한 작업이 실제로 독립인지
- 설계오류 검증이 실제로 설계를 봤는지, 표면만 훑었는지
- 기록된 의존성 순서가 옳은 순서인지 (순환 없음 ≠ 올바름)
- 작업순서 문서의 내용이 실제 작업 계획과 일치하는지

## 이미 아는 한계 (다시 쓰지 않고 참조)

- DRAFT-2 / decision-1: 커맨드 문자열 매칭은 구조적으로 새는 검사다. `PreToolUse(Bash)`에
  두는 모든 검사(4단계의 `backlog task create` 차단 포함)가 이 한계를 그대로 물려받는다.
- DRAFT-8: "사용자가 직접 실행했다"류의 표식은 모델이 생성할 수 있다. 2단계의 사람 승인을
  트랜스크립트 표식으로 판정하려는 접근은 이 문제와 같은 성질이다.
- DRAFT-5: 훅이 늘어날 때의 레이턴시/세션 마비/무한루프 문제. 이 파이프라인을 강제하면
  PreToolUse 훅이 트랜스크립트 파싱까지 하게 되므로 레이턴시 항목이 직접 걸린다.
- DRAFT-3: backlog를 쓰지 않는 저장소에서는 4~7단계 검사가 조용히 통과해야 한다.
  반면 1~3단계는 backlog와 무관하게 적용 가능하다 — 적용 범위를 분리할지가 결정 사항.

## 착수 전에 정할 것

- **1~3단계를 강제할지, 관측만 할지.** 차단하면 "작은 수정 하나도 plan mode를 거쳐야
  하는가"라는 문제가 즉시 생긴다. 예외 기준(파일 수/변경 크기/유저의 명시적 지시)을 먼저
  정해야 한다. 관측만 한다면 Stop 훅에서 "이 세션은 계획 없이 구현했다"를 기록하는 정도.
- **2단계 승인의 근거를 무엇으로 삼을지.** 승인된 `ExitPlanMode` 호출을 증거로 인정할지,
  아니면 훅이 직접 검증 가능한 별도 신호(승인 파일 등)를 요구할지. DRAFT-8의 결론에 종속된다.
- **5단계 검사를 승격 시점에 둘지 커밋 시점에 둘지.** DRAFT-9가 이미 커밋 시점 검사를
  제안하고 있으므로 한 곳에 모을 수 있다. 다만 승격 시점(`PreToolUse(Bash)`에서
  `backlog draft promote` 감지)에 막으면 피드백이 빠르다.
- **DRAFT-9와의 관계.** 이 드래프트가 DRAFT-9를 흡수할지, DRAFT-9를 4/6/7단계 구현
  태스크로 남기고 이쪽이 1~3/5단계만 맡을지. 흡수하면 태스크 하나가 너무 커진다.
- **어느 레이어에 둘지.** claude-rails 훅은 Claude Code 이벤트 훅이고, git 훅(pre-commit 등)과
  레이어가 다르다. 사람이 터미널에서 직접 하는 작업까지 덮으려면 git 훅이 필요하다.

## 열린 질문 (추측하지 않고 남김)

- `PreToolUse`/`PostToolUse` 매처가 `ExitPlanMode`에 걸리는가 — 대화형 세션 실측 필요.
- plan mode에서 거부된(=유저가 승인하지 않은) `ExitPlanMode`의 `tool_result`는 승인된 경우와
  어떻게 구분되는가 — 승인 사례만 확인했다.
- `permission_mode`가 `"auto"`로 오는 걸 직접 못 봤다. `claude -p --permission-mode auto`로는
  페이로드에 `"default"`가 찍혔다(헤드리스에서 auto가 무시되는지, 매핑되는지 불명).
  트랜스크립트에는 `permissionMode: "auto"`가 분명히 존재하므로 대화형에서 재확인해야 한다.
- 서브에이전트 세션의 `permission_mode`는 부모와 어떻게 다른가 — 이 저장소의 워크플로가
  서브에이전트 위임을 기본값으로 삼고 있어서(유저 CLAUDE.md) 파이프라인 강제가 서브에이전트
  안에서도 걸려야 하는지 판단이 필요하다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ExitPlanMode에 PreToolUse/PostToolUse 매처가 실제로 걸리는지 대화형 세션에서 실측하고 결과를 기록
- [ ] #2 1~3단계(plan mode → 사람 검토 → 오토모드)를 차단으로 강제할지 관측·기록만 할지 결정 — 예외 기준 포함
- [ ] #3 2단계 사람 승인의 근거를 승인된 ExitPlanMode로 인정할지 별도 검증 가능 신호를 요구할지 결정(DRAFT-8 종속)
- [ ] #4 5단계 산출물 기반 검사(의존성 미설정 시 승격 거부, 작업순서 문서 존재·역참조, 순환 없음)를 검사 지점과 함께 설계
- [ ] #5 DRAFT-9와의 범위 분담 확정 — 흡수할지, 4/6/7단계는 DRAFT-9에 남길지
- [ ] #6 결정(2026-10-03): 1~3단계는 차단하지 않고 관측·기록만 한다. 세션별로 plan mode 진입·ExitPlanMode 승인·드래프트 생성·승격·커밋 여부를 기록하고, 계획 기록 없이 프로젝트 파일을 고친 세션은 Stop에서 경고(비차단)한다
- [ ] #7 4/6/7단계는 DRAFT-9 범위로 남긴다(흡수하지 않는다)
- [ ] #8 테스트를 추가하고 전체 스위트가 통과하며, settings.hooks.json·README 훅 표·설치된 사본에 반영한다
<!-- AC:END -->
