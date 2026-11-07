<div align="center">

<pre align="center">
 █████╗  ██████╗ ██╗   ██╗████████╗███████╗██╗     ███████╗
██╔══██╗██╔════╝ ╚██╗ ██╔╝╚══██╔══╝██╔════╝██║     ██╔════╝
███████║██║  ███╗ ╚████╔╝    ██║   █████╗  ██║     █████╗  
██╔══██║██║   ██║  ╚██╔╝     ██║   ██╔══╝  ██║     ██╔══╝  
██║  ██║╚██████╔╝   ██║      ██║   ███████╗███████╗███████╗
╚═╝  ╚═╝ ╚═════╝    ╚═╝      ╚═╝   ╚══════╝╚══════╝╚══════╝
</pre>

<p align="center">
  <strong>Pure Python Async Telegram Bridge for Google Antigravity CLI</strong>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square" alt="Python 3.10+" /></a>
  <a href="#purpose"><img src="https://img.shields.io/badge/Dependencies-Zero%20(Stdlib)-success?style=flat-square" alt="Zero Dependencies" /></a>
  <a href="#architecture"><img src="https://img.shields.io/badge/Protocol-Stream--JSON%20(NDJSON)-orange?style=flat-square" alt="Stream-JSON" /></a>
  <a href="#purpose"><img src="https://img.shields.io/badge/Security-Port%209877%20Lock-blueviolet?style=flat-square" alt="Socket Lock" /></a>
</p>

</div>

---

## Purpose

AgyTele is a lightweight, zero-dependency async Telegram bridge designed for the Google Antigravity CLI (`agy`). It connects your local AI coding assistant directly to mobile and desktop Telegram clients without third-party dependencies or runtime bloat.

It continuously bridges your environment to:
- Dispatch coding tasks and chat with Antigravity directly from Telegram via bidirectional NDJSON streaming.
- Stream real-time tool execution telemetry in place and cancel running tasks on demand.
- Switch AI models, project workspaces, and execution permission profiles using inline touch keyboards.
- Automatically track whichever AI model is currently active on your local machine (`settings.json`).

---

## Architecture

```text
  [ Telegram Client (Mobile / Desktop) ]
                     │
         (HTTPS Long Polling via stdlib)
                     ▼
        ┌─────────────────────────┐
        │     AgyTele Daemon      │ ◄── Port 9877 Lock (Localhost)
        └────────────┬────────────┘
                     │
          (Headless stream-json)
                     ▼
        ┌─────────────────────────┐
        │  Antigravity CLI (agy)  │ ──► Real-time Tool Telemetry
        └────────────┬────────────┘
                     │
          (Structured NDJSON Events)
                     ▼
        ┌─────────────────────────┐
        │  Telegram HTML Formatter│ ◄── In-place Live Updates
        └─────────────────────────┘
```

---

## Commands

| Command | Usage | Description |
| :--- | :--- | :--- |
| `/new` | `/new [prompt]` | Reset conversation context and optionally start a new turn |
| `/resume` | `/resume` | Browse and resume recent sessions from the local CLI brain |
| `/model` | `/model [id]` | Select an AI model via inline keyboard or sync with local CLI |
| `/workspace` | `/workspace [path]` | View or switch the active project directory |
| `/mode` | `/mode [mode]` | Set execution permission profile (`auto`, `accept-edits`, `plan`) |
| `/goal` | `/goal <objective>` | Dispatch an autonomous multi-step execution goal |
| `/stop` | `/stop` | Cancel active subprocesses and flush the prompt queue |
| `/status` | `/status` | Display system OS, active model, and connection state |
| `/usage` | `/usage` | View token consumption and turnaround latency |
| `/help` | `/help` | Print the quick reference guide |

---

## Quick Start

### 1. Configuration

Create or update `config.json`:

```json
{
  "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "allowed_user_ids": [6876958198],
  "default_workspace": "C:\\Users\\ADMIN",
  "default_model": "auto",
  "permission_mode": "auto"
}
```

*Note: When `default_model` is set to `"auto"`, AgyTele automatically synchronizes with whichever model is active in your local Antigravity settings.*

### 2. Run

On Windows, double-click `run.bat` or run:

```bash
# Optional interactive wizard:
python setup.py

# Start bridge:
python main.py
```

### 3. Run Unit Tests

```bash
python -m unittest discover -s tests -v
```

---

<div align="center">

**AgyTele &bull; Pure Python Telegram Bridge for Google Antigravity**  
Maintained by [huuan26](https://github.com/huuan26)

</div>
