---
id: doc-4
title: 작업 파이프라인 관측 설계
type: specification
created_date: "2026-10-03 07:34"
---

# 작업 파이프라인 관측 설계

TASK-32의 설계/실측 기록. 유저가 2026-09-26에 명시한 작업 파이프라인
(1 plan mode로 계획 → 2 사람 검토 → 3 오토모드 전환 → 4 드래프트 → 5 검증·정렬·문서화
→ 6 커밋 → 7 승격 후 다시 커밋)을 단계별로 "훅이 볼 수 있는가 / 막을 수 있는가 / 막아야
하는가"로 나누고, 1차 구현(`hooks/pipeline_trace.py`)의 범위를 적는다.

## 1. 단계별 강제 가능성

| 단계               | 훅이 보는 신호                                                                                                 | 이번 결정                                 | 담당                                |
| ------------------ | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | ----------------------------------- |
| 1 plan mode로 계획 | `permission_mode == "plan"`(UserPromptSubmit/PreToolUse/PostToolUse/Stop payload), `EnterPlanMode` PostToolUse | **관측·기록만**                           | `pipeline_trace.py`                 |
| 2 사람 검토·승인   | 승인된 `ExitPlanMode`의 PostToolUse (§2 실측) — 대리 신호일 뿐                                                 | **기록만, 게이트 근거로 쓰지 않음**       | `pipeline_trace.py`                 |
| 3 오토모드 전환    | 모드 전환 이벤트는 없음. 이후 이벤트의 `permission_mode`가 plan이 아니게 됨                                    | 별도 기록 안 함(2단계 승인 기록으로 갈음) | —                                   |
| 4 드래프트 경유    | 명령 위치의 `backlog task create`                                                                              | **차단**(기존)                            | `require_draft_first.py` (TASK-29)  |
| 5 검증·정렬·문서화 | 산출물(의존성, 작업순서 문서, 역참조)의 존재와 모양만                                                          | **설계만**(§4), 구현은 후속               | —                                   |
| 6 드래프트 커밋    | 스테이징 내용                                                                                                  | **차단**(기존)                            | `backlog_commit_scope.py` (TASK-29) |
| 7 승격 후 커밋     | 스테이징 내용                                                                                                  | **차단**(기존)                            | `backlog_commit_scope.py` (TASK-29) |

4/6/7단계의 실행 횟수(`draft create`/`draft promote`/`git commit`)는 `pipeline_trace.py`도
세션 상태에 **기록만** 한다 — 강제는 TASK-29 훅이 하고, 여기서는 한 세션의 흔적을 한 파일에서
읽을 수 있게 모을 뿐이다(검사 로직은 중복하지 않는다).

## 2. AC #1 실측: ExitPlanMode에 훅이 걸리는가

### 근거

- `session_logger.py`는 `PostToolUse`에 **matcher 없이** 등록돼 있다(`settings.hooks.json`).
  따라서 그 로그에 `ExitPlanMode`가 찍혔다면 PostToolUse 훅이 그 도구에 대해 실제로 실행된 것이다.
- `~/.claude/hooks-logs/sessions/154e853a-53bb-433c-aaea-27a46083c828.jsonl`에
  `{"event": "tool_use", "tool_name": "ExitPlanMode", "timestamp": "2026-09-12T06:30:49..."}`가 있다.
  같은 디렉토리에서 `ExitPlanMode` 레코드가 있는 세션 로그는 17개다.
- 교차 검증(2026-10-03): `~/.claude/projects/*/<session>.jsonl` 트랜스크립트에서 `ExitPlanMode`
  `tool_use`와 그 `tool_result`를 짝지어, 승인(`"User has approved your plan..."` /
  `"User has approved exiting plan mode..."`)과 거부(`is_error: true`, `"The user doesn't want to
proceed with this tool use..."`)를 세고, 같은 세션의 session_logger 로그 건수와 비교했다.

