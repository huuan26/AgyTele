from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.formatter import escape_html, markdown_to_telegram_html
from src.state_manager import StateManager
from src.telegram_api import TelegramClient


def find_agy_binary() -> str:
    """Tìm đường dẫn thực thi của `agy` trên hệ thống."""
    found = shutil.which("agy") or shutil.which("agy.exe")
    return found or "agy"


async def fetch_available_models() -> list[tuple[str, str]]:
    """
    Gọi `agy models` trực tiếp bằng subprocess (không cần node-pty).
    Trả về danh sách các cặp (model_id, display_name).
    """
    agy_bin = find_agy_binary()
    proc = await asyncio.create_subprocess_exec(
        agy_bin,
        "models",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Lệnh `agy models` quá thời gian chờ (15s).")

    output = stdout_bytes.decode("utf-8", errors="replace")
    models: list[tuple[str, str]] = []
    for line in output.splitlines():
        clean = line.strip()
        if not clean or "Fetching available models" in clean:
            continue
        if "\t" in clean:
            model_id, display_name = clean.split("\t", 1)
            models.append((model_id.strip(), display_name.strip()))
        else:
            models.append((clean, clean))
    return models


def format_tool_status(tool_name: str, params: dict[str, Any]) -> str:
    """Biến đổi thông tin gọi Tool từ stream-json thành dòng trạng thái trực quan trên Telegram."""
    short_name = tool_name.split(":")[-1]

    if short_name in ("run_command", "unsandboxed"):
        cmd = str(params.get("CommandLine") or params.get("toolSummary") or "")
        if len(cmd) > 55:
            cmd = cmd[:52] + "..."
        return f"⚡ <b>Chạy lệnh:</b> <code>{escape_html(cmd)}</code>"

    if short_name in ("read_file", "view_file"):
        file_path = str(params.get("Path") or params.get("AbsolutePath") or "")
        base = Path(file_path).name if file_path else "file"
        return f"📄 <b>Đọc file:</b> <code>{escape_html(base)}</code>"

    if short_name in ("write_file", "write_to_file", "edit_file", "replace_file_content", "multi_replace_file_content"):
        file_path = str(params.get("Path") or params.get("TargetFile") or "")
        base = Path(file_path).name if file_path else "file"
        return f"💾 <b>Cập nhật file:</b> <code>{escape_html(base)}</code>"

    if short_name in ("grep_search", "find_by_name"):
        query = str(params.get("Query") or params.get("Pattern") or "")
        return f"🔎 <b>Tìm kiếm mã nguồn:</b> <code>{escape_html(query[:40])}</code>"

    if short_name == "search_web":
        query = str(params.get("query") or "")
        return f"🌐 <b>Tìm kiếm Web:</b> <i>{escape_html(query[:45])}</i>"

    if short_name == "list_dir":
        dir_path = str(params.get("DirectoryPath") or "")
        base = Path(dir_path).name if dir_path else dir_path
        return f"📂 <b>Duyệt thư mục:</b> <code>{escape_html(base)}</code>"

    if short_name in ("invoke_subagent", "manage_subagents"):
        role = str(params.get("Role") or "Subagent")
        return f"🤖 <b>Khởi chạy Subagent:</b> <code>{escape_html(role)}</code>"

    summary = str(params.get("toolSummary") or "")
    if summary:
        return f"⚙️ <b>{escape_html(short_name)}:</b> <i>{escape_html(summary)}</i>"
    return f"⚙️ <b>Đang thực thi:</b> <code>{escape_html(short_name)}</code>"


@dataclass
class QueuedPrompt:
    chat_id: int
    prompt_text: str
    force_new: bool = False


@dataclass
class ActiveJob:
    process: asyncio.subprocess.Process | None = None
    cancelled: bool = False
    tool_history: list[str] = field(default_factory=list)


class AgyBridge:
    """
    Bộ điều phối tiến trình `agy` sử dụng giao thức `--output-format stream-json`.
    - Nhận trực tiếp sự kiện JSON theo thời gian thực từ stdout (không cần đọc lén ổ cứng).
    - Hỗ trợ hàng đợi (Queue) theo từng chat_id.
    - Hỗ trợ hủy lệnh đang chạy ngay lập tức (/stop hoặc bấm nút Inline).
    """

    def __init__(self, tg: TelegramClient, state: StateManager) -> None:
        self.tg = tg
        self.state = state
        self._queues: dict[int, list[QueuedPrompt]] = {}
        self._active_jobs: dict[int, ActiveJob] = {}

    def is_busy(self, chat_id: int) -> bool:
        return chat_id in self._active_jobs

    async def stop_task(self, chat_id: int) -> bool:
        """Dừng tiến trình `agy` đang chạy cho chat_id và xóa hàng đợi."""
        self._queues.pop(chat_id, None)
        job = self._active_jobs.get(chat_id)
        if not job:
            return False

        job.cancelled = True
        if job.process and job.process.returncode is None:
            try:
                job.process.terminate()
                await asyncio.sleep(0.3)
                if job.process.returncode is None:
                    job.process.kill()
            except ProcessLookupError:
                pass
        return True

    async def stop_all(self) -> None:
        """Dọn dẹp toàn bộ tiến trình đang chạy khi tắt Bot."""
        for chat_id in list(self._active_jobs.keys()):
            await self.stop_task(chat_id)

    async def enqueue_prompt(self, chat_id: int, prompt_text: str, force_new: bool = False) -> None:
        """Đưa yêu cầu vào hàng đợi hoặc chạy ngay nếu Agent đang rảnh."""
        item = QueuedPrompt(chat_id=chat_id, prompt_text=prompt_text, force_new=force_new)

        if self.is_busy(chat_id):
            queue = self._queues.setdefault(chat_id, [])
            queue.append(item)
            pos = len(queue)
            preview = escape_html(prompt_text[:80] + ("..." if len(prompt_text) > 80 else ""))
            await self.tg.send_message(
                chat_id,
                f"📥 <b>Đã thêm vào hàng đợi (#{pos}):</b>\n<i>{preview}</i>",
            )
            return

        asyncio.create_task(self._worker_loop(item))

    async def _worker_loop(self, first_item: QueuedPrompt) -> None:
        chat_id = first_item.chat_id
        current: QueuedPrompt | None = first_item

        while current is not None:
            job = ActiveJob()
            self._active_jobs[chat_id] = job
            try:
                await self._execute_single_turn(current, job)
            except Exception as exc:
                await self.tg.send_message(
                    chat_id,
                    f"❌ <b>Lỗi thực thi hệ thống:</b>\n<pre>{escape_html(str(exc))}</pre>",
                )
            finally:
                self._active_jobs.pop(chat_id, None)

            queue = self._queues.get(chat_id)
            if queue:
                current = queue.pop(0)
            else:
                current = None

    async def _execute_single_turn(self, item: QueuedPrompt, job: ActiveJob) -> None:
        chat_id = item.chat_id
        session = self.state.get_session(chat_id)

        if item.force_new:
            self.state.set_conversation(chat_id, None)
            session.conversation_id = None

        stop_markup = {
            "inline_keyboard": [
                [{"text": "⏹ Dừng tác vụ đang chạy", "callback_data": "stop_task"}]
            ]
        }

        effective_model = self.state.get_effective_model(chat_id)
        model_display = (
            f"{effective_model} (Đồng bộ theo máy)"
            if session.model in ("auto", "local")
            else session.model
        )

        # 1. Gửi tin nhắn trạng thái ban đầu kèm nút Stop
        status_res = await self.tg.send_message(
            chat_id,
            f"🧠 <b>Antigravity đang xử lý...</b>\n"
            f"• <b>Model:</b> <code>{escape_html(model_display)}</code>\n"
            f"• <b>Workspace:</b> <code>{escape_html(session.workspace)}</code>",
            reply_markup=stop_markup,
        )
        status_msg_id: int | None = None
        if status_res.get("ok") and status_res.get("result"):
            status_msg_id = status_res["result"]["message_id"]

        # 2. Xây dựng danh sách tham số cho `agy` CLI (luôn đặt --output-format trước --print)
        agy_bin = find_agy_binary()
        args: list[str] = [
            "--output-format",
            "stream-json",
        ]

        if session.conversation_id:
            args.extend(["--conversation", session.conversation_id])

        if session.model and session.model.lower() not in ("auto", "local"):
            args.extend(["--model", session.model])
        elif effective_model and effective_model.lower() != "auto":
            args.extend(["--model", effective_model])

        if session.permission_mode == "auto":
            args.append("--dangerously-skip-permissions")
        elif session.permission_mode in ("accept-edits", "plan"):
            args.extend(["--mode", session.permission_mode])

        args.extend(["--print", item.prompt_text])

        cwd = session.workspace if Path(session.workspace).is_dir() else str(Path.home())
        env = {**os.environ, "COLUMNS": "10000"}

        # 3. Khởi chạy subprocess `agy` với buffer limit lớn (16MB) cho các dòng JSON dài
        proc = await asyncio.create_subprocess_exec(
            agy_bin,
            *args,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,
        )
        job.process = proc

        # Vòng lặp gửi hiệu ứng "typing..." định kỳ lên Telegram
        async def _typing_loop() -> None:
            while proc.returncode is None and not job.cancelled:
                await self.tg.send_chat_action(chat_id, "typing")
                await asyncio.sleep(4.0)

        typing_task = asyncio.create_task(_typing_loop())

        last_ui_update = 0.0
        accumulated_deltas: list[str] = []
        final_response_text: str | None = None
        final_usage: dict[str, Any] = {}
        duration_sec: float = 0.0

        async def _update_live_status(headline: str, force: bool = False) -> None:
            nonlocal last_ui_update
            now = time.monotonic()
            if not status_msg_id or (not force and now - last_ui_update < 1.2):
                return
            last_ui_update = now

            lines = [headline]
            if job.tool_history:
                lines.append("\n<b>Hoạt động gần nhất:</b>")
                for step_str in job.tool_history[-5:]:
                    lines.append(f"  • {step_str}")

            await self.tg.edit_message_text(
                chat_id,
                status_msg_id,
                "\n".join(lines),
                reply_markup=stop_markup,
            )

        # 4. Đọc luồng sự kiện NDJSON trực tiếp từ stdout theo thời gian thực
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            if job.cancelled:
                break
            line_str = raw_line.decode("utf-8", errors="replace").strip()
            if not line_str or not line_str.startswith("{"):
                continue

            try:
                event_data = json.loads(line_str)
            except json.JSONDecodeError:
                continue

            event_type = event_data.get("event")

            if event_type == "init":
                conv_id = event_data.get("conversation_id")
                if conv_id:
                    self.state.set_conversation(chat_id, conv_id)

            elif event_type == "step_update":
                step = event_data.get("step_update") or {}
                step_type = step.get("step_type")
                state_str = step.get("state")

                if step_type == "tool" and state_str == "ACTIVE":
                    tool_name = str(step.get("tool_name") or "tool")
                    tool_info = step.get("tool_info") or {}
                    params = tool_info.get("parameters") or {}
                    status_line = format_tool_status(tool_name, params)
                    job.tool_history.append(status_line)
                    await _update_live_status("⚙️ <b>Antigravity đang thực thi công cụ...</b>")

                elif step_type == "agent_response":
                    delta = step.get("text_delta")
                    if delta:
                        accumulated_deltas.append(str(delta))
                        await _update_live_status("✍️ <b>Antigravity đang soạn câu trả lời...</b>")

            elif event_type == "result":
                res_obj = event_data.get("result") or {}
                conv_id = res_obj.get("conversation_id")
                if conv_id:
                    self.state.set_conversation(chat_id, conv_id)
                if res_obj.get("response") is not None:
                    final_response_text = str(res_obj["response"])
                final_usage = res_obj.get("usage") or {}
                duration_sec = float(res_obj.get("duration_seconds") or 0.0)

        typing_task.cancel()
        stderr_bytes = await proc.stderr.read() if proc.stderr else b""
        return_code = await proc.wait()

        # 5. Xử lý nếu người dùng đã bấm nút Dừng (/stop)
        if job.cancelled:
            if status_msg_id:
                await self.tg.edit_message_text(
                    chat_id,
                    status_msg_id,
                    "🛑 <b>Đã dừng tác vụ theo yêu cầu của bạn.</b>",
                )
            return

        # 6. Xóa tin nhắn chờ tạm thời để khung chat luôn gọn gàng
        if status_msg_id:
            await self.tg.delete_message(chat_id, status_msg_id)

        # 7. Kiểm tra lỗi tiến trình
        if return_code != 0 and not final_response_text and not accumulated_deltas:
            err_text = stderr_bytes.decode("utf-8", errors="replace").strip() or f"Mã lỗi: {return_code}"
            await self.tg.send_message(
                chat_id,
                f"❌ <b>Lệnh `agy` kết thúc với lỗi (code {return_code}):</b>\n<pre>{escape_html(err_text[:3000])}</pre>",
            )
            return

        # 8. Lưu thống kê Token & gửi kết quả cuối cùng
        if final_usage:
            self.state.record_usage(chat_id, final_usage, duration_sec)

        output_md = (final_response_text or "".join(accumulated_deltas)).strip()
        if not output_md:
            output_md = "✅ *Đã hoàn thành tác vụ.*"

        formatted_html = markdown_to_telegram_html(output_md)
        await self.tg.send_message(chat_id, formatted_html)
