"""점검.py — 모듈이 끝날 때마다 여기서 합격 판정을 받습니다.

사용법:
    py 점검.py 0     ← 출발선 (프로그램이 다 깔렸는지)
    py 점검.py 1     ← 직원 뽑기
    py 점검.py 2     ← 일하는 방법 가르치기
    py 점검.py 3     ← 팀으로 묶기
    py 점검.py 4     ← 슬랙에서 부르기
    py 점검.py 5     ← 사무실 차리기
    py 점검.py 6     ← 전체 점검

이 파일은 고치지 마세요. 여러분이 만든 것이 규격에 맞는지 확인하는 채점표입니다.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 윈도우 콘솔에서 한글·이모지가 깨지지 않도록.
#
# 한국어 윈도우의 검은 창은 기본 코드페이지가 949 다. 거기에 utf-8 로 내보내면
# 글자가 전부 깨진다(cmd·PowerShell 둘 다 똑같이 깨진다 — 셸 문제가 아니라 코드페이지 문제다).
# 그래서 출력 방식을 바꾸기 전에 창의 코드페이지 자체를 65001(UTF-8)로 먼저 바꾼다.
# 이렇게 해두면 수강생이 chcp 65001 을 외우지 않아도 된다.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
OK, NO = "✅", "❌"


# ── 도우미 ────────────────────────────────────────────────

def run(cmd):
    """명령어를 실행해 첫 줄을 돌려준다. 실패하면 None."""
    exe = shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        out = subprocess.run([exe] + cmd[1:], capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    text = (out.stdout or out.stderr).strip()
    return text.splitlines()[0] if text else None


def major(version_text):
    """'v22.1.0' / 'Python 3.13.1' 에서 앞 숫자 두 개를 뽑는다."""
    m = re.search(r"(\d+)\.(\d+)", version_text or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def agent_files():
    return sorted((ROOT / ".claude" / "agents").glob("*.md"))


def skill_files():
    return sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))


def front_matter(path):
    """파일 맨 위 --- 로 둘러싸인 부분에서 key: value 를 읽는다."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    m = re.match(r"^\s*---\s*\n(.*?)\n---", text, re.S)
    body = m.group(1) if m else text[:800]
    found = {}
    for line in body.splitlines():
        kv = re.match(r"\s*([A-Za-z_]+)\s*:\s*(.+?)\s*$", line)
        if kv:
            found[kv.group(1).lower()] = kv.group(2)
    return found


# ── 결과물(인쇄물) 검사 도우미 ─────────────────────────────
# 2026-08-15 추가. 카드 P4·P8b 가 .md 뿐 아니라 .html 까지 만들도록 바뀌어서,
# "파일이 나왔는지"를 파일 이름이 아니라 **내용**으로 판별한다.
# (AI 가 파일 이름을 매번 조금씩 다르게 짓기 때문)

_TEXT_CACHE = {}


def text_of(path):
    """파일 내용을 읽어 캐시한다. 못 읽으면 빈 문자열."""
    key = str(path)
    if key not in _TEXT_CACHE:
        try:
            _TEXT_CACHE[key] = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            _TEXT_CACHE[key] = ""
    return _TEXT_CACHE[key]


def result_html():
    d = ROOT / "workspace" / "결과물"
    return sorted(d.glob("*.html")) if d.is_dir() else []


def decks():
    """16:9 슬라이드 판형(1440 × 810)이 들어 있는 html"""
    return [p for p in result_html() if "1440" in text_of(p) and "810" in text_of(p)]


def workbooks():
    """A4 인쇄 판형(794 × 1123 또는 size:A4)이 들어 있는 html"""
    out = []
    for p in result_html():
        t = text_of(p).replace(" ", "")
        if ("794" in t and "1123" in t) or "size:A4" in t:
            out.append(p)
    return out


def company_name():
    """facts.md 에서 '회사 이름' 값을 뽑는다. 못 찾으면 None."""
    f = ROOT / "workspace" / "memory" / "facts.md"
    if not f.is_file():
        return None
    for line in text_of(f).splitlines():
        m = re.match(r"\s*[-*]?\s*회사\s*이름\s*[:：]\s*(.+?)\s*$", line)
        if m:
            v = m.group(1).strip().strip("[]").strip()
            return v or None
    return None


