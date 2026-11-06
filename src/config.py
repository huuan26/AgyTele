from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"
DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class AppConfig:
    bot_token: str
    allowed_user_ids: set[int]
    default_workspace: str
    default_model: str
    permission_mode: str = "auto"  # "auto" (--dangerously-skip-permissions), "accept-edits", hoặc "plan"


def load_config(config_path: Path | None = None) -> AppConfig:
    """Đọc và kiểm tra tính hợp lệ của file config.json."""
    path = config_path or Path(os.environ.get("ANTI_TELE_CONFIG", DEFAULT_CONFIG_PATH))

    if not path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file cấu hình tại: {path}\n"
            f"👉 Vui lòng chạy lệnh `python setup.py` để thiết lập Bot Token và User ID trước!"
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"File cấu hình {path} không đúng định dạng JSON: {exc}") from exc

    token = str(raw.get("bot_token") or raw.get("token") or "").strip()
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        raise ValueError("Bot Token đang trống hoặc chưa được thay thế trong config.json.")

    raw_ids = raw.get("allowed_user_ids") or raw.get("allowedUserIds") or raw.get("allowedUserId") or []
    if not isinstance(raw_ids, list):
        raw_ids = [raw_ids]

    allowed_ids: set[int] = set()
    for item in raw_ids:
        try:
            allowed_ids.add(int(str(item).strip()))
        except ValueError:
            continue

    if not allowed_ids:
        raise ValueError("Danh sách `allowed_user_ids` trong config.json phải có ít nhất 1 Telegram User ID hợp lệ.")

    default_ws = str(raw.get("default_workspace") or Path.home()).strip()
    if not Path(default_ws).is_dir():
        default_ws = str(Path.home())

    default_model = str(raw.get("default_model") or "gemini-4-argon-high").strip()
    permission_mode = str(raw.get("permission_mode") or "auto").strip()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        bot_token=token,
        allowed_user_ids=allowed_ids,
        default_workspace=default_ws,
        default_model=default_model,
        permission_mode=permission_mode,
    )
