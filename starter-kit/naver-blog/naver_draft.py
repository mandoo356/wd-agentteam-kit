"""네이버 블로그 임시저장 자동화 (Playwright).

Claude in Chrome 확장은 blog.naver.com 을 허용하지 않으므로, 전용 Chrome
프로필을 Playwright로 직접 구동한다. 평소 쓰는 브라우저는 건드리지 않는다.

  py -3.14 naver_draft.py login --blog-id 내블로그아이디   # 1회: 사람이 직접 로그인 (세션 저장)
  py -3.14 naver_draft.py check --blog-id 내블로그아이디   # 세션 살아있는지 확인
  py -3.14 naver_draft.py probe --blog-id 내블로그아이디   # 에디터 DOM 구조 덤프 (셀렉터 조사용)
  py -3.14 naver_draft.py draft --blog-id 내블로그아이디 --title "제목" --body-file post.md

설계 원칙
  - 로그인은 절대 자동화하지 않는다. 비밀번호를 코드가 만지지 않는다.
    네이버는 자동 로그인을 차단하고 계정을 잠글 수 있다.
  - "발행"은 누르지 않는다. 임시저장까지만.
  - 매 단계 스크린샷을 남긴다. 확인 못 한 성공은 성공이 아니다.
  - 종료 코드로 결과를 알린다: 0 성공 / 2 로그인 필요 / 3 저장 실패 / 4 입력 실패
"""
from __future__ import annotations

import argparse
import json
import re as _re0
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = Path(__file__).resolve().parent
PROFILE_DIR = BASE / ".naver-profile"
# 세션 쿠키 백업. 네이버는 '로그인 상태 유지'를 끄면 인증 쿠키를 세션 쿠키로
# 발급하고, 그건 브라우저를 닫는 순간 프로필에서 사라진다(실제로 두 번 날아갔다).
# storage_state 는 세션 쿠키까지 직렬화하므로 체크박스 여부와 무관하게 살아남는다.
# ⚠ 이 파일은 로그인 토큰이다. 유출되면 계정 접근이 가능하니 PC 밖으로 내보내지 말 것.
STATE_FILE = BASE / ".naver-state.json"
SHOT_DIR = BASE / "logs" / "naver_shots"
# main() 에서 --blog-id 로 채운다. 빈 채로 두면 아무 페이지도 못 연다.
BLOG_ID = ""
WRITE_URL = ""
BLOG_URL = ""

EXIT_OK, EXIT_LOGIN, EXIT_SAVE, EXIT_INPUT = 0, 2, 3, 4

# 기본 정책: 블로그 한 편에 이미지는 최대 4장.
# 넘으면 에러가 아니라 앞에서 4장만 쓰고, 몇 장을 뺐는지 반드시 알린다.
MAX_IMAGES = 4


# blog/*.md 는 발행용 본문과 내부 메모가 한 파일에 섞여 있다. 이 표시가 붙은
# 섹션부터 아래는 사람·에이전트 작업용 메모이므로 블로그에 나가면 안 된다.
INTERNAL_MARKERS = (
    "발행 전", "발행 후", "활용 가이드", "확인 필요", "체크리스트",
    "QA", "제목 5안", "제목 후보", "SEO", "assumptions", "참고 노트",
    "검증", "해시태그", "태그 분석", "점수 근거",
    # 2026-08-09 대표 지적: 키워드 전략표·이미지 ALT 캡션표가 본문에 그대로
    # 나갔다. 둘 다 에이전트 작업용 메모다.
    "키워드 전략", "키워드 배치", "대체텍스트", "ALT", "캡션", "이미지 계획",
    "변경 요약", "수정 요약", "작업 메모",
    # 2026-08-09 대표 지적 2차: 실행 명령 안내 섹션이 통째로 본문에 들어갔다.
    # 마커 목록에 없으면 살아남는 구조라, 운영 안내 계열을 전부 추가한다.
    "명령", "실행", "임시저장", "작업 디렉터리", "사용법", "안내", "가이드", "TODO",
    "참고", "볼트", "근거", "출처", "내부",
)

# 정제 규칙은 "마커에 없으면 통과"라 계속 새는 구조다. 이 표시로 감싸면
# 그 안쪽만 본문으로 쓴다 — 확실한 쪽이 우선.
BODY_START = "<!-- BODY:START -->"
BODY_END = "<!-- BODY:END -->"

# 본문에 절대 있으면 안 되는 흔적. 하나라도 걸리면 저장하지 않고 멈춘다.
# 마커 목록은 "빠뜨리면 통과"라서, 최종 게이트를 따로 둔다.
FORBIDDEN_IN_BODY = (
    "naver_draft.py", "--body-file", "--title", "py -3.14", "```",
    "C:/", "C:\\", ".md", ".pptx", "[[",
)