def offline_ok(files):
    """인터넷 주소를 쓴 파일 이름 목록. 비어 있으면 오프라인에서 열린다."""
    bad = []
    for p in files:
        t = text_of(p)
        if 'src="http' in t or "src='http" in t or 'href="http' in t or "href='http" in t:
            bad.append(p.name)
    return bad


def printable(files):
    """인쇄 설정(@page)이 들어간 파일이 하나라도 있는지"""
    return any("@page" in text_of(p) for p in files)


# ── 모듈별 검사 ────────────────────────────────────────────

def module_0():
    checks = []

    node = run(["node", "-v"])
    checks.append(("Node.js 22 이상", node is not None and major(node)[0] >= 22,
                   node or "설치 안 됨 → nodejs.org 에서 LTS 설치"))

    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    # 수업 표준은 3.14 (환경점검이 무조건 설치). 다른 버전으로 이 파일을 돌리면 여기서 알려준다.
    checks.append(("Python 3.14 (수업 표준)", sys.version_info[:2] == (3, 14),
                   f"현재 {py}" + ("" if sys.version_info[:2] == (3, 14) else " → 환경점검.bat 을 실행하면 3.14 가 깔리고 py 가 3.14 로 고정됩니다")))

    git = run(["git", "--version"])
    checks.append(("Git", git is not None, git or "설치 안 됨 → git-scm.com"))

    claude = shutil.which("claude") or shutil.which("claude.cmd")
    codex = shutil.which("codex") or shutil.which("codex.cmd")
    checks.append(("AI 코딩 도구 (claude 또는 codex)", bool(claude or codex),
                   claude or codex or "둘 중 하나는 설치돼 있어야 합니다"))

    need = [".claude/agents", ".claude/skills", "workspace/inbox", "workspace/memory"]
    missing = [d for d in need if not (ROOT / d).is_dir()]
    checks.append(("스타터킷 폴더 구조", not missing,
                   "정상" if not missing else "없는 폴더: " + ", ".join(missing)))

    # 자동 저장·안전장치 (.claude/settings.json + hooks 2개). 이게 없으면 직원이 한 일이 기록되지 않고
    # 삭제·덮어쓰기도 확인 없이 지나간다.
    hooks = [".claude/settings.json", ".claude/hooks/autosave.py", ".claude/hooks/guard.py"]
    lost = [h for h in hooks if not (ROOT / h).is_file()]
    ok_json = True
    if not lost:
        try:
            import json
            cfg = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
            ok_json = bool(cfg.get("hooks", {}).get("PreToolUse")) and bool(cfg.get("hooks", {}).get("Stop"))
        except Exception:
            ok_json = False
    checks.append(("자동 저장·안전장치 (기록 + 삭제 확인)", not lost and ok_json,
                   "켜져 있음" if not lost and ok_json else
                   ("없는 파일: " + ", ".join(lost) if lost else "settings.json 이 깨졌습니다 → 스타터킷 원본에서 다시 복사")))
    launcher = shutil.which("py")
    checks.append(("py 실행기 (안전장치가 py -3 로 돈다)", launcher is not None,
                   launcher or "py 가 없습니다 → 환경점검.bat 을 다시 실행 (py launcher 포함 설치)"))
    pinned = os.environ.get("PY_PYTHON3", "") == "3.14" or sys.version_info[:2] == (3, 14)
    checks.append(("py 가 3.14 를 가리킨다 (PY_PYTHON3)", pinned,
                   "정상" if pinned else "환경점검.bat 을 다시 실행하면 고정됩니다. 새 창을 열어야 적용됩니다"))

    checks.append(("한글 경로에서 실행 중", True, str(ROOT)))
    return checks


