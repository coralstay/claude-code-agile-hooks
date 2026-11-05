# decisions

**무엇인가**: 아키텍처/정책 판단을 기록한 되돌릴 수 없는 역사적 기록이다. 태스크가
아니라 "왜 이렇게 하기로 했는지"에 대한 근거를 남긴다. 현재 decision-1부터 decision-9까지
9건이 있다(decision-9는 decision-8을 개정한 기록).

**언제 쓰나**: 여러 방식 중 하나를 선택하고 그 선택이 앞으로의 작업에 계속 영향을 줄
때(예: PR 병합 전략, README 길이 정책) 기록한다. 판단이 바뀌면 기존 파일을 지우지 않고
새 decision을 만들어 이전 것을 개정한다고 명시한다.

**관련 명령**:

- `backlog decision create "title"` — 새 의사결정 기록 생성
- `backlog decision list` — 전체 의사결정 목록 조회

**CLI 제약**: `decision update`나 `decision delete` 명령이 없다. 내용을 고치거나
지워야 할 때는 직접 파일을 다루게 되며, 이는 공식 가이드의 "직접 수정 금지" 원칙과
충돌하는 지점이라는 걸 인지하고 진행해야 한다(decision-9 참고).
