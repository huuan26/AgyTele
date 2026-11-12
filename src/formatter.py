from __future__ import annotations

import html
import re

MAX_TELEGRAM_LENGTH = 4000


def escape_html(text: str) -> str:
    """Escape các ký tự HTML đặc biệt (&, <, >)."""
    if not text:
        return ""
    return html.escape(str(text), quote=False)


def markdown_to_telegram_html(md_text: str) -> str:
    """
    Chuyển đổi Markdown của Antigravity sang định dạng HTML chuẩn của Telegram.
    Sử dụng kỹ thuật Placeholder cho khối code (<pre>, <code>) để tránh làm hỏng
    các ký tự như `__init__` hoặc `*args` bên trong đoạn mã nguồn.
    """
    if not md_text:
        return ""

    placeholders: list[str] = []

    def _save_placeholder(html_fragment: str) -> str:
        idx = len(placeholders)
        placeholders.append(html_fragment)
        return f"\x00CODEBLOCK{idx}END\x00"

    text = md_text.replace("\r\n", "\n")

    # 1. Tách riêng các khối ```code``` trước tiên
    def _replace_fenced_code(match: re.Match) -> str:
        lang = (match.group(1) or "").strip()
        code_body = escape_html(match.group(2).strip("\n"))
        if lang:
            return _save_placeholder(f'<pre><code class="language-{escape_html(lang)}">{code_body}</code></pre>')
        return _save_placeholder(f"<pre>{code_body}</pre>")

    text = re.sub(r"```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```", _replace_fenced_code, text)

    # 2. Tách riêng các đoạn inline `code`
    def _replace_inline_code(match: re.Match) -> str:
        code_body = escape_html(match.group(1))
        return _save_placeholder(f"<code>{code_body}</code>")

    text = re.sub(r"`([^`\n]+)`", _replace_inline_code, text)

    # 3. Escape HTML cho toàn bộ phần văn bản thường còn lại
    text = escape_html(text)

    # 4. Chuyển đổi file:/// links (Telegram không hỗ trợ protocol file:// trong thẻ <a>)
    def _replace_file_link(match: re.Match) -> str:
        label = match.group(1)
        raw_path = match.group(2)
        return f"📄 <b>{label}</b> (<code>{raw_path}</code>)"

    text = re.sub(r"\[([^\]]+)\]\(file:///([^\)]+)\)", _replace_file_link, text)
    text = re.sub(r"\[([^\]]+)\]\(conversation://([^\)]+)\)", r"💬 <b>\1</b> (<code>\2</code>)", text)

    # 5. Chuyển đổi link web chuẩn [label](https://...)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s\)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )

    # 6. Tiêu đề Markdown (# Heading -> 📌 <b>Heading</b>)
    text = re.sub(r"^(?:#{1,6})\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 7. Blockquote (> Quote -> <blockquote>Quote</blockquote>)
    text = re.sub(r"^&gt;\s?(.*)$", r"<blockquote>\1</blockquote>", text, flags=re.MULTILINE)
    text = text.replace("</blockquote>\n<blockquote>", "\n")

    # 8. In đậm (**bold** hoặc __bold__)
    text = re.sub(r"\*\*([^\*\n]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_\n]+)__", r"<b>\1</b>", text)

    # 9. In nghiêng (*italic* hoặc _italic_)
    text = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\b_([^_\n]+)_\b", r"<i>\1</i>", text)

    # 10. Gạch ngang (~~strikethrough~~ hoặc ~strikethrough~)
    text = re.sub(r"~~([^~\n]+)~~", r"<s>\1</s>", text)
    text = re.sub(r"(?<!~)~([^~\n]+)~(?!~)", r"<s>\1</s>", text)

    # 11. Spoiler (||spoiler||)
    text = re.sub(r"\|\|([^|\n]+)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)

    # 12. Gạch chân (++underline++)
    text = re.sub(r"\+\+([^\+\n]+)\+\+", r"<u>\1</u>", text)

    # 13. Khôi phục các khối code từ placeholder
    for idx, fragment in enumerate(placeholders):
        text = text.replace(f"\x00CODEBLOCK{idx}END\x00", fragment)

    return text


def split_html_message(html_text: str, limit: int = MAX_TELEGRAM_LENGTH) -> list[str]:
    """
    Chia nhỏ tin nhắn HTML dài (> 4000 ký tự) theo dòng và tự động đóng/mở lại
    các thẻ HTML (<pre>, <code>, <b>, <i>, <blockquote>, <tg-spoiler>) để không bị lỗi parse_mode=HTML.
    """
    if len(html_text) <= limit:
        return [html_text]

    tag_pattern = re.compile(r"</?([a-zA-Z0-9_-]+)(?:\s+[^>]*)?>")

    def _get_open_tags(chunk_str: str) -> list[tuple[str, str]]:
        stack: list[tuple[str, str]] = []
        for match in tag_pattern.finditer(chunk_str):
            full_tag = match.group(0)
            tag_name = match.group(1).lower()
            if full_tag.startswith("</"):
                if stack and stack[-1][0] == tag_name:
                    stack.pop()
            elif not full_tag.endswith("/>"):
                stack.append((tag_name, full_tag))
        return stack

    chunks: list[str] = []
    current = ""

    for line in html_text.split("\n"):
        # Nếu bản thân 1 dòng quá dài vượt ngưỡng limit
        while len(line) > limit - 200:
            if current:
                open_tags = _get_open_tags(current)
                close_str = "".join(f"</{name}>" for name, _ in reversed(open_tags))
                chunks.append(current + close_str)
                open_str = "".join(full for _, full in open_tags)
                current = open_str
            cut_pos = line.rfind(" ", 0, limit - 200)
            if cut_pos <= 0:
                cut_pos = limit - 200
            part = line[:cut_pos]
            line = line[cut_pos:].lstrip()
            open_tags = _get_open_tags(current + part)
            close_str = "".join(f"</{name}>" for name, _ in reversed(open_tags))
            chunks.append(current + part + close_str)
            current = "".join(full for _, full in open_tags)

        open_tags = _get_open_tags(current)
        close_len = sum(len(f"</{name}>") for name, _ in open_tags)
        reopen_len = sum(len(full) for _, full in open_tags)

        if len(current) + len(line) + 1 + close_len + reopen_len > limit:
            close_str = "".join(f"</{name}>" for name, _ in reversed(open_tags))
            chunks.append(current + close_str)
            open_str = "".join(full for _, full in open_tags)
            current = open_str + line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)

    return chunks
