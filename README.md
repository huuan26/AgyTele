# Anti-Tele-An ⚡ (Python Bridge cho Antigravity CLI)

Cầu nối điều khiển **Google Antigravity CLI (`agy`)** qua Telegram được viết mới 100% bằng **Python (`asyncio` thuần)**, giúp bạn điều khiển Agent trên máy tính cá nhân từ điện thoại một cách an toàn, minh bạch và dễ dàng tùy biến.

---

## 🌟 Điểm khác biệt về Kiến trúc so với bản JS (`agy-cli-telegram`)

| Tiêu chí | Bản JS gốc (`agy-cli-telegram`) | Bản Python (`Anti-Tele-An`) |
| :--- | :--- | :--- |
| **Giao tiếp với `agy`** | Chạy `--print` dạng text thường, phải cắt chuỗi ANSI & đoán lịch sử bằng `setTimeout` | Dùng chuẩn `--output-format stream-json` (NDJSON), nhận sự kiện có cấu trúc theo thời gian thực |
| **Theo dõi Tool đang chạy** | Dùng `setInterval(1000)` đọc lén 512KB cuối của file `transcript.jsonl` trên ổ cứng | Đọc trực tiếp sự kiện `step_update` (`state="ACTIVE"`) từ luồng `stdout` của tiến trình |
| **Lấy danh sách Model** | Phải cài `node-pty` (C++ native addon) giả lập Terminal ảo | Gọi trực tiếp `agy models` qua `asyncio.create_subprocess_exec` và tạo nút bấm Inline Keyboard |
| **Thư viện phụ thuộc** | `node-pty`, `inquirer`, `node-telegram-bot-api` | **0 thư viện ngoài** (100% Python Standard Library: `asyncio`, `urllib.request`, `json`, `pathlib`) |
| **Hủy tác vụ đang chạy** | Không hỗ trợ | Hỗ trợ lệnh `/stop` và nút bấm `[⏹ Dừng tác vụ đang chạy]` ngay dưới tin nhắn trạng thái |
| **Đổi thư mục dự án** | Cố định tại thư mục lúc bật bot | Hỗ trợ `/workspace` chuyển đổi qua lại giữa các dự án ngay trên điện thoại |
| **Cơ chế Bật / Tắt** | Hướng tới chạy 24/7 qua PM2 | Chỉ chạy khi bạn bật Terminal; tự động xả bỏ tin nhắn cũ lúc tắt máy & báo hiệu khi bật/tắt |

---

## 🏗 Sơ đồ Luồng hoạt động (System Flow)

```text
[Điện thoại Telegram]
        │
        ▼ (Long Polling qua src/telegram_api.py)
  [main.py] ──► Kiểm tra Single Instance (Port 9877)
        │   ──► Xóa tin nhắn tồn đọng lúc tắt máy (clear_old_updates)
        │   ──► Kiểm tra bảo mật Allowlist (allowed_user_ids)
        ▼
  [src/router.py]
        ├──► Lệnh quản trị (/model, /workspace, /resume, /mode, /usage, /stop)
        │       └──► Trả về nút bấm Inline Keyboard trực quan
        │
        └──► Prompt giao việc (/new, /goal, hoặc tin nhắn thường)
                ▼
        [src/agy_bridge.py]
                │  Khởi chạy: `agy --output-format stream-json --model <m> --print "<prompt>"`
                ├──► Sự kiện `init`        ──► Lưu `conversation_id` vào `data/sessions.json`
                ├──► Sự kiện `step_update` ──► Cập nhật Live Status (Tool đang chạy) lên Telegram
                └──► Sự kiện `result`      ──► Thống kê Token Usage & Format HTML trả kết quả
```

---

## 📂 Cấu trúc Thư mục

```text
Anti-Tele-An/
├── main.py                 # Điểm khởi chạy chính (Polling loop, Bảo mật, Graceful Shutdown)
├── setup.py                # Trình hướng dẫn cấu hình nhanh (tạo file config.json)
├── run.bat                 # File chạy nhanh bằng 1 cú đúp chuột trên Windows
├── config.example.json     # File mẫu cấu hình
└── src/
    ├── config.py           # Đọc và kiểm tra tính hợp lệ của config.json
    ├── telegram_api.py     # Async HTTP Client gọi trực tiếp Telegram Bot API
    ├── formatter.py        # Chuyển đổi Markdown -> Telegram HTML (bảo toàn khối code) & cắt tin nhắn dài
    ├── state_manager.py    # Quản lý Session (Conversation ID, Model, Workspace, Token Usage)
    ├── agy_bridge.py       # Quản lý tiến trình `agy --output-format stream-json`, Queue & nút Stop
    └── router.py           # Điều phối các lệnh Slash Commands và sự kiện bấm nút Inline Keyboard
```

---

## 🚀 Hướng dẫn Sử dụng

### 1. Thiết lập lần đầu
Mở Terminal (PowerShell hoặc CMD) tại thư mục dự án và chạy:

```powershell
python setup.py
```
Nhập **Telegram Bot Token** (lấy từ `@BotFather`) và **Telegram User ID** của bạn (lấy từ `@userinfobot`).

### 2. Khởi động Bot (Chỉ khi bạn mở máy và muốn dùng)
Bạn có thể nhấp đúp vào file `run.bat` hoặc chạy lệnh:

```powershell
python main.py
```
* Ngay khi bật, Bot sẽ tự động dọn sạch các tin nhắn cũ gửi trong lúc máy tắt và gửi thông báo **🟢 Anti-Tele-An đã khởi động!** vào Telegram của bạn.
* Khi muốn nghỉ hoặc trước khi tắt máy, bạn chỉ cần nhấn `Ctrl + C` ở cửa sổ Terminal — Bot sẽ tự động dừng mọi tiến trình `agy` đang chạy dở và báo **🔴 Anti-Tele-An đã ngừng hoạt động**.

---

## 🎮 Các lệnh trên Telegram

- `/new [nội dung]` — Tạo cuộc hội thoại mới (Reset Context).
- `/resume` — Hiển thị các cuộc hội thoại gần nhất trong lịch sử Antigravity để chọn tiếp tục.
- `/model` — Hiển thị danh sách AI Model từ `agy models` dưới dạng nút bấm 1 chạm.
- `/workspace [đường_dẫn]` — Xem hoặc chuyển đổi thư mục làm việc (`cwd`) của Agent.
- `/mode` — Chuyển đổi chế độ thực thi (`auto`, `accept-edits`, `plan`).
- `/goal <mục tiêu>` — Giao tác vụ tự động nhiều bước.
- `/stop` — Dừng ngay lập tức tác vụ đang chạy.
- `/usage` — Xem thống kê số lượt chat, Input/Output/Thinking Tokens và thời gian phản hồi.
- `/status` — Xem trạng thái kết nối và cấu hình hiện tại.
