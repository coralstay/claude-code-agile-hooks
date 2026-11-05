# tasks

**무엇인가**: 승격되어 실제로 진행 중이거나 앞으로 진행할 작업 단위를 담는다. 각 파일은
제목, 수용 기준(AC), 상태(To Do/In Progress/Done), 소속 마일스톤 등을 가진 하나의
태스크다.

**언제 쓰나**: draft가 사용자 승인을 받아 `backlog draft promote`로 승격되는 시점,
또는 계획이 필요 없는 명확한 작업을 바로 `backlog task create`로 만들 때 생긴다.
완료된 태스크는 삭제되지 않고 이 폴더에 Done 상태로 남아있다가, 오래되면
`backlog cleanup`으로 `completed/`로 이동한다.

**관련 명령**:

- `backlog task create "title" --ac "..."` — 새 태스크 생성
- `backlog task edit TASK-N -s "In Progress"` — 상태/마일스톤 등 메타데이터 수정
- `backlog task view TASK-N --plain` — 작업 시작 전 반드시 읽어야 하는 상세 내용
- `backlog task list --status "<status>" --plain` — 상태별 목록 조회
