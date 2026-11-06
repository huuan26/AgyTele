from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from src.agy_bridge import AgyBridge, fetch_available_models
from src.formatter import escape_html
from src.state_manager import StateManager
from src.telegram_api import TelegramClient


class BotRouter:
    """
    Bộ định tuyến xử lý toàn bộ tin nhắn văn bản (Commands & Prompts)
    và sự kiện bấm nút Inline Keyboard (Callback Queries).
    """

    def __init__(self, tg: TelegramClient, state: StateManager, bridge: AgyBridge) -> None:
        self.tg = tg
        self.state = state
        self.bridge = bridge
        self._workspace_candidates: dict[int, list[str]] = {}

    async def handle_message(self, chat_id: int, text: str) -> None:
        text = text.strip()
        if not text:
            return

        # 1. /start hoặc /help
        if text in ("/start", "/help"):
            await self._cmd_help(chat_id)
            return

        # 2. /status
        if text == "/status":
            await self._cmd_status(chat_id)
            return

        # 3. /stop (Hủy tác vụ đang chạy)
        if text == "/stop":
            stopped = await self.bridge.stop_task(chat_id)
            if stopped:
                await self.tg.send_message(chat_id, "🛑 <b>Đã gửi tín hiệu dừng tác vụ đang chạy và xóa hàng đợi.</b>")
            else:
                await self.tg.send_message(chat_id, "ℹ️ Hiện không có tác vụ nào đang chạy.")
            return

        # 4. /usage (Xem thống kê Token & cấu hình phiên)
        if text == "/usage":
            await self._cmd_usage(chat_id)
            return

        # 5. /model (Chọn model bằng nút bấm Inline)
        if text.startswith("/model"):
            arg = text[len("/model"):].strip()
            await self._cmd_model(chat_id, arg)
            return

        # 6. /mode (Chế độ quyền hạn của Agent: auto / accept-edits / plan)
        if text.startswith("/mode"):
            await self._cmd_mode(chat_id)
            return

        # 7. /workspace hoặc /cd (Đổi thư mục dự án làm việc)
        if text.startswith("/workspace") or text.startswith("/cd"):
            parts = text.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""
            await self._cmd_workspace(chat_id, arg)
            return

        # 8. /resume (Khôi phục cuộc hội thoại cũ)
        if text.startswith("/resume"):
            arg = text[len("/resume"):].strip()
            await self._cmd_resume(chat_id, arg)
            return

        # 9. /new (Bắt đầu cuộc hội thoại mới)
        if text.startswith("/new"):
            prompt = text[len("/new"):].strip()
            if not prompt:
                self.state.set_conversation(chat_id, None)
                await self.tg.send_message(
                    chat_id,
                    "🆕 <b>Đã làm mới ngữ cảnh (Reset Context)!</b>\n"
                    "Tin nhắn tiếp theo của bạn sẽ mở một cuộc hội thoại hoàn toàn mới.",
                )
            else:
                await self.bridge.enqueue_prompt(chat_id, prompt, force_new=True)
            return

        # 10. /goal (Chạy tác vụ tự động nhiều bước)
        if text.startswith("/goal"):
            prompt = text[len("/goal"):].strip()
            if not prompt:
                await self.tg.send_message(
                    chat_id,
                    "🎯 <b>Chế độ Goal (Tác vụ nhiều bước):</b>\n"
                    "Cú pháp: <code>/goal &lt;mô tả mục tiêu&gt;</code>\n"
                    "Ví dụ: <code>/goal Kiểm tra lỗi toàn bộ dự án và viết unit test</code>",
                )
            else:
                await self.bridge.enqueue_prompt(chat_id, f"/goal {prompt}", force_new=False)
            return

        # 11. Tin nhắn thông thường -> Gửi thẳng tới Antigravity CLI
        await self.bridge.enqueue_prompt(chat_id, text, force_new=False)

    async def handle_callback(self, callback_query: dict[str, Any]) -> None:
        cb_id = str(callback_query.get("id") or "")
        data = str(callback_query.get("data") or "")
        msg = callback_query.get("message") or {}
        chat_id = int((msg.get("chat") or {}).get("id", 0))
        msg_id = int(msg.get("message_id", 0))

        if not chat_id:
            return

        if data == "stop_task":
            stopped = await self.bridge.stop_task(chat_id)
            await self.tg.answer_callback_query(
                cb_id,
                "🛑 Đã dừng tác vụ!" if stopped else "Tác vụ đã kết thúc trước đó.",
            )
            return

        if data.startswith("set_model:"):
            model_id = data.split(":", 1)[1]
            self.state.set_model(chat_id, model_id)
            await self.tg.answer_callback_query(cb_id, f"Đã chọn: {model_id}")
            await self.tg.edit_message_text(
                chat_id,
                msg_id,
                f"🤖 <b>Đã chuyển sang Model:</b> <code>{escape_html(model_id)}</code>",
            )
            return

        if data.startswith("set_mode:"):
            mode = data.split(":", 1)[1]
            self.state.set_permission_mode(chat_id, mode)
            await self.tg.answer_callback_query(cb_id, f"Chế độ: {mode}")
            await self.tg.edit_message_text(
                chat_id,
                msg_id,
                f"🛡️ <b>Đã đổi chế độ thực thi sang:</b> <code>{escape_html(mode)}</code>",
            )
            return

        if data.startswith("resume_conv:"):
            conv_id = data.split(":", 1)[1]
            self.state.set_conversation(chat_id, conv_id)
            await self.tg.answer_callback_query(cb_id, "Đã khôi phục hội thoại!")
            await self.tg.edit_message_text(
                chat_id,
                msg_id,
                f"📂 <b>Đã chuyển sang hội thoại:</b>\n<code>{escape_html(conv_id)}</code>\n\n"
                f"👉 Bạn có thể nhắn tin tiếp tục ngay bây giờ!",
            )
            return

        if data.startswith("set_ws:"):
            idx_str = data.split(":", 1)[1]
            candidates = self._workspace_candidates.get(chat_id) or []
            try:
                idx = int(idx_str)
                if 0 <= idx < len(candidates):
                    chosen = candidates[idx]
                    self.state.set_workspace(chat_id, chosen)
                    await self.tg.answer_callback_query(cb_id, "Đã đổi Workspace!")
                    await self.tg.edit_message_text(
                        chat_id,
                        msg_id,
                        f"📁 <b>Thư mục làm việc hiện tại (Workspace):</b>\n<code>{escape_html(chosen)}</code>",
                    )
                    return
            except ValueError:
                pass
            await self.tg.answer_callback_query(cb_id, "Lựa chọn không hợp lệ.")

    async def _cmd_help(self, chat_id: int) -> None:
        session = self.state.get_session(chat_id)
        help_html = (
            "⚡ <b>Anti-Tele-An — Cầu nối Antigravity CLI (Python)</b>\n\n"
            "💬 <b>Cách dùng cơ bản:</b>\n"
            "• Nhắn bất kỳ nội dung nào để trò chuyện và giao việc trực tiếp cho Antigravity.\n\n"
            "🛠 <b>Danh sách lệnh điều khiển:</b>\n"
            "• /new <code>[nội dung]</code> — Tạo cuộc hội thoại mới (Reset Context)\n"
            "• /resume — Xem & khôi phục các cuộc hội thoại gần đây\n"
            "• /model — Chọn AI Model bằng nút bấm trực quan\n"
            "• /workspace <code>[đường_dẫn]</code> — Xem hoặc chuyển đổi thư mục dự án\n"
            "• /mode — Đổi chế độ quyền (<code>auto</code> / <code>accept-edits</code> / <code>plan</code>)\n"
            "• /goal <code>&lt;mục tiêu&gt;</code> — Chạy tác vụ tự động nhiều bước\n"
            "• /stop — Dừng ngay lập tức tiến trình đang chạy\n"
            "• /usage — Xem thống kê Token & cấu hình phiên hiện tại\n"
            "• /status — Kiểm tra trạng thái máy tính & kết nối\n\n"
            f"📌 <b>Hiện tại:</b> Model <code>{escape_html(session.model)}</code> | "
            f"Workspace: <code>{escape_html(session.workspace)}</code>"
        )
        await self.tg.send_message(chat_id, help_html)

    async def _cmd_status(self, chat_id: int) -> None:
        session = self.state.get_session(chat_id)
        busy_str = "⚡ Đang xử lý tác vụ" if self.bridge.is_busy(chat_id) else "🟢 Đang rảnh (Sẵn sàng)"
        conv_str = session.conversation_id or "Chưa có (Sẽ tạo mới ở tin nhắn tới)"
        status_html = (
            "🖥️ <b>Trạng thái Hệ thống Anti-Tele-An:</b>\n\n"
            f"• <b>Trạng thái Bot:</b> {busy_str}\n"
            f"• <b>Hệ điều hành:</b> <code>{escape_html(platform.system())} {escape_html(platform.release())}</code>\n"
            f"• <b>Python:</b> <code>{escape_html(platform.python_version())}</code>\n"
            f"• <b>Model đang dùng:</b> <code>{escape_html(session.model)}</code>\n"
            f"• <b>Chế độ thực thi:</b> <code>{escape_html(session.permission_mode)}</code>\n"
            f"• <b>Workspace:</b> <code>{escape_html(session.workspace)}</code>\n"
            f"• <b>Conversation ID:</b> <code>{escape_html(conv_str)}</code>"
        )
        await self.tg.send_message(chat_id, status_html)

    async def _cmd_usage(self, chat_id: int) -> None:
        session = self.state.get_session(chat_id)
        u = session.usage
        usage_html = (
            "📊 <b>Thống kê Sử dụng Phiên (Token Usage):</b>\n\n"
            f"• <b>Model hiện tại:</b> <code>{escape_html(session.model)}</code>\n"
            f"• <b>Số lượt phản hồi (Turns):</b> <code>{u.turns:,}</code>\n"
            f"• <b>Input Tokens:</b> <code>{u.input_tokens:,}</code>\n"
            f"• <b>Output Tokens:</b> <code>{u.output_tokens:,}</code>\n"
            f"• <b>Thinking Tokens:</b> <code>{u.thinking_tokens:,}</code>\n"
            f"• <b>Tổng Tokens:</b> <b><code>{u.total_tokens:,}</code></b>\n"
            f"• <b>Thời gian lượt cuối:</b> <code>{u.last_duration_sec}s</code>"
        )
        await self.tg.send_message(chat_id, usage_html)

    async def _cmd_model(self, chat_id: int, direct_arg: str = "") -> None:
        session = self.state.get_session(chat_id)
        if direct_arg:
            self.state.set_model(chat_id, direct_arg)
            await self.tg.send_message(
                chat_id,
                f"🤖 <b>Đã đặt Model:</b> <code>{escape_html(direct_arg)}</code>",
            )
            return

        wait_msg = await self.tg.send_message(chat_id, "⏳ <i>Đang lấy danh sách model từ Antigravity CLI...</i>")
        wait_id = (wait_msg.get("result") or {}).get("message_id")

        try:
            models = await fetch_available_models()
        except Exception as exc:
            err_html = f"❌ <b>Không thể lấy danh sách model:</b>\n<pre>{escape_html(str(exc))}</pre>"
            if wait_id:
                await self.tg.edit_message_text(chat_id, wait_id, err_html)
            else:
                await self.tg.send_message(chat_id, err_html)
            return

        keyboard: list[list[dict[str, str]]] = []
        for model_id, display_name in models:
            prefix = "✅ " if model_id == session.model else ""
            keyboard.append(
                [{"text": f"{prefix}{display_name}", "callback_data": f"set_model:{model_id}"}]
            )

        text_html = (
            f"🤖 <b>Chọn AI Model cho phiên làm việc:</b>\n"
            f"Hiện tại: <code>{escape_html(session.model)}</code>\n\n"
            f"👉 <i>Bấm trực tiếp vào nút bên dưới để chuyển đổi:</i>"
        )
        markup = {"inline_keyboard": keyboard}
        if wait_id:
            await self.tg.edit_message_text(chat_id, wait_id, text_html, reply_markup=markup)
        else:
            await self.tg.send_message(chat_id, text_html, reply_markup=markup)

    async def _cmd_mode(self, chat_id: int) -> None:
        session = self.state.get_session(chat_id)
        modes = [
            ("auto", "⚡ Auto (Tự động duyệt mọi công cụ & lệnh)"),
            ("accept-edits", "✏️ Accept Edits (Tự động cho phép sửa file)"),
            ("plan", "📋 Plan Only (Chỉ phân tích & lập kế hoạch)"),
        ]
        keyboard: list[list[dict[str, str]]] = []
        for m_id, label in modes:
            prefix = "✅ " if session.permission_mode == m_id else ""
            keyboard.append([{"text": f"{prefix}{label}", "callback_data": f"set_mode:{m_id}"}])

        await self.tg.send_message(
            chat_id,
            f"🛡️ <b>Chế độ Quyền thực thi (Permission Mode):</b>\n"
            f"Hiện tại: <code>{escape_html(session.permission_mode)}</code>",
            reply_markup={"inline_keyboard": keyboard},
        )

    async def _cmd_workspace(self, chat_id: int, raw_path: str = "") -> None:
        session = self.state.get_session(chat_id)
        if raw_path:
            target = Path(raw_path).expanduser().resolve()
            if not target.is_dir():
                await self.tg.send_message(
                    chat_id,
                    f"⚠️ Thư mục không tồn tại:\n<code>{escape_html(str(target))}</code>",
                )
                return
            self.state.set_workspace(chat_id, str(target))
            await self.tg.send_message(
                chat_id,
                f"📁 <b>Đã chuyển Workspace sang:</b>\n<code>{escape_html(str(target))}</code>",
            )
            return

        # Gợi ý nhanh các thư mục dự án trong Home và Documents
        candidates: list[str] = []
        home = Path.home()
        docs = home / "Documents"
        for base in [home, docs]:
            if base.is_dir():
                if str(base) not in candidates:
                    candidates.append(str(base))
                try:
                    for sub in sorted(base.iterdir()):
                        if sub.is_dir() and not sub.name.startswith("."):
                            if (sub / ".git").exists() or base == docs:
                                candidates.append(str(sub))
                except OSError:
                    pass

        candidates = candidates[:10]
        self._workspace_candidates[chat_id] = candidates

        keyboard: list[list[dict[str, str]]] = []
        for idx, folder in enumerate(candidates):
            prefix = "✅ " if Path(folder) == Path(session.workspace) else "📁 "
            short_label = folder.replace(str(home), "~")
            keyboard.append([{"text": f"{prefix}{short_label}", "callback_data": f"set_ws:{idx}"}])

        await self.tg.send_message(
            chat_id,
            f"📁 <b>Workspace hiện tại:</b>\n<code>{escape_html(session.workspace)}</code>\n\n"
            f"👉 Chọn nhanh thư mục bên dưới hoặc gõ:\n"
            f"<code>/workspace C:\\đường\\dẫn\\thư_mục</code>",
            reply_markup={"inline_keyboard": keyboard} if keyboard else None,
        )

    async def _cmd_resume(self, chat_id: int, direct_arg: str = "") -> None:
        recent = self.state.list_recent_conversations(limit=6)
        if not recent:
            await self.tg.send_message(chat_id, "⚠️ Không tìm thấy cuộc hội thoại nào trong lịch sử Antigravity.")
            return

        if direct_arg.isdigit():
            idx = int(direct_arg) - 1
            if 0 <= idx < len(recent):
                chosen = recent[idx]
                self.state.set_conversation(chat_id, chosen["id"])
                await self.tg.send_message(
                    chat_id,
                    f"📂 <b>Đã khôi phục hội thoại:</b> <i>{escape_html(chosen['title'])}</i>\n"
                    f"ID: <code>{escape_html(chosen['id'])}</code>",
                )
                return

        session = self.state.get_session(chat_id)
        lines = ["📂 <b>Các cuộc hội thoại gần nhất:</b>\n"]
        keyboard: list[list[dict[str, str]]] = []

        for idx, item in enumerate(recent, start=1):
            is_current = item["id"] == session.conversation_id
            mark = "✅ " if is_current else ""
            lines.append(
                f"<b>{idx}.</b> {mark}<code>{escape_html(item['title'])}</code>\n"
                f"   <i>Cập nhật: {item['updated_at']}</i>"
            )
            keyboard.append(
                [
                    {
                        "text": f"{mark}{idx}. {item['title'][:32]}",
                        "callback_data": f"resume_conv:{item['id']}",
                    }
                ]
            )

        lines.append("\n👉 <i>Bấm vào hội thoại bên dưới để tiếp tục:</i>")
        await self.tg.send_message(
            chat_id,
            "\n".join(lines),
            reply_markup={"inline_keyboard": keyboard},
        )