| 집계                                                                                        | 값                                                                                 |
| ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| ExitPlanMode가 있는 트랜스크립트 중 세션 로그도 있는 세션                                   | 23                                                                                 |
| 그중 "로그 건수 == 승인 건수"가 정확히 일치한 세션                                          | 22                                                                                 |
| 일치 세션의 승인 합계 / 로그 합계                                                           | 28 / 28                                                                            |
| 일치 세션의 거부(에러 포함) 합계                                                            | 67 — 로그에는 0건                                                                  |
| `nerf-receipts.jsonl`(PostToolUse + PostToolUseFailure, matcher 없음)의 ExitPlanMode 레코드 | PostToolUse 28, PostToolUseFailure 0 (같은 파일의 PostToolUseFailure 전체는 303건) |

불일치 1건(`acc14d94…`, 승인 2·로그 0)은 승인 시각(2026-09-04~09-10 01:08)이 그 세션 로그의
첫 레코드(2026-09-10 01:33, 로거 설치 시점)보다 앞서서 생긴 것이다.

### 결론

- **PostToolUse 훅은 `ExitPlanMode`에 걸린다** — 그리고 **승인된 경우에만** 걸린다.
  거부된 `ExitPlanMode`는 PostToolUse도 PostToolUseFailure도 남기지 않았다(관측 기간 안에서).
  따라서 "PostToolUse(ExitPlanMode) 발생 = 유저가 그 계획을 승인했다"로 읽을 수 있다.
- **PreToolUse 매처는 `ExitPlanMode`에 걸린다 — 거부·승인 모두** (2026-10-04 대화형 세션 실측).
  임시 측정 훅(프로젝트 로컬 설정에 PreToolUse·PostToolUse matcher `ExitPlanMode`로 등록, payload를
  그대로 기록)으로 같은 계획을 두 번 올렸다. 1회차 거부: PreToolUse만 실행(`permission_mode` plan),
  PostToolUse 없음. 2회차 승인: PreToolUse(plan)와 PostToolUse(`auto`) 둘 다 실행.
  PreToolUse payload 키는 `cwd, effort, hook_event_name, permission_mode, prompt_id, scratchpad_dir,
session_id, tool_input, tool_name, tool_use_id, transcript_path`이고, PostToolUse는 여기에
  `duration_ms`, `tool_response`(`{plan, filePath, isAgent}` — 승인된 계획 본문)가 더해진다.
- 따라서 PreToolUse(ExitPlanMode) = "계획을 올렸다(승인 여부 미정)", PostToolUse(ExitPlanMode) =
  "승인됐다"로 구분된다. 거부는 짝(`tool_use_id`)이 되는 PostToolUse가 없는 것으로만 추론된다.
  승인 직후 PostToolUse 시점에는 모드가 이미 plan을 벗어나 있다(`auto`).
- `permission_mode`는 PostToolUse payload에도 온다(위 실측).

## 3. 결정

### AC #2 / #6 — 1~3단계는 차단하지 않고 관측·기록만 한다

- 차단하면 "오타 하나 고치는 데도 plan mode를 거쳐야 하는가"라는 예외 기준 문제가 즉시
  생기고, `require_active_task.py`와 plan mode가 이미 한 번 충돌했던 것처럼(계획 파일 저장 차단)
  Edit/Write 게이트끼리 데드락을 만들 위험이 있다. 관측만 하면 예외 기준이 필요 없다.
- **예외 기준(경고 대상에서 빠지는 것)**: 프로젝트 밖 경로(realpath 기준, `~/.claude/plans`·
  memory·scratchpad — TASK-27과 같은 판정), 프로젝트 안이라도 `backlog/` 아래(문서·태스크
  파일은 구현이 아님), git 저장소가 아닌 cwd(버전 관리 밖의 스크래치 디렉토리는 보호할 이력이
  없고 경고는 잡음만 된다).
