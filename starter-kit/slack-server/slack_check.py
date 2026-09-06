"""slack_check.py — 슬랙 열쇠 3개가 실제로 통하는지 확인합니다. 값은 화면에 찍지 않습니다.

쓰는 법 (slack-server 폴더 또는 아무 데서나):
    py -3 slack_check.py

환경점검.bat 이 열쇠를 저장한 직후 자동으로 이걸 돌립니다.
서버를 켜기 전에 "봇 토큰이 틀렸다 / 앱 토큰에 connections:write 가 없다" 를 한 줄로 알려주는 게 목적입니다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

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

HERE = Path(__file__).resolve().parent
ENV = HERE / ".env"


def load_env() -> dict[str, str]:
    vals: dict[str, str] = {}
    if not ENV.is_file():
        return vals
    # utf-8-sig: 메모장이 붙이는 BOM 을 견딘다
    for line in ENV.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip().upper()] = v.strip().strip('"').strip("'")
    return vals


def main() -> int:
    vals = load_env()
    bot = vals.get("SLACK_BOT_TOKEN", "")
    app = vals.get("SLACK_APP_TOKEN", "")
    owner = vals.get("OWNER_USER_ID", "")

    if not ENV.is_file():
        print("NG .env 파일이 없습니다 — 환경점검.bat 을 실행해 열쇠 3개를 붙여넣으세요")
        return 1
    missing = [k for k, v in (("SLACK_BOT_TOKEN", bot), ("SLACK_APP_TOKEN", app), ("OWNER_USER_ID", owner)) if not v]
    if missing:
        print("NG .env 에 비어 있음: " + ", ".join(missing))
        return 1
    if not bot.startswith("xoxb-"):
        print("NG SLACK_BOT_TOKEN 은 xoxb- 로 시작해야 합니다 (xapp- 을 넣으셨다면 자리가 바뀐 것)")
        return 1
    if not app.startswith("xapp-"):
        print("NG SLACK_APP_TOKEN 은 xapp- 로 시작해야 합니다")
        return 1

    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
    except ImportError:
        print("NG slack_sdk 꾸러미가 없습니다 — py -3 -m pip install -r requirements.txt")
        return 1

    # ① 봇 토큰 — 워크스페이스 이름까지 받아온다
    try:
        me = WebClient(token=bot).auth_test()
        team = me.get("team") or "내 워크스페이스"
        print(f"OK 봇 토큰(xoxb-) 통과 — 워크스페이스 '{team}', 봇 이름 '{me.get('user', 'AI')}'")
    except SlackApiError as e:
        err = e.response.get("error", "") if getattr(e, "response", None) else str(e)
        if err in ("invalid_auth", "not_authed", "account_inactive", "token_revoked"):
            print("NG 봇 토큰(xoxb-)이 틀렸습니다 — OAuth & Permissions 에서 Bot User OAuth Token 을 다시 복사하세요")
        else:
            print(f"NG 봇 토큰 확인 실패: {err}")
        return 1
    except Exception as e:  # 인터넷·방화벽
        print(f"NG 슬랙에 연결하지 못했습니다 (인터넷·방화벽): {type(e).__name__}")
        return 1

    # ② 앱 토큰 — 소켓 모드 연결 허가를 받아 본다 (connections:write 가 없으면 여기서 걸린다)
    try:
        r = WebClient(token=app).apps_connections_open()
        if r.get("ok"):
            print("OK 앱 토큰(xapp-) 통과 — 소켓 연결 허용됨 (connections:write 있음)")
        else:
            print(f"NG 앱 토큰 확인 실패: {r.get('error', '')}")
            return 1
    except SlackApiError as e:
        err = e.response.get("error", "") if getattr(e, "response", None) else str(e)
        if err in ("invalid_auth", "not_authed"):
            print("NG 앱 토큰(xapp-)이 틀렸습니다 — Basic Information → App-Level Tokens 에서 새로 하나 더 만드세요")
        elif err in ("missing_scope", "not_allowed_token_type"):
            print("NG 앱 토큰에 connections:write 권한이 없습니다 — 새 토큰을 만들 때 Add Scope → connections:write")
        else:
            print(f"NG 앱 토큰 확인 실패: {err}")
        return 1
    except Exception as e:
        print(f"NG 슬랙에 연결하지 못했습니다: {type(e).__name__}")
        return 1

    # ③ 멤버 ID — 모양만 본다 (users:read 권한이 없어 조회는 하지 않는다)
    if owner[:1].upper() in ("U", "W") and len(owner) >= 9 and owner.isalnum():
        print(f"OK 멤버 ID 모양 정상 ({owner[:2]}… {len(owner)}자)")
    else:
        print("NG OWNER_USER_ID 가 U 로 시작하는 멤버 ID 가 아닙니다")
        return 1

    print(f"OK 슬랙 열쇠 3개 전부 통과 — '{team}' 에서 서버를 켤 수 있습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
