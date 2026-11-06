from __future__ import annotations

import getpass
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


def main() -> None:
    print("=" * 60)
    print("⚙️  THIẾT LẬP CẤU HÌNH ANTI-TELE-AN (PYTHON)")
    print("=" * 60)

    if CONFIG_PATH.exists():
        ans = input("File config.json đã tồn tại. Bạn có muốn ghi đè không? (y/N): ").strip().lower()
        if ans not in ("y", "yes"):
            print("Đã giữ nguyên cấu hình hiện tại.")
            return

    print("\n--- BƯỚC 1: TELEGRAM BOT TOKEN ---")
    print("1. Mở Telegram, tìm @BotFather")
    print("2. Gõ /newbot (hoặc lấy token của bot đã có)")
    while True:
        try:
            token = getpass.getpass("🔑 Nhập Telegram Bot Token (ký tự sẽ được ẩn để bảo mật): ").strip()
        except Exception:
            token = input("🔑 Nhập Telegram Bot Token: ").strip()
        if not token:
            token = input("🔑 Nhập Telegram Bot Token: ").strip()
        if len(token) > 15 and ":" in token:
            break
        print("⚠️ Token không hợp lệ (cần có dạng 123456:ABC-DEF...). Vui lòng thử lại.")

    print("\n--- BƯỚC 2: TELEGRAM USER ID (BẢO MẬT ALLOWLIST) ---")
    print("1. Mở Telegram, tìm @userinfobot và nhấn Start")
    print("2. Copy dãy số Id của bạn (có thể nhập nhiều ID cách nhau bằng dấu phẩy)")
    while True:
        raw_ids = input("🛡️ Nhập Telegram User ID: ").strip()
        parts = [p.strip() for p in raw_ids.split(",") if p.strip().isdigit()]
        if parts:
            allowed_ids = [int(p) for p in parts]
            break
        print("⚠️ Vui lòng nhập ít nhất 1 User ID chỉ gồm chữ số.")

    print("\n--- BƯỚC 3: THƯ MỤC LÀM VIỆC MẶC ĐỊNH (WORKSPACE) ---")
    default_ws = str(Path.home())
    ws_input = input(f"📁 Nhập đường dẫn Workspace mặc định [{default_ws}]: ").strip()
    workspace = ws_input if ws_input and Path(ws_input).is_dir() else default_ws

    print("\n--- BƯỚC 4: MODEL MẶC ĐỊNH ---")
    default_model = "gemini-4-argon-high"
    model_input = input(f"🤖 Nhập Model mặc định [{default_model}]: ").strip()
    model = model_input or default_model

    config_data = {
        "bot_token": token,
        "allowed_user_ids": allowed_ids,
        "default_workspace": workspace,
        "default_model": model,
        "permission_mode": "auto",
    }

    CONFIG_PATH.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n✅ Đã lưu cấu hình thành công vào:", CONFIG_PATH)
    print("🚀 Bây giờ bạn có thể khởi động Bot bằng lệnh: python main.py (hoặc chạy run.bat)")


if __name__ == "__main__":
    main()
