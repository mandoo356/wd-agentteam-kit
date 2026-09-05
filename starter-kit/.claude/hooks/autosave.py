"""autosave.py — 직원이 한 일을 자동으로 남긴다. (고치지 마세요)

Claude Code 가 세 시점에 이 파일을 부른다 (.claude/settings.json 의 hooks).

  UserPromptSubmit  대표가 명령을 칠 때        → workspace/기록/작업기록_<날짜>.md 에 명령 원문
  PostToolUse       직원이 파일을 만들·고칠 때  → 같은 파일에 "어느 파일이 어떻게" 한 줄
  Stop              한 번 답이 끝날 때          → git add -A && git commit  (자동 저장 지점)

기록 파일은 한글로 읽을 수 있게 쓰고, 02_내작업_백업.bat 이 workspace/ 를 묶을 때 같이 들어간다.
git 저장소가 아직 없으면(모듈 0 의 git init 전) 커밋만 조용히 건너뛴다.
어떤 경우에도 이 스크립트는 직원의 일을 막지 않는다 — 실패해도 exit 0.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

MAX_PROMPT = 400     # 기록에 남기는 명령 길이
MAX_CMD = 160        # 기록에 남기는 실행 명령 길이


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


def one_line(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit] + " …"


def rel(root, path):
    try:
        return str(Path(path).resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path)


class Journal:
    def __init__(self, root):
        self.root = root
        self.dir = root / "workspace" / "기록"
        self.now = datetime.now()
        self.path = self.dir / f"작업기록_{self.now:%Y-%m-%d}.md"

    def append(self, line):
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            new = not self.path.exists()
            with self.path.open("a", encoding="utf-8") as f:
                if new:
                    f.write(f"# 작업 기록 {self.now:%Y-%m-%d}\n\n")
                    f.write("직원(에이전트)이 한 일이 자동으로 남는 파일입니다. 손으로 고치지 않아도 됩니다.\n")
                    f.write("`git log --oneline` 으로 자동 저장 지점을 보고, 되돌릴 땐 `git checkout <번호> -- <파일>`.\n\n")
                f.write(f"- {self.now:%H:%M:%S} {line}\n")
        except Exception:
            pass

    def last_prompt(self):
        try:
            for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
                if "📝 명령:" in line:
                    return line.split("📝 명령:", 1)[1].strip()
        except Exception:
            pass
        return ""


def channel_tag():
    ch = os.environ.get("WD_CHANNEL", "").strip()
    return f"[{ch}] " if ch else ""


def on_prompt(data, j):
    prompt = data.get("prompt", "")
    if not str(prompt).strip():
        return
    j.append(f"{channel_tag()}📝 명령: {one_line(prompt, MAX_PROMPT)}")


def on_tool_done(data, j):
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    root = j.root
    if tool == "Write":
        j.append(f"💾 저장: {rel(root, inp.get('file_path', ''))}")
    elif tool == "Edit":
        old = one_line(inp.get("old_string", ""), 60)
        new = one_line(inp.get("new_string", ""), 60)
        j.append(f"✏️ 수정: {rel(root, inp.get('file_path', ''))}  「{old}」→「{new}」")
    elif tool == "MultiEdit":
        n = len(inp.get("edits") or [])
        j.append(f"✏️ 수정: {rel(root, inp.get('file_path', ''))}  ({n}곳)")
    elif tool == "NotebookEdit":
        j.append(f"✏️ 노트북 수정: {rel(root, inp.get('notebook_path', ''))}")
    elif tool == "Bash":
        j.append(f"▶ 실행: {one_line(inp.get('command', ''), MAX_CMD)}")


def git(root, *args, timeout=50):
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def on_stop(data, j):
    root = j.root
    if not (root / ".git").exists():
        return  # 모듈 0 의 git init 전 — 조용히 건너뜀
    try:
        git(root, "add", "-A", timeout=50)
        staged = git(root, "-c", "core.quotepath=false", "diff", "--cached", "--name-only", timeout=20)
        files = [f.strip().strip('"') for f in staged.stdout.splitlines() if f.strip()]
        # 바뀐 게 없거나, 기록 파일만 바뀐 경우(직전 커밋의 sha 한 줄)는 건너뛴다 — 다음 진짜 변경과 함께 들어간다.
        if not files or all(f.startswith("workspace/기록/") for f in files):
            return
        what = j.last_prompt()
        msg = f"자동저장 {j.now:%Y-%m-%d %H:%M}"
        if what:
            msg += " · " + one_line(what, 48)
        r = git(root,
                "-c", "user.name=에이전트팀 자동저장",
                "-c", "user.email=autosave@agent-team.local",
                "-c", "core.quotepath=false",
                "commit", "-q", "-m", msg, timeout=50)
        if r.returncode == 0:
            sha = git(root, "rev-parse", "--short", "HEAD", timeout=10).stdout.strip()
            j.append(f"🗂️ 자동 저장 지점 {sha}  ({msg})")
            # 기록 파일 자체가 방금 커밋 뒤에 바뀌었으므로 다음 Stop 때 함께 들어간다.
        else:
            j.append(f"⚠️ 자동 저장 실패: {one_line(r.stderr or r.stdout, 120)}")
    except Exception as e:  # noqa: BLE001
        j.append(f"⚠️ 자동 저장 실패: {one_line(e, 120)}")


def main():
    data = read_input()
    root = find_root(data)
    j = Journal(root)
    event = data.get("hook_event_name", "")
    if event == "UserPromptSubmit":
        on_prompt(data, j)
    elif event == "PostToolUse":
        on_tool_done(data, j)
    elif event == "Stop":
        on_stop(data, j)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
