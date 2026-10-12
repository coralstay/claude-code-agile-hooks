---
id: DRAFT-10
title: JS · TS · Java · Python · C++ 커버리지 100%와 리포트 생성을 훅으로 강제한다
status: Draft
assignee: []
created_date: '2026-10-12 02:27'
updated_date: '2026-10-12 02:28'
labels:
  - hooks
dependencies: []
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
- [ ] #1 매니페스트(package.json/tsconfig.json · pom.xml/build.gradle(.kts) · pyproject.toml/setup.cfg/pytest.ini · CMakeLists.txt)로 5개 언어를 감지한다
- [ ] #2 감지된 언어가 있는데 coverageCommand가 설정되지 않았으면 push와 -s Done을 deny한다(이 경우 opt-in에서 필수로 바뀜)
- [ ] #3 coverageCommand가 실패하거나(100% 미달) 실행 후 언어별 리포트 위치에 리포트 파일이 없으면 deny한다
- [ ] #4 언어별 100% 설정 예(--cov-fail-under=100 · coverageThreshold · thresholds.100 · JaCoCo minimum 1.0 · gcovr --fail-under-*)와 리포트 위치를 README에 적는다
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. 공식 문서로 언어별 기본 리포트 위치와 100% 강제 옵션을 확인하고, 그 결과를 draft 설명에 적는다.
2. pre_push_coverage_check.py에 언어 감지와 '필수화' 분기를 추가한다. 감지되는 언어가 없으면 지금처럼 opt-in으로 동작한다.
3. 실행 후 리포트 위치(설정 키 coverageReportDir로 바꿀 수 있음, 기본값은 언어별 공식 위치)의 파일 존재와 mtime이 이번 실행 이후인지 확인한다.
4. -s Done 게이트는 require_test_first.py와 같은 파싱으로 감지한다(새 훅으로 둘지, 기존 훅을 확장할지는 착수 시 정한다).
5. 언어마다 픽스처 프로젝트를 만들어 테스트한다(외부 툴체인은 스텁으로 대체).
<!-- SECTION:PLAN:END -->
