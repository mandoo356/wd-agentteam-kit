"""슬랙에서 온 말을 Claude 에게 전달하고 답을 받아오는 다리.

⚙️ 이 파일은 엔진입니다. 수업 중에는 고칠 일이 없습니다.
   (궁금하면 읽어보셔도 좋지만, 고쳐서 안 되면 `git checkout .` 로 되돌리세요)

하는 일:
  - Claude 를 한 번 켜두고 계속 재사용한다 (매번 켜면 20초씩 걸린다)
  - 직전 대화를 이어받는다 (서버를 껐다 켜도 하던 얘기를 기억한다)
  - Claude 가 죽으면 한 번 되살려서 다시 시도한다
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
)

from roster import load_agents, owner_name, describe

log = logging.getLogger("agent.bridge")

# 스타터킷 폴더 (slack-server 의 부모). 여기에 .claude/ 와 workspace/ 가 있다.
KIT_ROOT = Path(__file__).resolve().parent.parent

# 한 사람의 요청이 팀 전체를 오래 붙잡지 못하게 하는 상한.
QUERY_TIMEOUT_SEC = int(os.environ.get("QUERY_TIMEOUT_SEC", "180"))
RETRY_TIMEOUT_SEC = int(os.environ.get("RETRY_TIMEOUT_SEC", "90"))
DISCONNECT_TIMEOUT_SEC = 10

# 대화 이어가기용 세션 ID. 이게 없으면 서버를 껐다 켤 때마다
# 직원이 하던 일을 통째로 잊는다.
SESSION_FILE = Path(__file__).resolve().parent / ".agent_session.json"
# 3시간. 예전엔 24시간이었는데, 어제 대화(다른 이름·옛 요청)를 오늘까지 끌고 와서
# "왜 아직도 그 얘기야" 가 됐다. 슬랙에서 "새 대화" 라고 치면 즉시 잊는다 (server.py).
SESSION_MAX_AGE_SEC = int(os.environ.get("SESSION_MAX_AGE_SEC", str(3 * 3600)))
# 직원 파일 본문을 프롬프트에 넣을 때 상한. 2026-09-08 1,400 → 3,000.
# 카드 P5·P6·P7 이 팀장 파일에 줄을 덧붙이면 1,400 을 넘겨 뒤쪽 규칙이 잘려 나갔다 —
# "역할을 잊는" 게 아니라 못 본 것이었다. 입력 길이는 도구 왕복 한 번보다 훨씬 싸다.
AGENT_BODY_LIMIT = int(os.environ.get("AGENT_BODY_LIMIT", "3000"))
# 슬랙 답에 쓸 모델. 비우면 Claude Code 기본값. 슬랙 답은 5줄이라 sonnet 이면 체감이 크게 빨라진다.
# 강사 시연 PC 처럼 큰 산출물 품질이 중요하면 .env 에 AGENT_MODEL=opus.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "sonnet").strip()
# 한 대화에 이만큼 주고받으면 서버가 스스로 "새 대화"를 한다. 뒤로 갈수록 느려지고
# 앞 직원의 정체성이 섞이는 것을 막는다. 결과물은 파일·inbox 에 남으니 실무 손해는 작다.
SESSION_MAX_TURNS = int(os.environ.get("SESSION_MAX_TURNS", "30"))
# 팀 규약(facts.md)을 프롬프트에 넣을 때 상한
FACTS_LIMIT = int(os.environ.get("FACTS_LIMIT", "3000"))


class ClaudeError(RuntimeError):
    pass


def find_claude_cli(explicit: Optional[str] = None) -> str:
    """claude 명령어가 어디 깔렸는지 찾는다."""
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
    raise ClaudeError(
        "claude 명령어를 찾을 수 없습니다.\n"
        "  → 검은 창에서  npm install -g @anthropic-ai/claude-code\n"
        "  → 그래도 안 되면 .env 에 CLAUDE_CLI=전체경로 를 적어주세요"
    )


class AgentPool:
    """Claude 연결 하나를 켜두고 모든 요청이 돌려 쓴다."""

    def __init__(self, workspace: Path, cli_path: str):
        self.workspace = workspace
        self.cli_path = cli_path
        self._client: Optional[ClaudeSDKClient] = None
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._session_id: Optional[str] = self._load_session()
        self._turns = 0  # 이 세션에서 주고받은 횟수 (SESSION_MAX_TURNS 넘으면 새 대화)

    # ---- 대화 기억 ---------------------------------------------------------
    @staticmethod
    def _load_session() -> Optional[str]:
        try:
            d = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
        sid, ts = d.get("session_id"), d.get("updated_at", 0)
        if not sid:
            return None
        age = time.time() - ts
        if age > SESSION_MAX_AGE_SEC:
            log.info("저장된 대화가 %.0f시간 전 것이라 새로 시작합니다", age / 3600)
            return None
        log.info("직전 대화를 이어받습니다 (%.0f분 전)", age / 60)
        return sid

    def _save_session(self, sid: str) -> None:
        if not sid:
            return
        self._session_id = sid
        try:
            SESSION_FILE.write_text(
                json.dumps({"session_id": sid, "updated_at": time.time()},
                           ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning("대화 ID 저장 실패: %s", e)

    def forget_session(self) -> None:
        self._session_id = None
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    def _make_options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            cli_path=self.cli_path,
            # 스타터킷 폴더에서 실행해야 .claude/agents/ 의 직원들이 로드된다.
            cwd=str(KIT_ROOT),
            add_dirs=[str(KIT_ROOT), str(self.workspace)],
            resume=self._session_id,
            model=AGENT_MODEL or None,
            permission_mode="bypassPermissions",
            # .claude/hooks/guard.py 가 "슬랙에서 부른 작업"임을 알아, 삭제·덮어쓰기를 확인 창 대신 차단한다.
            env={"WD_CHANNEL": "slack"},
            # "user" + "project" 둘 다 읽는다 (2026-09-07 수정).
            #   project — 이 폴더의 .claude/ (수강생이 만든 직원·스킬·안전장치)
            #   user    — 내 계정 설정(~/.claude). 구글 캘린더·지메일·드라이브 커넥터와
            #             노트북에서 이미 로그인해 둔 연결이 여기 있다.
            # 예전엔 project 만 읽어서, 노트북에서는 되는 구글·네이버 연결이 슬랙으로 부르면
            # "다시 로그인하라"고 나왔다. 직원이 연결을 이어받지 못한 원인이 이 한 줄이었다.
            setting_sources=["user", "project"],
            load_timeout_ms=int(os.environ.get("LOAD_TIMEOUT_MS", "120000")),
            # 기본 1MB 로는 이미지를 읽을 때 넘친다.
            max_buffer_size=int(os.environ.get("MAX_BUFFER_SIZE", str(16 * 1024 * 1024))),
        )

    @staticmethod
    def _is_alive(client: ClaudeSDKClient) -> bool:
        """Claude 프로세스가 아직 살아 있는지.

        죽어도 객체는 멀쩡해 보이고, 다음 요청부터 전부 실패한다.
        모양을 모르겠으면 살아 있다고 보고 요청에서 판별한다.
        """
        try:
            proc = getattr(getattr(client, "_transport", None), "_process", None)
            if proc is None:
                return True
            return getattr(proc, "returncode", None) is None
        except Exception:
            return True

    async def _ensure_connected(self) -> ClaudeSDKClient:
        async with self._connect_lock:
            if self._client is not None:
                if self._is_alive(self._client):
                    return self._client
                log.warning("Claude 연결이 끊겨 있어 다시 붙습니다")
                await self._close_locked()
            log.info("Claude 연결 중...")
            try:
                client = ClaudeSDKClient(options=self._make_options())
                await client.connect()
            except Exception as e:
                if not self._session_id:
                    raise
                # 저장된 대화가 깨졌을 수 있다. 그것 때문에 서버 전체가 못 뜨면
                # 안 되니 대화를 버리고 한 번 더 시도한다.
                log.warning("대화 이어받기 실패(%s) — 새 대화로 시작합니다", type(e).__name__)
                self.forget_session()
                client = ClaudeSDKClient(options=self._make_options())
                await client.connect()
            self._client = client
            log.info("Claude 연결됨")
            return client

    async def _close_locked(self) -> None:
        if self._client is None:
            return
        client, self._client = self._client, None
        try:
            await asyncio.wait_for(client.disconnect(), timeout=DISCONNECT_TIMEOUT_SEC)
        except Exception as e:
            log.warning("연결 종료 중 오류: %s", e)

    async def close(self) -> None:
        async with self._connect_lock:
            await self._close_locked()

    async def _reconnect(self) -> ClaudeSDKClient:
        await self.close()
        return await self._ensure_connected()

    # ---- 프롬프트 재료 --------------------------------------------------
    @staticmethod
    def _personas() -> dict:
        try:
            from personas import PERSONAS
            return PERSONAS
        except Exception as e:  # personas.py 를 고치다 문법이 깨진 경우
            log.warning("personas.py 를 못 읽었습니다: %s", e)
            return {}

    def _roster_text(self, agents: dict, personas: dict) -> str:
        """팀 명단 한 줄씩 — '표시이름 (키): 담당'. 직원 파일이 있는 키만."""
        keys = list(personas) + [k for k in agents if k not in personas]
        rows = []
        for k in keys:
            if k not in agents:
                continue  # personas 에만 있고 직원 파일이 없으면 명단에서 뺀다
            disp = personas.get(k, {}).get("display_name") or agents[k].get("name") or k
            rows.append(f"  - {disp} ({k}): {describe(agents.get(k)) or '담당 미정'}")
        return "\n".join(rows)

    @staticmethod
    def _facts_text() -> str:
        """팀 규약을 서버가 읽어 프롬프트에 넣는다.
        예전엔 "먼저 facts.md 를 읽어라"고 시켜서 메시지마다 모델이 파일을 읽으러 한 번씩
        왕복했다(2026-09-08 속도 개선). 지금은 여기서 읽어 주고, 모델은 바로 답한다."""
        p = KIT_ROOT / "workspace" / "memory" / "facts.md"
        try:
            t = p.read_text(encoding="utf-8-sig", errors="replace").strip()
        except Exception:
            return "(facts.md 없음 — 카드 P1 로 만든다)"
        if len(t) > FACTS_LIMIT:
            t = t[:FACTS_LIMIT] + "\n…(이하 생략 — 전문은 workspace/memory/facts.md)"
        return t or "(facts.md 비어 있음)"

    @staticmethod
    def _inbox_text(agent: str, limit: int = 3, each: int = 400) -> str:
        """자기 inbox 쪽지를 서버가 읽어 프롬프트에 넣는다. 없으면 한 줄."""
        d = KIT_ROOT / "workspace" / "inbox" / agent
        try:
            files = sorted((p for p in d.glob("*.md") if p.is_file()),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            files = []
        if not files:
            return "  (쪽지 없음)"
        rows = []
        for p in files[:limit]:
            try:
                body = p.read_text(encoding="utf-8-sig", errors="replace").strip()
            except Exception:
                body = ""
            if len(body) > each:
                body = body[:each] + " …"
            rows.append(f"  - {p.name}: {body}")
        if len(files) > limit:
            rows.append(f"  (외 {len(files) - limit}개 — workspace/inbox/{agent}/)")
        return "\n".join(rows)

    def build_prompt(self, agent: str, user_message: str,
                     speaker_name: str = "") -> str:
        agents = load_agents(KIT_ROOT)
        personas = self._personas()
        disp = personas.get(agent, {}).get("display_name") or agents.get(agent, {}).get("name") or agent
        boss, _src = owner_name(KIT_ROOT)
        boss = speaker_name or boss
        if boss:
            who = f"{boss} — 이 회사의 대표 본인"
        else:
            who = ("이 회사의 대표 본인 (이름은 workspace/memory/facts.md 의 '이름:' 에 있다. "
                   "없으면 '대표님' 이라고 부른다)")
        body = (agents.get(agent, {}).get("body") or "").strip()
        if len(body) > AGENT_BODY_LIMIT:
            body = body[:AGENT_BODY_LIMIT] + f"\n…(이하 생략 — 전문은 .claude/agents/{agent}.md)"
        roster = self._roster_text(agents, personas) or "  (직원 파일이 없습니다 — .claude/agents/ 를 확인)"

        parts = [
            "[슬랙으로 온 요청]",
            f"말을 거는 사람: {who}. 이 사람을 다른 이름·다른 사람으로 부르지 않는다. "
            "이름을 정정해 주면 그 이름으로 부르고 facts.md 의 '이름:' 줄에 반영한다.",
            f"기본 담당: {disp} ({agent})",
            "",
            "[우리 팀 명단 — 답할 때 쓰는 이름은 왼쪽 표시 이름 그대로]",
            roster,
            "",
            f"[담당 직원 {disp} 의 정체성 — 이 성격·말투·담당대로 답한다]",
            body or "(직원 파일 본문 없음)",
            "",
            "[팀 규약 — workspace/memory/facts.md 전문. 다시 읽으러 가지 않는다]",
            self._facts_text(),
            "",
            f"[내 inbox — workspace/inbox/{agent}/ 에 온 쪽지. 다시 읽으러 가지 않는다]",
            self._inbox_text(agent),
            "",
            "[일하는 규칙]",
            "- 위 팀 규약과 inbox 는 이미 읽은 것으로 친다 (다시 읽지 않는다). 인사·질문·짧은 답은 도구 없이 바로 답한다. "
            "캘린더·메일·파일을 실제로 봐야 하는 일은 도구를 쓰고 결과까지 답한다 — '확인 중이에요' 같은 미완의 말로 끝내지 않는다.",
            "- 요청이 기본 담당의 일이 아니면 명단에서 맞는 직원을 고르고 그 직원 이름으로 답한다. "
            "여러 직원이 얽힌 일이면 관련된 직원이 각자 한 줄씩 말한다 (팀장 혼자 다 말하지 않는다).",
            "- 파일을 만드는 큰 일이 다른 직원 몫이면 Agent 도구로 그 직원(subagent_type=키)에게 맡기고, "
            "결과를 그 직원 이름으로 보고한다. 작은 답은 바로 그 직원 이름으로 한다.",
            "- 산출물은 workspace/결과물/ 에 파일로 저장한다. 다른 직원이 이어받아야 하면 "
            "workspace/inbox/<상대키>/ 에 쪽지를 남긴다.",
            "- 모르는 금액·날짜·고객사 이름은 지어내지 않는다.",
            "",
            "[답하는 방식 — 지킬 것]",
            f"- 카톡처럼 한 줄에 한 마디. 모든 줄을 '표시이름: 내용' 형태로 쓴다. 예) {disp}: 착수했어요",
            "- 표시이름은 위 명단의 이름 그대로. staff2 같은 영어 키나 '직원2' 를 쓰지 않는다.",
            "- 한 줄 40자 내외, 전체 5줄 이내. 과정 설명·요약·서론 금지. 결론과 사람이 할 일만.",
            "- 마크다운 강조(**), 불릿, 제목, 코드블록 쓰지 않는다.",
            "",
            "---",
            user_message,
            "",
            f"(지금 답하는 사람은 {disp} 다. 앞 대화에서 누가 답했든 이번 답은 {disp} 의 정체성으로 한다.)",
        ]
        return "\n".join(parts)

    async def query_agent(self, agent: str, user_message: str,
                          timeout_sec: Optional[int] = None,
                          speaker_name: str = "") -> str:
        timeout_sec = timeout_sec or QUERY_TIMEOUT_SEC
        prompt = self.build_prompt(agent, user_message, speaker_name)
        async with self._lock:
            if SESSION_MAX_TURNS > 0 and self._turns >= SESSION_MAX_TURNS:
                log.info("대화가 %d번을 넘어 새 대화로 시작합니다 (SESSION_MAX_TURNS)", self._turns)
                self.forget_session()
                await self.close()
                self._turns = 0
            self._turns += 1
            try:
                return await self._do_query(prompt, timeout_sec)
            except Exception as e:
                log.warning("첫 시도 실패(%s) — 다시 붙어서 한 번 더 해봅니다", type(e).__name__)
                try:
                    await self._reconnect()
                    return await self._do_query(prompt, RETRY_TIMEOUT_SEC)
                except Exception:
                    # 의심스러운 연결을 다음 요청에 넘기지 않는다.
                    await self.close()
                    raise

    async def _do_query(self, prompt: str, timeout_sec: int) -> str:
        client = await self._ensure_connected()
        final: list[str] = []
        narration: list[str] = []

        async def collect():
            await client.query(prompt=prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    texts = [t for b in msg.content if (t := getattr(b, "text", None))]
                    # 도구를 쓰면서 하는 말("파일 확인해볼게요")은 답이 아니라 중계다.
                    # 버리지 말고 따로 둔다 — 도구 호출로 끝나도 할 말은 남게.
                    if any(type(b).__name__ == "ToolUseBlock" for b in msg.content):
                        if texts:
                            narration.clear()
                            narration.extend(texts)
                        continue
                    if texts:
                        final.clear()
                        final.extend(texts)
                elif isinstance(msg, ResultMessage):
                    if getattr(msg, "session_id", None):
                        self._save_session(msg.session_id)
                    break

        await asyncio.wait_for(collect(), timeout=timeout_sec)
        result = "".join(final).strip() or "".join(narration).strip()
        return result or "(빈 응답 — logs/server.log 를 확인해 보세요)"


_pool: Optional[AgentPool] = None


def get_pool(workspace: Path, cli_path: str) -> AgentPool:
    global _pool
    if _pool is None:
        _pool = AgentPool(workspace=workspace, cli_path=cli_path)
    return _pool


async def invoke_agent(agent: str, user_message: str, workspace: Path,
                       cli_path: str, timeout_sec: Optional[int] = None,
                       speaker_name: str = "") -> str:
    pool = get_pool(workspace, cli_path)
    return await pool.query_agent(agent, user_message, timeout_sec=timeout_sec,
                                  speaker_name=speaker_name)


async def reset_conversation(workspace: Path, cli_path: str) -> None:
    """슬랙에서 '새 대화' 라고 하면 — 저장된 대화를 버리고 Claude 를 새로 붙인다."""
    pool = get_pool(workspace, cli_path)
    pool.forget_session()
    await pool.close()