def module_1():
    files = agent_files()
    checks = [("직원이 1명 이상 있다", len(files) >= 1, f"{len(files)}명")]
    checks.append(("직원이 5명 이상 있다", len(files) >= 5, f"{len(files)}명"))

    bad = []
    names = []
    for f in files:
        fm = front_matter(f)
        missing = [k for k in ("name", "description") if k not in fm]
        if missing:
            bad.append(f"{f.name}({','.join(missing)} 없음)")
        if "name" in fm:
            names.append(fm["name"])
    checks.append(("모든 직원 파일에 name·description 이 있다", not bad,
                   "정상" if not bad else " / ".join(bad)))

    dupes = {n for n in names if names.count(n) > 1}
    checks.append(("직원 이름이 서로 겹치지 않는다", not dupes,
                   "정상" if not dupes else "겹침: " + ", ".join(sorted(dupes))))

    # ── 2026-09-04 추가 — 브랜드 색이 facts.md 에 있는지 (P1 / P1-B) ──
    # 제안서(P4)·교재(P8)·프로필(S7)이 전부 이 네 줄을 읽어 칠한다. 없으면 나중에 전부 남색 예시로 나온다.
    facts = ROOT / "workspace" / "memory" / "facts.md"
    ftxt = facts.read_text(encoding="utf-8", errors="ignore") if facts.is_file() else ""
    hexes = {m.upper() for m in re.findall(r"#[0-9A-Fa-f]{6}\b", ftxt)}
    sample = {"#12314B", "#1F5B8E", "#E9A23B", "#EAF1F8"}
    if not facts.is_file():
        hit, why = False, "facts.md 가 없습니다 — 카드 P1 을 붙여넣으세요"
    elif len(hexes) < 3:
        hit, why = False, f"색 hex 가 {len(hexes)}개뿐입니다 — 카드 P1 을 다시 붙여넣으세요 (진한·기본·강조·옅은)"
    elif not (hexes - sample):
        hit, why = True, "예시 남색 그대로입니다 — 카드 P1-B 로 내 색을 뽑으면 제안서·프로필이 내 브랜드 색으로 나옵니다"
    else:
        hit, why = True, f"내 브랜드 색 {len(hexes)}개 확인 ({', '.join(sorted(hexes))})"
    checks.append(("브랜드 색 네 줄이 facts.md 에 있다", hit, why))
    return checks


def module_2():
    files = skill_files()
    # 카드 P4 는 스킬을 1개 만든다. 여기서 2개를 요구하면 카드대로 한 사람이
    # 통과를 못 한다(2026-08-13 리허설에서 발견). 1개가 합격선이고,
    # 2개째는 시간이 남는 사람만 만든다.
    checks = [("스킬이 1개 이상 있다", len(files) >= 1, f"{len(files)}개")]

    bad = []
    for f in files:
        fm = front_matter(f)
        missing = [k for k in ("name", "description") if k not in fm]
        if missing:
            bad.append(f"{f.parent.name}({','.join(missing)} 없음)")
    checks.append(("모든 SKILL.md 에 name·description 이 있다", not bad,
                   "정상" if not bad else " / ".join(bad)))

    made = [p for p in (ROOT / "workspace" / "결과물").glob("*") if p.is_file()]
    checks.append(("스킬을 돌려서 결과물이 1개 이상 생겼다", len(made) >= 1,
                   f"{len(made)}개" if made else "workspace/결과물 이 비어 있습니다"))

    linked = any("skill" in front_matter(f).get("description", "").lower()
                 or "스킬" in f.read_text(encoding="utf-8", errors="ignore")
                 for f in agent_files())
    checks.append(("직원 파일에서 스킬을 언급한다", linked,
                   "정상" if linked else "어느 직원이 어느 스킬을 쓰는지 적어주세요"))

    # ── 2026-08-15 추가 — 제안서 덱까지 나왔는지 ──
    dk = decks()
    checks.append(("제안서 덱(.html)이 나왔다", len(dk) >= 1,
                   dk[0].name if dk else
                   "카드 P4 를 그대로 붙여넣으면 .md 와 .html 두 개가 나옵니다"))

    checks.append(("덱이 인쇄해서 PDF로 저장된다", printable(dk),
                   "정상 (@page 설정 있음)" if printable(dk) else
                   "덱에 @page 인쇄 설정이 없습니다 — 카드 P4 를 다시 붙여넣으세요"))

    name = company_name()
    if not dk:
        hit, why = False, "덱이 아직 없습니다"
    elif not name:
        hit, why = True, "facts.md 에 '회사 이름:' 줄이 없어 이 검사는 건너뜁니다"
    else:
        hit = any(name in text_of(p) for p in dk)
        why = f"'{name}' 확인" if hit else \
              f"facts.md 의 회사 이름 '{name}' 이 덱에 없습니다 — \"덱에 회사 이름 넣어줘\""
    checks.append(("덱에 내 회사 이름이 들어갔다", hit, why))

    bad = offline_ok(dk)
    checks.append(("덱이 인터넷 없이 열린다", bool(dk) and not bad,
                   "정상" if dk and not bad else
                   ("덱이 아직 없습니다" if not dk else
                    "인터넷 주소를 쓴 파일: " + ", ".join(bad) + " — 강의장에서 깨집니다")))
    return checks


