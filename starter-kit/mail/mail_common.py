"""mail_common.py — 메일 세 스크립트가 같이 쓰는 바닥. (엔진 — 고칠 일 없음)

mail_check.py / mail_read.py / mail_send.py 가 여기서 가져다 쓴다.

  load_config()          mail/.env → slack-server/.env 순으로 MAIL_* 값을 읽는다
  connect_imap(cfg)      받은편지함에 붙는다 (IMAP4_SSL 993 + 앱 비밀번호)
  connect_smtp(cfg)      보내는 서버에 붙는다 (SMTP_SSL 465 + 앱 비밀번호)
  decode_str("=?utf-8?..")  깨진 제목·보낸 사람을 사람이 읽는 글자로
  extract_body(msg)      본문 — text/plain 먼저, 없으면 html 에서 태그를 걷어낸다
  MailError / die(e)     오류는 "[mail] 원인 → 해결" 한 줄로 stderr 에 내고 종료 코드 1

🔒 원칙 — 비밀번호(MAIL_APP_PASSWORD)는 어디에도 찍지 않는다. print·로그·오류 메시지·JSON 전부.
   오류가 나도 "비밀번호가 틀렸다"까지만 말하고 값은 절대 보여주지 않는다.

2026-09-08 신설. 참고한 것 — 대표 자비스의 naver/daum 메일 리더·발송기(같은 인증 방식, 같은 본문 추출).
"""
from __future__ import annotations

import email
import html as _html
import imaplib
import os
import re
import smtplib
import socket
import ssl
import sys
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path

# 윈도우 콘솔이 cp949 라서 ✅·📌 같은 글자에서 죽는 것을 막는다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent          # 스타터킷/mail
KIT_ROOT = HERE.parent                          # 스타터킷
ENV_FILES = [HERE / ".env", KIT_ROOT / "slack-server" / ".env"]   # 앞이 우선

# ── 제공자 표 ──────────────────────────────────────────────────
# 셋 다 IMAP 993(SSL) / SMTP 465(SSL). 앱 비밀번호로 로그인한다.
PROVIDERS = {
    "naver": {"label": "네이버", "imap": ("imap.naver.com", 993), "smtp": ("smtp.naver.com", 465),
              "imap_hint": "네이버 메일 → 환경설정 → POP3/IMAP 설정 → IMAP 사용 켜기",
              "pw_hint": "네이버 계정 → 보안 → 2단계 인증 → 애플리케이션 비밀번호"},
    "daum": {"label": "다음", "imap": ("imap.daum.net", 993), "smtp": ("smtp.daum.net", 465),
             "imap_hint": "Daum 메일 → 설정 → IMAP/SMTP 사용 켜기",
             "pw_hint": "카카오계정 → 2단계 인증 → 앱 비밀번호"},
    "gmail": {"label": "지메일", "imap": ("imap.gmail.com", 993), "smtp": ("smtp.gmail.com", 465),
              "imap_hint": "지메일은 IMAP 이 기본으로 켜져 있습니다 (설정 → 전달 및 POP/IMAP 확인)",
              "pw_hint": "구글 계정 → 보안 → 2단계 인증 → 앱 비밀번호"},
}

# 강의 문의로 볼 낱말 — 제목·본문에 하나라도 있으면 📌문의
INQUIRY_WORDS = ("강의", "교육", "특강", "워크숍", "연수", "제안", "견적", "강사")

TIMEOUT = 30   # 초. 네트워크가 막혀 있으면 이 시간 뒤에 "네트워크" 오류로 끝난다.


