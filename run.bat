@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run install.bat first!
    pause
    exit /b 1
)

echo Starting Copilot Desktop MCP Server on stdio transport...
.\.venv\Scripts\python.exe -m copilot_desktop_mcp.server %*
