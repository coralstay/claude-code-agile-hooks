# backlog

**무엇인가**: 이 저장소(interlock, 옛 이름 claude-rails)의 작업 기록 전체를 담는 최상위 디렉토리다. 할 일부터
초안, 참고 문서, 의사결정, 마일스톤, 완료/보관 태스크까지 Backlog.md CLI가 관리하는
모든 산출물이 여기 들어간다.

**언제 쓰나**: `backlog init`으로 저장소를 초기화할 때 한 번 생성되며, 이후로는
직접 건드릴 일 없이 아래 서브폴더별 CLI 명령을 통해서만 내용이 채워진다.

**관련 명령**:

- `backlog overview` — 전체 현황(진행 중 태스크, 마일스톤 진척도 등) 요약
- `backlog board view` — 상태별 칸반 보드로 태스크 확인
- `backlog search "query"` — 태스크/문서/의사결정 전체에서 키워드 검색

**서브폴더 안내**: `tasks/`, `drafts/`, `docs/`, `decisions/`, `milestones/`,
`completed/`, `archive/` — 각 폴더의 역할은 폴더 안의 readme.md를 참고한다.
