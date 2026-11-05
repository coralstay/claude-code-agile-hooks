# docs

**무엇인가**: 태스크나 의사결정으로 분류하기엔 애매한 참고 문서(레퍼런스, 세션 회고 등)를
담는다. 현재 doc-1(세션 회고)과 doc-2(상세 레퍼런스) 두 건이 있으며, 서브폴더 없이
평평한 구조를 유지한다.

**언제 쓰나**: 같은 산출물(예: README)을 여러 태스크에 걸쳐 계속 손볼 때는 새 doc을
만들지 않고 기존 doc의 표에 이어 기록한다(decision-9). 완전히 다른 주제일 때만 새 doc을
만든다.

**관련 명령**:

- `backlog doc create "title"` — 새 문서 생성
- `backlog doc update DOC-N --content "..."` — 문서 내용 갱신(전체 교체)
- `backlog doc view DOC-N --plain` — 문서 내용 조회
- `backlog doc list` — 전체 문서 목록 조회
