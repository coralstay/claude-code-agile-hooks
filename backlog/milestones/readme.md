# milestones

**무엇인가**: 관련 태스크 여러 개를 하나의 큰 목표(Epic)로 묶는다. 태스크 자체가 아니라
태스크들을 그룹화하는 상위 단위다. 현재 m-0(훅 안전장치 감사 및 수정, TASK-1~12),
m-1(README 재작성, TASK-13~21), m-2(문서 체계 정리, TASK-22) 3개가 있다.

**언제 쓰나**: 여러 태스크가 하나의 큰 흐름(예: 감사 → 수정, 여러 차례의 README
재작성)을 이룰 때, 나중에 `task list`만으로는 그 묶음이 보이지 않으므로 milestone으로
묶어둔다.

**관련 명령**:

- `backlog milestone add "name" -d "..."` — 새 마일스톤 생성
- `backlog task edit TASK-N -m "milestone"` — 태스크를 마일스톤에 배정
- `backlog milestone list --show-completed` — 완료된 마일스톤까지 포함해 조회
