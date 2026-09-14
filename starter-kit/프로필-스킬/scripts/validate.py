#!/usr/bin/env python3
"""강사 프로필 덱 자동 QA 게이트. FAIL이 하나라도 있으면 완료 선언 금지."""
import sys, re

# Windows 콘솔은 기본이 cp949라 —·이모지 등을 출력하다 죽는다. UTF-8로 강제한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REQUIRED = ["p-cover", "p-intro", "p-history", "p-why", "p-thanks"]
ORDER = ["p-cover","p-intro","p-domain","p-history","p-press","p-why","p-review","p-field","p-thanks"]
NEUTRALS = {
    "#fff","#ffffff","#333","#111","#666","#444","#bbb","#aaa","#1b1b1b","#000",
}


def extract_root_colors(html: str) -> set[str]:
    """:root{...} 안에 --main·--deep·--accent·--pale 로 선언한 값을 허용 색으로 삼는다.
    학생마다 facts.md 색이 다르므로 고정 화이트리스트 대신 문서 자체에서 뽑는다."""
    m = re.search(r':root\s*\{([^}]*)\}', html, re.S)
    if not m:
        return set()
    return {h.lower() for h in re.findall(r'#[0-9A-Fa-f]{3,6}', m.group(1))}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: validate.py <file.html>"); sys.exit(2)
    html = open(sys.argv[1], encoding="utf-8").read()
    fails, warns = [], []
    # base64 데이터 URI는 검사 대상에서 제외 (오탐 방지)
    text = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', 'data:image/png;base64,LOGO', html)

    # 1. 자리표시자 잔존
    # 2026-09-14: 견본 인물뿐 아니라 "남의 실적·고객사" 도 잡는다.
    # 예전에는 홍길동만 검사해서, 누적 4,000회·KT·LG전자 가 그대로 남은 파일이 통과했다.
    for ph in ["[인격유형]", "[강사명]", "[소속사]", "[직함명]", "[자격명]", "[고객사]",
               "TODO", "Lorem ipsum", "홍길동", "길동컨설팅",
               "4,000회", "200회 이상 출강", "12년차",
               "KT", "LG전자", "고용노동부",
               "{{", "}}"]:
        if ph in text:
            fails.append(f"자리표시자 잔존: {ph}")

    # 2. 필수 슬라이드
    slides = re.findall(r'class="slide ([a-z0-9\- ]+)"', html)
    kinds = [s.split()[0] for s in slides]
    for r in REQUIRED:
        if r not in kinds:
            fails.append(f"필수 슬라이드 누락: .{r}")

    # 3. 순서
    idx = [ORDER.index(k) for k in kinds if k in ORDER]
    if idx != sorted(idx):
        fails.append(f"슬라이드 순서 오류: {kinds}")

    # 4. 표지/감사 위치
    if kinds and kinds[0] != "p-cover":
        fails.append("첫 슬라이드가 표지(.p-cover)가 아님")
    if kinds and kinds[-1] != "p-thanks":
        fails.append("마지막 슬라이드가 감사(.p-thanks)가 아님")

    # 5. 슬라이드 규격
    if re.search(r'\.slide\s*\{[^}]*width:\s*1920px', html) is None:
        fails.append(".slide width:1920px 규격 누락")
    if re.search(r'\.slide\s*\{[^}]*height:\s*1080px', html) is None:
        fails.append(".slide height:1080px 규격 누락")

    # 6. 페이지 번호 연속성 (표지 제외)
    nums = [int(n) for n in re.findall(r'class="page-num[^"]*">\s*(\d+)\s*<', html)]
    expected = list(range(2, 2 + len(nums)))
    if nums and nums != expected:
        fails.append(f"페이지 번호 불연속: {nums} (기대: {expected})")

    # 7. 폰트 — var(--f) 가 아닌 개별 지정 폰트가 있으면 규칙 위반
    for decl in re.findall(r'font-family:\s*([^;]+);', html):
        if "var(--f)" not in decl:
            fails.append(f"font-family가 var(--f)가 아님: {decl.strip()[:40]}")

    # 8. 색상 화이트리스트 — :root 에 선언한 색(=facts.md 색) + 무채색만 허용
    allowed = NEUTRALS | extract_root_colors(html)
    for c in set(m.lower() for m in re.findall(r"#[0-9A-Fa-f]{3,6}\b", text)):
        if c not in allowed:
            warns.append(f"facts.md에 없는 색상 사용: {c}")

    # 9. 외부 이미지 핫링크
    ext = [u for u in re.findall(r'<img[^>]+src="(https?://[^"]+)"', html)]
    for u in ext:
        warns.append(f"외부 이미지 핫링크: {u[:70]}")
    if "unsplash.com" in html:
        fails.append("unsplash 이미지 사용 금지 (서비스 종료)")

    # 10. WHY 카드/배지 개수
    if "p-why" in kinds:
        if html.count('class="why-card"') != 3:
            fails.append(f'why-card 3개여야 함 (현재 {html.count(chr(34)+"why-card"+chr(34))})')
        if html.count('class="why-col"') != 3:
            fails.append("why-col 3개여야 함")

    # 11. 현장 그리드 셀 수
    for i, blk in enumerate(re.findall(r'class="fd-grid">(.*?)</div>\s*<div class="fd-foot"', html, re.S)):
        c = blk.count('class="fd-cell"')
        if c > 8:
            fails.append(f"교육현장 {i+1}번 슬라이드 셀 {c}개 (최대 8)")
        elif c == 0:
            fails.append(f"교육현장 {i+1}번 슬라이드 셀 없음")

    # 12. 로고 마크
    if html.count('class="brand-mark"') + html.count('class="cv-logo"') == 0:
        fails.append("로고 마크가 한 곳도 없음 (.brand-mark / .cv-logo)")

    print("=" * 56)
    print(f"슬라이드 {len(kinds)}장: {' → '.join(kinds)}")
    print("=" * 56)
    for w in warns: print(f"WARN  {w}")
    for f in fails: print(f"FAIL  {f}")
    if fails:
        print(f"\n결과: FAIL ({len(fails)}건) — 수정 후 재실행"); sys.exit(1)
    print(f"\n결과: PASS (경고 {len(warns)}건)")


if __name__ == "__main__":
    main()
