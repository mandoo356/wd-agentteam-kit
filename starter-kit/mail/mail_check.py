"""mail_check.py — 메일 연동이 되는지 로그인만 해 본다. (읽지도 보내지도 않는다)

  py -3.14 mail\\mail_check.py

  잘 되면   OK: naver hong@naver.com IMAP ✅ SMTP ✅            (종료 코드 0)
  안 되면   FAIL: naver hong@naver.com IMAP ❌ 원인 → 해결      (종료 코드 1)

한 줄만 낸다 — 환경점검(PowerShell)이 이 줄을 그대로 화면에 보여준다.
🔒 비밀번호는 어디에도 찍지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail_common import KoArgumentParser, MailError, connect_imap, connect_smtp, load_config   # noqa: E402


def main() -> int:
    ap = KoArgumentParser(
        prog="mail_check.py",
        description="메일 서버에 로그인만 해 봅니다 (IMAP 받기 + SMTP 보내기). 메일을 읽거나 보내지는 않습니다.",
        epilog="결과는 한 줄: OK: … IMAP ✅ SMTP ✅  또는  FAIL: … ❌ 원인 → 해결")
    ap.parse_args()

    try:
        cfg = load_config()
    except MailError as e:
        print(f"FAIL: ❌ {e.line()}")
        return 1

    head = f"{cfg.provider} {cfg.user}"

    # IMAP (받기)
    try:
        M = connect_imap(cfg)
        try:
            M.logout()
        except Exception:
            pass
    except MailError as e:
        print(f"FAIL: {head} IMAP ❌ {e.line()}")
        return 1

    # SMTP (보내기)
    try:
        S = connect_smtp(cfg)
        try:
            S.quit()
        except Exception:
            pass
    except MailError as e:
        print(f"FAIL: {head} IMAP ✅ SMTP ❌ {e.line()}")
        return 1

    print(f"OK: {head} IMAP ✅ SMTP ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
