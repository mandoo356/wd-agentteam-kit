"""직원들의 슬랙 표시 이름·아이콘·인사말.

🎨 여기는 마음껏 고치셔도 됩니다. 고장 안 납니다.

  display_name  슬랙에 뜨는 이름 — 직원이 답할 때 "팀장: …" 처럼 이 이름을 쓰면 그 직원 말풍선이 됩니다
  icon_emoji    슬랙에 뜨는 아이콘. ":page_facing_up:" 도 되고 그냥 "📄" 를 넣어도 됩니다 (서버가 바꿔 줍니다)
  intro         "팀 소개" 라고 하면 하는 인사 — [무엇] 같은 대괄호 빈칸을 꼭 내 말로 채우세요.
                빈칸이 남아 있으면 서버가 직원 파일의 description 으로 대신 인사합니다 (캐릭터가 밋밋해집니다)
  intro_class   "애들아 인사" 라고 하면 하는 인사 (남들 앞에서 보여줄 때)

기본값은 직원견본 5명(팀장·교재대리·블로그대리·일정매니저·프로필대리)과 **짝이 맞춰져 있습니다**
   — 카드 P3 으로 견본을 데려오면 슬랙에 뜨는 이름과 직원 파일의 담당이 처음부터 일치합니다.
   P11 에서는 이름을 내 취향대로 바꾸고 인사말의 [빈칸]만 채우면 됩니다.

🚨 딱 하나만: 왼쪽의 staff1, staff2 같은 <영어 키>는 바꾸지 마세요.
   .claude/agents/ 의 파일 이름과 짝이라서, 바꾸면 연결이 끊깁니다.
   바꿔도 되는 건 display_name 과 icon_emoji, 그리고 인사말입니다.

➕ 6번째 직원을 데려오면(카드 P14) 아래에 "staff6": {...} 칸을 하나 더 만들고 INTRO_ORDER 에도 넣으세요.
   직원 파일이 없는 키는 명단에서 자동으로 빠지지만, 점검 4 에서 "짝이 없는 키"로 잡힙니다.

고친 뒤에는 서버를 껐다 켜야 반영됩니다. (검은 창에서 Ctrl+C → 다시 실행)
"""

PERSONAS = {
    "staff1": {
        "display_name": "팀장",
        "icon_emoji": ":page_facing_up:",
        "intro": "📄 팀장입니다. 제 담당은 [무엇]이에요. 필요하실 때 불러주세요.",
        "intro_class": (
            "📄 여러분 안녕하세요! [무슨 일] 담당 *팀장*입니다.\n"
            "저는 사람이 아니라 AI 직원인데요, [재밌는 한마디]"
        ),
    },
    "staff2": {
        "display_name": "교재대리",
        "icon_emoji": ":books:",
        "intro": "📚 교재대리입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "📚 반갑습니다, [무슨 일] 담당 *교재대리*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff3": {
        "display_name": "블로그대리",
        "icon_emoji": ":lower_left_ballpoint_pen:",
        "intro": "✍️ 블로그대리입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "✍️ 안녕하세요! [무슨 일] 담당 *블로그대리*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff4": {
        "display_name": "일정매니저",
        "icon_emoji": ":calendar:",
        "intro": "📅 일정매니저입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "📅 반갑습니다, [무슨 일] 담당 *일정매니저*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff5": {
        "display_name": "프로필대리",
        "icon_emoji": ":bust_in_silhouette:",
        "intro": "🪪 프로필대리입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "🪪 안녕하세요, [무슨 일] 담당 *프로필대리*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
}

# "팀 소개" 할 때 인사하는 순서
INTRO_ORDER = ["staff1", "staff2", "staff3", "staff4", "staff5"]

# 강의장에서 "애들아 인사" 했을 때 맨 앞뒤에 붙는 말
CLASS_OPENING = (
    "🙌 여러분 안녕하세요! [내 회사 이름]입니다.\n"
    "대표님이 부르셔서 저희 다 나왔습니다. 한 명씩 인사드릴게요!"
)
CLASS_CLOSING = (
    "🙌 이상입니다! 저희는 AI 직원이라 월급을 안 받습니다.\n"
    "오늘 잘 부탁드려요!"
)


def get_persona(agent: str) -> dict:
    return PERSONAS.get(agent, {
        "display_name": agent,
        "icon_emoji": ":robot_face:",
        "intro": "",
        "intro_class": "",
    })


def get_intro(agent: str, audience: str = "boss") -> str:
    """audience='class' 면 남들 앞에서 하는 인사. 없으면 업무용 인사로 떨어진다."""
    p = get_persona(agent)
    if audience == "class":
        return p.get("intro_class") or p.get("intro", "")
    return p.get("intro", "")