def module_3():
    facts = ROOT / "workspace" / "memory" / "facts.md"
    checks = [("팀 규약(facts.md)이 있다", facts.is_file(), str(facts.relative_to(ROOT)))]

    size = facts.stat().st_size if facts.is_file() else 0
    checks.append(("팀 규약에 내용이 채워져 있다", size > 200, f"{size} 바이트 (200 이상 필요)"))

    notes = [p for p in (ROOT / "workspace" / "inbox").rglob("*") if p.is_file()]
    checks.append(("직원끼리 넘긴 쪽지가 1개 이상 있다", len(notes) >= 1,
                   f"{len(notes)}개" if notes else "workspace/inbox 가 비어 있습니다"))

    made = [p for p in (ROOT / "workspace" / "결과물").glob("*") if p.is_file()]
    checks.append(("결과물이 2개 이상 쌓였다", len(made) >= 2, f"{len(made)}개"))

    # ── 2026-08-15 추가 — 교재 워크북까지 나왔는지 (카드 P8b) ──
    wb = workbooks()
    checks.append(("교재 워크북(.html)이 나왔다", len(wb) >= 1,
                   wb[0].name if wb else
                   "카드 P8b 를 붙여넣고 'staff2 불러서 inbox 확인하고 이어서 교재 만들어줘'"))

    checks.append(("워크북이 인쇄용 A4다", printable(wb),
                   "정상 (@page 설정 있음)" if printable(wb) else
                   "A4 인쇄 설정이 없습니다 — 나눠줄 수가 없습니다"))

    bad = offline_ok(wb)
    checks.append(("워크북이 인터넷 없이 열린다", bool(wb) and not bad,
                   "정상" if wb and not bad else
                   ("워크북이 아직 없습니다" if not wb else
                    "인터넷 주소를 쓴 파일: " + ", ".join(bad))))
    return checks


