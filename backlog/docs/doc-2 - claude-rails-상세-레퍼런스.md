---
id: doc-2
title: claude-rails 상세 레퍼런스
type: specification
created_date: '2026-09-19 04:46'
updated_date: '2026-10-03 16:00'
---
# claude-rails 상세 레퍼런스

README.md는 의도만 짧게 담고, 이 문서가 전체 스펙이다 — 운영/개인 레포 구분, 전체
Phase 명세, HIL 지점 표, 27개(→28개→30개→31개→32개→33개) 훅 하나하나의 이벤트/matcher/설명, 설치/삭제
절차, 파일 구성까지 전부 여기 있다. README가 "왜"를 말한다면, 이 문서는 "무엇을,
어떻게"를 말한다.

---

## 0. 이 저장소가 존재하는 실제 맥락 — 왜 "개인 레포까지만"인가

이 저장소가 강제하는 워크플로는 실제 업무 프로세스 하나를 전제로 한다. 대상은 특정 프로젝트
하나가 아니라 **실제로 운영되는(production) 오픈소스/사내 레포 전반**이다:

```
운영(production) 레포                개인 레포 (fork)                 사람
─────────────────────    fork    ─────────────────────
어떤 운영 레포든           ─────▶  내 계정의 fork            ◀── Claude가 여기서 작업
(예: anthropics/claude-code,                                    (CI 게이트까지 전부 통과)
     anthropics/claude-cookbooks,
     그 외 실제로 기여 중인 모든 레포)
                                          │
                                          │  PR은 반드시 사람이
                                          ▼
                                   운영 레포로 Pull Request  ◀── 사람이 직접
```

- **개인 레포(fork)**: Claude가 자유롭게 작업하는 곳. 이 저장소의 훅들이 강제하는 "태스크
  기반 작업, 테스트 통과 후 커밋, dirty 상태로 턴 종료 금지" 같은 규칙은 전부 **여기까지만**
  적용된다 — 개인 레포 안에서는 CI 게이트(커밋/푸시 전 검증)까지 Claude가 전부 통과시켜야
  한다.
- **운영 레포(production)**: 실제 업스트림 프로젝트 전반 — 특정 레포 하나로 한정되지 않는다.
  여기로의 Pull Request는 **항상 사람이 직접** 연다. Claude가 PR 내용을 아무리 잘
  준비해놓아도(커밋, 설명, 테스트 결과까지 다 만들어놔도) 운영 레포에 실제로 제출하는 행위
  자체는 사람만 한다 — `gh pr merge`처럼 "이미 만들어진 PR을 머지"하는 것과, "운영 레포에 새
  PR을 여는 것"은 이 저장소 안에서 전혀 다른 신뢰 레벨로 취급된다.
- **이 레포 자체가 기록소다**: 개인 레포에서 Claude와 함께 작업하다 만난 훅의 구멍,
  잘못 짠 안전장치, 헷갈렸던 판단들을 backlog.md에 남긴다 — 회고는 `backlog doc list`,
  핵심 판단은 `backlog decision list`로 확인(예: `doc-1`, `decision-1`~`decision-5`).

지금까지 이 워크플로로 실제 작업해본 참고 프로젝트(전체 목록이 아니라 예시):

