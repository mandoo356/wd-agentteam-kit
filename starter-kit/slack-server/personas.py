"""직원들의 슬랙 표시 이름·아이콘·인사말.

🎨 여기는 마음껏 고치셔도 됩니다. 고장 안 납니다.

  display_name  슬랙에 뜨는 이름 — 직원이 답할 때 "팀장: …" 처럼 이 이름을 쓰면 그 직원 말풍선이 됩니다
  icon_emoji    슬랙에 뜨는 아이콘. ":page_facing_up:" 도 되고 그냥 "📄" 를 넣어도 됩니다 (서버가 바꿔 줍니다)
  intro         "팀 소개" 라고 하면 하는 인사 — [무엇] 같은 대괄호 빈칸을 꼭 내 말로 채우세요.
                빈칸이 남아 있으면 서버가 직원 파일의 description 으로 대신 인사합니다 (캐릭터가 밋밋해집니다)
  intro_class   "애들아 인사" 라고 하면 하는 인사 (남들 앞에서 보여줄 때)

🚨 딱 하나만: 왼쪽의 staff1, staff2 같은 <영어 키>는 바꾸지 마세요.
   .claude/agents/ 의 파일 이름과 짝이라서, 바꾸면 연결이 끊깁니다.
   바꿔도 되는 건 display_name 과 icon_emoji, 그리고 인사말입니다.

고친 뒤에는 서버를 껐다 켜야 반영됩니다. (검은 창에서 Ctrl+C → 다시 실행)
"""

PERSONAS = {
    "staff1": {
        "display_name": "직원1",
        "icon_emoji": ":page_facing_up:",
        "intro": "📄 직원1입니다. 제 담당은 [무엇]이에요. 필요하실 때 불러주세요.",
        "intro_class": (
            "📄 여러분 안녕하세요! [무슨 일] 담당 *직원1*입니다.\n"
            "저는 사람이 아니라 AI 직원인데요, [재밌는 한마디]"
        ),
    },
    "staff2": {
        "display_name": "직원2",
        "icon_emoji": ":mortar_board:",
        "intro": "🎓 직원2입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "🎓 안녕하세요, [무슨 일] 담당 *직원2*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff3": {
        "display_name": "직원3",
        "icon_emoji": ":books:",
        "intro": "📚 직원3입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "📚 반갑습니다, [무슨 일] 담당 *직원3*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff4": {
        "display_name": "직원4",
        "icon_emoji": ":lower_left_ballpoint_pen:",
        "intro": "✍️ 직원4입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "✍️ 안녕하세요! [무슨 일] 담당 *직원4*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff5": {
        "display_name": "직원5",
        "icon_emoji": ":moneybag:",
        "intro": "💰 직원5입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "💰 [무슨 일] 담당 *직원5*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff6": {
        "display_name": "직원6",
        "icon_emoji": ":bust_in_silhouette:",
        "intro": "🪪 직원6입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "🪪 안녕하세요, [무슨 일] 담당 *직원6*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff7": {
        "display_name": "직원7",
        "icon_emoji": ":calendar:",
        "intro": "📅 직원7입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "📅 반갑습니다, [무슨 일] 담당 *직원7*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
    "staff8": {
        "display_name": "직원8",
        "icon_emoji": ":art:",
        "intro": "🎨 직원8입니다. 제 담당은 [무엇]이에요.",
        "intro_class": (
            "🎨 안녕하세요! [무슨 일] 담당 *직원8*입니다.\n"
            "[재밌는 한마디]"
        ),
    },
}

# "팀 소개" 할 때 인사하는 순서
INTRO_ORDER = ["staff1", "staff2", "staff3", "staff4", "staff5", "staff6", "staff7", "staff8"]

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
