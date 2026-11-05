---
id: TASK-2
title: 'protect_secrets.py: 업스트림 delegation-sink 패턴 이식'
status: Done
assignee: []
created_date: '2026-09-18 16:12'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - hooks/protect_secrets.py
  - ../claude-code-hooks/plugins/protect-secrets/protect-secrets.js
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
karanb192/claude-code-hooks 업스트림(main)이 이 저장소가 포팅한 시점보다 훨씬 앞서 있다 — delegation-sink 탐지(시크릿 파일/변수가 gemini/codex/llm 등 외부 모델 CLI나 알려진 모델 API 호스트로 흘러가는 패턴)가 추가됐는데 claude-rails의 protect_secrets.py에는 없다. 단, 인터프리터로 파일을 읽어 Claude 자신의 컨텍스트로만 흘려보내는 패턴(외부 유출 아님, 예: python3 -c "print(open('.env').read())")은 업스트림 최신판도 문자열 매칭 구조상 못 막는 구조적 한계로 확인됨 — 이건 고칠 버그가 아니라 문서화 대상.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 karanb192 업스트림 protect-secrets.js(main)의 delegation-sink 정규식 로직을 Python으로 이식
- [x] #2 test_protect_secrets.py에 이식된 패턴에 대한 회귀 테스트 추가
- [x] #3 README 8장 훅 스펙 테이블에 업스트림 포팅 시점과 이번에 반영한 버전 명시
- [x] #4 인터프리터로 파일을 읽어 Claude 자신의 컨텍스트로만 흘려보내는 패턴은 구조적 한계로 README 10장에 명시
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
업스트림 karanb192/claude-code-hooks main의 protect-secrets.js에서 delegation-sink 탐지(시크릿 파일/변수 -> gemini/codex/llm 등 외부 모델 CLI, api.openai.com 등 모델 API 호스트) 로직을 hooks/protect_secrets.py에 bash_targets_delegation_sink()로 이식했다. 기존 bash_targets_protected_file() 구조는 그대로 유지하고 main()에서 두 검사를 함께 수행하도록 통합. test_protect_secrets.py에 회귀 테스트 9건(차단 5건 + 정상 명령 통과 3건 + 직접 함수 호출 1건) 추가, 전부 통과 확인. README.md 8장 protect_secrets.py 행에 업스트림 재동기화 시점과 delegation-sink 추가 사실을 명시하고, 10장에 '커맨드 문자열 매칭 방식은 인터프리터로 파일을 읽어 Claude 자신의 컨텍스트로만 흘려보내는 패턴을 구조적으로 못 막는다'는 알려진 한계를 추가했다. python3 -m pytest hooks/test_protect_secrets.py -v: 21 passed. python3 -m pytest hooks/ -q: 364 passed, 3 failed (test_main_exits_cleanly_on_malformed_stdin x3, 기존부터 있던 무관한 실패).
<!-- SECTION:FINAL_SUMMARY:END -->
