from __future__ import annotations

import asyncio
import socket
import sys
from datetime import datetime

from src.agy_bridge import AgyBridge
from src.config import load_config
from src.formatter import escape_html
from src.router import BotRouter
from src.state_manager import StateManager
from src.telegram_api import TelegramClient

SINGLE_INSTANCE_PORT = 9877


def acquire_single_instance_lock(port: int = SINGLE_INSTANCE_PORT) -> socket.socket:
    """Đảm bảo chỉ có duy nhất 1 tiến trình Bot chạy trên máy tại một thời điểm."""
    lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_sock.bind(("127.0.0.1", port))
        lock_sock.listen(1)
        return lock_sock
    except OSError:
        print("=" * 65)
        print(f"❌ LỖI: Cổng nội bộ {port} đang được sử dụng!")
        print("Một tiến trình Anti-Tele-An khác đang chạy trên máy tính này.")
        print("Vui lòng đóng cửa sổ Terminal cũ trước khi mở phiên mới.")
        print("=" * 65)
        sys.exit(1)


async def run_bot() -> None:
    try:
        app_config = load_config()
    except (FileNotFoundError, ValueError) as err:
        print(f"\n⚠️ {err}\n")
        sys.exit(1)

    _lock = acquire_single_instance_lock()

    tg = TelegramClient(app_config.bot_token)
    state = StateManager(app_config)
    bridge = AgyBridge(tg, state)
    router = BotRouter(tg, state, bridge)

    print("=" * 60)
    print("🚀 ANTI-TELE-AN (Python Bridge cho Antigravity CLI)")
    print(f"📁 Default Workspace : {app_config.default_workspace}")
    print(f"🤖 Default Model     : {app_config.default_model}")
    print(f"🛡️ Allowed User IDs  : { sorted(app_config.allowed_user_ids) }")
    print("=" * 60)

    # 1. Xóa webhook cũ (nếu có) và đăng ký Menu lệnh trên Telegram
    await tg.delete_webhook()
    await tg.set_my_commands(
        [
            {"command": "new", "description": "Tạo cuộc hội thoại mới (Reset Context)"},
            {"command": "resume", "description": "Khôi phục cuộc hội thoại gần đây"},
            {"command": "model", "description": "Chọn AI Model bằng nút bấm"},
            {"command": "workspace", "description": "Xem hoặc đổi thư mục dự án (Workspace)"},
            {"command": "mode", "description": "Đổi chế độ quyền (auto / accept-edits / plan)"},
            {"command": "goal", "description": "Chạy tác vụ tự động nhiều bước"},
            {"command": "stop", "description": "Dừng ngay tiến trình đang chạy"},
            {"command": "usage", "description": "Xem thống kê Token & cấu hình"},
            {"command": "status", "description": "Kiểm tra trạng thái kết nối"},
            {"command": "help", "description": "Xem hướng dẫn sử dụng"},
        ]
    )
    print("✅ Đã đăng ký Menu lệnh với Telegram.")

    # 2. Bỏ qua các tin nhắn cũ gửi trong lúc máy tính/Terminal đang tắt
    offset = await tg.clear_old_updates()
    if offset:
        print(f"🧹 Đã bỏ qua các tin nhắn cũ lúc máy tắt (Next offset: {offset}).")

    # 3. Thông báo cho chủ sở hữu biết Bot đã sẵn sàng
    now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    admin_id = next(iter(app_config.allowed_user_ids))
    await tg.send_message(
        admin_id,
        f"🟢 <b>Anti-Tele-An đã khởi động!</b> (<code>{now_str}</code>)\n"
        f"• <b>Model:</b> <code>{escape_html(app_config.default_model)}</code>\n"
        f"• <b>Workspace:</b> <code>{escape_html(app_config.default_workspace)}</code>\n"
        f"<i>Các tin nhắn gửi lúc tắt máy đã được dọn sạch. Gõ /help để xem bảng điều khiển.</i>",
    )

    print("💬 Đang lắng nghe tin nhắn từ Telegram... (Nhấn Ctrl + C để dừng)\n")

    try:
        while True:
            resp = await tg.get_updates(offset=offset, timeout=25)
            if not resp.get("ok"):
                await asyncio.sleep(2.0)
                continue

            for update in resp.get("result") or []:
                offset = int(update["update_id"]) + 1

                # Xử lý sự kiện bấm nút Inline Keyboard
                if "callback_query" in update:
                    cb = update["callback_query"]
                    user_id = int((cb.get("from") or {}).get("id", 0))
                    if user_id not in app_config.allowed_user_ids:
                        await tg.answer_callback_query(
                            str(cb.get("id")),
                            "🚷 Bạn không có quyền điều khiển Bot này.",
                            show_alert=True,
                        )
                        continue
                    await router.handle_callback(cb)
                    continue

                # Xử lý tin nhắn văn bản
                msg = update.get("message")
                if not msg or "text" not in msg:
                    continue

                user_id = int((msg.get("from") or {}).get("id", 0))
                chat_id = int((msg.get("chat") or {}).get("id", 0))
                text = str(msg.get("text") or "").strip()

                if user_id not in app_config.allowed_user_ids:
                    print(f"⚠️ Từ chối truy cập từ UserID lạ: {user_id}")
                    await tg.send_message(chat_id, "🚷 Bạn không có quyền điều khiển hệ thống này.")
                    continue

                print(f"[{datetime.now().strftime('%H:%M:%S')}] 👤 User ({user_id}): {text[:80]}")
                await router.handle_message(chat_id, text)

    except asyncio.CancelledError:
        pass
    finally:
        print("\n🛑 Đang dừng các tiến trình Antigravity và ngắt kết nối...")
        await bridge.stop_all()
        await tg.send_message(
            admin_id,
            "🔴 <b>Anti-Tele-An đã ngừng hoạt động</b> (Terminal trên máy tính đã đóng).",
        )
        _lock.close()
        print("👋 Đã đóng kết nối an toàn!")


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
