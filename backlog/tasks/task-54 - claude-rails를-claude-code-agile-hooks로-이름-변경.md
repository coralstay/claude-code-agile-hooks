---
id: TASK-54
title: claude-rails를 claude-code-agile-hooks로 이름 변경
status: In Progress
assignee: []
created_date: '2026-10-05 07:49'
updated_date: '2026-10-05 11:45'
labels:
  - rename
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
유저가 claude-rails의 새 이름으로 claude-code-agile-hooks를 골랐다(Claude Code 작업에 애자일(스크럼·칸반) 절차와 품질·안전 게이트를 거는 훅 모음). GitHub 저장소도 coralstay/claude-code-agile-hooks로 이름이 바뀌었다. 계획: ~/.claude/plans/typed-chasing-conway.md

수용 기준(승격 시 AC로 등록):
1. 설치 경로를 ~/.claude/hooks/claude-code-agile-hooks로 바꾼다 (install.sh, settings.hooks.json)
2. 훅 출력 접두사 [claude-rails]와 코드·주석·docstring의 이름을 claude-code-agile-hooks로 바꾼다
3. 프로젝트 설정은 .claude-code-agile-hooks.json을 먼저 읽고 없으면 .claude-rails.json을 읽는다(로그 디렉토리도 같음). 세 경우(새 이름만/옛 이름만/둘 다) 테스트
4. 이 저장소의 .claude-rails.json을 .claude-code-agile-hooks.json으로 바꾸고 .gitignore는 두 로그 디렉토리를 모두 무시
5. install.sh는 옛 설치본이 있으면 안내만 하고 지우지 않는다
6. README · CLAUDE.md.snippet · doc-2 등 레퍼런스 문서 이름 변경. 완료 태스크·decision·회고 기록은 그대로 둔다
7. 테스트·커버리지 100% 게이트 통과
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 설치 경로를 ~/.claude/hooks/claude-code-agile-hooks로 바꾼다 (install.sh, settings.hooks.json)
- [ ] #2 훅 출력 접두사 [claude-rails]와 코드·주석·docstring의 이름을 claude-code-agile-hooks로 바꾼다
- [ ] #3 프로젝트 설정은 .claude-code-agile-hooks.json을 먼저 읽고 없으면 .claude-rails.json을 읽는다(로그 디렉토리도 같음). 새 이름만/옛 이름만/둘 다 테스트
- [ ] #4 이 저장소의 .claude-rails.json을 .claude-code-agile-hooks.json으로 바꾸고 .gitignore는 두 로그 디렉토리를 모두 무시
- [ ] #5 install.sh는 옛 설치본이 있으면 안내만 하고 지우지 않는다
- [ ] #6 README · CLAUDE.md.snippet · doc-2 등 레퍼런스 문서 이름 변경, 완료 태스크·decision·회고 기록은 그대로
- [ ] #7 테스트·커버리지 100% 게이트 통과
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
claude-rails를 claude-code-agile-hooks로 이름 변경.
- 설치 경로 ~/.claude/hooks/claude-code-agile-hooks, 훅 출력 접두사 [claude-code-agile-hooks], CLAUDE.md 마커 CLAUDE-CODE-AGILE-HOOKS:BEGIN/END.
- 프로젝트 설정: project_config_path()가 .claude-code-agile-hooks.json 우선, 없으면 .claude-rails.json. 로그는 옛 설정을 쓰고 .claude-code-agile-hooks/가 없을 때만 .claude-rails/, 그 외 .claude-code-agile-hooks/. 두 훅에 복사하고 dedup_drift_guard REGISTRY에 등록.
- merge_settings: 옛 hooks/claude-rails/ 경로의 같은 훅은 제자리에서 새 경로로 이전(중복 방지), 다른 도구 훅은 그대로.
- install.sh: 옛 CLAUDE.md 마커 블록과 옛 설치본은 안내만 하고 지우지 않음.
- README·doc-2·CLAUDE.md.snippet·backlog/config.yml(project_name)·backlog/readme.md·CI 갱신. 기록 문서는 그대로.
- 검증: 테스트 1695 통과, 커버리지 100%.
<!-- SECTION:FINAL_SUMMARY:END -->
