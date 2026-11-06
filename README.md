# Copilot Desktop MCP 🖥️⚡

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Standard](https://img.shields.io/badge/MCP-FastMCP%20Standard-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](https://microsoft.com/windows)

A secure, policy-controlled [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects AI assistants (Claude Desktop, Antigravity, Cursor, Windsurf) with native Windows desktop productivity, document generation, and workspace tooling.

---

## 🌟 Why Copilot Desktop MCP?

Most LLM models can reason about code and data, but cannot natively generate native binary office documents (`.xlsx`, `.docx`, `.pptx`, `.pdf`), inspect open desktop windows, or capture screen contexts.

**Copilot Desktop MCP** bridges this gap while enforcing **strict security sandboxing**:
- 🛡️ **Workspace Sandboxing:** Tools can only read and write within explicitly allowed directories (`allowed_roots`).
- 🔒 **Secrets Redaction:** Automatically blocks sensitive files (`.env`, SSH keys) from tool access and redacts tokens in audit logs.
- 📜 **Full Audit Logging:** Every tool call, argument, and execution outcome is recorded to `logs/audit.log`.

---

## 🚀 Key Features & Tools

### 1. 📊 Office & Document Suite
* **`read_document`**: Parse text from PDF (`.pdf`), Word (`.docx`), Excel (`.xlsx`, `.xlsm`), and PowerPoint (`.pptx`).
* **`create_excel`**: Generate native Excel spreadsheets with formatted headers, auto-fit columns, and multiple sheets.
* **`create_docx`**: Create formatted Word documents from structured blocks (headings, paragraphs, bullet lists, tables).
* **`create_pptx`**: Build PowerPoint slide decks with titles, bullet points, and speaker notes.
* **`create_pdf`**: Render formatted PDF documents.
* **`pdf_merge` & `pdf_split`**: Merge multiple PDFs or split a PDF into individual pages.

### 2. 👁️ Desktop Awareness & OCR
* **`take_screen_snapshot`**: Capture the active window or full virtual screen as PNG.
* **`read_image_text`**: Optical Character Recognition (OCR) via Tesseract for extracting text from screenshots and diagrams.
* **`get_active_window`**: Inspect the currently focused foreground application (title, PID, process name, bounds).
* **`list_open_windows`**: Enumerate visible application windows currently running on the desktop.
* **`get_clipboard` & `set_clipboard`**: Seamlessly read and write text to the Windows clipboard.
* **`notify_user`**: Trigger native Windows Toast Notification popups.

### 3. 🛡️ Sandboxed Workspace Operations
* **`list_directory`**: Safely explore folders within allowed project roots.
* **`read_file` & `write_file`**: Read and write plain text files with strict byte limits.
* **`apply_text_replacement`**: Perform precise, single-occurrence text replacements in files.
* **`search_files`**: Fast regex/text search across codebases.
* **`create_archive`**: Compress files and directories into `.zip` archives.
* **`create_sqlite`**: Provision local SQLite databases with predefined schemas and data.
* **`fetch_url`**: Read and extract cleaned readable text from public web pages.

### 4. 🧰 Daily Smart Utilities
* **`system_status`**: Real-time CPU, RAM, and Disk utilization metrics.
* **`disk_usage_report`**: Identify which subdirectories are consuming the most disk space.
* **`create_qrcode`**: Instantly generate QR codes for links or text.
* **`calculate`**: Safe AST-based mathematical expression evaluator.
* **`ping_host` & `tcp_port_check` & `dns_lookup`**: Essential network diagnostics.

---

## 📦 Installation & Quickstart

### Prerequisites
- Windows 10 / 11
- Python 3.10 or higher
- *(Optional)* [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) for OCR capability.

### Setup
```bash
# Clone the repository
git clone https://github.com/your-username/copilot-desktop-mcp.git
cd copilot-desktop-mcp

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install package and dependencies
pip install -e ".[windows]"

# Setup configuration
copy config.example.yaml config.yaml
```

---

## 🔌 Integration with MCP Clients

### 1. Claude Desktop
Add this to your `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "copilot-desktop": {
      "command": "python",
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
      "command": "python",
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

ocr:
  tesseract_cmd: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
```

---

## 🔒 Security Architecture

* **Least Privilege:** Destructive commands (e.g. system reboots, mouse/keyboard hijacking, arbitrary shell scripts) are completely omitted.
* **Path Traversal Protection:** Absolute path canonicalization ensures no escaping outside `allowed_roots`.
* **Safe Subprocesses:** Commands executed via diagnostic tools use explicit arguments lists (`subprocess.run`), preventing shell injection.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
