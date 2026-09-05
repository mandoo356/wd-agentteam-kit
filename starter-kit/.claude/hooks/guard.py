"""guard.py — 위험한 일은 실행 전에 반드시 대표에게 묻는다. (고치지 마세요)

Claude Code 가 Bash·Edit·Write 도구를 쓰기 직전(PreToolUse)에 이 파일을 부른다.
여기서 "ask" 를 돌려주면 확인 창이 뜨고, 대표가 허락해야만 실행된다.
`bypassPermissions` 모드(슬랙 서버)에서도 이 훅의 판정은 그대로 먹는다.

묻는 것 (ask)
  · 파일·폴더 삭제        rm / del / erase / rmdir / rd / Remove-Item, 파이썬 os.remove·shutil.rmtree 등
  · 되돌리기·되감기       git checkout / restore / reset / clean / rm / stash / push
  · 이미 있는 파일 덮어쓰기   Write 로 기존 파일을 통째로 다시 쓸 때 (workspace/기록·inbox 는 예외)
  · 보호 구역 수정        .claude/(직원·스킬) · workspace/memory/(팀 규약) · slack-server/.env · office/company.config.ts
막는 것 (deny)
  · 채점표 점검.py 와 이 안전장치(.claude/settings.json, .claude/hooks/) 수정
  · 디스크 포맷류 명령

슬랙에서 부른 작업(WD_CHANNEL=slack)은 확인 창을 띄울 사람이 없으므로 "ask" 대신 "deny" 로 막고,
직원이 "노트북 터미널에서 해 달라"고 대표에게 답하게 한다.
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 규칙 ──────────────────────────────────────────────────────────────
DELETE_CMD = re.compile(
    r"(?:^|[\s;&|(])(?:rm|del|erase|rmdir|rd)\s+"
    r"|(?:^|[\s;&|(])Remove-Item\b"
    r"|\bos\.(?:remove|unlink|rmdir)\s*\("
    r"|\bshutil\.rmtree\s*\("
    r"|\bPath\([^)]*\)\.(?:unlink|rmdir)\s*\("
    r"|\.(?:unlink|rmdir)\(\s*\)",
    re.IGNORECASE,
)
GIT_RISKY = re.compile(
    r"\bgit\s+(?:checkout|restore|reset|clean|rm|stash|push|branch\s+-[dD]|filter-branch)\b",
    re.IGNORECASE,
)
TRUNCATE = re.compile(r"(?<![>\d])>\s*(?!\s*(?:&|nul\b|/dev/null))\S", re.IGNORECASE)  # 파일 비우기(덮어쓰기)
FORBIDDEN_CMD = re.compile(
    r"(?:^|[\s;&|(])(?:format\s+[a-z]:|diskpart|Format-Volume|Clear-Disk|Initialize-Disk|bcdedit|reg\s+delete\s+HKLM)",
    re.IGNORECASE,
)

PROTECTED_DIRS = (".claude/", "workspace/memory/")
PROTECTED_FILES = ("slack-server/.env", "office/company.config.ts", "office/company.config.js", ".gitignore")
LOCKED_FILES = ("점검.py", ".claude/settings.json")
LOCKED_DIRS = (".claude/hooks/",)
OVERWRITE_OK_DIRS = ("workspace/기록/", "workspace/inbox/")   # 이어 쓰는 곳은 덮어쓰기라도 묻지 않음


def read_input():
    # Claude Code 는 UTF-8 JSON 을 보낸다. 한국어 윈도우 콘솔(cp949) 기본값으로 읽으면 한글 경로가 깨진다.
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def find_root(data):
    for cand in (os.environ.get("CLAUDE_PROJECT_DIR"), data.get("cwd")):
        if cand and (Path(cand) / ".claude").is_dir():
            return Path(cand)
    return Path(__file__).resolve().parents[2]


def rel(root, path):
    try:
        p = Path(path)
        if not p.is_absolute():
            p = root / p
        return str(p.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def log(root, line):
    try:
        d = root / "workspace" / "기록"
        d.mkdir(parents=True, exist_ok=True)
        with (d / f"작업기록_{datetime.now():%Y-%m-%d}.md").open("a", encoding="utf-8") as f:
            f.write(f"- {datetime.now():%H:%M:%S} {line}\n")
    except Exception:
        pass


def judge(data, root):
    """(결정, 이유) — 결정은 'allow' | 'ask' | 'deny'."""
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}

    if tool == "Bash":
        cmd = str(inp.get("command", ""))
        if FORBIDDEN_CMD.search(cmd):
            return "deny", "디스크·시스템을 건드리는 명령은 이 스타터킷에서 실행하지 않습니다."
        if DELETE_CMD.search(cmd):
            return "ask", "파일이나 폴더를 지우는 명령입니다. 무엇을 지우는지 대표에게 확인받고 진행하세요."
        if GIT_RISKY.search(cmd):
            return "ask", "작업을 되돌리거나 지우는 git 명령입니다. 지금까지 한 일이 사라질 수 있으니 대표에게 확인받고 진행하세요."
        if TRUNCATE.search(cmd) and ">>" not in cmd:
            return "ask", "> 로 파일을 덮어쓰는 명령입니다. 기존 내용이 사라지니 대표에게 확인받고 진행하세요."
        return "allow", ""

    if tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        r = rel(root, path)
        if r in LOCKED_FILES or any(r.startswith(d) for d in LOCKED_DIRS):
            return "deny", f"{r} 는 채점표·안전장치입니다. 수강생이 고치는 파일이 아닙니다."
        if any(r.startswith(d) for d in PROTECTED_DIRS) or r in PROTECTED_FILES:
            what = {"Write": "덮어쓰기", "Edit": "수정", "MultiEdit": "수정", "NotebookEdit": "수정"}[tool]
            if tool == "Write" and not (root / r).exists():
                return "allow", ""   # 보호 구역이라도 새 파일 만들기는 허용 (직원 뽑기·규약 처음 쓰기)
            return "ask", f"{r} 는 직원·스킬·팀 규약·설정 파일입니다. {what} 전에 대표에게 확인받으세요."
        if tool == "Write":
            target = root / r
            if target.exists() and not any(r.startswith(d) for d in OVERWRITE_OK_DIRS):
                return "ask", f"{r} 는 이미 있는 파일입니다. 통째로 덮어쓰면 기존 내용이 사라집니다. 대표에게 확인받으세요."
        return "allow", ""

    return "allow", ""


def main():
    data = read_input()
    root = find_root(data)
    decision, reason = judge(data, root)
    if decision == "allow":
        return 0

    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    target = inp.get("command") or inp.get("file_path") or inp.get("notebook_path") or ""
    target = " ".join(str(target).split())[:140]
    slack = os.environ.get("WD_CHANNEL", "").strip().lower() == "slack"

    if decision == "ask" and slack:
        decision = "deny"
        reason = ("[슬랙에서는 실행 불가] " + reason +
                  " 슬랙에서는 확인 창을 띄울 수 없어 이 작업을 막았습니다. "
                  "대표에게 '이 작업은 파일을 지우거나 덮어쓰기 때문에 노트북 터미널에서 진행해 주세요'라고 답하세요. "
                  "다른 방법으로 우회해서 실행하지 마세요.")

    tag = {"ask": "🛡️ 확인 요청", "deny": "⛔ 차단"}[decision]
    log(root, f"{tag} [{tool}] {target}  — {reason}")
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # 안전장치 자체가 고장 나도 직원의 일은 막지 않는다
