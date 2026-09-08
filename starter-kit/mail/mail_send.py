"""mail_send.py — 메일을 보낸다. 단, 안전장치가 먼저다.

  py -3.14 mail\\mail_send.py --to hong@naver.com --subject "제목" --body "본문"
      → --approved 가 없으므로 보내지 않는다. 초안(미발송)을 화면에 보여주고 종료 코드 2.

  py -3.14 mail\\mail_send.py --to hong@naver.com --subject "제목" --body-file 초안.md --approved
      → 보낸다. 끝나면  SENT: hong@naver.com / 제목  한 줄.

  --cc 주소        참조 (여러 번 가능)
  --attach 파일    첨부 (여러 번 가능)

안전장치 세 겹
  ① --approved 없음            → 초안만 보여주고 끝 (종료 2). 서버에 붙지도 않는다.
  ② 받는 사람이 내가 아닌데 MAIL_ALLOW_EXTERNAL 이 1 이 아님 → 거부 (종료 3)
  ③ 그 밖의 오류(설정·첨부·로그인)  → [mail] 한 줄 (종료 1)
🔒 비밀번호는 어디에도 찍지 않는다.
"""
from __future__ import annotations

import mimetypes
import os
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail_common import KoArgumentParser, MailError, connect_smtp, die, load_config   # noqa: E402

ATTACH_LIMIT_MB = 20    # 네이버·다음·지메일 모두 첨부 25MB 근처가 한도. 그 전에 막는다.


def _addr(s: str) -> str:
    """'홍길동 <hong@naver.com>' → 'hong@naver.com' (소문자)."""
    return parseaddr(s or "")[1].strip().lower()


def build_message(sender: str, to: list[str], cc: list[str], subject: str, body: str, attach: list[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)
    for path in attach:
        ctype, _ = mimetypes.guess_type(path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(path, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(path))
    return msg


def show_draft(sender: str, to: list[str], cc: list[str], subject: str, body: str, attach: list[str]) -> None:
    print("초안(미발송) — --approved 가 없어서 보내지 않았습니다. 내용을 확인하고 \"보내\"라고 하면 그때 보냅니다.")
    print("─" * 72)
    print(f"보내는 사람: {sender}")
    print(f"받는 사람  : {', '.join(to)}")
    if cc:
        print(f"참조       : {', '.join(cc)}")
    print(f"제목       : {subject}")
    if attach:
        print("첨부       : " + ", ".join(os.path.basename(p) for p in attach))
    print("─" * 72)
    print(body.rstrip())
    print("─" * 72)


def main() -> int:
    ap = KoArgumentParser(
        prog="mail_send.py",
        description="메일을 보냅니다. --approved 가 없으면 보내지 않고 초안만 보여줍니다 (종료 코드 2).",
        epilog="내 주소가 아닌 곳으로 보내려면 mail/.env 의 MAIL_ALLOW_EXTERNAL=1 이 필요합니다 (아니면 종료 코드 3).")
    ap.add_argument("--to", action="append", default=[], metavar="주소", required=True, help="받는 사람 (여러 번 가능)")
    ap.add_argument("--subject", required=True, metavar="제목", help="제목")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--body", metavar="텍스트", help="본문 글")
    g.add_argument("--body-file", metavar="파일", help="본문이 든 파일 (UTF-8, .md/.txt)")
    ap.add_argument("--cc", action="append", default=[], metavar="주소", help="참조 (여러 번 가능)")
    ap.add_argument("--attach", action="append", default=[], metavar="파일", help="첨부 파일 (여러 번 가능)")
    ap.add_argument("--approved", action="store_true", help="실제로 보낸다. 대표가 \"보내\"라고 한 그 건에만 붙인다")
    args = ap.parse_args()

    # ── 0. 인자 정리 (서버에 붙기 전에 전부 끝낸다) ─────────────
    to = [a.strip() for a in args.to if a.strip()]
    cc = [a.strip() for a in args.cc if a.strip()]
    bad = [a for a in to + cc if "@" not in _addr(a)]
    if bad:
        die(MailError(f"받는 사람 주소 모양이 아닙니다: {', '.join(bad)}", "hong@naver.com 처럼 @ 가 들어간 주소로"))
    subject = args.subject.strip()
    if not subject:
        die(MailError("제목이 비어 있습니다", "--subject 에 제목을 넣으세요"))

    if args.body_file:
        p = Path(args.body_file)
        if not p.is_file():
            die(MailError(f"본문 파일이 없습니다: {p}", "경로를 확인하세요"))
        body = p.read_text(encoding="utf-8-sig", errors="replace")
    else:
        body = args.body or ""
    if not body.strip():
        die(MailError("본문이 비어 있습니다", "--body 또는 --body-file 에 내용을 넣으세요"))

    attach = [str(Path(a)) for a in args.attach]
    missing = [a for a in attach if not Path(a).is_file()]
    if missing:
        die(MailError(f"첨부 파일이 없습니다: {', '.join(missing)}", "경로를 확인하세요"))
    total = sum(Path(a).stat().st_size for a in attach)
    if total > ATTACH_LIMIT_MB * 1024 * 1024:
        die(MailError(f"첨부 합계 {total / 1048576:.1f}MB — {ATTACH_LIMIT_MB}MB 를 넘습니다",
                      "파일을 줄이거나 대용량 링크로 보내세요"))

    # ── 1. 설정 (.env) ─────────────────────────────────────────
    try:
        cfg = load_config()
    except MailError as e:
        die(e)
        return 1
    sender = cfg.user

    # ── 2. 승인 없음 → 초안만 보여주고 끝 (서버에 붙지 않는다) ──
    if not args.approved:
        show_draft(sender, to, cc, subject, body, attach)
        return 2

    # ── 3. 외부 발송 잠금 ──────────────────────────────────────
    me = sender.lower()
    external = [a for a in to + cc if _addr(a) != me]
    if external and not cfg.allow_external:
        print(f"[mail] 외부 주소({', '.join(external)})로는 보내지 않았습니다 — "
              "외부 발송은 mail/.env 의 MAIL_ALLOW_EXTERNAL=1 로 켠 뒤 대표가 직접 지시할 때만",
              file=sys.stderr, flush=True)
        return 3

    # ── 4. 보낸다 ──────────────────────────────────────────────
    try:
        msg = build_message(sender, to, cc, subject, body, attach)
        S = connect_smtp(cfg)
        try:
            S.send_message(msg)
        finally:
            try:
                S.quit()
            except Exception:
                pass
    except MailError as e:
        die(e)
        return 1
    except Exception as e:       # 서버가 거절한 경우 등. 비밀번호는 예외 문구에 안 들어간다.
        die(MailError(f"보내는 중 실패했습니다 ({type(e).__name__}: {str(e)[:120]})",
                      "받는 주소·첨부 크기를 확인하고 다시 시도하세요"))
        return 1

    print(f"SENT: {', '.join(to)} / {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
