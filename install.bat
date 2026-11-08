@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   Copilot Desktop MCP Server - Windows One-Click Setup
echo ========================================================
echo.

:: Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in PATH!
    echo Please install Python 3.10 or higher from https://python.org
    echo and ensure "Add Python to PATH" is checked during setup.
    pause
    exit /b 1
)

echo [1/4] Checking Python environment...
for /f "tokens=2 delims= " %%v in ('python --version') do set PY_VER=%%v
echo Found Python %PY_VER%

:: Create Virtual Environment
echo [2/4] Setting up virtual environment in .venv...
if not exist ".venv" (
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
)

:: Upgrade pip and install package
echo [3/4] Installing dependencies and MCP tools...
call .\.venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1

echo Installing core tools, Windows extensions, and AI Meeting Minutes suite...
pip install -e ".[full]"
if %errorlevel% neq 0 (
    echo [WARNING] Full install failed, falling back to core Windows dependencies...
    pip install -e ".[windows]"
)

:: Copy configuration files if missing
echo [4/4] Setting up configuration templates...
if not exist "config.yaml" (
    copy config.example.yaml config.yaml >nul
    echo Created config.yaml from config.example.yaml
)
if not exist ".env" (
    copy .env.example .env >nul
    echo Created .env from .env.example
)

echo.
echo ========================================================
echo   Setup Complete! Your Copilot Desktop MCP is ready.
echo ========================================================
echo.
echo  To run the server:
echo    run.bat
echo.
echo  Or configure in Claude Desktop / Cursor / Antigravity:
echo    command: C:\Project\copilot-desktop-mcp\.venv\Scripts\python.exe
echo    args:    ["-m", "copilot_desktop_mcp.server"]
echo.
pause