# ── 오류 ──────────────────────────────────────────────────────
class MailError(Exception):
    """사람에게 보여줄 한국어 한 줄. reason(무엇이 잘못됐나) + fix(어떻게 하나)."""

    def __init__(self, reason: str, fix: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.fix = fix

    def line(self) -> str:
        return f"{self.reason} → {self.fix}" if self.fix else self.reason


def die(e: MailError | str, code: int = 1) -> None:
    """`[mail] 원인 → 해결` 을 stderr 에 한 줄 내고 끝낸다."""
    msg = e.line() if isinstance(e, MailError) else str(e)
    print(f"[mail] {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ── 한국어 --help ──────────────────────────────────────────────
# argparse 의 'usage:' 'options:' 'show this help message' 와 오류 문구는 영어가 기본이다.
# 비개발자가 보는 화면이므로 셋 다 한국어로 바꾼다.
import argparse   # noqa: E402  (위쪽 import 묶음과 떨어져 있어도 의도한 것)

_ARG_MSGS = (
    ("the following arguments are required:", "꼭 필요한 인자가 빠졌습니다:"),
    ("one of the arguments", "다음 중 하나는 있어야 합니다:"),
    ("is required", ""),
    ("unrecognized arguments:", "모르는 인자입니다:"),
    ("expected one argument", "값이 하나 필요합니다"),
    ("invalid int value:", "숫자가 아닙니다:"),
    ("not allowed with argument", "와(과) 같이 쓸 수 없습니다:"),
    ("argument ", "인자 "),
)


class _KoFormatter(argparse.HelpFormatter):
    def _format_usage(self, usage, actions, groups, prefix):
        return super()._format_usage(usage, actions, groups, "사용법: " if prefix is None else prefix)


class KoArgumentParser(argparse.ArgumentParser):
    """도움말·오류가 한국어로 나오는 ArgumentParser."""

    def __init__(self, *a, **k):
        k.setdefault("add_help", False)
        k.setdefault("formatter_class", _KoFormatter)
        super().__init__(*a, **k)
        self.add_argument("-h", "--help", action="help", help="이 도움말을 보여주고 끝냅니다")
        self._optionals.title = "옵션"
        self._positionals.title = "인자"

    def error(self, message: str) -> None:
        for en, ko in _ARG_MSGS:
            message = message.replace(en, ko)
        message = re.sub(r"\s{2,}", " ", message).strip()
        self.print_usage(sys.stderr)
        self.exit(2, f"[mail] 인자 오류: {message}\n")


# ── .env ──────────────────────────────────────────────────────
def _parse_env_file(path: Path) -> dict[str, str]:
    """python-dotenv 가 있으면 그걸로, 없으면 직접 읽는다.
    utf-8-sig 로 읽는 이유: 메모장으로 저장한 .env 는 맨 앞에 안 보이는 표식(BOM)이 붙어서
    첫 줄 키 이름이 깨진 채로 잡힌다."""
    try:
        from dotenv import dotenv_values   # type: ignore
        vals = dotenv_values(path, encoding="utf-8-sig")
        return {k: (v or "") for k, v in vals.items() if k}
    except ImportError:
        pass
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":   # 따옴표로 감싼 값
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def load_env() -> tuple[dict[str, str], str]:
    """(값 묶음, 출처). mail/.env 가 있으면 그것, 없으면 slack-server/.env.
    둘 다 없으면 ({}, ''). 이미 떠 있는 환경변수(MAIL_*)가 있으면 그것이 파일보다 앞선다."""
    vals: dict[str, str] = {}
    source = ""
    for p in ENV_FILES:
        if p.is_file():
            vals = _parse_env_file(p)
            source = str(p)
            break
    for k in ("MAIL_PROVIDER", "MAIL_USER", "MAIL_APP_PASSWORD", "MAIL_ALLOW_EXTERNAL"):
        if os.environ.get(k):
            vals[k] = os.environ[k]
            source = source or "환경변수"
    return vals, source


class MailConfig:
    """provider / user / app_password / allow_external. 🔒 repr 에도 비밀번호는 안 나온다."""

    def __init__(self, provider: str, user: str, app_password: str, allow_external: bool, source: str):
        self.provider = provider
        self.user = user
        self.app_password = app_password
        self.allow_external = allow_external
        self.source = source

    @property
    def spec(self) -> dict:
        return PROVIDERS[self.provider]

    @property
    def label(self) -> str:
        return self.spec["label"]

    def __repr__(self) -> str:
        return f"MailConfig(provider={self.provider!r}, user={self.user!r}, allow_external={self.allow_external})"


def load_config() -> MailConfig:
    """MAIL_* 네 값을 읽어 확인한다. 하나라도 빠지면 MailError."""
    vals, source = load_env()
    if not vals or not any(k.startswith("MAIL_") for k in vals):
        raise MailError(
            "mail/.env 가 없습니다",
            "mail/.env.example 을 복사해 .env 로 만들고 MAIL_PROVIDER · MAIL_USER · MAIL_APP_PASSWORD 를 채우세요")

    provider = (vals.get("MAIL_PROVIDER") or "").strip().lower()
    user = (vals.get("MAIL_USER") or "").strip()
    pw = (vals.get("MAIL_APP_PASSWORD") or "").strip()
    allow = (vals.get("MAIL_ALLOW_EXTERNAL") or "0").strip()

    if provider not in PROVIDERS:
        raise MailError(
            f"MAIL_PROVIDER 값이 '{provider or '(비어 있음)'}' 입니다",
            "naver / daum / gmail 중 하나로 적으세요")
    if not user or "@" not in user or user.startswith("아이디@"):
        raise MailError(
            "MAIL_USER 가 비어 있거나 메일 주소 모양이 아닙니다",
            "hong@naver.com 처럼 @ 가 들어간 전체 주소를 적으세요")
    if not pw:
        raise MailError(
            "MAIL_APP_PASSWORD 가 비어 있습니다",
            f"{PROVIDERS[provider]['pw_hint']} 에서 발급받아 붙여넣으세요 (평소 로그인 비밀번호가 아닙니다)")
    if " " in pw:
        # 구글 앱 비밀번호는 'abcd efgh ijkl mnop' 처럼 띄어서 보여준다. 붙여 쓰는 게 맞다.
        pw = pw.replace(" ", "")
    return MailConfig(provider, user, pw, allow == "1", source)


# ── 접속 ──────────────────────────────────────────────────────
def _login_ids(cfg: MailConfig) -> list[str]:
    """로그인 아이디 후보. 네이버는 '아이디' 와 '아이디@naver.com' 둘 다 받는 경우가 있어
    전체 주소로 먼저, 안 되면 @ 앞부분으로 한 번 더 시도한다."""
    ids = [cfg.user]
    if cfg.provider == "naver":
        ids.append(cfg.user.split("@", 1)[0])
    return ids


def _net_error(e: Exception, host: str) -> MailError:
    return MailError(
        f"{host} 에 연결하지 못했습니다 ({type(e).__name__})",
        "인터넷 연결·회사 방화벽·VPN 을 확인하세요. 강의장 와이파이는 993/465 포트를 막기도 합니다")


def connect_imap(cfg: MailConfig) -> imaplib.IMAP4_SSL:
    """받은편지함 서버에 로그인해서 돌려준다. 실패하면 MailError (비밀번호는 절대 안 찍힘)."""
    host, port = cfg.spec["imap"]
    try:
        M = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT)
    except (socket.gaierror, socket.timeout, TimeoutError, ConnectionError, OSError, ssl.SSLError) as e:
        raise _net_error(e, host)

    last = ""
    for uid in _login_ids(cfg):
        try:
            M.login(uid, cfg.app_password)
            return M
        except imaplib.IMAP4.error as e:
            last = str(e)
            continue
    try:
        M.logout()
    except Exception:
        pass
    raise _auth_error(cfg, last, "IMAP")


def connect_smtp(cfg: MailConfig) -> smtplib.SMTP_SSL:
    """보내는 서버에 로그인해서 돌려준다. 실패하면 MailError."""
    host, port = cfg.spec["smtp"]
    try:
        S = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=TIMEOUT)
    except (socket.gaierror, socket.timeout, TimeoutError, ConnectionError, OSError, ssl.SSLError) as e:
        raise _net_error(e, host)

    last = ""
    for uid in _login_ids(cfg):
        try:
            S.login(uid, cfg.app_password)
            return S
        except smtplib.SMTPAuthenticationError as e:
            last = str(e)
            continue
        except smtplib.SMTPException as e:
            last = str(e)
            break
    try:
        S.quit()
    except Exception:
        pass
    raise _auth_error(cfg, last, "SMTP")


