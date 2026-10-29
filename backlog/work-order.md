<!-- work-order-hash: 211a8b995b74cd85a9c5a04ed476e5d7fe83a7a13ee159a9fce66d53e199545b -->
# 작업 순서

`work_order.py`가 backlog/tasks의 의존(`dependencies`)으로 만든 파일이다 — 직접 고치지 말고 다시 생성한다. 같은 단계의 태스크는 병렬로, 단계는 위에서 아래로 순차로 진행한다. Done 태스크와 없는 태스크에 대한 의존은 충족된 것으로 본다.

| 단계 | ID | 제목 |
|---|---|---|
| 1 | TASK-64 | 앞으로 할 일(draft · To Do)이 생길 때마다 의존 정리 · 작업 순서 재계산 · 커밋을 강제한다 |
| 1 | TASK-65 | 최상위 TASK-15 · 17 · 18의 설계 변경을 이 저장소 design/에 반영한다(새 훅 6개 · 계획 승인 · 작업 순서 · 테스트 파일 구조 · 커버리지) |
| 1 | TASK-66 | require_design_propagation: 태스크 변경을 브랜치 범위가 아니라 커밋 메시지의 태스크 ID로 고른다(쌓인 브랜치 · 브랜치 없음 대응) |
| 1 | TASK-67 | 설치본에만 있던 변경(project_root · 테스트 타임아웃)을 저장소로 회수하고, pre_commit · pre_push가 명령의 대상 저장소를 보게 고친다 |
