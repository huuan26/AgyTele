from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import DATA_DIR, AppConfig


@dataclass
class UsageStats:
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0
    last_duration_sec: float = 0.0


@dataclass
class ChatSession:
    chat_id: int
    conversation_id: str | None = None
    model: str = "gemini-4-argon-high"
    workspace: str = ""
    permission_mode: str = "auto"
    usage: UsageStats = field(default_factory=UsageStats)


class StateManager:
    """
    Quản lý trạng thái phiên làm việc của từng Chat ID và lưu trữ bền vững vào data/sessions.json.
    Đồng thời hỗ trợ đọc danh sách hội thoại gần đây từ thư mục brain của Antigravity CLI.
    """

    def __init__(self, app_config: AppConfig, sessions_file: Path | None = None) -> None:
        self.app_config = app_config
        self.sessions_file = sessions_file or (DATA_DIR / "sessions.json")
        self.brain_dir = Path.home() / ".gemini" / "antigravity-cli" / "brain"
        self._sessions: dict[int, ChatSession] = {}
        self._load()

    def _load(self) -> None:
        if not self.sessions_file.exists():
            return
        try:
            raw = json.loads(self.sessions_file.read_text(encoding="utf-8"))
            for k, val in raw.items():
                chat_id = int(k)
                usage_raw = val.get("usage") or {}
                usage = UsageStats(
                    turns=int(usage_raw.get("turns", 0)),
                    input_tokens=int(usage_raw.get("input_tokens", 0)),
                    output_tokens=int(usage_raw.get("output_tokens", 0)),
                    thinking_tokens=int(usage_raw.get("thinking_tokens", 0)),
                    total_tokens=int(usage_raw.get("total_tokens", 0)),
                    last_duration_sec=float(usage_raw.get("last_duration_sec", 0.0)),
                )
                self._sessions[chat_id] = ChatSession(
                    chat_id=chat_id,
                    conversation_id=val.get("conversation_id"),
                    model=val.get("model") or self.app_config.default_model,
                    workspace=val.get("workspace") or self.app_config.default_workspace,
                    permission_mode=val.get("permission_mode") or self.app_config.permission_mode,
                    usage=usage,
                )
        except Exception:
            self._sessions = {}

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        serializable = {str(k): asdict(v) for k, v in self._sessions.items()}
        self.sessions_file.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_session(self, chat_id: int) -> ChatSession:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = ChatSession(
                chat_id=chat_id,
                conversation_id=None,
                model=self.app_config.default_model,
                workspace=self.app_config.default_workspace,
                permission_mode=self.app_config.permission_mode,
            )
            self._save()
        return self._sessions[chat_id]

    def set_conversation(self, chat_id: int, conversation_id: str | None) -> None:
        session = self.get_session(chat_id)
        session.conversation_id = conversation_id
        self._save()

    def set_model(self, chat_id: int, model_id: str) -> None:
        session = self.get_session(chat_id)
        session.model = model_id
        self._save()

    def set_workspace(self, chat_id: int, workspace_path: str) -> None:
        session = self.get_session(chat_id)
        session.workspace = workspace_path
        self._save()

    def set_permission_mode(self, chat_id: int, mode: str) -> None:
        session = self.get_session(chat_id)
        session.permission_mode = mode
        self._save()

    def record_usage(self, chat_id: int, usage_dict: dict[str, Any], duration_sec: float) -> None:
        session = self.get_session(chat_id)
        session.usage.turns += 1
        session.usage.input_tokens += int(usage_dict.get("input_tokens", 0))
        session.usage.output_tokens += int(usage_dict.get("output_tokens", 0))
        session.usage.thinking_tokens += int(usage_dict.get("thinking_tokens", 0))
        session.usage.total_tokens += int(usage_dict.get("total_tokens", 0))
        session.usage.last_duration_sec = round(float(duration_sec), 2)
        self._save()

    def list_recent_conversations(self, limit: int = 6) -> list[dict[str, str]]:
        """
        Quét nhanh các hội thoại gần nhất trong ~/.gemini/antigravity-cli/brain
        khi người dùng gõ lệnh /resume.
        """
        if not self.brain_dir.exists():
            return []

        items: list[tuple[float, str, Path]] = []
        for entry in self.brain_dir.iterdir():
            if not entry.is_dir():
                continue
            transcript = entry / ".system_generated" / "logs" / "transcript.jsonl"
            if transcript.exists():
                mtime = transcript.stat().st_mtime
                items.append((mtime, entry.name, transcript))

        items.sort(key=lambda x: x[0], reverse=True)
        results: list[dict[str, str]] = []

        for mtime, conv_id, transcript_path in items[:limit]:
            title = self._extract_first_prompt(transcript_path)
            dt_str = datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M")
            results.append(
                {
                    "id": conv_id,
                    "title": title,
                    "updated_at": dt_str,
                }
            )
        return results

    @staticmethod
    def _extract_first_prompt(transcript_path: Path) -> str:
        try:
            with transcript_path.open("r", encoding="utf-8", errors="ignore") as f:
                for _ in range(30):
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("type") == "USER_INPUT" and data.get("content"):
                        raw_text = str(data["content"])
                        match = re.search(r"<USER_REQUEST>([\s\S]*?)</USER_REQUEST>", raw_text)
                        if match:
                            raw_text = match.group(1)
                        clean = " ".join(raw_text.split()).strip()
                        if len(clean) > 48:
                            clean = clean[:45] + "..."
                        return clean or "Hội thoại không tiêu đề"
        except Exception:
            pass
        return "Hội thoại mới"