def _auth_error(cfg: MailConfig, server_msg: str, which: str) -> MailError:
    """서버가 뱉은 영어 한 줄을 보고 세 가지 중 하나로 번역한다.
    ① IMAP/SMTP 사용을 안 켬 ② 앱 비밀번호 틀림(또는 로그인 비밀번호를 넣음) ③ 그 밖."""
    m = server_msg.lower()
    if which == "IMAP" and any(w in m for w in ("not enabled", "disabled", "imap", "not allowed", "unavailable")):
        return MailError(
            f"{cfg.label} IMAP 사용이 꺼져 있는 것 같습니다",
            cfg.spec["imap_hint"])
    if which == "SMTP" and any(w in m for w in ("not enabled", "disabled", "smtp")) and "auth" not in m:
        return MailError(
            f"{cfg.label} SMTP 사용이 꺼져 있는 것 같습니다",
            cfg.spec["imap_hint"])
    return MailError(
        f"{cfg.label} {which} 로그인 실패 — 앱 비밀번호가 틀렸거나 평소 로그인 비밀번호를 넣은 것 같습니다",
        f"{cfg.spec['pw_hint']} 에서 새로 발급받아 mail/.env 의 MAIL_APP_PASSWORD 에 붙여넣으세요"
        f" (아이디는 {cfg.user} 가 맞는지도 확인)")


