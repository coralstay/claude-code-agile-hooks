# drafts

**무엇인가**: 아직 사용자 승인을 받지 못한 계획 초안을 담는다. task와 달리 곧바로
실행되지 않으며, 검토와 승인을 거쳐야 정식 태스크가 된다.

**언제 쓰나**: plan mode에서 세운 계획을 프롬프트로 먼저 보여주고 승인받은 뒤,
그 결과를 `backlog draft create`로 기록할 때 생긴다. 이 저장소의 워크플로에서는
draft가 다시 한번 사용자 승인을 받아야 `tasks/`로 승격된다.

**관련 명령**:

- `backlog draft create "title"` — 새 초안 생성
- `backlog draft promote DRAFT-N` — 승인된 초안을 정식 태스크로 승격
- `backlog draft archive DRAFT-N` — 진행하지 않기로 한 초안 보관
- `backlog draft list` — 대기 중인 초안 목록 조회
