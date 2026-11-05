# archive

**무엇인가**: 더 이상 유효하지 않게 된 태스크를 담는 soft-delete 보관소다. 삭제가 아니라
이동이라서 이력은 남고, ID는 재사용 가능해진다.

**언제 쓰나**: 계획을 세웠지만 진행하지 않기로 한 태스크, 혹은 상황이 바뀌어 더 이상
의미가 없어진 태스크를 `backlog task archive`로 옮길 때 생긴다. 지금은 22개 태스크
전부 실제로 완료된 유효한 작업이라 archive로 옮길 대상이 없어 비어 있다.

**관련 명령**:

- `backlog task archive TASK-N` — 태스크를 이 폴더로 이동(soft delete)
- `backlog task list --plain` — archive된 태스크는 기본 목록에서 제외되고 조회됨
