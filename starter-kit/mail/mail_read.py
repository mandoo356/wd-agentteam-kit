"""mail_read.py — 받은편지함에서 최근 N통을 읽어 보여준다. (읽음 표시는 건드리지 않는다)

  py -3.14 mail\\mail_read.py                       최근 10통
  py -3.14 mail\\mail_read.py --count 20            최근 20통
  py -3.14 mail\\mail_read.py --unseen              안 읽은 것만
  py -3.14 mail\\mail_read.py --since 2026-09-01    이 날짜 이후만
  py -3.14 mail\\mail_read.py --search 특강         제목·보낸 사람·본문에 이 낱말이 있는 것만
  py -3.14 mail\\mail_read.py --json                사람용 표 대신 JSON 배열

한 통마다 번호 · 날짜 · 보낸 사람 · 제목, 그 아래 본문 앞 400자.
강의 문의로 보이는 메일(강의·교육·특강·워크숍·연수·제안·견적·강사)에는 📌문의 가 붙는다.
BODY.PEEK 로 읽어서 메일함의 "안 읽음" 상태가 그대로 남는다.
🔒 비밀번호는 어디에도 찍지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mail_common import (KoArgumentParser, MailError, connect_imap, decode_str, die, extract_body,   # noqa: E402
                         load_config, looks_like_inquiry, parse_message, snippet)

SNIPPET_LEN = 400
SEARCH_SCAN_MAX = 200     # --search 는 서버가 한글 검색을 못 해서, 최근 이만큼 안에서 직접 걸러낸다


def _since_arg(s: str) -> str:
    """'2026-09-01' → IMAP 이 알아듣는 '01-Sep-2026'."""
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError("날짜는 2026-09-01 처럼 YYYY-MM-DD 로 적으세요")
    return d.strftime("%d-%b-%Y")


def _fmt_date(raw: str) -> str:
    """메일의 Date 헤더를 '2026-09-08 10:12' 로. 못 읽으면 원문 그대로."""
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is not None:
            d = d.astimezone()
        return d.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return (raw or "")[:16]


def fetch_messages(args) -> tuple[list[dict], str]:
    """받은편지함에서 조건에 맞는 것을 최신순으로 최대 count 통. (목록, 계정 설명)"""
    cfg = load_config()
    M = connect_imap(cfg)
    try:
        typ, _ = M.select("INBOX", readonly=True)     # readonly — 읽음 표시가 절대 안 바뀐다
        if typ != "OK":
            raise MailError("받은편지함(INBOX)을 열지 못했습니다", "잠시 뒤 다시 시도하세요")

        criteria = []
        if args.unseen:
            criteria.append("UNSEEN")
        if args.since:
            criteria += ["SINCE", args.since]
        if not criteria:
            criteria = ["ALL"]
        typ, data = M.search(None, *criteria)
        if typ != "OK":
            raise MailError("메일 목록을 받지 못했습니다", "잠시 뒤 다시 시도하세요")
        ids = data[0].split()
        ids.reverse()                                  # 최신이 앞

        limit = SEARCH_SCAN_MAX if args.search else args.count
        kw = (args.search or "").strip().lower()
        out: list[dict] = []
        for i in ids[:limit]:
            typ, msg_data = M.fetch(i, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            msg = parse_message(msg_data[0][1])
            subject = decode_str(msg.get("Subject")) or "(제목 없음)"
            sender = decode_str(msg.get("From"))
            body = extract_body(msg)
            if kw and kw not in f"{subject}\n{sender}\n{body}".lower():
                continue
            out.append({
                "no": len(out) + 1,
                "date": _fmt_date(decode_str(msg.get("Date"))),
                "from": sender,
                "to": decode_str(msg.get("To")),
                "subject": subject,
                "snippet": snippet(body, SNIPPET_LEN),
                "inquiry": looks_like_inquiry(subject, body),
                "message_id": (msg.get("Message-ID") or "").strip(),
            })
            if len(out) >= args.count:
                break
        return out, f"{cfg.provider} {cfg.user}"
    finally:
        try:
            M.logout()
        except Exception:
            pass


def print_table(items: list[dict], account: str, args) -> None:
    cond = []
    if args.unseen:
        cond.append("안 읽은 것만")
    if args.since:
        cond.append(f"{args.since} 이후")
    if args.search:
        cond.append(f"'{args.search}' 검색")
    head = f"받은편지함 최근 {len(items)}통 ({account})" + (" — " + " · ".join(cond) if cond else "")
    print(head)
    print("─" * 72)
    if not items:
        print("조건에 맞는 메일이 없습니다.")
        return
    for m in items:
        tag = "  📌문의" if m["inquiry"] else ""
        print(f"{m['no']:>2} · {m['date']} · {m['from']}")
        print(f"     제목: {m['subject']}{tag}")
        if m["snippet"]:
            print(f"     {m['snippet']}")
        print()
    n_inq = sum(1 for m in items if m["inquiry"])
    if n_inq:
        print(f"📌문의 로 보이는 메일 {n_inq}통 — 강의·교육·특강·워크숍·연수·제안·견적·강사 낱말이 들어 있습니다.")


def main() -> int:
    ap = KoArgumentParser(
        prog="mail_read.py",
        description="받은편지함에서 최근 메일을 읽어 보여줍니다. 읽음 표시는 바꾸지 않습니다.",
        epilog="강의 문의로 보이는 메일에는 📌문의 가 붙습니다.")
    ap.add_argument("--count", type=int, default=10, metavar="N", help="몇 통 볼지 (기본 10)")
    ap.add_argument("--unseen", action="store_true", help="안 읽은 메일만")
    ap.add_argument("--since", type=_since_arg, metavar="YYYY-MM-DD", help="이 날짜 이후 메일만")
    ap.add_argument("--search", metavar="키워드", help="제목·보낸 사람·본문에 이 낱말이 있는 것만")
    ap.add_argument("--json", action="store_true", help="표 대신 JSON 배열로 출력")
    args = ap.parse_args()
    if args.count < 1:
        ap.error("--count 는 1 이상이어야 합니다")

    try:
        items, account = fetch_messages(args)
    except MailError as e:
        die(e)
        return 1

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        print_table(items, account, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
