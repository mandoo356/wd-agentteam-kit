"""test_join_request.py — "채널에 들어가" 판별기가 업무 지시를 가로채지 않는지 본다.

    py -3 test_join_request.py

server.py 를 통째로 import 하면 슬랙에 붙으려 하므로, 판별기 부분만 떼어내 시험한다.
2026-09-15 신설 — 이 판별기가 너무 헐거우면 "초대장 만들어줘" 같은 평범한 지시를
채널 입장 요청으로 잘못 읽고 일을 안 한다. 그 사고를 막는 게 이 파일의 목적이다.
"""
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SRC = (Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
_ns = {"re": re}
exec(SRC[SRC.index("JOIN_WORDS = ("):SRC.index("async def list_channels")], _ns)
is_join_request = _ns["is_join_request"]

SHOULD_JOIN = {
    "#소셜 채널에 들어가": "소셜",
    "소셜 채널에 들어가줘": "소셜",
    "#codex-전체 들어가": "codex-전체",
    "#새-채널 에 입장해": "새-채널",
    "제안서 채널에 조인해줘": "제안서",
}
SHOULD_ASK = ["채널에 너가 초대해줘", "채널에 들어가", "채널 들어가줘"]
SHOULD_IGNORE = [
    "제안서 만들어줘",
    "초대장 시안 만들어줘",
    "교육 채널에 쓸 자료 만들어줘",
    "워크숍 참여 인원 정리해줘",
    "이 채널 규칙을 문서로 정리해줘",
    "고객사에 보낼 초대장 문구 다듬어줘",
    "다음 주 강의 일정 캘린더에 넣어줘",
    "블로그 원고에 들어가야 할 항목 알려줘",
    "이 파일 읽고 요약해줘",
]

def main() -> int:
    bad = 0
    for text, want in SHOULD_JOIN.items():
        got = is_join_request(text)
        ok = got == want
        bad += not ok
        print(f"{'OK' if ok else 'NG'} 입장   {text!r} -> {got!r}")
    for text in SHOULD_ASK:
        got = is_join_request(text)
        ok = got == "?"
        bad += not ok
        print(f"{'OK' if ok else 'NG'} 되물음 {text!r} -> {got!r}")
    for text in SHOULD_IGNORE:
        got = is_join_request(text)
        ok = got == ""
        bad += not ok
        print(f"{'OK' if ok else 'NG'} 통과   {text!r} -> {got!r}")
    print("전부 통과" if not bad else f"실패 {bad}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
