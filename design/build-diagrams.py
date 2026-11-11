#!/usr/bin/env python3
# ---
# title: build-diagrams
# description: design/diagrams의 DOT·mermaid 원본을 SVG로 렌더하는 빌드 스크립트
# authors: [coralstay]
# license: AGPL-3.0-only
# status: draft
# created_date: '2026-11-06'
# updated_date: '2026-11-06'
# ---
"""design/diagrams/*.dot (·.mmd) → design/diagrams/<이름>.svg 독립 SVG 렌더.

표기 원칙 — DOT 우선:
  그래프 · 트리 · DAG · 플로우차트 · 파이프라인 · 클래스 다이어그램 · 경계 표현은 전부
  Graphviz DOT(.dot)으로 쓴다. DOT에 대응물이 없는 것(시퀀스 다이어그램 등)만 mermaid(.mmd)로
  쓴다. 이유는 레이아웃 품질(특히 의존성 DAG)과 소스 분리다.

원본과 생성물:
  원본은 design/diagrams/ 안의 .dot(그리고 시퀀스 하나는 .mmd)이다. 같은 디렉토리의 .svg는
  이 스크립트가 만드는 생성물이므로 직접 고치지 않는다. 그림을 고치려면 .dot/.mmd를 고치고
  이 스크립트를 다시 돌린다.

색 — 라이트/다크 대응:
  색은 .dot(그리고 mermaid-theme.json)에 센티넬 hex(#f00001 …)로 적는다. 이 스크립트가
  센티넬을 CSS 변수(var(--diagram-*))로 치환하고, 그 변수를 SVG 안의 <style>에 정의한다 —
  라이트 값이 기본이고 @media (prefers-color-scheme: dark)가 다크 값으로 덮는다. 그래서
  SVG 파일 하나가 장 Markdown의 ![](…svg) · GitHub <img> 어디서나
  보는 쪽 테마를 따라간다.

빌드 전제: graphviz(`dot`), mermaid 렌더용 `npx` + 로컬 Chrome.
mermaid-cli가 실패하면 기존 SVG를 그대로 둔다(아직 토큰화되지 않은 원시 mermaid 출력이면
토큰화만 한다).

사용: python3 design/build-diagrams.py
"""
import io, os, re, subprocess, sys, pathlib, tempfile

ROOT = pathlib.Path(__file__).parent
DIA = ROOT / "diagrams"
BUILD_MARK = 'data-generated-by="design/build-diagrams.py"'

TOKENS = {  # ---- 1
    "#f00001": "var(--diagram-ink)",     "#f00002": "var(--diagram-muted)",
    "#f00003": "var(--diagram-line)",    "#f00004": "var(--diagram-surface)",
    "#f00005": "var(--diagram-surface-2)", "#f00006": "var(--diagram-accent)",
    "#f00007": "var(--diagram-accent-bg)", "#f00008": "var(--diagram-accent-ink)",
    "#f00009": "var(--diagram-impl)",    "#f0000a": "var(--diagram-impl-bg)",
    "#f0000b": "var(--diagram-review)",  "#f0000c": "var(--diagram-review-bg)",
    "#f0000d": "var(--diagram-verify)",  "#f0000e": "var(--diagram-verify-bg)",
    "#f0000f": "var(--diagram-logger)",  "#f00010": "var(--diagram-logger-bg)",
}
# mermaid가 렌더한 SVG(시퀀스)는 일부 기본 팔레트를 하드코딩한다 — 같은 방식으로 토큰화한다.
MERMAID_TOKENS = {  # ---- 2
    "#262b34": "var(--diagram-ink)",      "#000000": "var(--diagram-ink)",
    "#f2f3f5": "var(--diagram-surface)",  "#eaeaea": "var(--diagram-surface-2)",
    "#9aa4b8": "var(--diagram-line)",     "#a8adb8": "var(--diagram-muted)",
    "#edf2ae": "var(--diagram-accent-bg)", "#fff5ad": "var(--diagram-accent-bg)",
    "#575247": "var(--diagram-muted)",    '"#666"': '"var(--diagram-line)"',
    '"#999"': '"var(--diagram-line)"',
}
# 토큰 값 — RFC(2026-09-26, git 이력)의 :root(--diagram-*)가 라이트,
# 같은 문서의 다크 블록(--ink · --line · --accent · --role-* …)이 다크 값이다.
LIGHT = {  # ---- 3
    "ink": "#1a2330", "muted": "#51616c", "line": "#c9d3d8",
    "surface": "#ffffff", "surface-2": "#eaf0f2",
    "accent": "#0e7c86", "accent-bg": "#d8eeef", "accent-ink": "#08565d",
    "impl": "#2b6cb0", "impl-bg": "#dbe9f7", "review": "#7c3aed", "review-bg": "#ece3fc",
    "verify": "#2f855a", "verify-bg": "#def0e6", "logger": "#5b6b78", "logger-bg": "#e4e9ec",
}
DARK = {
    "ink": "#e7eef2", "muted": "#9aaab4", "line": "#2e3d47",
    "surface": "#182129", "surface-2": "#1f2a33",
    "accent": "#3fc4ce", "accent-bg": "#163238", "accent-ink": "#8ee3e9",
    "impl": "#7db3e8", "impl-bg": "#1c2c3d", "review": "#b79bf5", "review-bg": "#291f3d",
    "verify": "#7cd1a3", "verify-bg": "#173226", "logger": "#a6b4bd", "logger-bg": "#232e36",
}
FONT = '"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif'