- 1~3단계는 backlog 사용 여부와 무관하게 적용한다(DRAFT-3 쟁점). 단 위처럼 **git 저장소로 한정**한다.
- Stop 경고는 **세션당 한 번**(`warned_at`), **exit 0**. JSON `systemMessage`(유저에게 표시)와
  stderr에 같은 문장을 낸다. 가시성 주의: Stop 훅의 exit 0 stderr는 Claude 컨텍스트에 들어가지
  않고, `systemMessage`도 유저 화면용이다 — 즉 이 경고는 **유저를 위한 기록**이고 Claude를 다시
  돌게 만들지 않는다(그게 의도: 차단-재시도 루프 없음, doc-3 문제 #3).

### AC #3 — 2단계 승인의 근거는 "승인된 ExitPlanMode"로 인정하되, 게이트에는 쓰지 않는다

- §2 실측대로 PostToolUse(ExitPlanMode)는 승인에서만 발생하므로 관측 신호로는 충분하다.
- 하지만 DRAFT-8/TASK-30이 보였듯 트랜스크립트 표식류는 위조 가능성을 원천 배제할 수 없고,
  무엇보다 1~3단계를 차단하지 않기로 했으므로 **승인 신호를 근거로 무언가를 허용/거부하지 않는다**.
  별도 승인 파일 같은 "검증 가능한 신호"는 요구하지 않는다 — 게이트가 없으니 위조할 동기도 없다.
  나중에 1~3단계를 차단으로 올린다면 이 결정을 다시 연다.

### AC #5 / #7 — DRAFT-9(TASK-29)와의 분담

- 4/6/7단계는 TASK-29의 `require_draft_first.py`/`backlog_commit_scope.py`에 남긴다(흡수하지 않음).
- 이 태스크는 1~3단계 관측과 5단계 설계만 맡는다. `pipeline_trace.py`가 4/6/7단계 실행을
  세는 건 기록용이며 검사 로직은 복사하지 않았다. 명령 토크나이저(`tokenize`/`split_segments`/
  `strip_heredoc_bodies`)와 프로젝트 경로 판정(`is_outside_project`)은 원본을 그대로 복사하고
  `dedup_drift_guard.py` REGISTRY에 등록했다(decision-2/3: 공용 모듈 대신 사후 검증).

## 4. AC #4 — 5단계 산출물 검사 설계 (구현은 후속)

훅은 판단의 품질이 아니라 **산출물의 존재와 모양**만 본다. 아래는 그 범위 안의 설계다.

### 검사 지점: 승격 커밋 시점 (`PreToolUse(Bash)`, `git commit`)

- 후보는 (a) 승격 명령 시점(`backlog draft promote` 감지)과 (b) 승격 커밋 시점이다.
- **(b)를 택한다.** 이유: `backlog_commit_scope.py`가 이미 "이 커밋이 승격 커밋인가"
  (`backlog/drafts/* → backlog/tasks/*` rename)를 스테이징으로 판정하므로, 승격되는 태스크 집합을
  명령 문자열 추측 없이 **인덱스에서 정확히** 얻는다. 여러 드래프트를 연달아 승격한 뒤 한 커밋으로
  묶는 경우도 자연스럽게 "한 묶음"이 된다. (a)는 피드백이 빠르지만 승격을 한 건씩 하면 "2건 이상"
  규칙을 적용할 시점을 알 수 없다.
- 구현 위치: `backlog_commit_scope.py`에 붙이지 않고 별도 훅(예: `promotion_artifacts_check.py`)으로
  둔다 — 기존 차단 훅의 동작을 바꾸지 않기 위해서. 판정 헬퍼(`parse_name_status`,
  `is_promotion_rename`)는 복사 + REGISTRY 등록.

### 규칙

1. **의존성 미설정(복수 승격)** — 한 승격 커밋에 태스크가 2개 이상이고 그중 **어느 태스크에도**
   `dependencies`가 없으면 경고. 단일 승격에는 적용하지 않는다(의존성 없는 게 정상).
   의존성이 없는 게 정답인 묶음(완전 병렬)도 있으므로 1차는 **경고**, 실제 오탐률을 본 뒤 차단 여부를 정한다.
2. **작업순서 문서 존재** — 복수 승격일 때 `backlog/docs/` 어딘가에 이번 태스크 ID들을 본문에서
   모두 참조하는 문서가 있어야 한다. 없으면 `backlog doc create` 안내(경고).
3. **역참조** — 승격된 태스크의 frontmatter `documentation`에 그 작업순서 문서가 걸려 있어야 한다
   (`backlog task edit <ID> --doc <path>`). 한쪽만 가리키면 `task view` 한 번으로 맥락이 안 모인다.
4. **순환 없음** — 승격 묶음 + 기존 태스크의 `dependencies` 그래프에 순환이 있으면 이건 판단이 아니라
   순수 일관성 오류이므로 **차단 후보**. 1차 구현도 경고로 시작해 오탐이 없음을 확인한 뒤 올린다.
5. **검증 흔적(가장 약함)** — 드래프트 본문에 순차/병렬/설계오류 검증 섹션이 있는지. 제목만 보는
   검사라 우회가 자유로우므로 영구히 경고 전용.

### 의도적으로 포기하는 것

병렬 판단이 실제로 독립인지, 설계오류 검증이 설계를 봤는지, 의존성 순서가 옳은지(순환 없음 ≠ 올바름),
작업순서 문서가 실제 계획과 맞는지 — 훅이 볼 수 없다. 형식만 채우는 의식(ritual)이 되지 않도록
규칙 5는 차단으로 올리지 않는다.

## 5. 1차 구현: `hooks/pipeline_trace.py`

- 이벤트: `UserPromptSubmit`, `PostToolUse`(matcher 없음), `Stop`. PreToolUse에는 등록하지 않았다 —
  plan mode에서 쓰는 도구 호출은 PostToolUse에도 오고, plan mode 진입은 UserPromptSubmit·
  `EnterPlanMode`·`ExitPlanMode`로 잡히므로 PreToolUse 프로세스를 하나 더 띄울 이유가 없다(doc-3 레이턴시).
- 상태 파일: `~/.claude/hooks-logs/pipeline/<session_id>.json`(`CC_PIPELINE_DIR`로 변경). TASK-31
  `flags/`와 형제 디렉토리지만 파일은 분리했다 — 두 훅이 같은 Stop에서 같은 파일을 read-modify-write
  하면 키가 유실될 수 있어서. 쓰기는 `fcntl` 락 + 임시파일 `os.replace`(병렬 PostToolUse의 카운트 유실 방지).
- 기록 키: `plan_mode_seen(_at)`, `plan_approved_count`/`plan_approved_at`/`last_plan_title`,
  `draft_create_count`, `draft_promote_count`, `commit_count`, `project_edit_count`/
  `first_project_edit_at`, `edited_before_plan`, `warned_at`. 스키마 주석은 모듈 docstring.
- 명령 감지는 명령 위치 기준(따옴표 인자·heredoc 본문 무시, basename 정규화, env/래퍼 건너뜀).
  `bash -c`/`eval` 경유는 못 본다(decision-1). `commit_count`는 PostToolUse까지 간 시도 수이고
  커밋 성공 여부는 확인하지 않는다.
- fail-open: 어떤 예외도 exit 0. 관련 없는 도구 호출은 파일을 건드리지 않는다.

## 6. 열린 질문

- ~~PreToolUse 매처가 `ExitPlanMode`에 걸리는가~~ — 걸린다, 거부·승인 모두(§2, 2026-10-04 실측).
- 거부된 `ExitPlanMode`가 이벤트를 전혀 남기지 않는 게 모든 거부 방식(Esc, 피드백 입력 등)에서
  같은가 — 관측된 거부 67건은 전부 이벤트 없음이었지만 거부 방식별로 나눠 보진 않았다.
- `permission_mode == "auto"`가 대화형 payload에 실제로 오는가, PostToolUse payload에도 오는가.
- 서브에이전트: 서브에이전트 도구 호출 훅이 부모의 `session_id`로 오는지 확인 필요. 같다면 서브에이전트의
  수정은 부모 세션의 계획 기록으로 판정된다(현재 동작). 서브에이전트 종료는 `SubagentStop`이라 경고는
  부모 `Stop`에서만 난다.
- 경고가 실제로 유용한지(오탐 비율) — 설치 후 `pipeline/` 상태 파일을 모아 본 뒤 5단계 구현 여부와 함께 판단.