def _topics_from_body(title: str, body: str, count: int) -> list[str]:
    """삽화 주제 N개를 뽑는다.

    ① 소제목이 있으면 그걸 쓴다.
    ② 네이버 본문은 대개 소제목이 없다. 그럴 땐 본문을 N등분해 각 구간의 첫
       문장을 쓴다 — 이미지도 어차피 본문 사이에 균등 배치되므로, 그 자리에서
       하는 이야기가 곧 그 그림의 주제가 된다.
    ③ 그래도 못 뽑으면 제목으로 채우되, 장면이 겹치지 않게 관점을 달리 준다.
    """
    def tidy(s: str) -> str:
        s = _re0.sub(r"[*_`\[\]#>|]", "", s)
        s = _re0.sub(r"https?://\S+", "", s)
        return _re0.sub(r"\s+", " ", s).strip()

    heads: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            s = s.lstrip("#")
        elif s.startswith(("■", "▶", "◆", "▪", "●")):
            s = s[1:]
        else:
            continue
        s = tidy(s)
        if 4 <= len(s) <= 40 and s not in heads:
            heads.append(s)

    if len(heads) < count:
        # 인사말·문의 안내는 그림으로 그릴 게 없다. 본문만 남긴다.
        skip = ("안녕하세", "감사합니", "문의", "연락", "댓글", "구독",
                "드림", "이상으로")
        paras = [t for t in (tidy(p) for p in body.split("\n"))
                 if 15 <= len(t) <= 120 and not any(k in t for k in skip)]
        if paras:
            step = max(1, len(paras) // count)
            for i in range(count):
                cand = paras[min(i * step, len(paras) - 1)]
                if cand not in heads:
                    heads.append(cand)

    # 마지막 안전망 — 같은 프롬프트를 N번 던지면 비슷한 그림만 나온다.
    angles = ["강의장 전경", "실습하는 참가자들의 손", "교육이 끝난 뒤의 변화"]
    i = 0
    while len(heads) < count:
        heads.append(f"{title} — {angles[i % len(angles)]}")
        i += 1
    return heads[:count]


def auto_generate_images(title: str, body: str, out_dir: Path, count: int) -> list[Path]:
    """삽화를 직접 만들어 온다.

    왜 여기서 만드나 — 예전에는 에이전트가 `gen_image.py` 를 따로 돌려 `--images` 로
    넘겨주기를 기대했다. 그런데 슬랙 경로의 에이전트는 시간 예산이 빠듯해서 그 단계를
    건너뛰고 `--no-images` 로 빠져나가곤 했고, 결과는 글만 올라간 임시저장이었다
    (2026-08-09, 2026-08-14 두 번). 사람이 기억해야 하는 절차는 계속 샌다.
    그래서 **안 주면 여기서 만든다.** 기본 정책대로 최대 4장, 기본 3장.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    gen = BASE / "gen_image.py"
    if not gen.exists():
        log(f"gen_image.py 를 찾을 수 없어 자동 생성을 건너뜁니다: {gen}")
        return []

    made: list[Path] = []
    for i, topic in enumerate(_topics_from_body(title, body, count), start=1):
        out = out_dir / f"auto_{i:02d}.png"
        if out.exists():
            log(f"[이미지 {i}/{count}] 이미 있음 — 재사용: {out.name}")
            made.append(out)
            continue
        # 제목을 앞에 붙여 장면이 글 주제에서 벗어나지 않게 묶는다.
        scene = topic if topic.startswith(title) else f"{title} 강의 현장 — {topic}"
        log(f"[이미지 {i}/{count}] 생성 중… 주제: {topic}")
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(gen),
                 "--topic", scene, "--out", str(out)],
                capture_output=True, timeout=180, cwd=str(BASE),
            )
        except subprocess.TimeoutExpired:
            log(f"[이미지 {i}/{count}] 시간 초과 — 건너뜁니다")
            continue
        if proc.returncode == 0 and out.exists():
            made.append(out)
        else:
            err = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
            log(f"[이미지 {i}/{count}] 실패 — {err or f'exit {proc.returncode}'}")
    log(f"자동 생성 완료: {len(made)}장")
    return made


def body_gate(body: str) -> list[str]:
    """정제 후에도 남은 내부 흔적을 잡는 최종 게이트. draft·publish 공통."""
    return [f"본문에 '{m}' 이 남아있음" for m in FORBIDDEN_IN_BODY if m in body]


def _is_md_table_sep(s: str) -> bool:
    return bool(s) and set(s) <= set("|-: ") and "-" in s and "|" in s


def clean_body(text: str) -> tuple[str, list[str]]:
    """마크다운 작업 문서 → 네이버에 붙여넣을 본문.

    (1) 내부 메모 섹션 이후를 잘라내고 (2) 네이버가 렌더링하지 못하는
    마크다운 문법을 벗긴다. 네이버 에디터는 마크다운을 해석하지 않아서
    '**굵게**' 가 별표째로 노출된다.

    돌려주는 두 번째 값은 잘라낸 섹션 제목 — 무엇을 뺐는지 보고하기 위함.
    """
    text = text.replace("\r\n", "\n")
    if BODY_START in text and BODY_END in text:
        inner = text.split(BODY_START, 1)[1].split(BODY_END, 1)[0]
        return _strip_markdown(inner), ["(BODY 표시 바깥 전체)"]

    lines = text.split("\n")
    kept: list[str] = []
    dropped: list[str] = []
    # 내부 메모는 문서 앞뒤에 흩어져 있다(SEO 제목 후보는 본문보다 앞, 검증표는 뒤).
    # 그래서 "첫 마커에서 끝까지 자르기"는 본문까지 날린다 — 실제로 5286자가
    # 151자가 됐다. 섹션 단위로 건너뛰고 다음 일반 제목에서 다시 살린다.
    cutting = False
    in_fence = False
    for ln in lines:
        stripped = ln.strip()
        # ```로 감싼 코드블록은 블로그 본문에 들어갈 일이 없다(실행 명령 안내다).
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # 마크다운 제목은 '# ' 처럼 뒤에 공백이 온다. 공백 없는 '#해시태그'
        # 은 해시태그 줄이므로 제목으로 보면 안 된다(맨 앞 # 이 잘려나갔다).
        if _re0.match(r"^#{1,6}[ \t]+", stripped):
            head = stripped.lstrip("#").strip()
            if any(m in head for m in INTERNAL_MARKERS):
                cutting = True
                dropped.append(head[:40])
                continue
            cutting = False
        if cutting:
            continue
        # 마크다운 표 구분행(|---|---|)은 네이버에서 그대로 노출된다
        if _is_md_table_sep(stripped):
            continue
        kept.append(ln)

    return _strip_markdown("\n".join(kept)), dropped


def _strip_markdown(out: str) -> str:
    """네이버 에디터는 마크다운을 해석하지 않는다. 문법 기호를 벗긴다."""
    for pat, rep in (
        ("**", ""), ("`", ""),           # 강조·코드 표시는 그대로 노출된다
    ):
        out = out.replace(pat, rep)
    # [[위키링크]] → 위키링크,  ## 제목 → 제목
    out = _re0.sub(r"\[\[([^\]]+)\]\]", r"\1", out)
    out = _re0.sub(r"^#{1,6}[ \t]+", "", out, flags=_re0.M)
    out = _re0.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def log(msg: str) -> None:
    print(f"[naver] {msg}", flush=True)


def shot(page, name: str) -> str:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = SHOT_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{name}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
        log(f"screenshot: {p}")
    except Exception as e:
        log(f"screenshot failed: {e}")
    return str(p)


def launch(pw, headless: bool):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",          # 번들 Chromium 대신 실제 Chrome
        headless=headless,
        viewport={"width": 1440, "height": 960},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        permissions=["clipboard-read", "clipboard-write"],
        args=["--disable-blink-features=AutomationControlled"],
    )


def save_state(ctx) -> None:
    # 성공/실패 문구를 확실히 갈라둔다. 예전 문구("세션 백업 저장: ...")를
    # 에이전트가 실패로 읽고 사용자에게 잘못 보고한 적이 있다.
    try:
        ctx.storage_state(path=str(STATE_FILE))
        log(f"[OK] 세션 백업 저장 완료 ({STATE_FILE.name})")
    except Exception as e:
        log(f"[FAIL] 세션 백업 저장 실패: {e}")


def restore_state(ctx) -> bool:
    """백업된 쿠키를 컨텍스트에 주입한다. 프로필에 세션이 없을 때의 구제책."""
    if not STATE_FILE.exists():
        return False
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        cookies = data.get("cookies") or []
        if not cookies:
            return False
        ctx.add_cookies(cookies)
        log(f"세션 백업 주입: 쿠키 {len(cookies)}개")
        return True
    except Exception as e:
        log(f"세션 백업 주입 실패: {e}")
        return False


def ensure_session(ctx, page) -> bool:
    """로그인 상태를 확보한다. 프로필 → 백업 주입 순으로 시도."""
    page.goto(WRITE_URL, wait_until="domcontentloaded")
    time.sleep(3)
    if is_logged_in(page):
        return True
    # 네이버가 세션 쿠키로 발급하므로 프로필에는 남지 않는다. 매번 나오는
    # 정상 흐름이지 오류가 아니다.
    log("[정상] 프로필에 세션 없음 → 백업 쿠키로 복원합니다")
    if not restore_state(ctx):
        return False
    page.goto(WRITE_URL, wait_until="domcontentloaded")
    time.sleep(3)
    return is_logged_in(page)


def is_logged_in(page) -> bool:
    """미로그인 판정.

    주의: 공개 블로그 홈은 로그인 없이도 200으로 열린다. URL만 보고 판단하면
    오탐이 난다(실제로 그랬다). 그래서 (1) 로그인 페이지 리다이렉트,
    (2) 화면의 '로그인' 버튼 / 'guest' 표기를 함께 본다.
    """
    if "nid.naver.com" in page.url:
        return False
    try:
        for fr in page.frames:
            hit = fr.evaluate("""() => {
                const t = document.body ? document.body.innerText : '';
                const hasLoginBtn = [...document.querySelectorAll('a,button')]
                    .some(e => (e.innerText||'').trim() === '로그인');
                return hasLoginBtn || /\\bguest\\b/.test(t);
            }""")
            if hit:
                return False
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- modes

AUTH_COOKIES = ("NID_AUT", "NID_SES")


def _auth_cookie_state(ctx) -> tuple[bool, bool]:
    """(인증쿠키 있음, 디스크에 남는 영구쿠키임) 을 돌려준다.

    expires == -1 이면 세션 쿠키다. '로그인 상태 유지'를 켜지 않으면 이렇게
    발급되고 브라우저를 닫는 순간 사라진다 — 실제로 첫 시도가 이렇게 날아갔다.
    """
    try:
        cookies = ctx.cookies()
    except Exception:
        return False, False
    found = [c for c in cookies if c.get("name") in AUTH_COOKIES]
    if not found:
        return False, False
    persistent = all(c.get("expires", -1) and c.get("expires", -1) > 0 for c in found)
    return True, persistent


def cmd_login(headless: bool) -> int:
    """사람이 직접 로그인한다. 코드는 창만 열고 쿠키만 관찰한다.

    이전 버전은 대기 중에 page.goto() 로 화면을 옮겨서 로그인 흐름을 방해했다.
    지금은 어떤 네비게이션도 하지 않고 컨텍스트의 쿠키만 폴링한다 —
    사용자가 어느 탭에서 로그인하든 잡힌다.
    """
    with sync_playwright() as pw:
        ctx = launch(pw, headless=False)  # 로그인은 반드시 보이는 창
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
        time.sleep(2)

        # '로그인 상태 유지'를 코드가 미리 켜둔다. 이걸 사람에게 맡겼더니 세 번
        # 연속으로 꺼진 채 로그인됐고, 그때마다 세션 쿠키라 몇 시간 뒤 만료돼
        # 재로그인을 요청해야 했다. 비밀번호가 아니라 옵션 토글이므로 코드가 만져도 된다.
        keep = page.evaluate("""() => {
            const boxes = [...document.querySelectorAll("input[type=checkbox]")];
            const target = boxes.find(b => {
                if (b.id === 'keep') return true;
                let lab = '';
                if (b.id) { const l = document.querySelector(`label[for="${b.id}"]`); if (l) lab = l.innerText; }
                if (!lab && b.closest('label')) lab = b.closest('label').innerText;
                return (lab || '').includes('로그인 상태 유지');
            });
            if (!target) return 'not_found';
            if (!target.checked) target.click();
            return target.checked ? 'checked' : 'click_failed';
        }""")
        log(f"'로그인 상태 유지' 자동 설정: {keep}")

        log("=" * 60)
        log("브라우저 창에서 아이디·비밀번호만 입력해 주세요.")
        if keep == "checked":
            log("'로그인 상태 유지'는 제가 켜뒀습니다. 건드리지 않으셔도 됩니다.")
        else:
            log("★ '로그인 상태 유지' 체크박스를 켜주세요 (자동 설정 실패) ★")
        log("로그인되면 자동 감지합니다. (최대 5분)")
        log("=" * 60)

        deadline = time.time() + 300
        ok = persistent = False
        while time.time() < deadline:
            ok, persistent = _auth_cookie_state(ctx)
            if ok:
                log("인증 쿠키 감지됨" + ("(영구)" if persistent else "(세션 전용!)"))
                break
            time.sleep(2)

        if ok and not persistent:
            # 관측 결과: '로그인 상태 유지'를 켜도 네이버는 NID_AUT/NID_SES 를
            # 세션 쿠키로 발급한다. 즉 이건 오류가 아니라 정상이며, 지속성은
            # storage_state 백업이 담당한다. 예전엔 이걸 '체크박스가 꺼졌다'고
            # 잘못 안내해 재로그인을 세 번이나 요청했다.
            log("[정상] 네이버는 인증 쿠키를 세션 쿠키로 발급합니다.")
            log("→ storage_state 백업으로 저장하므로 다음 실행에 재사용됩니다.")

        # 저장 여부를 실제로 검증한다: 글쓰기 화면이 리다이렉트 없이 열리는지
        verified = False
        if ok:
            try:
                page.goto(WRITE_URL, wait_until="domcontentloaded")
                time.sleep(3)
                verified = is_logged_in(page)
            except Exception as e:
                log(f"검증 네비게이션 실패: {e}")
        shot(page, "login_result")

        # 창을 닫기 전에 백업한다 — 닫은 뒤에는 세션 쿠키가 이미 사라진다.
        if verified:
            save_state(ctx)
        ctx.close()

        if verified:
            log("로그인 완료" + (" (영구 쿠키)" if persistent else " (세션 쿠키 + 백업)"))
            return EXIT_OK
        log("로그인 확인 실패.")
        return EXIT_LOGIN


def cmd_check(headless: bool) -> int:
    with sync_playwright() as pw:
        ctx = launch(pw, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # 글쓰기 URL 로 확인한다 — 인증이 필요한 화면이라 판정이 확실하다.
        ok = ensure_session(ctx, page)
        log(f"url={page.url}")
        log("세션 살아있음" if ok else "로그인 필요 — `login` 모드를 먼저 실행하세요")
        shot(page, "check")
        if ok:
            save_state(ctx)   # 쿠키가 갱신됐을 수 있으니 백업을 최신화
        ctx.close()
        return EXIT_OK if ok else EXIT_LOGIN


def _editor_frame(page):
    """SmartEditor 는 mainFrame iframe 안에 있을 수도, 최상위일 수도 있다."""
    for f in page.frames:
        try:
            if f.query_selector(".se-documentTitle, .se-content, [contenteditable='true']"):
                return f
        except Exception:
            continue
    return page.main_frame


def cmd_probe(headless: bool) -> int:
    """에디터 실제 구조를 덤프한다. 셀렉터가 안 맞을 때 진단용."""
    with sync_playwright() as pw:
        ctx = launch(pw, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not ensure_session(ctx, page):
            log("로그인 필요")
            shot(page, "probe_login_needed")
            ctx.close()
            return EXIT_LOGIN
        time.sleep(3)

        log(f"url={page.url}")
        log(f"frames={[f.name or '(main)' for f in page.frames]}")
        fr = _editor_frame(page)
        log(f"editor frame = {fr.name or '(main)'}")
        # 팝업이 떠 있으면 에디터 본문이 초기화되지 않아 셀렉터가 안 보인다.
        _dismiss_popups(fr)
        time.sleep(2)
        fr = _editor_frame(page)

        info = fr.evaluate("""() => {
            const pick = el => ({
                tag: el.tagName, cls: (el.className||'').toString().slice(0,120),
                text: (el.innerText||'').trim().slice(0,40),
                editable: el.getAttribute('contenteditable'),
            });
            const out = {};
            out.editables = [...document.querySelectorAll("[contenteditable='true']")].slice(0,10).map(pick);
            out.buttons = [...document.querySelectorAll("button,a[role=button]")]
                .map(b => (b.innerText||b.getAttribute('aria-label')||'').trim())
                .filter(t => t && t.length < 20).slice(0,60);
            // 툴바 클래스가 50개를 넘어 본문 영역이 잘렸던 적이 있다.
            // 그래서 문서 영역만 좁혀서 본다.
            out.docArea = [...document.querySelectorAll(
                "[class*='documentTitle'],[class*='se-title'],[class*='se-text'],"
                + "[class*='se-content'],[class*='placeholder'],[class*='se-section']")]
                .slice(0,25).map(el => ({
                    cls: el.className.toString().slice(0,90),
                    editable: el.getAttribute('contenteditable'),
                    text: (el.innerText||'').trim().slice(0,30),
                }));
            const ce = document.querySelector("[contenteditable='true']");
            out.editableChildren = ce ? [...ce.children].slice(0,15).map(el => ({
                tag: el.tagName, cls: el.className.toString().slice(0,90),
                text: (el.innerText||'').trim().slice(0,30),
            })) : [];
            out.dialogs = [...document.querySelectorAll("[class*='pop'],[class*='layer'],[role=dialog]")]
                .map(d => (d.innerText||'').trim().slice(0,80)).filter(Boolean).slice(0,10);
            return out;
        }""")
        for k, v in info.items():
            log(f"--- {k} ---")
            for item in (v if isinstance(v, list) else [v]):
                log(f"    {item}")
        shot(page, "probe")
        ctx.close()
        return EXIT_OK


def _click_exact_text(fr, label: str) -> bool:
    """정확히 이 텍스트인 클릭 가능 요소를 누른다.

    네이버 복구 팝업의 '취소'/'확인'은 <button> 이 아니라서
    button:has-text() 로는 안 잡힌다(probe 로 확인). 그래서 DOM 을 직접 훑는다.
    """
    try:
        return bool(fr.evaluate("""(label) => {
            const els = [...document.querySelectorAll('a,button,span,div,li')];
            for (const el of els) {
                if ((el.textContent || '').trim() !== label) continue;
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                el.click();
                return true;
            }
            return false;
        }""", label))
    except Exception:
        return False


def _dismiss_popups(fr) -> bool:
    """'작성 중인 글이 있습니다' 복구 팝업 처리.

    반드시 '취소'. '확인'을 누르면 이전 임시저장 내용을 이어받아 덮어쓰게 된다.
    ('취소'는 그 임시저장을 지우지 않는다 — 저장 목록에 그대로 남는다.)
    """
    try:
        txt = fr.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except Exception:
        return False
    if "작성 중인 글" not in txt and "이어서 작성" not in txt:
        return False
    log("복구 팝업 감지 → '취소' (기존 임시저장 보존, 새 글로 시작)")
    for label in ("취소", "닫기"):
        if _click_exact_text(fr, label):
            time.sleep(1.5)
            log(f"팝업 닫음 ('{label}')")
            return True
    log("경고: 팝업을 닫지 못했습니다.")
    return False


PREFLIGHT_BLOCKERS = ("[미확인]", "[확인 필요]", "미확인]", "확인 필요]")


def preflight(title: str, body: str) -> list[str]:
    """발행 전 검사. 임시저장은 틀려도 지우면 되지만 발행은 공개된다."""
    problems = []
    hits = sum(body.count(m) for m in ("[미확인]", "[확인 필요]"))
    if hits:
        problems.append(f"본문에 미완성 표시 {hits}건 ([미확인]/[확인 필요])")
    if len(body.strip()) < 800:
        problems.append(f"본문이 너무 짧음 ({len(body.strip())}자)")
    if not title.strip():
        problems.append("제목이 비었음")
    for marker in INTERNAL_MARKERS:
        if marker in body:
            problems.append(f"내부 메모 흔적 '{marker}' 이 본문에 남아있음")
            break
    return problems


def _paste(page, fr, text: str) -> bool:
    """클립보드 경유 붙여넣기. 타이핑하면 에디터 자동서식이 개입한다."""
    try:
        page.evaluate("t => navigator.clipboard.writeText(t)", text)
        time.sleep(0.4)
        page.keyboard.press("Control+V")
        time.sleep(1.5)
        return True
    except Exception as e:
        log(f"붙여넣기 실패: {e}")
        return False


def _insert_image(page, fr, img: Path) -> bool:
    """'사진' 버튼 → filechooser → 파일 지정. probe 로 확인된 경로."""
    try:
        with page.expect_file_chooser(timeout=15000) as fc:
            fr.evaluate("""() => {
                const b = [...document.querySelectorAll('button')]
                    .find(x => (x.innerText||'').trim().startsWith('사진'));
                if (b) b.click();
            }""")
        fc.value.set_files(str(img))
        time.sleep(6)          # 업로드 + 썸네일 생성 대기
        log(f"이미지 삽입: {img.name}")
        return True
    except Exception as e:
        log(f"이미지 삽입 실패 ({img.name}): {type(e).__name__}: {e}")
        return False


def _fill_document(page, fr, title: str, body: str, images: list[Path] | None = None):
    """제목·본문을 채운다. draft 와 publish 가 공유. (성공여부, 갱신된 frame)"""
    _dismiss_popups(fr)
    time.sleep(2)
    fr = _editor_frame(page)

    filled = False
    for sel in (".se-component.se-documentTitle .se-text-paragraph",
                ".se-component.se-documentTitle", ".se-documentTitle", ".se-title-text"):
        try:
            el = fr.query_selector(sel)
            if el and el.is_visible():
                el.click()
                time.sleep(0.8)
                page.keyboard.type(title, delay=15)
                log(f"제목 입력 (셀렉터 {sel})")
                filled = True
                break
        except Exception as e:
            log(f"제목 셀렉터 {sel} 실패: {e}")
    if not filled:
        return False, fr

    time.sleep(0.8)
    moved = False
    for sel in (".se-component.se-text .se-text-paragraph",
                ".se-component.se-text", ".se-content .se-text-paragraph"):
        try:
            el = fr.query_selector(sel)
            if el and el.is_visible():
                el.click()
                moved = True
                break
        except Exception:
            continue
    if not moved:
        page.keyboard.press("Enter")
    time.sleep(0.8)

    body_norm = body.replace("\r\n", "\n")
    # CLI 에서도 자르지만 여기서 한 번 더 막는다. 다른 코드가 이 함수를
    # 직접 부를 때 상한이 조용히 무시되는 일이 없도록.
    images = (images or [])[:MAX_IMAGES]

    if not images:
        _paste(page, fr, body_norm)
    else:
        # 본문을 이미지 개수+1 덩어리로 나눠 사이사이에 넣는다. 빈 줄 경계에서만
        # 잘라야 문단 중간에 이미지가 끼어들지 않는다.
        paras = [p for p in body_norm.split("\n\n") if p.strip()]
        # 원고에 `[📷 ...]` 자리표시자가 이미지 장수만큼 있으면 균등분할 대신
        # 그 자리에 정확히 넣는다. 자리표시자 줄만 지우고 아래 사진 설명은 남긴다.
        marks = [i for i, p in enumerate(paras) if p.lstrip().startswith("[📷")]
        if len(marks) == len(images):
            chunks, tails, prev = [], [], 0
            for m in marks:
                chunks.append(paras[prev:m])
                tails.append("\n".join(paras[m].split("\n")[1:]).strip())
                prev = m + 1
            chunks.append(paras[prev:])
            for i, t in enumerate(tails):                # 설명은 이미지 뒤로
                if t:
                    chunks[i + 1].insert(0, t)
            log(f"자리표시자 {len(marks)}곳에 이미지를 맞춰 넣습니다")
        else:
            n = len(images) + 1
            size = max(1, len(paras) // n)
            chunks = [paras[i * size:(i + 1) * size] for i in range(n)]
            chunks[-1].extend(paras[n * size:])      # 나머지는 마지막 덩어리로
        for i, chunk in enumerate(chunks):
            if chunk:
                _paste(page, fr, "\n\n".join(chunk))
                page.keyboard.press("Enter")
                time.sleep(0.5)
            if i < len(images):
                _insert_image(page, fr, images[i])
                page.keyboard.press("End")
                time.sleep(0.5)

    head = (body_norm.strip().splitlines() or [""])[0][:15]
    seen = fr.evaluate("() => document.body.innerText") or ""
    if head and head not in seen:
        log("경고: 본문 첫 줄이 화면에서 확인되지 않습니다.")
    log(f"본문 입력 완료 ({len(body_norm)}자, 이미지 {len(images)}장)")
    return True, fr


def cmd_publish(title: str, body: str, open_type: str, confirm: bool,
                force: bool, headless: bool, images=None) -> int:
    """발행. 임시저장과 달리 되돌리기 어렵다 — 가드가 여러 겹이다."""
    if not confirm:
        log("발행은 --confirm 플래그가 있어야 실행됩니다. (실수 방지)")
        return 1
    problems = preflight(title, body)
    if problems:
        log("발행 전 검사에서 걸린 항목:")
        for p in problems:
            log(f"  - {p}")
        if not force:
            log("→ 발행 중단. 고치고 다시 하거나, 알고도 강행하려면 --force.")
            return 5
        log("→ --force 로 무시하고 진행합니다.")

    with sync_playwright() as pw:
        ctx = launch(pw, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(20000)
        if not ensure_session(ctx, page):
            log("로그인 필요 — 중단합니다.")
            ctx.close()
            return EXIT_LOGIN
        time.sleep(3)
        fr = _editor_frame(page)
        ok, fr = _fill_document(page, fr, title, body, images)
        if not ok:
            log("입력 실패 — 발행하지 않고 중단합니다.")
            shot(page, "publish_fail_input")
            ctx.close()
            return EXIT_INPUT
        shot(page, "publish_01_filled")

        # 헤더의 '발행' → 설정 패널 열기 (이 클릭만으로는 공개되지 않는다)
        opened = fr.evaluate("""() => {
            const b = [...document.querySelectorAll('button')]
                .find(x => (x.innerText||'').trim() === '발행');
            if (!b) return false;
            b.click(); return true;
        }""")
        if not opened:
            log("발행 패널을 열지 못했습니다.")
            shot(page, "publish_fail_panel")
            ctx.close()
            return EXIT_SAVE
        time.sleep(3)
        fr = _editor_frame(page)

        # 공개 범위. 실측된 매핑(2=전체공개, 1=이웃공개, 3=서로이웃공개, 0=비공개)은
        # DOM 순서와 어긋나므로 value 로 고르지 않는다. 라벨이 붙은 input 을 직접
        # 클릭한다 — 예전엔 label/span 을 클릭했는데 '클릭됨'만 반환하고 라디오는
        # 안 바뀌어서, 비공개로 지정한 글이 전체공개로 발행된 적이 있다.
        picked = fr.evaluate("""(want) => {
            const rs = [...document.querySelectorAll("input[name=open_type]")];
            for (const r of rs) {
                let lab = '';
                if (r.id) { const l = document.querySelector(`label[for="${r.id}"]`); if (l) lab = l.innerText; }
                if (!lab && r.closest('label')) lab = r.closest('label').innerText;
                if (!lab && r.parentElement) lab = r.parentElement.innerText;
                if ((lab||'').trim().includes(want)) { r.click(); return true; }
            }
            return false;
        }""", open_type)
        time.sleep(1)

        # 클릭했다는 것과 선택됐다는 것은 다르다. 반드시 다시 읽어서 확인한다.
        checked = fr.evaluate("""() => {
            const r = document.querySelector("input[name=open_type]:checked");
            if (!r) return null;
            let lab = '';
            if (r.id) { const l = document.querySelector(`label[for="${r.id}"]`); if (l) lab = l.innerText; }
            if (!lab && r.closest('label')) lab = r.closest('label').innerText;
            return {value: r.value, label: (lab||'').trim()};
        }""")
        log(f"공개 범위 요청='{open_type}' / 실제 선택={checked}")
        shot(page, "publish_02_panel")

        # 확인해놓고 결과를 무시하면 검증이 아니다. 어긋나면 여기서 멈춘다.
        if not picked or not checked or open_type not in (checked.get("label") or ""):
            log(f"공개 범위가 '{open_type}' 로 설정되지 않았습니다 — 발행하지 않고 중단합니다.")
            ctx.close()
            return EXIT_SAVE

        # 패널 안의 최종 '발행'. 헤더 버튼과 텍스트가 같으므로 마지막 것을 쓴다.
        finals = fr.evaluate("""() => [...document.querySelectorAll('button')]
            .map((b,i) => ({i, txt:(b.innerText||'').trim(),
                            cls:(b.className||'').toString().slice(0,40),
                            y: b.getBoundingClientRect().top}))
            .filter(x => x.txt === '발행')""")
        log(f"'발행' 버튼 후보: {finals}")
        if len(finals) < 2:
            log("최종 발행 버튼을 특정하지 못했습니다 — 안전을 위해 중단합니다.")
            shot(page, "publish_fail_final")
            ctx.close()
            return EXIT_SAVE

        fr.evaluate("""() => {
            const bs = [...document.querySelectorAll('button')]
                .filter(b => (b.innerText||'').trim() === '발행');
            bs[bs.length - 1].click();
        }""")
        log("최종 발행 클릭")
        time.sleep(6)

        # page.url 은 에디터 URL 그대로여서 판정에 못 쓴다(실제로 발행됐는데
        # '확인 못 함'으로 보고한 적이 있다). 발행된 글 화면의 표식으로 본다.
        shot(page, "publish_03_after")
        published = False
        try:
            for f in page.frames:
                t = f.evaluate("() => document.body ? document.body.innerText : ''") or ""
                if title[:20] in t and ("URL 복사" in t or "공감" in t or "통계" in t):
                    published = True
                    break
        except Exception as e:
            log(f"발행 확인 중 오류: {e}")
        ctx.close()
        if published:
            log(f"발행 완료 — 제목 '{title}', 공개 범위 '{open_type}'")
            return EXIT_OK
        log("발행 여부를 확인하지 못했습니다 → 블로그에서 직접 확인해 주세요.")
        return EXIT_SAVE


def cmd_draft(title: str, body: str, headless: bool, images=None) -> int:
    with sync_playwright() as pw:
        ctx = launch(pw, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(20000)

        if not ensure_session(ctx, page):
            log("로그인 필요 — 중단합니다. 비밀번호는 입력하지 않습니다.")
            shot(page, "draft_login_needed")
            ctx.close()
            return EXIT_LOGIN
        time.sleep(3)

        fr = _editor_frame(page)
        shot(page, "draft_01_editor_open")

        # 입력 로직은 publish 와 공유한다. 예전엔 여기에 같은 코드가 복사돼
        # 있어서, --images 를 붙여도 draft 에서는 이미지가 안 들어갔다.
        ok, fr = _fill_document(page, fr, title, body, images)
        if not ok:
            log("제목 입력 영역을 못 찾았습니다. probe 모드로 구조를 확인하세요.")
            shot(page, "draft_fail_title")
            ctx.close()
            return EXIT_INPUT
        time.sleep(1)
        shot(page, "draft_02_filled")

        # 실제로 들어갔는지 검증
        try:
            got = fr.evaluate("() => document.body.innerText") or ""
            probe_str = (body.strip().splitlines() or [""])[0][:15]
            if probe_str and probe_str not in got:
                log(f"경고: 본문 첫 줄('{probe_str}')이 화면에서 확인되지 않습니다.")
        except Exception:
            pass

        # ---- 임시저장. '발행'은 절대 누르지 않는다.
        clicked = False
        for sel in ("button.save_btn__bzc5B", "button:has-text('저장')",
                    "[class*='save'] button", "a:has-text('저장')"):
            try:
                for el in fr.query_selector_all(sel):
                    label = (el.inner_text() or "").strip()
                    if "발행" in label:
                        continue          # 안전장치
                    if el.is_visible():
                        log(f"저장 클릭 (셀렉터 {sel}, 라벨 '{label}')")
                        el.click()
                        clicked = True
                        break
                if clicked:
                    break
            except Exception as e:
                log(f"저장 셀렉터 {sel} 실패: {e}")

        if not clicked:
            log("저장 버튼을 못 찾았습니다. probe 모드로 버튼 라벨을 확인하세요.")
            shot(page, "draft_03_no_save_button")
            ctx.close()
            return EXIT_SAVE

        # 클릭했다는 것과 저장됐다는 것은 다르다.
        # 토스트로 확인하려 했으나 잡히지 않았다(너무 빨리 사라지거나 문구가 다름).
        # 임시저장 목록에 제목이 실제로 있는지 보는 것이 확실한 근거다.
        time.sleep(3)
        found = False
        try:
            opened = fr.evaluate("""() => {
                const b = document.querySelector('button.save_count_btn__ZTLNa')
                    || [...document.querySelectorAll('button')]
                        .find(x => /^\\d+\\+?$/.test((x.innerText||'').trim()));
                if (!b) return false;
                b.click(); return true;
            }""")
            if opened:
                time.sleep(3)
                fr = _editor_frame(page)
                listed = fr.evaluate("() => document.body.innerText") or ""
                found = title.strip() in listed
                log(f"임시저장 목록 열기 성공, 제목 검색 결과: {'있음' if found else '없음'}")
            else:
                log("임시저장 목록 버튼을 못 찾았습니다.")
        except Exception as e:
            log(f"목록 검증 실패: {e}")

        shot(page, "draft_03_after_save")
        ctx.close()
        if found:
            log(f"임시저장 확인 완료: '{title}'")
            return EXIT_OK
        log("저장 버튼은 눌렀으나 목록에서 제목을 확인하지 못했습니다.")
        log("→ 네이버 임시저장 목록을 직접 확인해 주세요.")
        return EXIT_SAVE


def main() -> int:
    ap = argparse.ArgumentParser(description="네이버 블로그 임시저장")
    ap.add_argument("mode", choices=["login", "check", "probe", "draft", "publish"])
    ap.add_argument("--blog-id", required=True,
                    help="네이버 블로그 아이디 (blog.naver.com/<이 아이디>). 본인 블로그 주소에서 확인")
    ap.add_argument("--open-type", default="전체공개",
                    choices=["전체공개", "이웃공개", "서로이웃공개", "비공개"])
    ap.add_argument("--confirm", action="store_true",
                    help="발행 모드 필수. 없으면 발행하지 않는다.")
    ap.add_argument("--force", action="store_true",
                    help="발행 전 검사(미완성 표시 등)를 무시하고 강행.")
    ap.add_argument("--title", default="")
    ap.add_argument("--body-file", default="")
    ap.add_argument("--headless", action="store_true",
                    help="창 없이 실행. 원격/무인용. 처음엔 끄고 눈으로 확인하세요.")
    ap.add_argument("--images", default="",
                    help="쉼표로 구분한 이미지 경로. 본문 사이사이에 균등 배치된다.")
    ap.add_argument("--images-dir", default="",
                    help="이 폴더의 이미지를 이름순으로 최대 4장 사용. --images 대신 쓴다.")
    ap.add_argument("--no-images", action="store_true",
                    help="(호환용) 이미지 없이 글만 올린다. 2026-09-08 판부터는 안 붙여도 이미지가 없으면 글만 올린다.")
    ap.add_argument("--auto-images", type=int, default=0,
                    help="이미지를 안 줬을 때 Gemini 로 직접 만들어 넣을 장수(최대 4). 기본 0 — 만들지 않는다. "
                         "AI 삽화 자동 생성은 오래 걸리고 결제 키가 필요해 기본에서 뺐다(2026-09-08). 쓰려면 naver-blog/.env 에 GOOGLE_API_KEY.")
    ap.add_argument("--raw", action="store_true",
                    help="정제 없이 파일 내용 그대로 붙여넣는다(내부 메모까지 들어감).")
    a = ap.parse_args()

    global BLOG_ID, WRITE_URL, BLOG_URL
    BLOG_ID = a.blog_id
    WRITE_URL = f"https://blog.naver.com/{BLOG_ID}?Redirect=Write"
    BLOG_URL = f"https://blog.naver.com/{BLOG_ID}"

    if a.mode == "login":
        return cmd_login(a.headless)
    if a.mode == "check":
        return cmd_check(a.headless)
    if a.mode == "probe":
        return cmd_probe(a.headless)

    if not a.title or not a.body_file:
        log(f"{a.mode} 모드는 --title 과 --body-file 이 필요합니다.")
        return 1
    bf = Path(a.body_file)
    if not bf.exists():
        log(f"본문 파일 없음: {bf}")
        return 1
    body = bf.read_text(encoding="utf-8")
    if a.raw:
        log("정제 생략(--raw): 파일 내용 그대로 넣습니다.")
    else:
        body, dropped = clean_body(body)
        log(f"본문 정제: {len(body)}자")
        if dropped:
            log(f"제외한 내부 섹션 {len(dropped)}개: {', '.join(dropped)}")
    # 정제해도 마커에 안 걸린 내부 메모가 남을 수 있다. 여기서 끊는다.
    if not a.raw:
        leaks = body_gate(body)
        if leaks:
            log("본문에 내부 메모가 남아있어 저장하지 않습니다:")
            for x in leaks:
                log(f"  - {x}")
            log("본문만 담긴 파일을 따로 만들어 --body-file 로 넘기세요.")
            return EXIT_INPUT

    imgs = [Path(x.strip()) for x in a.images.split(",") if x.strip()]
    if not imgs and a.images_dir:
        d = Path(a.images_dir)
        if not d.is_dir():
            log(f"이미지 폴더 없음: {d}")
            return 1
        imgs = sorted(p for p in d.iterdir()
                      if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
        log(f"{d} 에서 이미지 {len(imgs)}장 발견")
    # 2026-09-08: 이미지가 없으면 글만 올린다. AI 삽화 자동 생성(예전 기본 3장)은 오래 걸리고
    # 결제 키가 필요해 기본에서 뺐다. 대표가 찍은 사진은 --images / --images-dir 로 넣는다.
    if not imgs and not a.no_images and a.auto_images > 0:
        n = min(a.auto_images, MAX_IMAGES)
        log(f"이미지가 0장입니다 → 삽화 {n}장을 직접 생성합니다 (--auto-images {a.auto_images})")
        imgs = auto_generate_images(a.title, body, bf.parent / "img", n)
        if not imgs:
            log("자동 생성이 모두 실패했습니다 → 글만 올립니다.")
    if not imgs:
        log("이미지 없이 글만 올립니다. 사진을 넣으려면 --images 또는 --images-dir.")
    missing = [str(p) for p in imgs if not p.exists()]
    if missing:
        log(f"이미지 파일 없음: {missing}")
        return 1
    if len(imgs) > MAX_IMAGES:
        cut = [p.name for p in imgs[MAX_IMAGES:]]
        imgs = imgs[:MAX_IMAGES]
        log(f"이미지는 최대 {MAX_IMAGES}장까지만 넣습니다. 제외: {', '.join(cut)}")
    if imgs:
        log(f"이미지 {len(imgs)}장 사용")
    if a.mode == "publish":
        return cmd_publish(a.title, body, a.open_type, a.confirm,
                           a.force, a.headless, imgs)
    return cmd_draft(a.title, body, a.headless, imgs)


if __name__ == "__main__":
    sys.exit(main())
