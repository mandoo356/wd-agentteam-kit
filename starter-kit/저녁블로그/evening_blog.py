"""저녁 8시 자동 블로그 — 오늘 강의가 있었으면 초안을 쓰고 네이버에 임시저장한다.

윈도우 작업 스케줄러가 매일 저녁 8시에 이 파일을 부른다(카드 P20-c).

  1) 일정매니저(staff4) 가 구글 캘린더에서 "오늘 강의가 있었나" 를 본다
  2) 있으면 블로그대리(staff3) 가 초안을 쓰고, 네이버 임시저장까지 한다
  3) 결과를 슬랙으로 한 줄 알린다 (P20-b 에서 만든 Incoming Webhook 사용)

강의가 없는 날은 조용히 끝난다 — 슬랙으로 아무것도 보내지 않는다.

**발행은 하지 않는다.** 임시저장까지만 하고, 공개 버튼은 사람이 누른다.

이 파일은 바깥 라이브러리를 쓰지 않는다(파이썬만 있으면 돈다).
예약 작업은 슬랙 서버가 꺼져 있어도 따로 돌아가야 하기 때문이다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent                      # 스타터킷 폴더
WORKSPACE = KIT / "workspace"          # 직원들이 일하는 폴더
LOG = HERE / "evening_blog.log"

# ── .env 읽기 (slack-server/.env 를 그대로 쓴다) ──────────────────────────
def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (KIT / "slack-server" / ".env", HERE / ".env"):
        if not path.exists():
            continue
        # BOM 이 붙어 있어도 읽히게 utf-8-sig
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if v:
                env[k.strip()] = v
    return env


def log(msg: str) -> None:
    stamp = date.today().isoformat()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {msg}\n")
    print(msg)


# ── 슬랙 알림 ────────────────────────────────────────────────────────────
def notify(webhook: str, text: str) -> None:
    """P20-b 에서 만든 Incoming Webhook 으로 한 줄 보낸다."""
    if not webhook:
        log("SLACK_WEBHOOK_URL 이 없어 슬랙 알림은 건너뜁니다.")
        return
    body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        log("슬랙 알림 보냈습니다.")
    except Exception as e:  # 알림 실패로 전체를 죽이지 않는다
        log(f"슬랙 알림 실패: {e}")


# ── 직원 부르기 ──────────────────────────────────────────────────────────
def find_claude() -> str:
    """claude 명령어가 어디 깔렸는지 찾는다."""
    import shutil
    explicit = os.environ.get("CLAUDE_CLI")
    if explicit and Path(explicit).exists():
        return explicit
    for name in ("claude.cmd", "claude.exe", "claude"):
        found = shutil.which(name)
        if found:
            return found
    for c in (
        os.path.expandvars(r"%APPDATA%\npm\claude.cmd"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\claude\claude.exe"),
    ):
        if Path(c).exists():
            return c
    raise SystemExit(
        "claude 명령어를 찾을 수 없습니다.\n"
        "  → 검은 창에서  npm install -g @anthropic-ai/claude-code\n"
        "  → 그래도 안 되면 .env 에 CLAUDE_CLI=전체경로 를 적어주세요"
    )


def ask(cli: str, agent: str, prompt: str, timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        [
            cli, "-p",
            "--agent", agent,
            "--dangerously-skip-permissions",
            "--add-dir", str(WORKSPACE),
        ],
        input=prompt.encode("utf-8"),
        capture_output=True,
        cwd=str(WORKSPACE),
        timeout=timeout,
    )
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")[:400]
        log(f"{agent} 실패 — exit={proc.returncode} / {err}")
    return proc.returncode, out


# ── 본체 ─────────────────────────────────────────────────────────────────
def main() -> int:
    env = load_env()
    webhook = env.get("SLACK_WEBHOOK_URL", "")
    cli = find_claude()
    today = date.today().isoformat()
    log(f"시작 — 오늘 {today}")

    # 1단계 · 오늘 강의가 있었나 (일정매니저)
    check = f"""오늘({today}) 구글 캘린더를 조회해줘.

오늘 끝난 강의·교육 일정이 있으면 **아래 형식으로만** 답해. 다른 말은 붙이지 마.

LECTURE_TODAY: yes
CLIENT: <고객사>
LECTURE_NAME: <강의명>
LOCATION: <장소>
DURATION: <시간>

없으면 이 한 줄만.

LECTURE_TODAY: no

조회만 해. 등록·수정은 하지 마. 캘린더를 못 읽었으면 추측하지 말고
LECTURE_TODAY: no 로 답하고 왜 못 읽었는지 한 줄 덧붙여."""

    rc, out = ask(cli, "staff4", check, timeout=300)
    if rc != 0 or "LECTURE_TODAY: yes" not in out:
        log(f"오늘 강의 없음(또는 조회 실패) — 조용히 끝냅니다. 응답: {out[:200]}")
        return 0  # 조용한 종료. 없는 날 알림을 보내면 매일 울린다.

    info: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            info[k.strip()] = v.strip()
    client = info.get("CLIENT") or "(고객사 확인 필요)"
    lecture = info.get("LECTURE_NAME") or "(강의명 확인 필요)"
    log(f"오늘 강의 있음 — {client} / {lecture}")

    # 2단계 · 블로그 초안 + 네이버 임시저장 (블로그대리)
    blog = f"""오늘({today}) 다녀온 강의로 블로그 글을 써줘.

- 고객사: {client}
- 강의명: {lecture}
- 장소: {info.get('LOCATION', '(정보 없음)')}
- 시간: {info.get('DURATION', '(정보 없음)')}

순서대로 끝까지 해줘. 중간에 물어보지 말고:

1. 내 블로그 스킬(카드 P4-0 에서 만든 것)로 원고를 쓴다.
   저장 위치: `blog/{today}_{client}/` 안에 post.md · titles.md · hashtags.md

2. **네이버 블로그에 임시저장까지 한다.** `naver-blog/naver_draft.py` 를 쓴다.
   - 임시저장 목록에서 제목이 실제로 보이는지 확인하기 전에는 "저장했다"고 하지 마.
   - 사진은 넣지 않는다. 삽화를 만들지도 마 (이미지 0장이어도 글만 올라간다).

3. 🚫 **발행(공개) 버튼은 절대 누르지 않는다.** 임시저장까지만.

다 끝나면 슬랙에 뿌릴 짧은 알림 하나만 답해줘. 5줄 이내로:
- 어떤 강의 글을 썼는지
- 제목 후보 3개
- 임시저장이 됐는지 (됐으면 "네이버 임시저장함에 들어갔습니다")
- 비워둔 칸이 있으면 무엇인지 (참가자 반응·인원수 등)

캐릭터 인사말·서명은 빼줘. 슬랙에 이미 이름이 찍힌다."""

    rc, out = ask(cli, "staff3", blog, timeout=1800)
    if rc != 0:
        notify(webhook, f"✍️ 블로그 초안을 시도했는데 실패했어요. `저녁블로그/evening_blog.log` 를 봐주세요.")
        return 1

    notify(webhook, out or "✍️ 블로그 초안 준비됐어요.")
    log("완료")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.TimeoutExpired:
        log("시간 초과로 멈췄습니다.")
        sys.exit(2)