def theme_style() -> str:
    decl = lambda t: " ".join(f"--diagram-{k}: {v};" for k, v in t.items())
    return (f"<style>:root {{ {decl(LIGHT)} }}\n"
            f"@media (prefers-color-scheme: dark) {{ :root {{ {decl(DARK)} }} }}</style>")


def tokenize(svg: str) -> str:
    for table in (TOKENS, MERMAID_TOKENS):
        for sentinel, var in table.items():
            svg = svg.replace(sentinel, var).replace(sentinel.upper(), var)  # ---- 4
    return svg


def finish(svg: str, name: str, mermaid: bool) -> str:
    """정리 · 토큰화 · 테마 <style> 삽입을 거쳐 독립 SVG 문서를 만든다."""
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg, flags=re.S)
    svg = re.sub(r"<!--.*?-->\s*", "", svg, flags=re.S)
    # Graphviz가 깔아두는 흰 배경 폴리곤 제거(투명 배경 유지)
    svg = re.sub(r'<polygon fill="white"[^/]*/>\s*', "", svg)  # ---- 5
    svg = tokenize(svg)
    if not mermaid:
        svg = re.sub(r'font-family="[^"]*"', f"font-family='{FONT}'", svg)

    def fix_root(m):
        tag = m.group(0)
        if mermaid:
            # mermaid는 width="100%"와 style max-width를 준다 — <img>에서 크기가 잡히도록
            # viewBox 크기를 width/height로 쓴다.
            vb = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', tag)
            tag = re.sub(r'\s(width|height|style|role|aria-roledescription)="[^"]*"', "", tag)
            if vb:
                tag = tag.replace("<svg", f'<svg width="{vb.group(3)}" height="{vb.group(4)}"', 1)
        if "xmlns=" not in tag:
            tag = tag.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        return tag.replace("<svg", f'<svg {BUILD_MARK} role="img" aria-label="{name}"', 1)

    svg = re.sub(r"<svg\b[^>]*>", fix_root, svg, count=1)
    svg = re.sub(r"(<svg\b[^>]*>)", lambda m: m.group(1) + "\n" + theme_style(), svg, count=1)  # ---- 6
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg.strip() + "\n"


