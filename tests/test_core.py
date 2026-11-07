from __future__ import annotations

import unittest
from pathlib import Path

import tempfile

from src.agy_bridge import format_tool_status
from src.config import AppConfig
from src.formatter import markdown_to_telegram_html, split_html_message
from src.state_manager import StateManager


class TestFormatter(unittest.TestCase):
    def test_code_blocks_preserve_underscores_and_asterisks(self) -> None:
        md = (
            "### Tiêu đề\n"
            "Gọi hàm `def __init__(self, *args, **kwargs):` và `foo_bar_baz` trong **Python**.\n"
            "```python\n"
            "def __main__():\n"
            "    return a * b * c\n"
            "```\n"
            "Xem [config.py](file:///C:/Users/ADMIN/config.py)"
        )
        html_out = markdown_to_telegram_html(md)
        self.assertIn("<b>Tiêu đề</b>", html_out)
        self.assertIn("<code>def __init__(self, *args, **kwargs):</code>", html_out)
        self.assertIn("<code>foo_bar_baz</code>", html_out)
        self.assertIn("<b>Python</b>", html_out)
        self.assertIn("return a * b * c", html_out)
        self.assertIn("📄 <b>config.py</b> (<code>C:/Users/ADMIN/config.py</code>)", html_out)

    def test_split_html_message_balances_tags(self) -> None:
        long_code = "<pre>" + "\n".join(f"line_{i} = {i}" for i in range(500)) + "</pre>"
        chunks = split_html_message(long_code, limit=1000)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertTrue(chunk.startswith("<pre>"))
            self.assertTrue(chunk.endswith("</pre>"))


class TestToolFormatting(unittest.TestCase):
    def test_format_tool_status(self) -> None:
        status1 = format_tool_status("default_api:run_command", {"CommandLine": "git status -s"})
        self.assertIn("git status -s", status1)

        status2 = format_tool_status("default_api:read_file", {"Path": r"C:\Users\ADMIN\main.py"})
        self.assertIn("main.py", status2)


class TestStateManager(unittest.TestCase):
    def test_session_lifecycle(self) -> None:
        cfg = AppConfig(
            bot_token="123:ABC",
            allowed_user_ids={999},
            default_workspace=str(Path.home()),
            default_model="gemini-4-argon-high",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_sessions = Path(tmpdir) / "test_sessions.json"
            sm = StateManager(cfg, sessions_file=tmp_sessions)
            session = sm.get_session(999)
            self.assertEqual(session.model, "gemini-4-argon-high")

            sm.set_model(999, "gemini-3.8-flash-high")
            self.assertEqual(sm.get_session(999).model, "gemini-3.8-flash-high")


if __name__ == "__main__":
    unittest.main()
