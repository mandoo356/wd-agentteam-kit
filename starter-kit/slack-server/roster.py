"""roster.py — 직원 명단·대표 이름·아이콘을 한 곳에서 읽는다. (엔진 — 고칠 일 없음)

server.py / claude_bridge.py / 점검.py 가 같이 쓴다.

  load_agents(kit_root)     .claude/agents/*.md 를 읽어 {키: {name, description, body}} 로
  owner_name(kit_root)      대표 이름 — .env 의 OWNER_NAME → workspace/memory/facts.md 의 "이름:" 순
  to_slack_emoji("📄")      유니코드 이모지를 슬랙이 알아듣는 :page_facing_up: 으로 바꾼다
  build_aliases(...)        "팀장" / "staff1" / 직원 파일의 name → staff1  (누가 말했는지 찾는 표)
  intro_placeholders(text)  인사말에 [무엇] 같은 빈칸이 남아 있는지

2026-09-07 신설. 배경 — 강의장에서 세 가지가 터졌다.
  ① 직원이 대표를 남의 이름으로 부름   → 대표 이름을 매 요청에 명시한다 (owner_name)
  ② 팀장만 대답하고 나머지는 안 나옴   → 명단을 프롬프트에 넣고, 답 줄의 이름을 넓게 알아본다 (build_aliases)
  ③ 이모지·캐릭터가 안 생김           → 유니코드 이모지를 슬랙 형식으로 바꾸고, 인사말 빈칸을 잡는다
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

# ── 직원 파일 ──────────────────────────────────────────────────
_FRONT = re.compile(r"^\s*---\s*\n(.*?)\n\s*---\s*\n?(.*)$", re.S)


def load_agents(kit_root: Path) -> dict[str, dict]:
    """`.claude/agents/*.md` → {파일이름(확장자 뺀 것): {name, description, body}}.
    `_` 로 시작하는 파일(견본)은 뺀다."""
    out: dict[str, dict] = {}
    d = Path(kit_root) / ".claude" / "agents"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.md")):
        if p.name.startswith("_"):
            continue
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        meta: dict[str, str] = {}
        body = text
        m = _FRONT.match(text)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip().strip("'\"")
            body = m.group(2)
        out[p.stem] = {
            "name": meta.get("name") or p.stem,
            "description": meta.get("description", ""),
            "body": body.strip(),
        }
    return out


# ── 대표 이름 ──────────────────────────────────────────────────
_NAME_LINE = re.compile(r"^\s*[-*]?\s*(?:내\s*이름|대표\s*이름|이름|대표)\s*[:：]\s*(.+?)\s*$")
_PLACEHOLDER_NAMES = {"홍길동", "[홍길동]", "이름", "내 이름", "대표", "○○○", "ooo"}


def _clean_name(v: str) -> str:
    v = re.sub(r"\(.*?\)|<.*?>|←.*$", "", v).strip()   # 괄호 설명·화살표 주석 제거
    v = v.strip("[]*_` ").strip()
    if not v or v in _PLACEHOLDER_NAMES or v.startswith("["):
        return ""
    return v[:20]


def owner_name(kit_root: Path) -> tuple[str, str]:
    """(이름, 출처). 못 찾으면 ('', '')."""
    env = os.environ.get("OWNER_NAME", "").strip().strip("\"'")
    if env:
        return env[:20], ".env OWNER_NAME"
    facts = Path(kit_root) / "workspace" / "memory" / "facts.md"
    if facts.is_file():
        try:
            lines = facts.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except Exception:
            lines = []
        in_boss = False
        first_any = ""
        for line in lines:
            if line.startswith("#"):
                in_boss = "대표" in line
                continue
            m = _NAME_LINE.match(line)
            if not m:
                continue
            v = _clean_name(m.group(1))
            if not v:
                continue
            if in_boss:
                return v, "facts.md"
            if not first_any:
                first_any = v
        if first_any:
            return first_any, "facts.md"
    return "", ""


# ── 이모지 ────────────────────────────────────────────────────
# 슬랙은 icon_emoji 를 :이름: 형태로만 받는다. 유니코드 📄 를 그대로 주면 조용히 무시하고
# 앱 기본 아이콘이 뜬다 — "이모지가 안 바뀌어요"의 정체. 자주 쓰는 것을 표로 두고, 나머지는
# 유니코드 이름으로 최대한 맞춰 본다.
EMOJI_MAP = {
    "📄": "page_facing_up", "📃": "page_with_curl", "📑": "bookmark_tabs", "🎓": "mortar_board",
    "📚": "books", "📖": "book", "📕": "closed_book", "📗": "green_book", "📘": "blue_book",
    "✍": "writing_hand", "✏": "pencil2", "🖊": "lower_left_ballpoint_pen", "🖋": "lower_left_fountain_pen",
    "📝": "memo", "📋": "clipboard", "📁": "file_folder", "📂": "open_file_folder", "🗂": "card_index_dividers",
    "🗃": "card_file_box", "💰": "moneybag", "💵": "dollar", "💴": "yen", "💳": "credit_card",
    "💸": "money_with_wings", "🧾": "receipt", "🧮": "abacus", "📊": "bar_chart", "📈": "chart_with_upwards_trend",
    "📉": "chart_with_downwards_trend", "🪪": "identification_card", "🎨": "art", "🖼": "frame_with_picture",
    "📅": "calendar", "📆": "calendar", "🗓": "spiral_calendar_pad", "⏰": "alarm_clock", "⏱": "stopwatch",
    "🕐": "clock1", "📥": "inbox_tray", "📤": "outbox_tray", "📨": "incoming_envelope", "📧": "e-mail",
    "✉": "envelope", "📬": "mailbox_with_mail", "📮": "postbox", "📞": "telephone_receiver", "☎": "phone",
    "📱": "iphone", "💬": "speech_balloon", "🗨": "left_speech_bubble", "📣": "mega", "📢": "loudspeaker",
    "🔔": "bell", "🤖": "robot_face", "👑": "crown", "⭐": "star", "🌟": "star2", "✨": "sparkles",
    "💡": "bulb", "🚀": "rocket", "✅": "white_check_mark", "☑": "ballot_box_with_check", "🎯": "dart",
    "🏆": "trophy", "🥇": "first_place_medal", "🎖": "medal", "🔍": "mag", "🔎": "mag_right", "🧭": "compass",
    "🗺": "world_map", "🧩": "jigsaw", "🎲": "game_die", "🧠": "brain", "💪": "muscle", "🙋": "raising_hand",
    "👋": "wave", "🤝": "handshake", "👍": "+1", "🙌": "raised_hands", "👏": "clap", "🙏": "pray",
    "💼": "briefcase", "📌": "pushpin", "📍": "round_pushpin", "🛠": "hammer_and_wrench", "🔧": "wrench",
    "🔨": "hammer", "⚙": "gear", "🔑": "key", "🔒": "lock", "🛡": "shield", "🧰": "toolbox",
    "🌸": "cherry_blossom", "🌷": "tulip", "🌻": "sunflower", "🌹": "rose", "🍀": "four_leaf_clover",
    "🌈": "rainbow", "☀": "sunny", "🌙": "crescent_moon", "🔥": "fire", "💎": "gem", "🎁": "gift",
    "🎈": "balloon", "🎉": "tada", "🎤": "microphone", "🎬": "clapper", "📷": "camera", "📸": "camera_with_flash",
    "🎥": "movie_camera", "🎧": "headphones", "🎵": "musical_note", "☕": "coffee", "🍎": "apple", "🍒": "cherries",
    "🍰": "cake", "🍩": "doughnut", "🧸": "teddy_bear", "📦": "package", "🏠": "house", "🏢": "office",
    "🏫": "school", "🏦": "bank", "🚗": "car", "🚄": "bullettrain_side", "✈": "airplane", "🧳": "luggage",
    "🦉": "owl", "🐶": "dog", "🐱": "cat", "🐻": "bear", "🐼": "panda_face", "🦊": "fox_face", "🐰": "rabbit",
    "🐥": "hatched_chick", "🐣": "hatching_chick", "🐤": "baby_chick", "🐧": "penguin", "🐨": "koala",
    "🦁": "lion_face", "🐯": "tiger", "🐸": "frog", "🐢": "turtle", "🦄": "unicorn_face", "🐝": "bee",
    "🐬": "dolphin", "🐳": "whale", "🦋": "butterfly", "😀": "grinning", "😃": "smiley", "😄": "smile",
    "😊": "blush", "🙂": "slightly_smiling_face", "😎": "sunglasses", "🤓": "nerd_face", "🥰": "smiling_face_with_3_hearts",
    "😇": "innocent", "🤗": "hugging_face", "🤔": "thinking_face", "🧐": "face_with_monocle", "😺": "smiley_cat",
    "👩‍🏫": "female-teacher", "👨‍🏫": "male-teacher", "🧑‍🏫": "teacher", "👩‍💻": "female-technologist",
    "👨‍💻": "male-technologist", "🧑‍💻": "technologist", "👩‍💼": "female-office-worker", "👨‍💼": "male-office-worker",
    "🧑‍💼": "office_worker", "👩‍🎨": "female-artist", "👨‍🎨": "male-artist", "🧑‍🎨": "artist",
    "👩‍🔬": "female-scientist", "👨‍🔬": "male-scientist", "🕵": "sleuth_or_spy", "👷": "construction_worker",
    "🧑": "adult", "👩": "woman", "👨": "man", "👤": "bust_in_silhouette", "👥": "busts_in_silhouette",
    "❤": "heart", "💜": "purple_heart", "💙": "blue_heart", "💚": "green_heart", "💛": "yellow_heart",
    "🧡": "orange_heart", "🖤": "black_heart", "💖": "sparkling_heart",
}
_SHORTCODE = re.compile(r"^:[a-z0-9_+\-']+:$")
_STRIP_VS = re.compile("[︎️‍\U0001F3FB-\U0001F3FF]")   # 변형 선택자·피부색 제거


def to_slack_emoji(icon: str | None, default: str = ":robot_face:") -> str:
    """':page_facing_up:' 은 그대로, '📄' 는 ':page_facing_up:' 으로. 모르면 default."""
    s = (icon or "").strip()
    if not s:
        return default
    if _SHORTCODE.match(s):
        return s
    if re.match(r"^[a-z0-9_+\-']+$", s):          # 콜론만 빠뜨린 경우
        return f":{s}:"
    if s in EMOJI_MAP:                              # 결합 이모지(👩‍🏫)는 통째로 먼저
        return f":{EMOJI_MAP[s]}:"
    bare = _STRIP_VS.sub("", s)
    if bare in EMOJI_MAP:
        return f":{EMOJI_MAP[bare]}:"
    first = bare[:1]
    if first in EMOJI_MAP:
        return f":{EMOJI_MAP[first]}:"
    try:
        name = unicodedata.name(first).lower().replace(" ", "_").replace("-", "_")
        name = re.sub(r"[^a-z0-9_]", "", name)
        if name:
            return f":{name}:"
    except (ValueError, TypeError):
        pass
    return default


def emoji_ok(icon: str | None) -> bool:
    """점검용 — 슬랙 형식으로 바꿀 수 있는가."""
    return to_slack_emoji(icon, default="") != ""


# ── 누가 말했는지 ─────────────────────────────────────────────
_NAME_JUNK = re.compile(r"[\s*_`\[\]()【】「」<>@#·.,!?~\-]+")


def norm_name(s: str) -> str:
    s = _STRIP_VS.sub("", s or "")
    s = re.sub(r"\(.*?\)", "", s)          # "팀장 (staff1)" → "팀장"
    s = _NAME_JUNK.sub("", s)
    # 앞에 붙은 이모지 등 글자·숫자·한글이 아닌 것 제거
    s = "".join(ch for ch in s if ch.isalnum() or "가" <= ch <= "힣")
    return s.lower()


def build_aliases(personas: dict, agents: dict) -> dict[str, str]:
    """{정규화된 이름: 직원 키}. display_name · 키 · 직원 파일의 name · 파일 이름 전부."""
    al: dict[str, str] = {}
    for key, p in personas.items():
        for cand in (key, p.get("display_name", "")):
            n = norm_name(cand)
            if n and n not in al:
                al[n] = key
    for key, a in agents.items():
        for cand in (key, a.get("name", "")):
            n = norm_name(cand)
            if n and n not in al:
                al[n] = key
    return al


def match_alias(name: str, aliases: dict[str, str]) -> str | None:
    n = norm_name(name)
    if not n:
        return None
    if n in aliases:
        return aliases[n]
    # "교아니수석아" / "교아니수석님" 처럼 뒤에 호칭이 붙은 경우 — 긴 이름부터
    for a in sorted(aliases, key=len, reverse=True):
        if len(a) >= 2 and n.startswith(a) and len(n) - len(a) <= 2:
            return aliases[a]
    return None


_ROLE_PREFIX = re.compile(r"^\s*[@/]?\s*([^\s:：,，]{1,20})")


def agent_from_text(text: str, aliases: dict[str, str]) -> str | None:
    """'@교아니수석 ○○ 해줘' / '교아니수석 불러서 …' / '교아니수석아' → staff2."""
    m = _ROLE_PREFIX.match(text or "")
    if not m:
        return None
    return match_alias(m.group(1), aliases)


# ── 인사말 빈칸 ────────────────────────────────────────────────
_PH = re.compile(r"\[(무엇|무슨 일|재밌는 한마디|내 회사 이름|담당|이름)[^\]]*\]")


def intro_placeholders(text: str) -> list[str]:
    return [m.group(0) for m in _PH.finditer(text or "")]


def describe(agent_meta: dict | None, limit: int = 60) -> str:
    """직원 파일의 description 첫 문장을 짧게."""
    d = (agent_meta or {}).get("description", "") or ""
    d = re.split(r"(?<=[.。!?])\s", d.strip(), maxsplit=1)[0]
    return d[:limit]