def render_mmd(path: pathlib.Path) -> str | None:
    """mermaid 소스를 mermaid-cli로 렌더한다. 실패하면 None(기존 SVG 유지 판단은 호출자)."""
    with tempfile.TemporaryDirectory() as tmp:
        raw = pathlib.Path(tmp) / f"{path.stem}.svg"
        cmd = [
            "npx", "-y", "@mermaid-js/mermaid-cli@11",
            "-i", str(path), "-o", str(raw),
            "-c", str(DIA / "mermaid-theme.json"), "-b", "transparent",
        ]
        env = dict(os.environ)
        env.setdefault("PUPPETEER_EXECUTABLE_PATH",
                       "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        print(f"  {path.stem}: mermaid-cli 렌더 중…")
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if r.returncode or not raw.exists():  # ---- 7
            last = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""
            print(f"    ! mermaid-cli 실패 — {last}")
            return None
        return finish(io.open(raw, encoding="utf-8").read(), path.stem, mermaid=True)


def render_dot(path: pathlib.Path) -> str:
    out = subprocess.run(["dot", "-Tsvg", str(path)], capture_output=True, text=True)  # ---- 8
    if out.returncode:
        sys.exit(f"dot 실패: {path}\n{out.stderr}")
    return finish(out.stdout, path.stem, mermaid=False)


def main() -> None:
    sources = sorted(DIA.glob("*.dot")) + sorted(DIA.glob("*.mmd"))
    if not sources:
        sys.exit(f"소스 없음: {DIA}")
    written = 0
    for src in sources:
        target = src.with_suffix(".svg")
        if src.suffix == ".dot":
            svg = render_dot(src)
        else:  # DOT에 대응물이 없는 것(시퀀스 등)만 mermaid
            svg = render_mmd(src)
            if svg is None:
                if not target.exists():
                    sys.exit(f"mermaid-cli 실패, 대체할 SVG도 없다: {src}")
                old = io.open(target, encoding="utf-8").read()
                if BUILD_MARK in old:  # ---- 9
                    print(f"    기존 {target.name}을 그대로 둔다")
                    written += 1
                    continue
                svg = finish(old, src.stem, mermaid=True)
                print(f"    기존 원시 {target.name}을 토큰화해 쓴다")
        io.open(target, "w", encoding="utf-8").write(svg)
        written += 1
        print(f"  {target.name}: {len(svg):,} bytes")
    print(f"완료 — SVG {written}개 → {DIA}")


if __name__ == "__main__":
    main()

# ======== 노트 ========
# 1 센티넬 hex → CSS 변수 표
#   설명: .dot에는 #f00001 같은 센티넬 색을 쓰고 빌드가 이 표로 var(--diagram-*)로 바꾼다. 그래야 SVG 하나가 문서의 라이트/다크 테마를 그대로 따라간다. 색을 추가하려면 여기와 LIGHT/DARK 양쪽에 넣어야 한다.
#   개념: 센티넬 hex
# 2 mermaid 하드코딩 색 표
#   설명: mermaid-cli가 렌더한 SVG는 기본 팔레트를 직접 박아 넣으므로 같은 방식으로 토큰화해 테마를 따르게 한다. 값은 mermaid 출력에 실제로 나오는 hex와 따옴표 포함 문자열이다.
#   관련: design/diagrams/mermaid-theme.json
# 3 라이트/다크 토큰 값
#   설명: LIGHT가 기본 :root 값이고 DARK가 prefers-color-scheme: dark에서 덮는 값이다. 두 표의 키가 같아야 한다. 값의 출처는 RFC(2026-09-26)의 --diagram-* 이다.
# 4 센티넬 치환
#   설명: Graphviz는 hex를 소문자나 대문자로 낼 수 있어 두 형태를 모두 치환한다. 한쪽만 하면 일부 색이 토큰화되지 않고 남아 다크 모드에서 어긋난다.
# 5 흰 배경 폴리곤 제거
#   설명: Graphviz가 그래프 전체에 깔아두는 흰 배경 polygon을 지워 SVG를 투명 배경으로 만든다. 남기면 다크 모드에서 흰 사각형이 뜬다.
# 6 테마 <style> 삽입
#   설명: 루트 <svg> 태그 바로 뒤에 한 번만(count=1) CSS 변수 정의를 넣는다. 변수 정의가 SVG 파일 안에 있어야 <img>로 불러도 테마가 따라간다.
# 7 mermaid-cli 실패 판정
#   설명: 종료 코드가 0이 아니거나 출력 파일이 없으면 실패로 보고 None을 돌려준다. npx와 로컬 Chrome에 의존하는 단계라 환경에 따라 자주 깨지므로, 호출자가 기존 SVG를 유지할지 판단한다.
# 8 dot 렌더 호출
#   설명: Graphviz dot을 -Tsvg로 돌려 stdout의 SVG를 받는다. 실패하면 stderr와 함께 즉시 종료한다. 잘못된 .dot을 조용히 넘기지 않기 위해서다.
# 9 기존 SVG 유지 판정
#   설명: mermaid-cli가 실패했을 때 기존 SVG에 이미 빌드 표식이 있으면 토큰화가 끝난 생성물이므로 그대로 둔다. 표식이 없으면 원시 mermaid 출력이라 다시 토큰화한다.