def module_4():
    srv = ROOT / "slack-server"

    # ── 선행 조건 ────────────────────────────────────────────
    # 슬랙이 아무리 잘 붙어도 직원 파일이 없으면 아무도 대답하지 않는다.
    # 예전에는 이걸 안 봐서, 직원 0명인데 모듈 4가 통과하고 나중에 터졌다.
    agents = agent_files()
    checks = [("직원이 5명 이상 있다 (모듈 1 완료)", len(agents) >= 5,
               f"{len(agents)}명" if agents else "0명 — 모듈 1을 먼저 하세요")]

    # `.md.txt` 로 잘못 저장된 파일 잡기. 탐색기가 확장자를 숨기면 눈으로는 구별이 안 된다.
    agents_dir = ROOT / ".claude" / "agents"
    mistyped = [p.name for p in agents_dir.glob("*.md.*")
                if not p.name.startswith("_")] if agents_dir.is_dir() else []
    checks.append(("직원 파일 확장자가 .md 다", not mistyped,
                   "정상" if not mistyped
                   else "이름 끝을 .md 로 고치세요: " + ", ".join(mistyped)))

    checks.append(("slack-server 폴더가 있다", srv.is_dir(), str(srv.relative_to(ROOT))))
    checks.append(("server.py 가 있다", (srv / "server.py").is_file(), "server.py"))

    env = srv / ".env"
    checks.append((".env 파일을 만들었다", env.is_file(),
                   "있음" if env.is_file() else ".env.example 을 복사해서 .env 로 만드세요"))

    # `.env.txt` 로 저장된 경우. `.env` 가 없을 때만 알려주면 된다.
    if not env.is_file():
        stray = [p.name for p in srv.glob(".env.*") if p.name != ".env.example"]
        if stray:
            checks.append((".env 이름이 정확하다", False,
                           "이름 끝의 확장자를 지우세요: " + ", ".join(stray)))

    # 🔒 값은 절대 읽지 않는다. 키 이름이 있는지만 본다.
    # utf-8-sig 로 읽는 이유: 메모장·파워셸로 저장한 .env 는 맨 앞에 안 보이는 표식(BOM)이
    # 붙어서, 그냥 utf-8 로 읽으면 첫 줄 키 이름이 깨진 채로 잡힌다.
    keys = set()
    if env.is_file():
        for line in env.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            k = line.split("=", 1)[0].strip()
            if k and not k.startswith("#"):
                keys.add(k.upper())
    need = {"SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"}
    checks.append(("슬랙 열쇠 2개를 넣었다", need.issubset(keys),
                   "정상" if need.issubset(keys) else "빠진 항목: " + ", ".join(sorted(need - keys))))

    # 🔒 값의 "모양"만 본다. 값 자체는 화면에 절대 찍지 않는다.
    #    xoxb/xapp 자리 바꿔 넣기·따옴표·앞뒤 공백이 강의장 실패의 대부분이다.
    if env.is_file():
        vals = {}
        for line in env.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip().upper()] = v

        shape = []
        for key, head in (("SLACK_BOT_TOKEN", "xoxb-"), ("SLACK_APP_TOKEN", "xapp-")):
            raw = vals.get(key)
            if raw is None or not raw.strip():
                continue
            v = raw.strip()
            if v[:1] in "\"'" or v[-1:] in "\"'":
                shape.append(f"{key}: 따옴표를 지우세요")
            elif raw != raw.rstrip() or raw[:1] == " ":
                shape.append(f"{key}: 앞뒤 공백을 지우세요")
            elif not v.startswith(head):
                other = "xapp-" if head == "xoxb-" else "xoxb-"
                hint = f"{other} 을 여기 넣으신 것 같습니다" if v.startswith(other) else f"{head} 로 시작해야 합니다"
                shape.append(f"{key}: {hint}")
        checks.append(("열쇠 모양이 맞다 (xoxb / xapp)", not shape,
                       "정상" if not shape else " / ".join(shape)))

        # 🔒 내 멤버 ID(OWNER_USER_ID). 이게 있어야 직원이 "나"를 알아보고 실행한다.
        #    값은 찍지 않고 모양만 본다 — 슬랙 사용자 ID 는 U(또는 W) 로 시작한다.
        raw = vals.get("OWNER_USER_ID", "")
        v = raw.strip()
        if not v:
            owner_msg = "비어 있음 — 슬랙 앱 → 내 프로필 사진 → 프로필 → ⋯ 더보기 → 멤버 ID 복사"
        elif v[:1] in "\"'" or v[-1:] in "\"'":
            owner_msg = "따옴표를 지우세요"
        elif raw != raw.rstrip() or raw[:1] == " ":
            owner_msg = "앞뒤 공백을 지우세요"
        elif not v[:1].upper() in ("U", "W") or len(v) < 9 or not v.isalnum():
            owner_msg = "U 로 시작하는 멤버 ID 가 아닙니다 (이메일·이름이 아니라 '멤버 ID 복사' 값)"
        else:
            owner_msg = "정상"
        checks.append(("내 멤버 ID 를 넣었다 (OWNER_USER_ID)", owner_msg == "정상", owner_msg))

        # 메모장으로 저장하면 맨 앞에 안 보이는 표식(BOM)이 붙는다. server.py 는 견디지만
        # 다른 도구로 열면 첫 줄을 못 읽으므로 여기서 미리 알려준다.
        try:
            bom = env.read_bytes().startswith(b"\xef\xbb\xbf")
        except Exception:
            bom = False
        checks.append((".env 가 BOM 없이 저장됐다", not bom,
                       "정상" if not bom else "메모장 말고 VS Code 로 다시 저장하세요"))

    log = srv / "logs" / "server.log"
    started = log.is_file() and "running" in log.read_text(encoding="utf-8", errors="ignore").lower()
    checks.append(("서버가 한 번 이상 정상 기동했다", started,
                   "정상" if started else "slack-server 폴더에서 py -3 server.py (환경점검이 한 번 켜 봅니다)"))

    # ── 2026-09-08 추가: 강의장에서 실제로 난 세 가지 ─────────────────
    #   ① 직원이 대표를 남의 이름으로 부름  → facts.md 에 내 이름이 있어야 한다
    #   ② 팀장만 대답                        → personas 표시 이름이 직원 파일과 짝이 맞아야 한다
    #   ③ 이모지·캐릭터가 안 생김            → 아이콘이 슬랙 형식으로 바뀌는지, 인사말에 빈칸이 없는지
    try:
        sys.path.insert(0, str(srv))
        import roster  # slack-server/roster.py (엔진)
    except Exception:
        roster = None
    if roster is not None:
        name, src = roster.owner_name(ROOT)
        checks.append(("대표 이름을 facts.md 에 적었다 (직원이 나를 알아보는 근거)", bool(name),
                       f"정상 ({src})" if name
                       else "workspace/memory/facts.md 의 '- 이름:' 줄에 내 이름 (카드 P1). 홍길동은 빈칸으로 봅니다"))
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("personas_check", srv / "personas.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            personas = getattr(mod, "PERSONAS", {}) or {}
            perr = ""
        except Exception as e:  # noqa: BLE001
            personas, perr = {}, f"{type(e).__name__}: {str(e)[:60]}"
        checks.append(("personas.py 가 읽힌다", not perr,
                       "정상" if not perr else f"personas.py 문법 오류 — {perr}. git checkout slack-server/personas.py 로 되돌리고 P11 다시"))
        if personas:
            agents_keys = set(roster.load_agents(ROOT))
            orphan = [k for k in personas if k not in agents_keys]
            checks.append(("personas 의 키가 직원 파일과 짝이 맞다", not orphan,
                           "정상" if not orphan
                           else "짝이 없는 키: " + ", ".join(orphan) + " — 키(staff1 같은 영어 이름)는 바꾸지 마세요"))
            names = [str(p.get("display_name", "")).strip() for p in personas.values()]
            dup = sorted({n for n in names if names.count(n) > 1})
            default_names = [n for n in names if re.fullmatch(r"직원\d+", n)]
            checks.append(("표시 이름이 서로 다르고 '직원1' 기본값이 아니다", not dup and not default_names,
                           "정상" if not dup and not default_names
                           else ("겹침: " + ", ".join(dup) + " / " if dup else "") +
                                ("아직 기본값: " + ", ".join(default_names) + " → 카드 P11" if default_names else "")))
            bad_icon = [k for k, p in personas.items() if not roster.emoji_ok(p.get("icon_emoji"))]
            checks.append(("아이콘이 슬랙에 뜨는 형식이다 (📄 또는 :page_facing_up:)", not bad_icon,
                           "정상" if not bad_icon else "못 알아듣는 아이콘: " + ", ".join(bad_icon)))
            ph = [k for k, p in personas.items()
                  if roster.intro_placeholders(str(p.get("intro", "")) + str(p.get("intro_class", "")))]
            checks.append(("인사말에 [무엇] 빈칸이 없다 (팀 소개 때 캐릭터가 나오는 근거)", not ph,
                           "정상" if not ph else "빈칸 남음: " + ", ".join(ph) + " → 카드 P11 (인사말까지 채웁니다)"))
    return checks


def module_5():
    office = ROOT / "office"
    checks = [("office 폴더가 있다", office.is_dir(), str(office.relative_to(ROOT)))]

    cfg = next(office.glob("company.config.*"), None)
    checks.append(("company.config 파일이 있다", cfg is not None,
                   cfg.name if cfg else "없음"))

    changed = False
    if cfg:
        text = cfg.read_text(encoding="utf-8", errors="ignore")
        changed = "여기에_회사이름" not in text and "내 회사" not in text
    checks.append(("내 회사 이름으로 바꿨다", changed,
                   "정상" if changed else "company.config 의 회사 이름이 아직 기본값입니다"))

    checks.append(("직원 수가 office 와 맞는다", len(agent_files()) >= 5,
                   f"직원 {len(agent_files())}명"))
    return checks


def module_6():
    out = []
    for n in range(6):
        got = MODULES[n]()
        passed = sum(1 for _, ok, _ in got if ok)
        out.append((f"모듈 {n}", passed == len(got), f"{passed}/{len(got)} 통과"))
    return out


MODULES = {0: module_0, 1: module_1, 2: module_2,
           3: module_3, 4: module_4, 5: module_5, 6: module_6}

TITLES = {0: "출발선 맞추기", 1: "직원 뽑기", 2: "일하는 방법 가르치기",
          3: "팀으로 묶기", 4: "슬랙에서 부르기", 5: "사무실 차리기",
          6: "전체 점검"}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in [str(i) for i in MODULES]:
        print("사용법: py 점검.py <숫자 0~6>")
        print("  예)  py 점검.py 1")
        return 2

    n = int(sys.argv[1])
    print()
    print(f"  모듈 {n} — {TITLES[n]}")
    print("  " + "─" * 46)

    results = MODULES[n]()
    for label, ok, detail in results:
        print(f"  {OK if ok else NO}  {label}")
        if not ok or n == 0:
            print(f"        └ {detail}")

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("  " + "─" * 46)
    if passed == total:
        print(f"  🎉 {total}개 전부 통과! 다음 모듈로 넘어가세요.")
    else:
        print(f"  {passed}/{total} 통과 — ❌ 표시된 것만 고치면 됩니다.")
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