- [anthropics/claude-cookbooks](https://github.com/anthropics/claude-cookbooks)
- [anthropics/claude-code](https://github.com/anthropics/claude-code)

### 개인 레포에서 PR/이슈 한눈에 보기 — Claude 사고 선제 대응

개인 레포에서 Claude가 연 PR과, 그 과정에서 발견된 문제를 적어둔 Issue를 한 화면에서 같이
보면 "Claude가 이상한 소리를 했거나 사고를 쳤을 때" 더 빨리 알아챌 수 있다. `gh`는 PR과
Issue를 각각 따로 조회하는 명령만 제공하므로(자동 동기화 기능은 없음), 한 저장소 기준으로
둘을 나란히 보려면:

```bash
# 열려있는 PR + 열려있는 Issue를 한 화면에
gh pr list --repo <owner>/<repo> && echo "---" && gh issue list --repo <owner>/<repo>

# 최근 활동순으로 둘 다 보고 싶으면(더 빠르게 이상 징후 포착)
gh pr list --repo <owner>/<repo> --json number,title,updatedAt,author \
  --jq '.[] | "[PR]  #\(.number)  \(.updatedAt)  \(.title)"'
gh issue list --repo <owner>/<repo> --json number,title,updatedAt,author \
  --jq '.[] | "[ISSUE]  #\(.number)  \(.updatedAt)  \(.title)"'
```

**관례**: Claude가 뭔가 잘못 판단했거나("헛소리"), 작업 중 사고를 쳤을 때는 그 자리에서 고치고
끝내지 말고 GitHub Issue로 남긴다 — 제목에 `[claude-incident]` 접두어를 붙이고, 원인이 된 PR
번호를 본문에 링크한다. 이렇게 쌓인 Issue 목록 자체가 "Claude를 믿고 맡겨도 되는 범위가
어디까지인지"에 대한 누적 기록이 된다. (자동화된 PR↔Issue 연동 봇은 아직 없음 — 필요해지면
`10. 알려진 한계 / 다음 단계`에 추가할 것.)

---

## 1. 왜 이게 있는가

이 저장소의 의도는 하나다: **Claude Code와 함께 작업할 때, Claude가 내가 의도한 대로
행동하게 만드는 것.** 이상한 방향으로 새거나 반드시 지켜야 할 부분을 미리 명시해두고,
여러 보안 위협으로부터 사용자가 의도한 대로 Claude가 동작하도록 돕는 장치다 — 이게 이
저장소가 존재하는 유일한 이유이고, 이 문서의 나머지 장(章)은 전부 이 의도를 실제로
어떻게 구현했는지에 대한 설명이다.

**어떻게 구현했는가.** "이 순서로 작업해줘"라고 CLAUDE.md에 적어두는 자연어 약속만으로는
프롬프트 인젝션이나 컨텍스트 압축처럼, 의도와 다르게 흘러갈 수 있는 지점들 때문에 매번
지켜지기 어렵다 — 그래서 지킬 수 있는 부분은 아예 우회 불가능한 코드로 옮겼다. 이때
모든 규칙을 다 코드로 옮기려 하지 않고, 두 종류를 정확히 나눴다:

- **기계적으로 검증 가능한 지점** (태스크 없이 코드부터 수정, 테스트 없이 커밋, 커밋
  안 하고 턴 종료, 미완료 상태로 push, 시크릿 파일 열람, 위험한 셸 명령, 훅/설정 자체
  변조 등) → Claude Code의 [hooks](https://code.claude.com/docs/en/hooks)로
  **물리적으로 차단**한다. 프롬프트 인젝션을 포함해 어떤 경로로든 이 규칙을 벗어나면
  액션 자체가 실행되지 않는다.
- **결국 사람의 판단이 필요한 지점 — Phase 2 백로그 승인, Phase 4.3 push 전 코드 리뷰**
  → 훅으로 대체하지 않는다. 백로그 내용이 맞는지, 코드가 실제로 옳은지는 결국 사람이
  봐야 판단할 수 있는 문제이기 때문에, 이 두 곳만은 정직하게 사람에게 넘기고 대신
  **반드시 멈춰서 물어보게**(HIL) 설계했다 (7장 "HIL 지점 총정리" 참고). 모든 걸 훅으로
  막으려 하지 않는다는 게 이 저장소가 정직한 지점이다.

**그리고 이 장치의 범위는 "워크플로 준수 도구"보다 한 겹 넓다.** 애초 이 저장소는
backlog.md 워크플로 전용이었지만(5개 훅), 지금은 그 위에 프로젝트가 backlog.md를
쓰든 안 쓰든 항상 적용되는 범용 안전/관측 훅 23개가 더해졌고, TASK-29에서 드래프트 경유를 강제하는
backlog 전용 훅 2개가 늘어 총 30개가 됐다. TASK-30에서 하네스 예약 태그 출력을 막는 범용 훅
`reserved_tag_guard.py`가 더해져 범용 24개, 총 31개가 됐다. TASK-31에서 세션별 컨텍스트
플래그 파일을 기록하는 범용 훅 `context_flags.py`가 더해져 범용 25개, 총 32개가 됐다. TASK-32에서
작업 파이프라인(plan mode → 승인 → 드래프트 → 커밋 → 승격) 진행을 세션별로 기록하는 범용 관측 훅
`pipeline_trace.py`가 더해져 범용 26개, 총 33개다:

- **backlog.md 워크플로 전용** (7개, `backlog/config.yml`이 있는 프로젝트에서만 동작) —
  `session_start.py`, `require_active_task.py`, `pre_commit_check.py`,
  `pre_push_check.py`, `block_stop_if_dirty.py`(원래 bash로 있던 것과 1:1 대응),
  `require_draft_first.py`, `backlog_commit_scope.py`(TASK-29에서 추가).
- **범용 안전/관측 훅** (26개, backlog.md 여부와 무관하게 항상 동작) — 시크릿 보호,
  위험 명령 차단, 설정 변조 감시, 훅 자신의 복붙 코드가 사본 간에 어긋나지 않는지
  감시하는 self-guard(`dedup_drift_guard.py`), 세션 로깅, PR 리뷰 보조 등. 대부분
  [karanb192/claude-code-hooks](https://github.com/karanb192/claude-code-hooks)와
  [disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery)의
  MIT 라이선스 플러그인을 포팅한 것이다 (8장에 훅별로 출처 표시).

즉 이 33개는 "백로그 프로젝트의 워크플로 위반"만 막는 도구가 아니라, **이 컴퓨터에서
Claude Code가 하는 모든 행동에 대한 보안 경계**다 — backlog.md를 쓰지 않는 프로젝트
에서도 26개는 항상 켜져 있고, 그중 어느 하나도 Phase 2/4.3처럼 사람 판단이 필요한 것을
대신 판단해주지는 않는다. 기계적으로 검증 가능한 것과 아닌 것을 정확히 나눈 뒤, 전자는
코드로, 후자는 사람에게 — 이 구분이 "Claude가 내가 의도한 대로 행동하게 만든다"는
1장 첫머리의 의도를 실제로 지키는 방법이다.

---

## 2. 지금 이 컴퓨터에 뭐가 설치돼 있는가

전역 설치되어 있어 **모든 세션에 자동으로 적용**된다. 다만 1장에서 설명했듯 33개 중
7개(backlog.md 워크플로 훅)만 `backlog/config.yml`이 있는 프로젝트로 한정되고, 나머지
26개는 프로젝트 종류와 무관하게 항상 동작한다.

| 항목         | 경로                                                                                                                                |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| 훅 스크립트  | `~/.claude/hooks/claude-rails/*.py` (33개, Python, 실행권한 불필요 — `python3 <path>`로 호출)                                       |
| 훅 테스트    | `~/.claude/hooks/claude-rails/test_*.py` (훅과 같은 디렉토리에 33개, 1:1 대응 — `.coverage`/`.pytest_cache`도 이 디렉토리에서 생김) |
| 전역 설정    | `~/.claude/settings.json` (`hooks` 키만 병합됨, 기존 설정 보존)                                                                     |
| 전역 지침    | `~/.claude/CLAUDE.md` (`<!-- CLAUDE-RAILS:BEGIN -->` 블록)                                                                          |
| 설치 전 백업 | `~/.claude/settings.json.bak.<timestamp>`                                                                                           |
| 원본 소스    | 이 저장소 자체 ([github.com/coralstay/claude-rails](https://github.com/coralstay/claude-rails), private)                            |

각 훅 스크립트는 다른 훅 파일을 import하지 않는 **완전 독립형**이다 (bash 시절의
공용 함수 파일 `_lib.sh`는 더 이상 없음 — 각 스크립트가 필요한 로직을 자체적으로
갖는다. 부작용: 코드 중복은 있지만, 한 훅의 버그가 다른 훅을 절대 깨뜨리지 않는다).

재설치/업데이트하려면: 저장소에서 `git pull` 후 `./install.sh` 다시 실행 (재실행 안전,
CLAUDE.md는 마커로 중복 방지).

---

## 3. 어떻게 동작하는가 — 메커니즘 한눈에

1. Claude Code가 세션마다 `~/.claude/settings.json`의 `hooks` 설정을 읽는다.
2. 11가지 이벤트(`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
   `PostToolUseFailure`, `Stop`, `SessionEnd`, `ConfigChange`, `PreCompact`,
   `PermissionRequest`, `InstructionsLoaded`) 각각에 등록된 스크립트가 `matcher`(도구
   이름)와 `if`(명령 패턴) 조건에 맞을 때 자동 실행된다. 하나의 이벤트/매처에 여러
   훅이 걸려 있으면 등록 순서대로 전부 실행된다.
3. 33개 중 **backlog.md 워크플로 전용 7개**만 가장 먼저 "지금 이 디렉토리가 backlog.md
   프로젝트인가(`backlog/config.yml` 존재 여부)"부터 확인하고, 아니면 즉시 통과한다.
   나머지 **26개는 이 확인 없이 항상 동작**한다 — 시크릿 보호나 위험 명령 차단이 backlog
   프로젝트가 아니라고 꺼지면 안 되기 때문이다.
4. 차단이 필요한 훅은 **exit code 2**로 그 액션 자체를 막는다(편집 불가, 커밋 불가, 턴
   종료 불가, push 불가, 위험 명령 실행 불가 등). exit 2는 Claude Code 훅 사양상 대부분의
   차단 가능 이벤트에서 공통으로 통하는 방식이다. 단 `SessionStart`/`InstructionsLoaded`처럼
   애초에 차단을 지원하지 않는 이벤트도 있는데, 그런 훅은 정보 주입이나(`additionalContext`/
   `systemMessage`) 다른 이벤트(`UserPromptSubmit`/`PreToolUse`)와 짝을 이뤄 우회 차단하는
   방식을 쓴다(`instructions_audit.py`가 대표 사례, 8장 참고).
5. 차단이 아닌 훅도 많다 — 세션 로그 기록, TODO/FIXME 채점, 포매터 실행, 컨텍스트 비용
   집계처럼 **강제 없이 관측/보조만 하는 훅**이 33개 중 절반 가까이 된다(4장 범례의 ⚙️).
6. 막히면 Claude는 그 이유(스크립트가 stderr/JSON으로 낸 메시지)를 그대로 보고, 조건을
   충족시킨 뒤 다시 시도한다.

---

## 4. 표기 범례

이 문서 전체(아래 사용 흐름, Phase 표, HIL 표, 8장 훅 목록)에서 공통으로 쓰는 기호.
여기서 한 번만 정의하고 이후로는 재정의하지 않는다.

| 기호 | 의미                                                                                 |
| ---- | ------------------------------------------------------------------------------------ |
| 🧑   | 필수 HIL — 사람이 반드시 개입해야 진행됨                                             |
| 🧑?  | 조건부 HIL — 특정 상황에서만 Claude가 사람에게 멈춰서 물어봄                         |
| 🤖   | 훅으로 강제됨 — 어기면 그 액션 자체가 차단됨                                         |
| ⚙️   | 자동(강제 없음) — Claude가 스스로 판단/수행하거나, 훅이 관측/보조만 하고 막지는 않음 |

---

## 5. 사용 흐름 — 태스크 하나 따라가기 (backlog.md 워크플로)

까먹고 다시 왔을 때 이 섹션만 봐도 바로 쓸 수 있게, 실제로 손으로 치는 순서를 그대로
적는다. 이 흐름은 33개 훅 중 **backlog.md 워크플로 전용 7개**(2·3장 참고)가 관여하는
부분이다 — 시크릿 보호, 위험 명령 차단 같은 나머지 26개는 이 흐름과 별개로 항상
백그라운드에서 같이 동작한다.

```
🧑  "이 프로젝트에 로그인 기능 추가해줘" 라고 프롬프트

⚙️  Claude가 backlog overview / board view / search 로 현황 파악

⚙️  Claude가 backlog draft create "로그인 기능" --ac "..." (+ draft edit)
🤖  backlog task create로 바로 만들려 하면 훅(require_draft_first.py)이 막음
⚙️  Claude가 드래프트만 담아 git commit
🤖  드래프트 생성 커밋에 다른 파일이 섞이면 훅(backlog_commit_scope.py)이 막음

🧑  ★ Claude가 드래프트를 보여주면, 사람이 실제로 보고 승인/수정 지시
    (여기서 멈추지 않으면 Claude가 다음으로 못 넘어감 — 필수 HIL 중 하나, 다른 하나는
    아래 push 직전에 나옴)

⚙️  Claude가 backlog draft promote DRAFT-5 → TASK-12가 됨
⚙️  Claude가 backlog task edit TASK-12 --add-ref decision-3 --doc docs/auth.md
    (관련 결정/문서가 있으면 --ref/--doc으로 반드시 연결)
⚙️  Claude가 승격(+ ref/doc 연결)만 담아 git commit
🤖  승격 커밋에 다른 파일이 섞이면 훅(backlog_commit_scope.py)이 막음

⚙️  Claude가 backlog task view TASK-12 --plain 으로 태스크 정독
🤖  이걸 안 하면 다음 Edit/Write가 훅(require_active_task.py)에 막힘

⚙️  Claude가 backlog task edit TASK-12 -s "In Progress" -a @me
⚙️  Claude가 git checkout -b task/TASK-12

🤖  이제부터 Edit/Write 가능 (In Progress 태스크 있음 + task view 읽음)

⚙️  Claude가 작은 단위로 구현 → 테스트 → git commit
🤖  커밋 시점에 브랜치명(task/TASK-12)과 (설정했다면) 테스트 통과 여부를
    훅(pre_commit_check.py)이 확인
🤖  커밋 안 하고 턴을 끝내려 하면 훅(block_stop_if_dirty.py)이 막아서 계속 진행됨

    (위 사이클을 AC 단위로 반복 — 이 사이에도 포매터/시크릿 보호/위험 명령 차단 등
    범용 훅 26개는 매 Edit/Write/Bash마다 계속 같이 돈다)

🧑? 작업 중 AC 밖의 일을 발견하면 Claude가 반드시 먼저 물어봄
    (스코프를 넓힐지, 별도 태스크로 뺄지 — 조용히 확장 안 함)

⚙️  Claude가 backlog task edit --check-ac 1 --final-summary "..." -s Done

🧑  ★ push하기 전에 사람이 diff/커밋 로그를 실제로 검토
    (훅은 상태(Done)와 final summary 존재만 확인할 뿐, 코드 내용은 못 봄 — 여기서
    사람이 안 보면 아무도 안 본 채로 push된다)

⚙️  Claude가 git push
🤖  push 시점에 태스크가 Done 상태이고 final summary가 있는지 훅(pre_push_check.py)이
    확인 (프로젝트에 coverageCommand가 설정돼 있으면 pre_push_coverage_check.py가
    커버리지도 같이 확인)
```

이 흐름에서 **사람이 반드시 해야 하는 일은 두 가지**다 — 백로그를 만들었을 때 보고
승인하는 것, 그리고 push하기 전에 실제로 diff를 검토하는 것. 나머지는 Claude가 알아서
하거나, 어기면 훅이 막는다.

---

## 6. 전체 프로세스 명세 (Phase -1 ~ 5)

기호는 4장 표기 범례와 동일. backlog.md 워크플로 전용 훅 7개가 어느 Phase에서
관여하는지 표시한다.

### Phase -1. 셋업 🧑 (프로젝트당 최초 1회)

| #    | 액션                                         | 커맨드                                 |
| ---- | -------------------------------------------- | -------------------------------------- |
| -1.1 | 초기화                                       | `backlog init`                         |
| -1.2 | 상태/우선순위/타입/기본담당자 정의           | `backlog config set`                   |
| -1.3 | CLAUDE.md에 backlog 사용규칙 주입            | `backlog agents --update-instructions` |
| -1.4 | decision→`--ref`, doc→`--doc` 연결 규칙 명시 | (이 저장소의 CLAUDE.md 스니펫)         |

### Phase 0. 브리핑 & 현황 파악 🧑 트리거 → ⚙️ 자동

| #   | 액션                 | 커맨드                                          |
| --- | -------------------- | ----------------------------------------------- |
| 0.1 | 프로젝트 통계        | `backlog overview`                              |
| 0.2 | 칸반 스캔            | `backlog board view`                            |
| 0.3 | 통합 검색(중복 방지) | `backlog search "<키워드>" --plain`             |
| 0.4 | 진행중 작업 확인     | `backlog task list --status "<active>" --plain` |
| 0.5 | 기존 결정 확인       | `backlog decision list`                         |

### Phase 0.5. 드래프트 ⚙️ + 🤖 (필수 — 태스크는 드래프트 승격으로만 만든다)

TASK-29부터 🤖 `require_draft_first.py`가 `backlog task create`를 차단하고,
🤖 `backlog_commit_scope.py`가 "드래프트 생성 커밋"과 "승격 커밋"에 다른 변경이 섞이는
것을 막는다. 드래프트 생성 → 커밋 → (유저 승인) → 승격 → 커밋 순서로 각각 독립 커밋을 남긴다.

| #     | 액션           | 커맨드                   |
| ----- | -------------- | ------------------------ |
| 0.5.1 | 초안 생성/조회 | `draft create/list/view` |
| 0.5.2 | 확정 → 승격    | `draft promote <id>`     |
| 0.5.3 | 폐기           | `draft archive <id>`     |

### Phase 1. 백로깅 (Epic/Story/Task 생성) ⚙️ + 🤖

이 Phase를 지나는 순간부터 🤖 `require_active_task.py` 훅이 걸리기 시작한다 — In
Progress 태스크 없이는 이후 어떤 Edit/Write도 불가.

| #   | 액션                                   | 커맨드                                                                   |
| --- | -------------------------------------- | ------------------------------------------------------------------------ |
| 1.1 | 중복 확인                              | `search`, `task list --search`                                           |
| 1.2 | Epic 생성                              | `milestone add <name>`                                                   |
| 1.3 | 구조 결정 (단일/부모-자식/독립+의존성) | —                                                                        |
| 1.4 | 태스크 생성                            | `draft create --ac --dod ...` → 승인 후 `draft promote` (`task create`는 🤖 차단) |
| 1.5 | 관련 decision 연결                     | `--ref decision-N` → frontmatter `references:`                           |
| 1.6 | 관련 doc/외부링크 연결                 | `--doc <path\|url>` → frontmatter `documentation:`                       |
| 1.7 | 결과 보고                              | 태스크 ID/제목/AC 리스트업                                               |

### Phase 2. 검토 게이트 🧑 ★★★ — 필수 HIL

전체 프로세스에서 **훅으로 대체 불가능한 지점** 중 하나(다른 하나는 Phase 4.3 push 전
코드 리뷰). 사람이 실제로 백로그를 보고 승인해야만 Phase 3가 시작된다.

| #   | 액션           | 커맨드                                    |
| --- | -------------- | ----------------------------------------- |
| 2.1 | 전체 조망 제시 | `board view` / `board export` / `browser` |
| 2.2 | 승인           | → Phase 3 진행                            |
| 2.3 | 수정 요청      | `task edit`                               |
| 2.4 | 반려           | `task demote <id>` (Draft로 되돌림)       |

### Phase 3. 실행 루프 (태스크 단위, 반복)

| 서브단계              | 액션                                                                          | HIL/강제                                                                                        |
| --------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 3-0 컨텍스트 로딩     | `task view <ID> --plain` 먼저 읽기 (미승격 draft는 `draft list`로 수동 확인)  | 🤖 `require_active_task.py` — 안 읽으면 Edit/Write 차단                                         |
| 3-1 활성화            | `task edit -s "In Progress"` + `task/<ID>` 브랜치 전환                        | 🤖 `pre_commit_check.py` — 커밋 시 브랜치명 검사                                                |
| 3-2 리서치 → 계획     | 코드베이스 재조사 후 `task edit --plan` (생성 시점 접근법을 그대로 믿지 않음) | ⚙️ 판단 영역, 강제 없음                                                                         |
| 3-3 승인 게이트       | 중대한 설계/아키텍처 결정 포함 시 구현 전 승인 대기                           | 🧑? Claude Code Plan Mode 재사용                                                                |
| 3-4 구현 서브루프     | 슬라이스 구현→테스트→`--append-notes`→원자적 커밋→반복                        | 🤖 `pre_commit_check.py` — `.claude-rails.json`에 `testCommand` 설정 시 테스트 실패면 커밋 차단 |
| 3-4b 미커밋 종료 방지 | —                                                                             | 🤖 `block_stop_if_dirty.py` — dirty tree + In Progress면 턴 종료 차단                           |
| 3-5 스코프 이탈 감지  | AC 밖 발견 시 조용히 확장 않고 질문                                           | 🧑? 발견 시에만, 자동 검증은 미구현                                                             |
| 3-6 서브태스크 처리   | 서브태스크 1개만 할당 시 다음으로 자동 진행 금지                              | 🧑? 1개만 할당된 경우에만                                                                       |
| 3-7 완료 전환         | 증거(테스트 통과 로그 등) 확보 후에만 AC 체크                                 | ⚙️ 판단 영역, 자동 검증 미구현                                                                  |

### Phase 4. 완료 & 종결 🧑 + 🤖

| #   | 액션                            | 커맨드/강제                                                                                                                                                                     |
| --- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 4.1 | AC/DoD 체크, final-summary 작성 | `task edit --check-ac/--check-dod/--final-summary`                                                                                                                              |
| 4.2 | 상태 전환                       | `task edit -s Done`                                                                                                                                                             |
| 4.3 | **코드 리뷰**                   | 🧑 사람이 diff/커밋 로그를 실제로 검토 — push 전 필수 HIL                                                                                                                       |
| 4.4 | push 전 상태 확인               | 🤖 `pre_push_check.py` — `task/<ID>` 브랜치 push 시 status=Done && final summary 존재 확인. 프로젝트에 `coverageCommand` 설정 시 `pre_push_coverage_check.py`가 커버리지도 확인 |
| 4.5 | Push (기능/Story 단위)          | `git push`                                                                                                                                                                      |
| 4.6 | 태스크 아카이브                 | `task complete TASK-ID`                                                                                                                                                         |
| 4.7 | Epic 완료 시                    | `milestone archive`                                                                                                                                                             |
| 4.8 | (대안) 취소 경로                | `task archive` / `milestone remove/rename`                                                                                                                                      |

### Phase 5. 주기적 유지보수 ⚙️

훅은 세션 이벤트 기반이라 "며칠마다" 같은 진짜 주기 실행은 대상이 아니다 — `/loop`나
시스템 cron으로 별도 구성해야 한다. (`standup_autopilot.py`가 세션 단위로 일일 스탠드업
초안을 쌓아주긴 하지만, 이것도 세션이 열려야 실행되는 것이지 진짜 크론은 아니다.)

| #   | 액션             | 커맨드               |
| --- | ---------------- | -------------------- |
| 5.1 | 무결성 점검      | `doctor --fix --yes` |
| 5.2 | 완료 태스크 정리 | `cleanup`            |
| 5.3 | 정기 리포팅      | `overview`           |

---

## 7. HIL 지점 총정리

| 위치                            | 필수/조건부 | 트리거 조건                        | 훅으로 대체 가능?                                                                                                                                                                        |
| ------------------------------- | ----------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase -1 셋업                   | 필수        | 항상 (최초 1회)                    | 대체 불가 — 사람의 결정                                                                                                                                                                  |
| Phase 0 브리핑                  | 필수        | 항상 (요청 자체가 사람에게서 시작) | 대체 불가                                                                                                                                                                                |
| **Phase 2 검토 게이트**         | **필수**    | **항상, 예외 없음**                | **대체 불가 — 백로그 내용은 사람 판단**                                                                                                                                                  |
| 3-3 승인 게이트                 | 조건부      | 중대 설계/아키텍처 결정 포함 시    | Plan Mode로 흡수(이미 존재)                                                                                                                                                              |
| 3-5 스코프 이탈                 | 조건부      | AC 밖 작업 발견 시                 | 부분 대체 가능(LLM 판단형 훅, 미구현 — `dead_end_registry.py`는 "되돌린 접근 재시도"만 다루며 스코프 이탈과는 별개)                                                                      |
| 3-6 서브태스크                  | 조건부      | 서브태스크 1개만 할당 시           | 대체 어려움(판단 영역)                                                                                                                                                                   |
| **Phase 4.3 push 전 코드 리뷰** | **필수**    | **매 push 전, 예외 없음**          | **대체 불가 — 코드 내용은 사람 판단.** 현재 이 리뷰 자체를 확인하는 훅은 없음 — `pre_push_check.py`는 상태(Done)와 final summary 존재만 확인하고, "사람이 실제로 봤는지"는 검증하지 못함 |

Phase 2와 Phase 4.3, 두 곳 모두 **항상, 예외 없이** 발생하는 필수 HIL이다 — 나머지(3-3/3-5/3-6)는
특정 조건에서만 발생하는 조건부 HIL이라는 점에서 구분된다.

---

## 8. 훅 상세 스펙 — 33개, 이벤트별 정리

각 훅은 완전 독립형(다른 훅 파일을 import하지 않음)이다. 설명은 각 스크립트 최상단의
모듈 docstring을 그대로 옮긴 것 — 실제로 읽지 않은 동작은 적지 않는다. "출처" 열은
포팅 원본이 있는 경우만 표시(대부분
[karanb192/claude-code-hooks](https://github.com/karanb192/claude-code-hooks) 또는
[disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery), 둘 다
MIT/오픈소스). 🔒 backlog.md 프로젝트 전용(`backlog/config.yml` 없으면 즉시 통과), 나머지는
항상 동작.

### SessionStart

| 훅                     | 🔒  | 설명                                                                                                                                                                     |
| ---------------------- | --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [`session_start.py`](../../../hooks/session_start.py)     | 🔒  | backlog.md 프로젝트면 공식 워크플로 가이드와 무결성 이슈를 컨텍스트로 주입. SessionStart는 차단을 지원하지 않으므로 정보 주입 전용. bash 시절 `session-start.sh`의 후신  |
| [`session_logger.py`](../../../hooks/session_logger.py)    |     | 세션 전체(cwd, git 브랜치, 프롬프트, 파일 변경, bash 명령 — 시크릿은 best-effort로 마스킹)를 JSONL로 기록. `CC_SESSION_LOG_DIR`로 로그 위치 변경 가능(Obsidian vault 등) |
| [`dead_rules_audit.py`](../../../hooks/dead_rules_audit.py)  |     | CLAUDE.md 규칙 준수 스코어카드: Claude가 실제로 지킨/어긴 규칙을 집계해, 만성적으로 무시되는 규칙을 훅으로 승격할 후보로 표시                                            |
| [`standup_autopilot.py`](../../../hooks/standup_autopilot.py) |     | 전날 `session_logger.py` 로그에서 미해결 항목을 다음 세션 시작 시 다시 주입                                                                                              |
| [`bounty_board.py`](../../../hooks/bounty_board.py)      |     | 세션 시작 시 저장소의 TODO/FIXME/HACK 부채 현황을 보여줌(아래 PostToolUse 항목과 동일 스크립트)                                                                          |
| [`context_flags.py`](../../../hooks/context_flags.py)     |     | 세션별 컨텍스트 플래그 파일(`~/.claude/hooks-logs/flags/<session_id>.json`, `CC_HOOK_FLAGS_DIR`로 변경 가능)에 `source`를 기록하고, `compact`면 `post_compact`=true·압축 횟수 증가(TASK-31, 스키마는 doc-3). fail-open |

### UserPromptSubmit

| 훅                      | 🔒  | 설명                                                                                                                                                                                                                                                                              |
| ----------------------- | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`instructions_audit.py`](../../../hooks/instructions_audit.py) |     | CLAUDE.md/`.claude/rules/*.md`에서 숨겨진/적대적 지시(제로폭 유니코드, bidi override, 시크릿 유출 지시, curl\|sh 등)를 감지했을 때 세션을 잠그는 락 파일이 있으면 모든 프롬프트를 차단. `HOOK_AUDIT_LEVEL`(critical\|high\|strict, 기본 high), `HOOK_AUDIT_WARN_ONLY=true`로 조정 |
| [`session_logger.py`](../../../hooks/session_logger.py)     |     | 프롬프트를 세션 로그에 기록(이벤트 타입만 다름, 로그 파일은 SessionStart와 동일)                                                                                                                                                                                                  |
| [`dead_end_registry.py`](../../../hooks/dead_end_registry.py)  |     | "그거 안 됐어, 이유는 X" 같은 되돌림 패턴을 프롬프트에서 감지해 현재 세션에서 최근 편집한 파일에 등록                                                                                                                                                                             |
| [`pipeline_trace.py`](../../../hooks/pipeline_trace.py)  |     | payload의 `permission_mode == "plan"`이면 이 세션의 plan mode 진입을 파이프라인 상태 파일(`~/.claude/hooks-logs/pipeline/<session_id>.json`, `CC_PIPELINE_DIR`로 변경 가능)에 기록(TASK-32, 설계는 doc-4). 관측 전용, fail-open |

### PreToolUse

#### matcher: `Edit|Write`

| 훅                       | 🔒  | 설명                                                                                                                                          |
| ------------------------ | --- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| [`require_active_task.py`](../../../hooks/require_active_task.py) | 🔒  | In Progress 태스크가 있고 이번 세션에 `backlog task view`로 그 내용을 읽은 적이 있어야만 편집 허용. 대상 경로(realpath 기준)가 프로젝트 루트 밖이면(plan/memory/scratchpad 등) 검사하지 않는다. bash 시절 `require-active-task.sh`의 후신 |
| [`dead_end_registry.py`](../../../hooks/dead_end_registry.py)   |     | 등록된 죽은 접근을 다시 건드리려 하면 경고(차단 아님 — PreToolUse는 차단 이벤트에서 `additionalContext`를 지원하지 않으므로 stderr로만 표시)  |

#### matcher: `Bash`

| 훅                            | if 조건               | 🔒  | 설명                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------- | --------------------- | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`pre_commit_check.py`](../../../hooks/pre_commit_check.py)         | (없음)                | 🔒  | `task/<ID>` 브랜치에서만 커밋 허용 + `.claude-rails.json`의 `testCommand` 설정 시 테스트 통과 필수. bash 시절 `pre-commit-check.sh`의 후신. 명령 위치의 `git commit`만 판정(TASK-39, `echo`·따옴표·heredoc 안 글자 무시, 파싱 실패 시 보수적으로 커밋 취급). `if` 필터는 절대경로 호출을 놓쳐 제거                                                                                                                                                                                                                                                                                                          |
| [`backlog_commit_scope.py`](../../../hooks/backlog_commit_scope.py)      | (없음)                | 🔒  | `git commit` 시 스테이징(`git diff --cached --name-status -M`)을 보고, 새 드래프트(`backlog/drafts/` 추가)와 그 밖의 파일이 섞이면, 또는 승격(`backlog/drafts/` → `backlog/tasks/` rename)과 `backlog/tasks/` 밖의 파일이 섞이면 차단. 승격된 태스크 파일 자체의 수정은 허용. PreToolUse 시점 인덱스를 보므로 같은 명령 안의 단순 `git add <args>`와 `commit -a`는 임시 인덱스(GIT_INDEX_FILE)에서 재현해 판정한다. `git rm/mv`, pathspec 커밋, `bash -c` 우회, 터미널 직접 커밋은 범위 밖(모듈 docstring 참고). 커밋 감지와 `git add` 재현 모두 명령 위치만 본다(TASK-39, `if` 필터 제거) |
| [`require_draft_first.py`](../../../hooks/require_draft_first.py)       | (없음)                | 🔒  | 명령 위치에서 실제로 실행되는 `backlog task create`(basename 정규화, `;`/`&&`/`\|`/줄바꿈 세그먼트, env·래퍼 건너뜀)를 차단하고 `backlog draft create` → 승인 후 `draft promote`를 안내. 다른 명령의 따옴표 인자나 heredoc 본문 안의 텍스트는 통과. `bash -c`/`eval`/MCP 경유는 범위 밖(decision-1) |
| [`dedup_drift_guard.py`](../../../hooks/dedup_drift_guard.py)        | `Bash(git *)`         |     | 이 저장소 자체를 지키는 self-guard — REGISTRY가 손으로 복붙된 함수 12개(`is_backlog_project`, `has_command`, `has_active_task`, `run_shell`, `tokenize`, `split_segments`, `background_tasks_running`, `strip_heredoc_bodies`, `is_outside_project`, `command_head`, `git_subcommand_index`, `command_runs_git`)가 어느 훅 파일들에 등장해야 하는지를 추적해, 사본 간에 어긋나면(정규화된 AST 비교) 커밋 시점에 차단. `backlog/config.yml` 유무와 무관하게 `hooks/` 디렉토리 존재만으로 동작 판단(즉 REGISTRY가 가리키는 파일들이 실제로 있는 저장소, 곧 claude-rails 자신에서만 작동). REGISTRY는 검사 대상 저장소의 `hooks/dedup_drift_guard.py`(작업 트리)에서 `ast.literal_eval`로 데이터만 읽어 쓰고(import·실행 없음), 읽을 수 없거나 형태가 틀리면 설치본 REGISTRY로 검사(TASK-40). 저장소 REGISTRY는 비워져도 그대로 신뢰 — 보안 장치가 아니라 drift 감지기. `if` 필터는 의도적으로 유지(TASK-46): `/usr/bin/git commit`·`FOO=1 git commit`에선 실행되지 않지만 같은 drift를 `hooks/test_dedup_registry.py`가 테스트 스위트에서 잡으므로 조기 경고만 빠진다 — 계약 테스트 `hidden_ok`에 사유와 함께 등록 |
| [`pre_push_check.py`](../../../hooks/pre_push_check.py)           | (없음)                | 🔒  | `task/<ID>` 브랜치 push는 태스크가 Done && final summary 있을 때만 허용. bash 시절 `pre-push-check.sh`의 후신. `if` 필터는 `/usr/bin/git push`가 게이트를 우회하는 것이 실측돼 제거(TASK-46) |
| [`pre_push_coverage_check.py`](../../../hooks/pre_push_coverage_check.py)  | (없음)                |     | `.claude-rails.json`의 `coverageCommand` 설정 시 push 전 실제로 실행해 리포트를 보여줌(성공/실패 무관하게 매번), 실패 시에만 차단. 결과는 `<cwd>/.claude-rails/coverage-log.jsonl`에도 기록. 명령 위치의 `git push`만 판정(TASK-39). 실패 시 push를 막는 게이트라 pre_push_check와 같이 `if` 필터 제거(TASK-46) — push가 아닌 줄은 설정 파일·subprocess 없이 파싱 직후 종료 |
| [`block_dangerous_commands.py`](../../../hooks/block_dangerous_commands.py) | (없음)                |     | 재앙적/고위험 셸 명령 차단. `HOOK_SAFETY_LEVEL`(critical\|high\|strict)로 룰셋 선택                                                                                                                                                                                                                                                                                                                                                                 |
| [`pre_git_safety_check.py`](../../../hooks/pre_git_safety_check.py)     | (없음)                |     | main/master 직접 push, 보호 브랜치 삭제, 파괴적 `gh` 작업(pr merge/close, issue close, release/repo delete) 차단. git은 basename으로 비교(TASK-37). TASK-38: refspec 없는 bare push도 현재 브랜치·push.default·upstream으로 대상 판정. main/master는 `git ls-remote`로 원격 부재가 증명된 최초 push만 허용, 확인 실패·force·삭제는 차단. TASK-45: gh도 세그먼트별 명령 위치·basename으로 판정(`/usr/bin/gh`, `-R` 위치 무관), 같은 작업의 `gh api` 호출(PUT `pulls/N/merge`, DELETE repo·release, PATCH `state=closed`, GraphQL mutation)도 차단                                                                                                             |
| [`case_insensitive_guard.py`](../../../hooks/case_insensitive_guard.py)   | (없음)                |     | 대소문자만 다른 형제 경로가 있을 때 `rm -rf` 같은 삭제 명령이 의도치 않게 다른 대상을 지우지 않도록 방지(APFS/exFAT/NTFS 대응)                                                                                                                                                                                                                                                                                                                      |
| [`pr_provenance_stamp.py`](../../../hooks/pr_provenance_stamp.py)      | `Bash(gh pr create*)` |     | `gh pr create` 실행 전에 PR 본문에 provenance 정보(프롬프트 수, 테스트 실행 여부, Claude가 작성한 파일 수)를 자동 삽입. `/usr/bin/gh pr create`는 필터에 가려 도장이 빠지지만 차단 기능 없는 표시용이라 수용(TASK-46, 계약 테스트 `hidden_ok`) |

#### matcher: `Read|Edit|Write|Bash`

| 훅                   | 설명                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`protect_secrets.py`](../../../hooks/protect_secrets.py) | `.env`, SSH 키, 클라우드 자격증명, 키스토어 등 시크릿 파일의 읽기/수정/유출(Bash로 `cat`/`grep`/`cp` 하는 우회 포함)을 차단. `HOOK_SAFETY_LEVEL`(critical\|high\|strict, 기본 high). karanb192/claude-code-hooks의 MIT 라이선스 플러그인을 포팅한 것 — 2026-09-19에 업스트림 main과 재동기화해 delegation-sink 탐지(시크릿 파일/변수가 `gemini`/`codex`/`llm` 등 외부 모델 CLI나 `api.openai.com` 등 모델 API 호스트로 흘러가는 패턴 차단)를 추가로 이식함 |

#### matcher: `Bash|Edit|Write`

| 훅                 | 설명                                                                                                                                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`protect_tests.py`](../../../hooks/protect_tests.py) | 테스트 파일 삭제, 테스트처럼 안 보이게 리네임, skip/xfail로 테스트 비활성화 등 "가짜 그린"을 차단                                                                                                                                                 |
| [`config_guard.py`](../../../hooks/config_guard.py)  | 에이전트 자신의 가드레일 설정(`~/.claude/settings.json`, `~/.claude/hooks/`, `.claude/settings*.json`, `.mcp.json`, 플러그인 매니페스트) 변조 차단 — 존재하지 않던 파일을 새로 만드는 것도 변조로 취급. `CONFIG_GUARD_ALLOW=true`로 1회 우회 가능 |

#### matcher 없음 (모든 도구)

| 훅                      | 설명                                                                                                 |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| [`instructions_audit.py`](../../../hooks/instructions_audit.py) | 잠금 파일이 있으면 어떤 도구 호출도 차단(위 UserPromptSubmit 항목과 동일 스크립트, 같은 락 메커니즘) |

### PostToolUse

#### matcher 없음 (모든 도구)

| 훅                  | 설명                                                                                                                                                                                                                                              |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`session_logger.py`](../../../hooks/session_logger.py) | 도구 호출 결과를 세션 로그에 기록                                                                                                                                                                                                                 |
| [`nerf_receipts.py`](../../../hooks/nerf_receipts.py)  | 실패율, 편집 처리량, 모델 버전별 토큰/작업량을 기록하고 모델이 바뀌었을 때 실질적 변화를 표시. transcript의 `message.model`/`message.usage.iterations[]`를 그대로 사용(자기 보고 아님). `~/.claude/hooks-logs/nerf-receipts.jsonl`에 JSONL로 적재 |
| [`pipeline_trace.py`](../../../hooks/pipeline_trace.py) | 승인된 `ExitPlanMode`(PostToolUse는 승인된 경우에만 발생 — 실측), `EnterPlanMode`, 명령 위치에서 실제 실행된 `backlog draft create`/`promote`와 `git commit`, 프로젝트 안(realpath, `backlog/` 제외) 파일 수정을 세션별 상태 파일에 집계(위 UserPromptSubmit 항목과 동일 스크립트). 차단하지 않음 |

#### matcher: `Edit|Write`

| 훅                    | 설명                                                                                                                                                                                    |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`auto_stage.py`](../../../hooks/auto_stage.py)       | Claude가 수정한 파일을 자동으로 `git add`해서 `git status`가 항상 Claude가 건드린 것과 일치하게 함. git 저장소 밖/파일 밖에서는 조용히 무시                                             |
| [`format_code.py`](../../../hooks/format_code.py)      | 편집한 파일을 포매팅(ruff format/prettier --write) 후 린트/타입체크(ruff check/tsc --noEmit) 실행, 결과를 `systemMessage`로 피드백만 함(차단 없음). 해당 툴이 PATH에 없으면 조용히 무시 |
| [`dead_rules_audit.py`](../../../hooks/dead_rules_audit.py) | 편집이 있을 때마다 규칙 준수 집계를 갱신(SessionStart 항목과 동일 스크립트)                                                                                                             |
| [`bounty_board.py`](../../../hooks/bounty_board.py)     | TODO/FIXME/HACK 마커에 "발견 후 경과일수 기반" XP를 매기고, 마커가 포함된 줄을 지우면 지급. 기본 10 + 일당 2(최대 100)                                                                  |

#### matcher: `Read|Grep|Glob|Bash`

| 훅                | 설명                                                                                                             |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| [`context_hogs.py`](../../../hooks/context_hogs.py) | 도구 결과의 문자 수(÷4 근사치)를 로드한 파일에 귀속시켜, 세션에서 컨텍스트를 가장 많이 먹은 파일 리더보드를 만듦 |

### PostToolUseFailure

| 훅                 | 설명                                                                   |
| ------------------ | ---------------------------------------------------------------------- |
| [`nerf_receipts.py`](../../../hooks/nerf_receipts.py) | 도구 호출 실패도 같은 로그에 기록(위 PostToolUse 항목과 동일 스크립트) |

### Stop

| 훅                       | 🔒  | 설명                                                                                                                                          |
| ------------------------ | --- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| [`block_stop_if_dirty.py`](../../../hooks/block_stop_if_dirty.py) | 🔒  | In Progress 태스크가 있는데 커밋 안 된 변경이 있으면 턴 종료를 차단해 작은 커밋 루프를 끝까지 강제. bash 시절 `block-stop-if-dirty.sh`의 후신. TASK-31: Stop payload의 `background_tasks`가 비어있지 않으면(백그라운드 서브에이전트가 같은 트리를 수정 중일 수 있음) 통과, `stop_hook_active`면 통과해 차단-재시도 루프 없음 |
| [`reserved_tag_guard.py`](../../../hooks/reserved_tag_guard.py) |     | 어시스턴트의 마지막 응답(`last_assistant_message`)에 하네스 예약 태그(bash-input/bash-stdout/system-reminder 등 12종, 여닫는 형태 모두)가 펜스 코드블록·인라인 코드 밖에 있으면 정정을 요구하며 턴 종료를 차단(TASK-30). '사용자가 직접 실행했다'는 트랜스크립트 표식을 모델이 위조하는 걸 막는다. `stop_hook_active`면 통과해 무한루프 없음, transcript는 읽지 않음 |
| [`nerf_receipts.py`](../../../hooks/nerf_receipts.py)       |     | Stop 이벤트도 같은 로그에 기록                                                                                                                |
| [`standup_autopilot.py`](../../../hooks/standup_autopilot.py)   |     | 이번 턴의 파일/명령 활동을 오늘자 스탠드업 파일(`~/.claude/hooks-logs/standup/<YYYY-MM-DD>.md`)에 추가                                        |
| [`context_flags.py`](../../../hooks/context_flags.py)       |     | `background_tasks`로 `parallel_session`/`background_task_count`를 플래그 파일에 기록(위 SessionStart 항목과 동일 스크립트) |
| [`pipeline_trace.py`](../../../hooks/pipeline_trace.py)       |     | 이 세션이 plan mode/`ExitPlanMode` 기록 없이 프로젝트 파일을 수정했고 cwd가 git 저장소면 `systemMessage`(+stderr)로 한 번만 경고. exit 0 — 차단하지 않음(TASK-32 결정) |

### SessionEnd

| 훅                     | 설명                                 |
| ---------------------- | ------------------------------------ |
| [`session_logger.py`](../../../hooks/session_logger.py)    | 세션 종료를 로그에 기록              |
| [`dead_rules_audit.py`](../../../hooks/dead_rules_audit.py)  | 세션 종료 시점 규칙 준수 집계 마무리 |
| [`standup_autopilot.py`](../../../hooks/standup_autopilot.py) | 스탠드업 파일 마무리                 |

### ConfigChange (matcher: `user_settings\|project_settings\|local_settings\|policy_settings\|skills`)

| 훅                | 설명                                                                                                                                                                                                                                                                                                                                                                                            |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`config_watch.py`](../../../hooks/config_watch.py) | 세션 도중의 모든 설정 변경을 눈에 띄게 알림(기본) 또는 `CONFIG_WATCH_BLOCK=true`로 아예 차단. `config_guard.py`가 에이전트 자신의 편집을 막는 것과 달리, 이건 그 외 경로(악성 postinstall 스크립트의 `settings.json` 재작성 등)로 일어나는 아웃오브밴드 변경을 잡음. `policy_settings` 변경은 절대 차단하지 않고 경고만 함(관리형/엔터프라이즈 설정이라 이 세션이 오버라이드할 대상이 아니므로) |

### PreCompact

| 훅                      | 설명                                                                                                                                |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [`pre_compact_backup.py`](../../../hooks/pre_compact_backup.py) | 컨텍스트 압축으로 버려지기 직전에 전체 transcript를 `~/.claude/hooks-logs/transcript_backups/<session_id>-<timestamp>.jsonl`로 백업 |
| [`context_flags.py`](../../../hooks/context_flags.py) | 압축 `trigger`(auto/manual)와 시각을 플래그 파일에 기록(위 SessionStart 항목과 동일 스크립트) |

### PermissionRequest

| 훅                         | 설명                                                                                                                                                                                                                                               |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`permission_auto_allow.py`](../../../hooks/permission_auto_allow.py) | 실질적 위험이 없는 권한 요청만 자동 승인(Read/Glob/Grep은 항상, Bash는 셸 메타문자 없는 고정된 읽기전용 명령 목록에 한해). "allow"만 추가하며 "deny"는 절대 내리지 않음 — Edit/Write/그 외 Bash/MCP는 건드리지 않고 그대로 일반 권한 흐름으로 넘김 |

### InstructionsLoaded (matcher: 모두)

| 훅                      | 설명                                                                                                                                                                                                                                                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`instructions_audit.py`](../../../hooks/instructions_audit.py) | CLAUDE.md/`.claude/rules/*.md`가 로드될 때 내용을 스캔해 적대적 지시가 있으면 락 파일을 씀. 이 이벤트 자체는 차단을 지원하지 않으므로(exit code/`continue: false` 모두 현재 빌드에서 무시됨), 실제 차단은 락 파일을 확인하는 `UserPromptSubmit`/`PreToolUse` 쪽에서 일어남(위 항목들과 동일 스크립트, 3중 등록) |

---

## 9. 프로젝트별 설정 — `.claude-rails.json`

프로젝트 루트에 두면 두 가지를 켤 수 있다:

```json
{
  "testCommand": "npm test",
  "coverageCommand": "python3 -m pytest --cov=. --cov-fail-under=100"
}
```

- `testCommand` — `pre_commit_check.py`가 커밋 전에 실행해서 실패하면 커밋을 막는다.
- `coverageCommand` — `pre_push_coverage_check.py`가 push 전에 실행해서 그 커맨드 자체가
  실패(예: `--cov-fail-under` 미달)하면 push를 막는다. 항상 실제 실행 결과를 보여주며
  수치를 지어내지 않는다.

둘 다 없으면 해당 검사는 건너뛴다(`pre_commit_check.py`는 브랜치명 검사만 수행).
`testCommand`/`coverageCommand` 모두 내부적으로 셸에 그대로 넘겨 실행되므로, 신뢰할 수
있는 값만 넣을 것. 예시는 `.claude-rails.json.example` 참고(현재는 `testCommand`만
포함 — 필요하면 `coverageCommand`를 직접 추가).

---

## 10. 알려진 한계 / 다음 단계

- **상태 이름 고정**: backlog.md 워크플로 훅들이 `"In Progress"`를 하드코딩하고 있다.
  프로젝트가 `backlog config`로 상태명을 바꾸면 오작동할 수 있다.
- **`task view` 확인이 휴리스틱**: `require_active_task.py`는 transcript에서 "task
  view" 문자열 검색으로만 확인한다 — 완벽하지 않다.
- **3-5 스코프 이탈 감지 미구현**: `dead_end_registry.py`는 "이전에 되돌린 접근을
  재시도하는지"만 다루며, "AC 밖 작업으로 스코프가 넓어졌는지"는 별개 문제로 아직
  훅화되지 않았다. `prompt`/`agent` 타입 훅으로 LLM 판단을 걸 수는 있지만 오탐/누락
  검증이 필요해 보류 중.
- **3-7 AC 체크 전 증거 확인 미구현**: `PostToolUse`로 테스트 결과를 상태 파일에 남기고
  `--check-ac` 직전 `PreToolUse`가 그 파일을 확인하는 2단 구조가 필요하지만 미구현.
- **Phase 5 주기 실행 없음**: 훅은 세션 이벤트 기반이라 "N일마다" 실행은 `/loop`/cron으로
  별도 구성해야 한다. `standup_autopilot.py`도 세션이 열려야 도는 것이지 진짜 크론은
  아니다.
- **관측 훅들의 로그가 계속 쌓임**: `session_logger.py`/`nerf_receipts.py`/
  `pre_compact_backup.py`/`standup_autopilot.py`/`context_flags.py` 등이 `~/.claude/hooks-logs/` 아래에
  JSONL/마크다운/세션별 JSON을 계속 적재한다 — 로테이션/정리 메커니즘은 아직 없다.
- **PR↔Issue 자동 연동 없음**: 0장에서 설명한 `[claude-incident]` Issue 관례는 사람이
  수동으로 남기는 것이고, PR과 Issue를 자동으로 서로 링크/동기화해주는 봇/Action은 아직
  없다. 필요해지면 `gh pr comment`로 관련 Issue 번호를 자동 코멘트하는 GitHub Action 정도가
  다음 후보.
- **`protect_secrets.py`의 delegation-sink 탐지는 커맨드 문자열 매칭이라 구조적 한계가
  있다**: 인터프리터(`python3 -c "print(open('.env').read())"` 등)로 시크릿 파일을 읽어서
  외부로 보내지 않고 Claude 자신의 컨텍스트로만 흘려보내는 패턴은, 업스트림 최신판을 그대로
  옮겨도 막지 못한다 — 셸 명령을 정규식으로 매칭하는 방식 자체가 "읽은 내용이 실제로 어디로
  흘러가는지"까지는 추적하지 못하기 때문이다. 이건 버그가 아니라 이 탐지 방식의 근본적인
  한계로, 고치려면 커맨드 매칭이 아닌 다른 접근(예: 파일 접근 자체를 이 훅의 기존
  `is_protected_path` 경로로 별도 차단)이 필요하다. 이 한계를 근본적으로 풀 수 있는
  방향은 아래 syscall 레벨 샌드박스 항목과 같다 — `backlog draft view DRAFT-2` 참고.
- **커맨드 문자열 정규식/토큰 매칭 방식 자체가 구조적 한계다 — 이 저장소 대부분의 Bash
  매칭 훅이 이 방식이다**: `block_dangerous_commands.py`, `config_guard.py`,
  `protect_secrets.py`, `case_insensitive_guard.py`, `protect_tests.py`를 비롯해 이
  저장소의 Bash 훅 대부분이 `tool_input.command` 문자열을 정규식/토큰으로 검사해 위험한
  행동을 막는다. TASK-7에서 절대경로/상대경로로 verb를 위장하는 우회
  (`/usr/bin/git`, `./git` 등)를 `os.path.basename()` 정규화로 실제로 막았지만, 이건
  "발견되면 고칠 수 있는 버그"였다는 뜻이지 "정규식으로 위험한 행동을 완벽히 막을 수
  있다"는 뜻이 아니다. [sudoers 모범 사례](https://www.tecmint.com/sudoers-configurations-for-setting-sudo-in-linux/)가
  ([Red Hat 공식 문서](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/security_hardening/managing-sudo-access)도
  동일) verb 비교 시 절대경로 전체를 요구하거나 basename으로 정규화하는 걸 표준 대응으로
  삼는 것 자체가, 이런 매칭 방식이 원래 이런 우회에 취약하다는 방증이다. LLM 에이전트
  런타임 보안 리서치도 같은 결론이다 —
  [Characterizing Denylist Fragility in AI Agents (arXiv:2606.15549)](https://arxiv.org/pdf/2606.15549)는
  정규식 기반 커맨드 차단과 문자열 레벨 경로 검사가 인코딩 트릭, alias, 스크립팅 언어,
  간접 실행(변수 치환을 거친 재조립, 래퍼 스크립트, `eval` 등)으로 우회 가능함을 실측
  데이터로 보인다. 진짜 확실한 방어는 커널 레벨 강제(seccomp-bpf, eBPF, Landlock,
  bubblewrap 같은 syscall 가로채기)로 옮기는 것인데, 이미 LLM 에이전트 툴콜을 이렇게
  가두는 사례들이 있다 —
  [Sandlock: Confining AI Agent Code with Unprivileged Linux Primitives (arXiv:2605.26298)](https://arxiv.org/pdf/2605.26298),
  [커널 강제 샌드박스를 직접 구현한 사례](https://dev.to/xenaarchdev/how-i-built-a-kernel-enforced-sandbox-for-llm-agent-tool-calls-fm6).
  다만 Claude Code 훅은 애초에 커맨드 **문자열**만 건네받는 PreToolUse API이므로 이 훅
  스크립트들 안에서 syscall 레벨 강제를 구현하는 것 자체가 불가능하다 — 위 사례들처럼 하려면
  Claude Code 프로세스 자체를 감싸는 별도 샌드박스 레이어가 필요하고, 이는 이 저장소(훅
  스크립트 모음)의 범위를 벗어난다. 이 저장소가 포크해둔
  업스트림 `protect-secrets.js`도 README의 "Native pairing" 절에서 같은 한계("이 훅은
  커맨드 문자열만 보므로, 스크립트가 직접 여는 파일은 이 훅에 보이지 않는다")를 인정하고,
  Claude Code 자체의 `permissions.deny`(파일 경로 차단 — Bash의 `cat`/리더 명령/`< file`
  리다이렉트에도 적용됨)와 샌드박스 네트워크 화이트리스트
  (`sandbox.network.allowedDomains` + `strictAllowlist`)를 병행하라고 권한다:

  ```json
  {
    "permissions": {
      "deny": [
        "Read(.env)",
        "Read(.env.*)",
        "Read(~/.ssh/**)",
        "Read(~/.aws/**)",
        "Read(**/*.pem)"
      ]
    },
    "sandbox": {
      "enabled": true,
      "network": {
        "allowedDomains": ["github.com", "registry.npmjs.org"],
        "strictAllowlist": true
      }
    }
  }
  ```

  이 저장소의 훅들도 같은 원칙을 따라야 한다 — 커맨드 문자열 매칭은 "발견된 구멍을 계속
  찾아서 땜질하는" 층이지 완결된 방어선이 아니며, 실제 방어선은 이 훅들을 Claude Code
  자체의 `permissions.deny`/sandbox 설정과 같이 쓰는 조합이다. syscall 레벨 강제를 별도
  레이어로 분리할 가치가 있는지는 아직 탐색 단계다 — `backlog draft view DRAFT-2` 참고.

- **`if` 필터는 명령 텍스트를 하위 명령별 접두사로만 맞춘다 (2026-10-04 실측, TASK-46)**:
  설치본에서 `if: Bash(git *)`로 등록된 `pre_push_check.py`로 확인했다.
  `git push --dry-run nonexistent-remote-x some-branch`는 훅이 실행됐고(차단),
  `true && git push --dry-run ...`도 실행됐다(복합 명령은 하위 명령마다 맞춘다). 그러나
  `/usr/bin/git push --dry-run ...`는 훅이 실행되지 않고 명령이 그대로 실행됐다(원격이
  없어 실패했을 뿐) — 실행 파일 경로를 정규화하지 않는다. git 하위 명령이 없는 줄
  (`cd x && gh pr merge 1`)은 애초에 맞지 않는다 — 2026-10-03 PR 병합 사고(TASK-46)가
  이 경우다. 그래서 게이트·보안 훅은 `if` 없이 등록하고 훅 안에서 명령 위치로 판정한다.
  `hooks/test_hook_registration_contract.py`가 이 실측 의미를 흉내 내는 작은 시뮬레이터로
  각 훅의 검사 대상 대표 명령(훅 자신의 판정 함수로 확인)이 필터를 통과하는지 대조하고,
  필터에 가려지는 명령은 `hidden_ok`에 사유를 적은 것만 허용한다(현재 `dedup_drift_guard.py`
  경로·env 호출, `pr_provenance_stamp.py` 경로 호출). env 할당·래퍼(`FOO=1 git ...`,
  `sudo git ...`)는 실측하지 않아 맞지 않는 것으로 보수적으로 가정한다. Claude Code가
  바뀌면 다시 실측해 시뮬레이터를 고친다.

- **`dedup_drift_guard.py`는 사후검증만 한다**: REGISTRY에 등록된 함수가 사본 간에
  어긋나면 커밋 시점에 잡아내지만, "애초에 손으로 복붙 못 하게" 막지는 못한다 —
  Kubernetes의 `hack/update-codegen.sh` + `hack/verify-codegen.sh`처럼 하나의 소스에서
  생성하는 방식으로 바꾸는 게 더 근본적인 해법일 수 있는데, 아직 전환 여부를 판단하지
  않았다 — `backlog draft view DRAFT-1` 참고.

---

## 11. 설치 / 재설치 / 삭제

**설치/재설치**:

```bash
cd ~/githubs/claude-rails   # 이 저장소
./install.sh
```

전제조건: `backlog` CLI (`npm i -g backlog.md`), `python3` (`jq`는 더 이상 필요 없음).
재실행 안전 (CLAUDE.md는 마커로 중복 방지, 훅 스크립트는 그냥 덮어쓰기).

settings.json 병합은 `scripts/merge_settings.py`가 **추가 전용**으로 한다 (TASK-36 —
이전의 `jq -s '.[0] * .[1]'`은 배열을 통째로 교체해 같은 이벤트의 다른 도구 훅을 지웠다):

- 훅 항목은 (이벤트, matcher, command)로 식별한다. 없으면 같은 matcher의 첫 그룹에
  덧붙이고, 그런 그룹이 없으면 새로 만든다. 다른 도구의 항목과 `hooks` 외 최상위 키는
  건드리지 않고, 아무것도 지우지 않는다.
- 같은 command가 이미 있는데 `if`/`timeout` 등이 저장소와 다르면 그 자리에서 저장소
  값으로 갱신한다 (command가 `~/.claude/hooks/claude-rails/`를 가리키므로 저장소가 원본).
- 변경이 있을 때만 `settings.json.bak.<timestamp>` 백업 → 임시 파일에 쓰고 JSON 재검증 →
  원자적 교체. 기존 파일이 깨진 JSON이면 손대지 않고 중단한다. 추가/갱신 목록을 출력한다.
- 한계: 저장소에서 어떤 훅의 matcher나 이벤트를 바꾸면 옛 위치의 항목은 남는다(삭제하지
  않으므로). 그런 경우 백업과 비교해 수동으로 지운다.
- 테스트: `scripts/test_merge_settings.py` (임시 `HOME`에 대한 `install.sh` 종단 테스트
  포함). 훅 테스트와 함께 저장소 루트에서 `uvx pytest -q hooks scripts`로 돌린다.

**삭제**:

- `~/.claude/settings.json`에서 병합된 `hooks` 블록 제거
- `~/.claude/CLAUDE.md`의 `<!-- CLAUDE-RAILS:BEGIN -->` ~ `END` 블록 제거
- `~/.claude/hooks/claude-rails/` 삭제 (`.coverage`/`.pytest_cache`도 이 안에 있으므로
  같이 지워짐)

**검증**:

```bash
python3 -m json.tool ~/.claude/settings.json >/dev/null && echo OK
echo '{"cwd":"<backlog 프로젝트 경로>","transcript_path":"/nonexistent"}' \
  | python3 ~/.claude/hooks/claude-rails/require_active_task.py; echo "exit: $?"
```

훅 변경 후 반영이 안 되면 `/hooks` 메뉴를 한 번 열거나 세션을 재시작.

각 훅은 `test_<name>.py`로 단위 테스트가 있다 — 훅 로직을 고치면 같은 디렉토리에서
`python3 -m pytest`로 돌려볼 것:

```bash
cd ~/.claude/hooks/claude-rails && python3 -m pytest
```

---

## 12. 파일 구성

```
claude-rails/
├── README.md                # 이 문서 (단일 소스)
├── install.sh                # ~/.claude/에 설치하는 스크립트
├── settings.hooks.json       # ~/.claude/settings.json에 병합되는 hooks 블록
├── CLAUDE.md.snippet         # ~/.claude/CLAUDE.md에 추가되는 워크플로 안내
├── .claude-rails.json.example
├── scripts/                   # 훅이 아닌 보조 스크립트 (설치되지 않음)
│   └── merge_settings.py / test_merge_settings.py   # install.sh의 추가 전용 settings 병합
└── hooks/                     # 33개 훅 + 33개 test_*.py = 66개 파일, 전부 flat
    ├── session_start.py / test_session_start.py                    # 🔒 backlog 전용
    ├── require_active_task.py / test_require_active_task.py        # 🔒 backlog 전용
    ├── pre_commit_check.py / test_pre_commit_check.py               # 🔒 backlog 전용
    ├── pre_push_check.py / test_pre_push_check.py                   # 🔒 backlog 전용
    ├── block_stop_if_dirty.py / test_block_stop_if_dirty.py         # 🔒 backlog 전용
    ├── require_draft_first.py / test_require_draft_first.py         # 🔒 backlog 전용
    ├── backlog_commit_scope.py / test_backlog_commit_scope.py       # 🔒 backlog 전용
    └── (나머지 26개 훅 + 대응 test_*.py — 8장 이벤트별 표 참고)
```

각 훅과 그 테스트는 같은 디렉토리에 나란히 산다(별도 `tests/` 서브폴더 없음) — 설치
대상 디렉토리(`~/.claude/hooks/claude-rails/`)에 `.coverage`/`.pytest_cache`가 실제로
생기는 것도 테스트를 그 자리에서 그대로 돌리기 때문이다. `install.sh`도 이 컨벤션을
그대로 따라 훅 본체와 테스트를 함께 설치한다.

## 제거된 훅

**`pre_merge_check.py`** (2026-09-26, TASK-24에서 제거) — fast-forward 전용 병합을
강제했다. decision-10이 병합을 머지 커밋으로 바꾸면서 이 훅이 정책의 정반대를 강제하게 됐다.
`decision-5`(항상 rebase merge)의 관찰은 정확했으나 결론이 뒤집혀 있었다 — rebase merge는
committer 재작성을 없애지 않고 모든 커밋에 적용한다.
이후 `decision-11`(2026-10-03)이 decision-10을 대체했다 — 로컬 통합은 rebase 후
`git merge --ff-only`, 원격(GitHub PR) 병합은 머지 커밋(`gh pr merge --merge`)으로 한다.
