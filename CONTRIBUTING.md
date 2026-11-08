# Contributing to Copilot Desktop MCP 🤝

Thank you for your interest in contributing to **Copilot Desktop MCP**! We welcome all contributions from the community, whether it's adding new tools, fixing bugs, improving documentation, or suggesting new workflows.

---

## 🛠️ Development Setup

1. **Fork and Clone the Repository:**
   ```bash
   git clone https://github.com/your-username/copilot-desktop-mcp.git
   cd copilot-desktop-mcp
   ```

2. **Set Up a Virtual Environment:**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -e ".[dev,windows,meeting]"
   ```

3. **Verify Your Environment:**
   ```bash
   python -m compileall copilot_desktop_mcp
   ```

---

## 📐 Tool Design Guidelines

When adding a new tool to the MCP server, please follow these core architectural rules:

1. **Safety First:**
   * Never execute arbitrary, unvalidated shell strings.
   * Enforce filesystem boundaries using `get_workspace_helpers(config)` and `safe_path()`.
   * Never bypass the sandbox or access unauthorized user paths.

2. **Audit & Secret Redaction:**
   * Ensure any sensitive arguments (tokens, passwords, keys) follow naming patterns caught by `AuditLoggingMiddleware`.

3. **Type Annotations & Documentation:**
   * All tools must have explicit Python type annotations.
   * Provide clear docstrings explaining arguments and expected return structures, as LLMs use these docstrings to decide when and how to call your tool.

---

## 🚀 Submitting a Pull Request (PR)

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feature/my-cool-tool
   ```
2. Commit your changes with clear messages (e.g. `feat: add network traceroute tool`).
3. Push to your fork and submit a Pull Request against the `main` branch.
4. Describe your changes, the motivation, and provide verification evidence.

---

## 💬 Code of Conduct

Be kind, respectful, and constructive. We are building open-source software to empower everyone!
