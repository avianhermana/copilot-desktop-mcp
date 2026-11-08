# Copilot Desktop MCP 🖥️⚡

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Standard](https://img.shields.io/badge/MCP-FastMCP%20Standard-green.svg)](https://modelcontextprotocol.io/)
[![Tools: 50](https://img.shields.io/badge/Tools-50%20Active-brightgreen.svg)](#-key-features--tools-50-modular-tools)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](https://microsoft.com/windows)

A secure, policy-controlled [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects AI assistants (Claude Desktop, Antigravity, Cursor, Windsurf) with native Windows desktop productivity, Microsoft Teams meeting minutes, document synthesis, self-upgrade hot-reloading, and local automation.

---

## 🌟 Why Copilot Desktop MCP?

In most corporate environments, teams run predominantly on Windows, Microsoft 365, and Teams. However, default basic AI assistants lack true local OS integration:
- They cannot directly generate native binary Office documents (`.xlsx`, `.docx`, `.pptx`, `.pdf`) directly onto your workspace.
- They cannot record and transcribe internal Microsoft Teams / Zoom meetings into formatted meeting minutes (notulen) without expensive enterprise add-on subscriptions ($30/user/mo).
- They lack desktop awareness, local OCR, clipboard manipulation, and Telegram alert dispatching.
- They cannot autonomously update or self-upgrade without breaking or requiring manual terminal restarts.

**Copilot Desktop MCP** solves this by providing a unified, open-source bridge with **50 active tools** while enforcing **zero-trust security sandboxing**:
- 🛡️ **Workspace Sandboxing:** Tools can only access files within explicitly allowed directories (`allowed_roots`).
- 🔒 **Secrets Redaction:** Automatically blocks sensitive files (`.env`, SSH keys) from tool access and masks credentials in audit logs.
- 📜 **Full Audit Logging:** Every tool call, argument, and execution outcome is recorded to `logs/audit.log`.
- 🔄 **Safe Self-Upgrade & Hot-Reload:** Automatic backups and isolated subprocess validation before hot-restarting the server.

---

## 🚀 Key Features & Tools (50 Modular Tools)

### 1. 🎙️ AI Meeting Minutes & Teams Audio Transcriber
* **`start_meeting_recording`**: Captures meeting audio (Microsoft Teams, Zoom, Google Meet) via Windows WASAPI loopback (speaker audio of attendees) and/or local microphone.
* **`stop_meeting_recording`**: Finalizes the audio capture and reports recording duration and session ID.
* **`meeting_recording_status`**: Monitors live recording state and lists past saved audio sessions.
* **`transcribe_meeting`**: Local, privacy-preserving transcription via **Faster-Whisper** (supports Indonesian & English), generating synchronized speaker-labeled conversation logs for easy `.docx` notulen generation.

### 2. 📊 Office & Document Synthesis Engine
* **`read_document`**: Parse text from PDF (`.pdf`), Word (`.docx`), Excel (`.xlsx`, `.xlsm`), and PowerPoint (`.pptx`).
* **`create_excel`**: Generate native Excel spreadsheets with formatted headers, auto-fit columns, and multiple sheets.
* **`create_docx`**: Create formatted Word documents from structured blocks (headings, paragraphs, bullet lists, tables).
* **`create_pptx`**: Build PowerPoint slide decks with titles, bullet points, and speaker notes.
* **`create_pdf`**: Render formatted PDF documents.
* **`pdf_merge` & `pdf_split`**: Merge multiple PDFs or split a multi-page PDF into single-page files.

### 3. 📱 Telegram Assistant & Dispatcher
* **`send_telegram_message`**: Dispatch meeting summaries, reminders, or alert notifications directly to your Telegram chat or channel.
* **`send_telegram_document`**: Push generated reports (`.xlsx`, `.docx`, `.pdf`) directly to your mobile Telegram.
* **`test_telegram_connection`**: Validate bot credentials and verify API reachability.

### 4. 🔄 Autonomous Self-Upgrade & Hot-Reload
* **`apply_self_update`**: Atomic upgrade: creates a timestamped backup snapshot, validates syntax, and restarts the server process.
* **`restart_self`**: Hot-restart the MCP server in background so newly installed tools or code edits activate immediately.
* **`backup_self`**: Snapshot current code and configuration into `backups/`.
* **`list_backups`**: View and audit previous backup snapshots.
* **`restore_backup`**: Instant rollback to any previous working state if an error is detected.
* **`validate_pending_changes`**: Syntax compilation check in an isolated subprocess to prevent breaking live agents.
* **`check_git_updates`**: Check if newer commits are available on GitHub remote.
* **`pull_git_update`**: Pull latest GitHub updates with automatic rollback protection.

### 5. 👁️ Desktop Awareness & OCR
* **`take_screen_snapshot`**: Capture the active window or full virtual screen as PNG.
* **`read_image_text`**: Optical Character Recognition (OCR) via Tesseract for extracting text from screenshots and diagrams.
* **`get_active_window`**: Inspect the currently focused foreground application (title, PID, process name, bounds).
* **`list_open_windows`**: Enumerate visible application windows currently running on the desktop.
* **`get_clipboard` & `set_clipboard`**: Seamlessly read and write text to the Windows clipboard.
* **`notify_user`**: Trigger native Windows Toast Notification popups.
* **`run_diagnostic_ps`**: Execute safe, read-only diagnostic PowerShell queries (Get-*, Test-*, ipconfig, systeminfo).

### 6. 💻 Productivity Apps & Git Manager
* **`open_app`**: Launch whitelisted desktop applications (`vscode`, `notepad`, `calc`, `excel`, `word`, `powerpoint`, `terminal`).
* **`git_status`**: View short git status and branch info for workspaces.
* **`git_diff`**: View file change statistics and diffs.
* **`git_log`**: Inspect recent git commit logs.

### 7. 🛡️ Sandboxed Workspace Operations
* **`list_directory`**: Safely explore folders within allowed project roots.
* **`read_file` & `write_file`**: Read and write plain text files with strict byte limits.
* **`apply_text_replacement`**: Perform precise, single-occurrence text replacements in files.
* **`search_files`**: Fast regex/text search across codebases.
* **`create_archive`**: Compress files and directories into `.zip` archives.
* **`create_sqlite`**: Provision local SQLite databases with predefined schemas and data.
* **`fetch_url`**: Read and extract cleaned readable text from public web pages.

### 8. 🧰 Daily Smart Utilities
* **`system_status`**: Real-time CPU, RAM, and Disk utilization metrics.
* **`disk_usage_report`**: Identify which subdirectories are consuming the most disk space.
* **`create_qrcode`**: Instantly generate QR codes for links or text.
* **`calculate`**: Safe AST-based mathematical expression evaluator.
* **`unit_convert`**: Convert lengths, weights, volumes, and temperatures.
* **`ping_host` & `tcp_port_check` & `dns_lookup`**: Essential network diagnostics.

---

## 📦 Installation & Quickstart

### Prerequisites
- Windows 10 / 11
- Python 3.10 or higher
- *(Optional)* [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) for OCR capability.

### ⚡ Method A: One-Click Installer (Recommended)
1. Clone the repository:
   ```bash
   git clone https://github.com/avianhermana/copilot-desktop-mcp.git
   cd copilot-desktop-mcp
   ```
2. Double-click `install.bat`.
   * Automatically configures virtual environment `.venv`.
   * Installs core packages, Windows extensions, and Meeting Minutes suite.
   * Generates default `config.yaml` and `.env` templates.

### 🛠️ Method B: Manual Setup
```bash
python -m venv .venv
.\.venv\Scripts\activate

# Install all components (including audio recorder & whisper)
pip install -e ".[full]"

# Setup configuration
copy config.example.yaml config.yaml
copy .env.example .env
```

---

## 🔌 Integration with MCP Clients

### 1. Claude Desktop
Add this to your `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "copilot-desktop": {
      "command": "C:\\Project\\copilot-desktop-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "copilot_desktop_mcp.server",
        "--transport",
        "stdio"
      ],
      "cwd": "C:\\Project\\copilot-desktop-mcp"
    }
  }
}
```

### 2. Antigravity / Cursor / Windsurf
Configure your agent settings or MCP configuration:

```json
{
  "mcpServers": {
    "copilot-desktop": {
      "command": "C:/Project/copilot-desktop-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "copilot_desktop_mcp.server"],
      "cwd": "C:/Project/copilot-desktop-mcp"
    }
  }
}
```

---

## ⚙️ Configuration (`config.yaml`)

```yaml
workspace:
  allowed_roots:
    - "C:\\Project"   # Only paths under allowed_roots can be accessed
  blocked_names:
    - ".env"
    - "id_rsa"
  max_read_bytes: 2000000   # 2 MB limit
  max_write_bytes: 2000000

meeting:
  recordings_dir: "C:\\Project\\copilot-desktop-mcp\\recordings"
  default_whisper_model: "small"

ocr:
  tesseract_cmd: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

apps:
  allowed:
    vscode: "code"
    notepad: "notepad.exe"
    excel: "excel.exe"
```

---

## 🔒 Security Architecture

* **Least Privilege:** Destructive commands (reboots, keyboard/mouse hijacking, arbitrary shell scripts) are completely omitted.
* **Path Traversal Protection:** Absolute path canonicalization ensures no escaping outside `allowed_roots`.
* **Safe Subprocesses:** Diagnostic tools enforce strict command whitelisting to eliminate shell injection risks.
* **Confidentiality:** Audio recordings and OCR transcripts are processed 100% locally on your machine.
* **Safe Hot-Reload:** Code changes are verified for syntax validity in a fresh subprocess before any server restart.

---

## 🤝 Contributing

Contributions are what make the open-source community an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**!

Please see our [CONTRIBUTING.md](CONTRIBUTING.md) guide for details on our code of conduct and development setup.

---

## ☕ Support & Sponsorship

If this project saved you time, enhanced your AI workflow, or helped you in your daily work, consider supporting its development:

[![Buy Me a Coffee]
[![Saweria](https://img.shields.io/badge/Saweria-Support%20via%20QRIS-orange?style=for-the-badge)](https://saweria.co/avianhermana)
[![Trakteer](https://img.shields.io/badge/Trakteer-Support%20Author-red?style=for-the-badge)](https://trakteer.id/avianhermana)

Your support helps maintain the project, add more desktop tools, and keep it 100% open-source!

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
