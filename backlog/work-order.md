<!-- work-order-hash: c6951376760f80c571890b513198484bdf4664b16d2458e46393afe4f50c2b61 -->
# 작업 순서

`work_order.py`가 backlog/tasks의 의존(`dependencies`)으로 만든 파일이다 — 직접 고치지 말고 다시 생성한다. 같은 단계의 태스크는 병렬로, 단계는 위에서 아래로 순차로 진행한다. Done 태스크와 없는 태스크에 대한 의존은 충족된 것으로 본다.

| 단계 | ID | 제목 |
|---|---|---|
| 1 | TASK-64 | 앞으로 할 일(draft · To Do)이 생길 때마다 의존 정리 · 작업 순서 재계산 · 커밋을 강제한다 |
| 1 | TASK-65 | 설계 문서로 이 저장소의 현행 동작 방식을 정의한다(코드 기준 있는 그대로) — 최상위 TASK-15 · 17 · 18 · 19 전파 포함 |
| 1 | TASK-69 | testFirst Done 게이트에서 '(수동)'으로 끝나는 AC · DoD는 테스트 표식을 요구하지 않는다(비즈니스 규칙은 예외 없음) |
| 1 | TASK-75 | 게이트를 세션 cwd가 아니라 명령 · 파일의 대상 저장소로 판정한다(cd · git -C · BACKLOG_CWD · 하위 디렉터리 · 워크트리, 모르면 거부) |
| 2 | TASK-67 | pre_commit_check의 fail-closed 테스트 타임아웃을 저장소로 회수하고, 설치본 · 저장소를 다시 맞춘다 |
| 2 | TASK-68 | 착수 검사(계획 승인 · 형식 · 작업 순서)를 task 브랜치 생성 · 전환 때도 걸고, Edit/Write 게이트가 현재 task 브랜치 카드의 In Progress를 확인하게 한다 |
| 2 | TASK-70 | task 브랜치의 커밋 메시지에 그 태스크 ID가 없으면 git commit을 거부한다(RAIL-025) |
| 2 | TASK-73 | 수동 검증 Done 게이트: [수동 검증] 항목은 증거 줄 + 사람 서명 Manual-Verified(Card-Digest)로 통과, 승인 시점 대비 변경 · 브랜치 무관 Done 차단 |
| 3 | TASK-66 | require_design_propagation: 태스크 변경을 브랜치 범위가 아니라 커밋 메시지의 태스크 ID로 고른다(쌓인 브랜치 · 브랜치 없음 대응) |
