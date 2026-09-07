"""내 AI 회사 — 슬랙 서버.

슬랙에 말을 걸면 → 이 프로그램이 받아서 → 직원(에이전트)을 깨우고 → 답을 슬랙에 올립니다.

켜는 법:   py -3 server.py
끄는 법:   검은 창에서 Ctrl + C
필요한 것: 같은 폴더의 .env 파일에 슬랙 열쇠 2개

⚙️ 이 파일은 엔진입니다. 수업 중에 고칠 일은 없습니다.
   이름·아이콘을 바꾸려면 personas.py, 채널을 늘리려면 agent_channels.py 를 고치세요.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from agent_channels import resolve_agent
from claude_bridge import find_claude_cli, invoke_agent, reset_conversation
from personas import (
    PERSONAS, INTRO_ORDER, CLASS_OPENING, CLASS_CLOSING,
    get_persona, get_intro,
)
from roster import (
    load_agents, owner_name, to_slack_emoji, build_aliases, match_alias,
    agent_from_text, intro_placeholders, describe,
)

# ── 설정 읽기 ───────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
KIT_ROOT = HERE.parent                       # 스타터킷 폴더

# encoding="utf-8-sig" 가 중요하다. 메모장이나 파워셸로 .env 를 저장하면 파일 맨 앞에
# 눈에 안 보이는 표식(BOM)이 붙는데, 그러면 첫 줄의 SLACK_BOT_TOKEN 을 못 읽어서
# "열쇠가 비어 있다"고 나온다. 값은 멀쩡히 들어 있는데도. 강의장에서 제일 잡기 어려운 종류다.
load_dotenv(HERE / ".env", encoding="utf-8-sig")

MISSING = [k for k in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "OWNER_USER_ID")
           if not os.environ.get(k, "").strip()]
if MISSING:
    print()
    print("  ❌ .env 에 이게 비어 있습니다: " + ", ".join(MISSING))
    print()
    print("  1) slack-server 폴더의 .env.example 을 복사해서 .env 로 이름을 바꾸고")
    print("  2) 열쇠 2개(xoxb-, xapp-)와 내 멤버 ID(U…)를 붙여넣으세요.")
    if "OWNER_USER_ID" in MISSING:
        print("     멤버 ID 는 슬랙 앱 → 내 프로필 사진 → 프로필 → ⋯ 더보기 → 멤버 ID 복사")
    print()
    sys.exit(1)

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
OWNER_USER_ID = os.environ.get("OWNER_USER_ID", "").strip()
WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE") or (KIT_ROOT / "workspace"))
LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "server.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("agent")

if not WORKSPACE.exists():
    log.error("workspace 폴더가 없습니다: %s", WORKSPACE)
    sys.exit(1)

try:
    CLAUDE_CLI = find_claude_cli(os.environ.get("CLAUDE_CLI") or None)
except Exception as e:
    print(f"\n  ❌ {e}\n")
    sys.exit(1)

AGENTS = load_agents(KIT_ROOT)            # {staff1: {name, description, body}}
AGENT_COUNT = len(AGENTS)
ALIASES = build_aliases(PERSONAS, AGENTS)  # "팀장"/"staff1"/직원 파일 name → staff1
OWNER_NAME, OWNER_NAME_SRC = owner_name(KIT_ROOT)

log.info("스타터킷: %s", KIT_ROOT)
log.info("결과물 저장 위치: %s", WORKSPACE)
log.info("claude 명령어: %s", CLAUDE_CLI)
log.info("직원 파일: %d개", AGENT_COUNT)
if AGENT_COUNT == 0:
    log.warning("⚠️  .claude/agents/ 에 직원이 한 명도 없습니다 — 모듈 1을 먼저 하세요")
for _k, _p in PERSONAS.items():
    if _k not in AGENTS:
        log.warning("⚠️  personas.py 의 %s(%s) 에 짝이 되는 직원 파일 .claude/agents/%s.md 가 없습니다",
                    _k, _p.get("display_name", ""), _k)
_ph = [k for k, p in PERSONAS.items() if intro_placeholders(p.get("intro", "") + p.get("intro_class", ""))]
if _ph:
    log.warning("⚠️  personas.py 인사말에 [무엇] 같은 빈칸이 남아 있습니다 (%s) — 카드 P11 로 채우세요. "
                "그동안은 직원 파일의 description 으로 대신 인사합니다", ", ".join(_ph))

# 🔒 직원은 파일을 읽고 쓸 수 있는 권한(bypassPermissions)으로 실행된다. OWNER_USER_ID가
# 비어 있으면 이 워크스페이스에서 봇에게 말을 걸 수 있는 사람 누구나 그 권한을 쓴다 —
# DM은 원래 나 혼자지만, 채널에 초대(/invite)하면 그 채널의 다른 사람도 포함된다.
# OWNER_USER_ID 는 위에서 비어 있으면 이미 종료됐다. 여기서는 설정됐음을 남기기만 한다.
log.info("본인 확인: OWNER_USER_ID 설정됨 — 그 외 사용자는 응답만 받고 실행은 거절됩니다")

app = AsyncApp(token=SLACK_BOT_TOKEN)


# ── 도우미 ──────────────────────────────────────────────────
async def get_channel_name(client, channel_id: str) -> str:
    try:
        info = await client.conversations_info(channel=channel_id)
        return (info.get("channel") or {}).get("name", "") or ""
    except Exception as e:
        log.warning("채널 이름을 못 읽었습니다 (%s): %s", channel_id, e)
        return ""


def log_conversation(agent: str, user_id: str, direction: str, text: str) -> None:
    """대화를 워크스페이스에 남긴다. 나중에 뭘 시켰는지 찾아볼 수 있게."""
    inbox_dir = WORKSPACE / "inbox" / agent
    inbox_dir.mkdir(parents=True, exist_ok=True)
    logfile = inbox_dir / f"slack_{date.today().isoformat()}.md"
    with logfile.open("a", encoding="utf-8") as f:
        f.write(f"\n### {direction} [{user_id}]\n\n{text}\n")


MAX_BUBBLES = 8
_SPEAKER = re.compile(r"^(?P<name>[^:：]{1,24}?)\s*[:：]\s*(?P<body>.+)$")


def split_reply(reply: str) -> list[tuple[str | None, str]]:
    """답을 카톡 말풍선처럼 쪼갠다.

    "팀장: 착수했습니다" 같은 줄은 팀장 이름·아이콘으로 올라간다.
    이름은 personas 의 표시 이름뿐 아니라 staff2 같은 키, 직원 파일의 name,
    "**팀장**:" / "[팀장]:" / "팀장 (staff1):" 처럼 꾸며진 것도 알아본다.
    """
    bubbles: list[tuple[str | None, str]] = []
    for raw in reply.splitlines():
        line = raw.strip().lstrip("-•· ").strip()
        if not line:
            continue
        who = None
        body = line
        m = _SPEAKER.match(line)
        if m:
            who = match_alias(m.group("name"), ALIASES)
            if who:
                body = m.group("body").strip().strip("*_").strip()
        bubbles.append((who, body))
    if len(bubbles) > MAX_BUBBLES:
        head = bubbles[: MAX_BUBBLES - 1]
        tail = " / ".join(b for _, b in bubbles[MAX_BUBBLES - 1:])
        bubbles = head + [(None, tail)]
    return bubbles


async def post_as_agent(client, channel_id: str, agent: str, text: str,
                        thread_ts: str | None = None):
    """그 직원의 이름·아이콘으로 슬랙에 올린다."""
    p = get_persona(agent)
    # 📄 같은 유니코드 이모지는 슬랙이 조용히 무시한다 → :page_facing_up: 으로 바꿔서 보낸다
    icon = to_slack_emoji(p.get("icon_emoji"))
    try:
        return await client.chat_postMessage(
            channel=channel_id, text=text,
            username=p["display_name"], icon_emoji=icon,
            thread_ts=thread_ts,
        )
    except Exception as e:
        # chat:write.customize 권한이 없으면 이름을 못 바꾼다. 그래도 답은 보낸다.
        log.warning("이름 바꿔 올리기 실패 (슬랙 앱 OAuth & Permissions → Bot Token Scopes 에 "
                    "chat:write.customize 추가 후 Reinstall): %s", e)
        return await client.chat_postMessage(
            channel=channel_id,
            text=f"*{p['display_name']}* {icon}\n{text}",
            thread_ts=thread_ts,
        )


def intro_text(agent: str, audience: str) -> str:
    """인사말. personas.py 에 [무엇] 빈칸이 남아 있으면 직원 파일 description 으로 대신한다."""
    text = get_intro(agent, audience)
    if text and not intro_placeholders(text):
        return text
    p = get_persona(agent)
    job = describe(AGENTS.get(agent)) or "담당 업무는 직원 파일에 적혀 있어요"
    if audience == "class":
        return f"여러분 안녕하세요! {p['display_name']}입니다. 저는 AI 직원이고, {job}"
    return f"{p['display_name']}입니다. {job}"


def pick_agent(channel_name: str, text: str) -> str:
    """누가 받을지. ① 문장 앞의 이름(@교아니수석 / 교아니수석 불러서 / 교아니수석아)
    ② 채널 이름(#교아니수석 · #staff2) ③ agent_channels.py 표 ④ 기본 직원."""
    by_text = agent_from_text(text, ALIASES)
    if by_text and by_text in AGENTS:
        return by_text
    if channel_name:
        by_ch = match_alias(channel_name.lstrip("#"), ALIASES)
        if by_ch and by_ch in AGENTS:
            return by_ch
    return resolve_agent(channel_name, text)


def explain_failure(e: BaseException) -> str:
    """오류를 사람이 뭘 해야 할지 아는 말로 바꾼다."""
    name = type(e).__name__
    msg = str(e)
    if "not found" in msg.lower() and "claude" in msg.lower():
        return ("❌ claude 명령어를 못 찾았습니다.\n"
                "검은 창에서 `claude` 라고 쳐보세요. 반응이 없으면 설치가 안 된 겁니다.")
    if name in ("TimeoutError", "asyncio.TimeoutError") or "timeout" in msg.lower():
        return ("⏳ 시간이 너무 오래 걸려서 멈췄습니다.\n"
                "일이 큰 경우입니다. 더 작게 쪼개서 다시 시켜보세요.")
    if "connection" in msg.lower() or "connect" in name.lower():
        return ("🔌 Claude 와 연결이 끊겼습니다.\n"
                "검은 창을 껐다 켜보세요 (Ctrl+C 후 `py -3 server.py`).")
    return f"❌ 오류가 났습니다: {name}\n자세한 내용은 slack-server/logs/server.log 에 있습니다."


# ── "인사" 기능 ─────────────────────────────────────────────
CLASS_TRIGGERS = ("애들아 인사", "얘들아 인사", "애들아인사", "얘들아인사",
                  "애들아 안녕", "얘들아 안녕", "직원들 인사")
TEAM_TRIGGERS = ("팀 소개", "팀소개", "다 인사", "모두 인사", "자기소개",
                 "누가 있어", "너희 소개", "직원 소개")
RESET_TRIGGERS = ("새 대화", "새대화", "대화 초기화", "기억 지워", "기억지워", "처음부터 다시",
                  "리셋", "reset")


def is_reset(text: str) -> bool:
    low = text.strip().lower()
    return len(low) <= 12 and any(t in low for t in RESET_TRIGGERS)


def is_class_intro(text: str) -> bool:
    low = text.strip().lower()
    return any(t in low for t in CLASS_TRIGGERS)


def is_team_intro(text: str) -> bool:
    low = text.strip().lower()
    return any(t in low for t in TEAM_TRIGGERS)


async def roll_call(client, channel_id: str, user_id: str, audience: str = "boss"):
    """직원들이 순서대로 한 명씩 인사한다."""
    is_class = audience == "class"
    first = INTRO_ORDER[0] if INTRO_ORDER else "staff1"
    if is_class:
        opening, closing, gap = CLASS_OPENING, CLASS_CLOSING, 1.4  # 청중이 읽을 시간
    else:
        opening = "🙌 팀 소개 요청받았습니다. 한 명씩 인사드릴게요."
        closing = "이상입니다. 필요하실 때 채널이나 이름으로 부르시면 됩니다."
        gap = 0.6

    await post_as_agent(client, channel_id, first, opening)
    for name in INTRO_ORDER:
        if name not in AGENTS and name not in PERSONAS:
            continue
        await post_as_agent(client, channel_id, name, intro_text(name, audience))
        await asyncio.sleep(gap)
    await post_as_agent(client, channel_id, first, closing)
    log_conversation(first, user_id, "USER →", f"[{audience} intro]")


# ── 메시지 처리 ─────────────────────────────────────────────
@app.event("message")
async def on_message(event, client, say):
    if event.get("subtype") or event.get("bot_id"):
        return  # 봇이 자기 말에 반응하지 않게

    text = (event.get("text") or "").strip()
    user_id = event.get("user", "")
    channel_id = event.get("channel", "")
    if not text:
        return

    channel_type = event.get("channel_type", "")
    channel_name = "" if channel_type == "im" else await get_channel_name(client, channel_id)

    # 🔒 OWNER_USER_ID가 설정돼 있으면 그 사람 말고는 직원을 실행시킬 수 없다.
    # 파일을 읽고 쓰는 권한(bypassPermissions)으로 도는 작업이라, 아무나 말을 걸어서
    # 실행되게 두면 안 된다. 설정을 안 했으면(빈 값) 예전처럼 누구든 받는다 — 그 위험은
    # 서버 켤 때 로그로 이미 경고했다.
    if OWNER_USER_ID and user_id != OWNER_USER_ID:
        log.warning("본인 아님 — 요청 거절: user=%s channel=%s", user_id, channel_name or "DM")
        await client.chat_postMessage(
            channel=channel_id,
            text="죄송해요, 이 팀은 개인용이라 등록된 대표님만 시킬 수 있어요.",
        )
        return

    # 인사는 Claude 를 거치지 않고 바로 답한다 (몇 초 vs 수십 초)
    if is_class_intro(text):
        log.info("강의장 인사 요청: %s", user_id)
        await roll_call(client, channel_id, user_id, audience="class")
        return
    if is_team_intro(text):
        log.info("팀 소개 요청: %s", user_id)
        await roll_call(client, channel_id, user_id, audience="boss")
        return
    if is_reset(text):
        # 어제 대화·잘못 기억한 이름을 끊고 새로 시작한다. Claude 를 거치지 않는다.
        log.info("새 대화 요청: %s", user_id)
        await reset_conversation(WORKSPACE, CLAUDE_CLI)
        who = f"{OWNER_NAME} 대표님" if OWNER_NAME else "대표님"
        await post_as_agent(client, channel_id, INTRO_ORDER[0] if INTRO_ORDER else "staff1",
                            f"새 대화로 시작합니다. {who}, 무엇을 도와드릴까요?")
        return

    agent = pick_agent(channel_name, text)
    log.info("전달: 채널=%s 직원=%s 내용=%r", channel_name or "DM", agent, text[:60])
    log_conversation(agent, user_id, "USER →", text)

    p = get_persona(agent)
    ack = await post_as_agent(client, channel_id, agent, f"_{p['display_name']} 처리 중..._")

    async def drop_ack():
        """'처리 중' 말풍선을 지운다. 실패해도 반드시 지워야 한다 —
        답 없이 남은 '처리 중'이 딱 멈춘 것처럼 보인다."""
        if not ack:
            return
        try:
            await client.chat_delete(channel=channel_id, ts=ack["ts"])
        except Exception as e:
            log.warning("'처리 중' 삭제 실패: %s", e)

    try:
        reply = await invoke_agent(
            agent=agent, user_message=text,
            workspace=WORKSPACE, cli_path=CLAUDE_CLI,
            speaker_name=OWNER_NAME,
        ) or "(빈 응답)"
        bubbles = split_reply(reply) or [(None, "(빈 응답)")]
        await drop_ack()
        for who, body in bubbles:
            await post_as_agent(client, channel_id, who or agent, body[:3800])
            await asyncio.sleep(0.4)  # 대화처럼 보이게
        log_conversation(agent, "bot", f"{agent} ←", reply)
    except Exception as e:
        # 넓게 잡는다: 여기서 예외가 새면 슬랙에는 '처리 중'만 남고 끝난다.
        log.exception("직원 호출 실패 (%s): %s", type(e).__name__, e)
        await drop_ack()
        try:
            await post_as_agent(client, channel_id, agent, explain_failure(e))
        except Exception as post_err:
            log.error("오류 안내조차 못 올렸습니다: %s", post_err)
        log_conversation(agent, "bot", "ERROR", f"{type(e).__name__}: {e}")


@app.event("app_mention")
async def on_mention(event, client, say):
    """@봇 으로 부른 것도 일반 메시지처럼 처리한다."""
    event = dict(event)
    event["channel_type"] = event.get("channel_type", "channel")
    await on_message(event, client, say)


async def check_tokens() -> str:
    """열쇠가 맞는지 먼저 확인한다.

    이걸 안 하면 "준비 완료"를 찍어놓고 곧바로 빨간 오류가 수십 줄 쏟아진다.
    수강생이 가장 당황하는 지점이라, 연결 전에 확인해서 한 줄로 알려준다.
    """
    try:
        me = await app.client.auth_test()
        return me.get("team") or "내 워크스페이스"
    except Exception as e:
        detail = str(e)
        print()
        if "invalid_auth" in detail or "not_authed" in detail:
            print("  ❌ 슬랙 열쇠(SLACK_BOT_TOKEN)가 틀렸습니다.")
            print()
            print("     .env 를 열어서 확인해 보세요:")
            print("       · xoxb- 로 시작하나요?  (xapp- 을 여기 넣은 경우가 많습니다)")
            print("       · 앞뒤에 따옴표나 공백이 섞이지 않았나요?")
            print("       · 줄바꿈 없이 한 줄로 붙어 있나요?")
        else:
            print("  ❌ 슬랙에 연결하지 못했습니다.")
            print(f"     {detail[:200]}")
            print()
            print("     인터넷 연결과 .env 의 열쇠 2개를 확인해 주세요.")
        print()
        sys.exit(1)


async def resolve_owner_name() -> None:
    """대표 이름. facts.md 에 없으면 슬랙 프로필에서 가져와 본다 (users:read 권한이 있을 때만)."""
    global OWNER_NAME, OWNER_NAME_SRC
    if OWNER_NAME:
        return
    try:
        info = await app.client.users_info(user=OWNER_USER_ID)
        u = info.get("user") or {}
        name = (u.get("real_name") or (u.get("profile") or {}).get("display_name") or "").strip()
        if name:
            OWNER_NAME, OWNER_NAME_SRC = name[:20], "슬랙 프로필"
    except Exception as e:
        log.info("슬랙 프로필에서 이름을 못 읽었습니다(%s) — facts.md 의 '이름:' 줄을 채우면 됩니다",
                 type(e).__name__)


async def main():
    roster = ", ".join(f"{PERSONAS[k]['display_name']}({k})" if k in PERSONAS else k for k in AGENTS) or "없음"
    log.info("직원 등록: %s", roster)
    log.info("슬랙 열쇠 확인 중...")
    team = await check_tokens()
    await resolve_owner_name()
    if OWNER_NAME:
        log.info("대표 이름: %s (출처: %s)", OWNER_NAME, OWNER_NAME_SRC)
    else:
        log.warning("⚠️  대표 이름을 모릅니다 — workspace/memory/facts.md 의 '이름:' 줄을 채우세요 (카드 P1). "
                    "그전까지는 '대표님' 으로 부릅니다")

    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    print()
    print(f"  ✅ 준비 완료 — 슬랙 '{team}' 에서 말을 걸어보세요.")
    print(f"     직원 {AGENT_COUNT}명 · 대표 {OWNER_NAME or '(이름 모름)'}")
    print("     직원을 찍어 부르려면 문장 맨 앞에 이름 — 예) 교안담당 불러서 ○○ 해줘 / @팀장 …")
    print("     이름을 잘못 기억하거나 옛 얘기를 하면 슬랙에 「새 대화」 라고 치세요.")
    print("     이 창을 닫으면 회사가 문을 닫습니다. 켜둔 채로 두세요.")
    print("     끄려면 Ctrl + C")
    print()
    try:
        await handler.start_async()
    except Exception as e:
        # 여기까지 오면 SLACK_APP_TOKEN(xapp-) 쪽 문제일 가능성이 높다.
        log.error("소켓 연결 실패: %s", e)
        print()
        print("  ❌ 연결이 끊겼습니다. SLACK_APP_TOKEN(xapp- 로 시작하는 것)을 확인해 주세요.")
        print()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  서버를 껐습니다. 다시 켜려면  py -3 server.py\n")
