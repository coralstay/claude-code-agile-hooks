---
id: TASK-62
title: JS · TS · Java · Python · C++ 커버리지 100%와 리포트 생성을 훅으로 강제한다
status: Done
assignee: []
created_date: '2026-10-12 02:27'
updated_date: '2026-10-21 14:05'
labels:
  - hooks
dependencies: []
references:
  - decision-3
  - decision-12
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저 요청(2026-10-12): JavaScript · TypeScript · Java · Python · C++ 단위 테스트는 코드 커버리지 100%를 강제하고, 매번 리포트를 따로 둔 디렉토리(프레임워크를 쓰면 공식 문서의 기본 위치)에 만든다.

현재 상태: pre_push_coverage_check.py는 opt-in이다. 프로젝트 설정에 coverageCommand가 있을 때만 push 전에 실행하고, 명령이 실패할 때만 막는다. 임계값과 리포트 위치는 프로젝트가 정한다.

리포트 위치(공식 기본값, 구현 전에 각 공식 문서로 다시 확인한다):
- Python: pytest-cov / coverage.py → htmlcov/ (+ coverage.xml)
- JS/TS: Jest coverageDirectory 기본값 coverage/ · Vitest coverage.reportsDirectory 기본값 ./coverage
- Java: JaCoCo Maven target/site/jacoco/ · Gradle build/reports/jacoco/test/
- C++: 공식 기본값이 없음 → gcovr / llvm-cov 출력을 coverage/에 둔다

미결: 기준을 line + branch로 할지, function · statement까지 포함할지.

관련: pre_push_coverage_check.py, protect_tests.py(커버리지 무력화 방지), RAIL-006. 설계 문서 반영은 coralstay-software-factory 후속 draft(NFR-017 예정)에서 한다.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 매니페스트(package.json/tsconfig.json · pom.xml/build.gradle(.kts) · pyproject.toml/setup.cfg/pytest.ini · CMakeLists.txt)로 5개 언어를 감지한다
- [x] #2 감지된 언어가 있는데 coverageCommand가 설정되지 않았으면 push와 -s Done을 deny한다(이 경우 opt-in에서 필수로 바뀜)
- [x] #3 coverageCommand가 실패하거나(100% 미달) 실행 후 언어별 리포트 위치에 리포트 파일이 없으면 deny한다
- [x] #4 언어별 100% 설정 예(--cov-fail-under=100 · coverageThreshold · thresholds.100 · JaCoCo minimum 1.0 · gcovr --fail-under-*)와 리포트 위치를 README에 적는다
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 전체 테스트 통과 · 커버리지 100%(coverageCommand)
- [x] #2 새 훅은 settings.hooks.json · dedup REGISTRY · 등록 계약 테스트에 반영
- [x] #3 각 커밋에 TASK ID, push 전 Done + final summary
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Subjective
유저는 JS · TS · Java · Python · C++ 단위 테스트에 코드 커버리지 100%를 강제하고, 매번 리포트를 언어별 공식 기본 위치에 만들길 원한다(2026-10-12). 지표는 line + branch로 정했다(2026-10-21).

### Objective
- pre_push_coverage_check.py는 opt-in이다: coverageCommand가 있을 때만 push 전에 실행하고, 명령이 실패할 때만 막는다. 임계값 · 리포트 위치는 프로젝트가 정한다.
- 리포트 기본 위치 후보(공식 문서로 재확인 필요): Python htmlcov/ · coverage.xml, Jest · Vitest coverage/, JaCoCo Maven target/site/jacoco/ · Gradle build/reports/jacoco/test/, C++ 공식 기본값 없음 → coverage/.
- -s Done 시점의 커버리지 게이트는 없다.

### Assessment
언어 감지(매니페스트)가 되면 coverageCommand를 필수로 바꾸고, 실행 후 언어별 리포트 위치에 이번 실행 이후 mtime의 리포트가 있어야 통과시킨다. 감지 언어가 없으면 지금처럼 opt-in. 리포트 위치는 coverageReportDir로 바꿀 수 있다. 100% 기준은 line + branch이고, 판정은 coverageCommand의 종료 코드로 한다(임계값은 도구 설정에 둔다). -s Done 게이트는 성격이 같은 새 독립 훅(require_coverage_on_done.py, decision-3)으로 두고 push 훅과 감지 · 실행 로직을 REGISTRY 복사로 공유한다.

### Plan
1. 공식 문서로 언어별 기본 리포트 위치와 line + branch 100% 옵션을 확인해 README 표의 근거로 남긴다.
2. AC #1: 매니페스트로 5개 언어 감지 — 테스트 먼저.
3. AC #2: 감지됐는데 coverageCommand가 없으면 push · -s Done deny — 테스트 먼저.
4. AC #3: 명령 실패 또는 리포트 없음(이번 실행 이후 mtime) deny — 테스트 먼저(툴체인은 스텁).
5. AC #4: README에 언어별 100% 설정 예와 리포트 위치. 이 저장소 coverageCommand가 리포트를 만들도록 맞출 필요가 있으면 함께 고친다. 전체 테스트 · 커버리지 100%.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
착수 시 결정(유저, 2026-10-21): 커버리지 지표는 line + branch. -s Done 게이트는 새 독립 훅으로(Claude 판단, decision-3).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
JS · TS · Java · Python · C++ 프로젝트에 커버리지 100%(line + branch)와 리포트 생성을 강제했다.

- AC #1 pre_push_coverage_check.py: 프로젝트 루트 매니페스트(package.json · tsconfig.json · pom.xml · build.gradle(.kts) · pyproject.toml · setup.cfg · pytest.ini · CMakeLists.txt)로 언어 감지(4e7677a)
- AC #2 언어가 감지됐는데 coverageCommand가 없으면 push와 -s Done을 deny. -s Done 게이트는 새 독립 훅 require_coverage_on_done.py(decision-3, REGISTRY · settings · 등록 계약 반영). 감지 언어가 없으면 기존 opt-in 그대로(0bc1a0d)
- AC #3 명령 실패(100% 미달) 또는 이번 실행 이후 mtime의 리포트가 언어별 위치(python htmlcov/ · coverage.xml, js · ts · cpp coverage/, java target/site/jacoco/ · build/reports/jacoco/)에 없으면 deny. coverageReportDir(문자열 또는 언어별 맵)로 위치 변경(eef2e42)
- AC #4 README 언어별 100% 설정 예 · 리포트 위치 · 공식 문서 출처(2026-10-21 확인, Jest 기본값은 소스 근거, Gradle Kotlin · Vitest 100 리터럴은 미확인으로 표시), CLAUDE.md.snippet(77c8331)
- 이 저장소: coverageCommand에 --cov-report=term-missing --cov-report=xml 추가(push 게이트가 coverage.xml을 요구), .gitignore에 coverage.xml · htmlcov/

검증: 새 coverageCommand → 1905 passed, 4156 stmts · 1690 branches 100%, coverage.xml 생성 확인.
알려진 제한: 도구용 package.json만 있는 Python 저장소도 JS 리포트를 요구받는다(coverageReportDir 맵으로 우회). -s Done마다 coverageCommand 전체 실행(이 저장소 약 17초). 범위 밖: push 훅의 systemMessage 위치 · allow 자동 승인(기존 동작), dedup_drift_guard docstring 'The 27 hooks', CI 명령은 그대로.
<!-- SECTION:FINAL_SUMMARY:END -->
