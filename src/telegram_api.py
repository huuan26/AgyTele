from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any

from src.formatter import split_html_message


class TelegramClient:
    """
    Async HTTP Client gọn nhẹ giao tiếp trực tiếp với Telegram Bot API.
    Sử dụng chuẩn asyncio + urllib của Python để không phụ thuộc thư viện ngoài,
    kiểm soát 100% luồng request, timeout và cơ chế tự động fallback khi lỗi HTML.
    """

    def __init__(self, bot_token: str) -> None:
        if not bot_token:
            raise ValueError("Bot token không được để trống.")
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def _sync_post(self, method: str, payload: dict[str, Any], http_timeout: float) -> dict[str, Any]:
        url = f"{self.base_url}/{method}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=http_timeout) as resp:
                raw_body = resp.read().decode("utf-8")
                return json.loads(raw_body)
        except urllib.error.HTTPError as err:
            try:
                err_body = err.read().decode("utf-8")
                return json.loads(err_body)
            except Exception:
                return {"ok": False, "error_code": err.code, "description": str(err)}
        except Exception as exc:
            return {"ok": False, "description": str(exc)}

    async def call_api(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        http_timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Gọi API Telegram bất đồng bộ (non-blocking)."""
        return await asyncio.to_thread(self._sync_post, method, payload or {}, http_timeout)

    async def _send_single_chunk(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        res = await self.call_api("sendMessage", payload)
        if not res.get("ok"):
            # Fallback: Nếu thẻ HTML không hợp lệ, tự động lọc thẻ và gửi dạng văn bản thuần
            plain_text = re.sub(r"<[^>]+>", "", text)
            fallback_payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": plain_text,
                "disable_web_page_preview": True,
            }
            if reply_markup:
                fallback_payload["reply_markup"] = reply_markup
            res = await self.call_api("sendMessage", fallback_payload)
        return res

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Gửi tin nhắn HTML tới Telegram.
        Tự động chia nhỏ nếu vượt quá 4000 ký tự và gắn reply_markup vào phần cuối.
        """
        chunks = split_html_message(str(text))
        last_res: dict[str, Any] = {"ok": False}
        for idx, chunk in enumerate(chunks):
            is_last = idx == len(chunks) - 1
            markup = reply_markup if is_last else None
            last_res = await self._send_single_chunk(chat_id, chunk, reply_markup=markup)
        return last_res

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cập nhật nội dung tin nhắn đang hiển thị (dùng cho Live Status)."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        res = await self.call_api("editMessageText", payload)
        if not res.get("ok") and "message is not modified" not in str(res.get("description", "")).lower():
            plain_text = re.sub(r"<[^>]+>", "", text)
            payload.pop("parse_mode", None)
            payload["text"] = plain_text
            res = await self.call_api("editMessageText", payload)
        return res

    async def delete_message(self, chat_id: int | str, message_id: int) -> dict[str, Any]:
        return await self.call_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

    async def send_chat_action(self, chat_id: int | str, action: str = "typing") -> dict[str, Any]:
        return await self.call_api("sendChatAction", {"chat_id": chat_id, "action": action}, http_timeout=5.0)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text
        return await self.call_api("answerCallbackQuery", payload)

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        return await self.call_api("setMyCommands", {"commands": commands})

    async def delete_webhook(self) -> dict[str, Any]:
        return await self.call_api("deleteWebhook", {"drop_pending_updates": False})

    async def get_updates(self, offset: int = 0, timeout: int = 25) -> dict[str, Any]:
        return await self.call_api(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query"],
            },
            http_timeout=float(timeout + 10),
        )

    async def clear_old_updates(self) -> int:
        """
        Xả bỏ toàn bộ tin nhắn cũ tồn đọng trong thời gian máy tính tắt.
        Đảm bảo Bot chỉ xử lý các lệnh mới gửi từ lúc bật chương trình.
        """
        res = await self.call_api("getUpdates", {"limit": 100, "timeout": 0})
        if res.get("ok") and res.get("result"):
            updates = res["result"]
            if updates:
                next_offset = updates[-1]["update_id"] + 1
                await self.call_api("getUpdates", {"offset": next_offset, "limit": 1, "timeout": 0})
                return next_offset
        return 0