# ── 글자·본문 ──────────────────────────────────────────────────
def decode_str(s) -> str:
    """'=?utf-8?B?...?=' 로 뭉개진 제목·보낸 사람을 사람이 읽는 글자로."""
    if not s:
        return ""
    try:
        return str(make_header(decode_header(str(s)))).strip()
    except Exception:
        return str(s).strip()


def _part_text(part: Message) -> str:
    raw = part.get_payload(decode=True)
    if raw is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:            # 서버가 이상한 문자셋 이름을 준 경우
        return raw.decode("utf-8", errors="replace")


_HTML_DROP = re.compile(r"<(script|style|head)[^>]*>.*?</\1>", re.S | re.I)
_HTML_TAG = re.compile(r"<[^>]+>")


def html_to_text(raw: str) -> str:
    """태그를 걷어내고 &nbsp; 같은 것을 글자로 되돌린다."""
    t = _HTML_DROP.sub(" ", raw)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", t, flags=re.I)
    t = _HTML_TAG.sub(" ", t)
    t = _html.unescape(t).replace("\xa0", " ")    # &nbsp; → 보통 공백
    return t


def extract_body(msg: Message) -> str:
    """본문 글자. text/plain 을 먼저 찾고, 없으면 text/html 을 글자로 바꾼다. 첨부는 건너뛴다."""
    plain, htmls = "", ""
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart():
            continue
        disp = str(part.get("Content-Disposition") or "")
        if "attachment" in disp.lower():
            continue
        ctype = part.get_content_type()
        try:
            if ctype == "text/plain" and not plain:
                plain = _part_text(part)
            elif ctype == "text/html" and not htmls:
                htmls = _part_text(part)
        except Exception:
            continue
    text = plain or html_to_text(htmls)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def snippet(text: str, limit: int = 400) -> str:
    """본문 앞 limit 글자를 한 줄로."""
    t = re.sub(r"\s+", " ", text or "").strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def looks_like_inquiry(subject: str, body: str) -> bool:
    """제목·본문에 강의 문의 낱말이 하나라도 있으면 True."""
    hay = f"{subject}\n{body}"
    return any(w in hay for w in INQUIRY_WORDS)


def parse_message(raw: bytes) -> Message:
    return email.message_from_bytes(raw)
