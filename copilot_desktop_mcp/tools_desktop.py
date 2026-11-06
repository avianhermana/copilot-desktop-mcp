from __future__ import annotations

import base64
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations
from .tools_workspace import get_workspace_helpers

logger = logging.getLogger("copilot_desktop_mcp.desktop")

_SAFE_PS_START = re.compile(
    r"^(get-|test-|resolve-dnsname|ipconfig|netstat|systeminfo|route\s+print|tracert|whoami)",
    re.IGNORECASE,
)
_BLOCKED_PS_TOKENS = re.compile(
    r"(\b(set|new|remove|start|stop|restart|clear|enable|disable|write|add|rename|move|copy|install|uninstall|update)-"
    r"|[;&`>]|&&|\|\||\biex\b|\binvoke-|\bout-file\b|\bset-content\b|\badd-content\b|\bdel\s+|\brmdir\s+"
    r"|\bformat\s+[a-z]:|\bshutdown\b|\bdiskpart\b|\bpowershell\b|\bcmd\b)",
    re.IGNORECASE,
)
_ALLOWED_PS_PIPE = re.compile(
    r"^(select-object|where-object|sort-object|format-table|format-list|measure-object|group-object|compare-object|out-string|findstr|select|where|sort|ft|fl)(\s|$)",
    re.IGNORECASE,
)


def _diagnostic_ps_is_safe(command: str) -> bool:
    cmd = command.strip()
    if not cmd or len(cmd) > 500:
        return False
    if _BLOCKED_PS_TOKENS.search(cmd):
        return False
    parts = [p.strip() for p in cmd.split("|")]
    if not _SAFE_PS_START.match(parts[0]):
        return False
    for p in parts[1:]:
        if not _ALLOWED_PS_PIPE.match(p):
            return False
    return True


def _dispatch_toast_async(title: str, message: str) -> None:
    def _runner():
        clean_title = re.sub(r"[\r\n']+", " ", title).strip()[:100]
        clean_msg = re.sub(r"[\r\n']+", " ", message).strip()[:250]
        ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName('text')
$textNodes.Item(0).InnerText = @'
{clean_title}
'@
$textNodes.Item(1).InnerText = @'
{clean_msg}
'@
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Copilot Desktop').Show($toast)
"""
        try:
            b64 = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64],
                capture_output=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            logger.warning("Failed to show toast notification: %s", e)

    threading.Thread(target=_runner, daemon=True).start()


def register_desktop_tools(mcp: Any, config: dict[str, Any]) -> None:
    safe_path, _, _, _, _, max_read, _ = get_workspace_helpers(config)
    tesseract_cmd = config.get("ocr", {}).get("tesseract_cmd", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_active_window() -> dict[str, Any]:
        """Inspect the currently focused foreground window on Windows desktop.
        Returns the window title, process name, PID, and screen boundaries."""
        try:
            import psutil
            import win32gui
            import win32process

            hwnd = win32gui.GetForegroundWindow()
            if not hwnd or not win32gui.IsWindowVisible(hwnd):
                return {
                    "active": False,
                    "title": "",
                    "process_name": "",
                    "pid": None,
                    "note": "No active window in foreground (desktop may be locked or idle).",
                }
            title = win32gui.GetWindowText(hwnd).strip()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = ""
            if pid:
                try:
                    proc_name = psutil.Process(pid).name()
                except Exception:
                    pass
            rect = win32gui.GetWindowRect(hwnd)
            return {
                "active": True,
                "hwnd": hwnd,
                "title": title,
                "process_name": proc_name,
                "pid": pid,
                "bounds": {
                    "left": rect[0],
                    "top": rect[1],
                    "right": rect[2],
                    "bottom": rect[3],
                    "width": max(0, rect[2] - rect[0]),
                    "height": max(0, rect[3] - rect[1]),
                },
            }
        except ImportError:
            return {"active": False, "error": "pywin32 / psutil is required for window inspection."}
        except Exception as exc:
            return {"active": False, "error": f"{type(exc).__name__}: {exc}"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_open_windows(max_results: int = 50) -> list[dict[str, Any]]:
        """List visible application windows currently open on desktop with their titles, PIDs, and bounds."""
        try:
            import psutil
            import win32gui
            import win32process

            results: list[dict[str, Any]] = []

            def _enum_callback(hwnd: int, _: Any) -> None:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd).strip()
                if not title:
                    return
                rect = win32gui.GetWindowRect(hwnd)
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                if w <= 10 or h <= 10:
                    return
                proc_name = ""
                pid = None
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid:
                        proc_name = psutil.Process(pid).name()
                except Exception:
                    pass
                results.append({
                    "hwnd": hwnd,
                    "title": title,
                    "process_name": proc_name,
                    "pid": pid,
                    "bounds": {"x": rect[0], "y": rect[1], "width": w, "height": h},
                })

            win32gui.EnumWindows(_enum_callback, None)
            return results[: max(1, min(int(max_results), 100))]
        except ImportError:
            return [{"error": "pywin32 / psutil required for listing open windows."}]
        except Exception as exc:
            return [{"error": f"{type(exc).__name__}: {exc}"}]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def take_screen_snapshot(target: str = "active", output_path: str = "") -> dict[str, Any]:
        """Capture a visual snapshot of the desktop or the currently active window and save as PNG.
        `target` can be 'active' (active window only) or 'screen' (entire virtual desktop)."""
        try:
            from PIL import ImageGrab

            target_mode = target.strip().lower()
            if target_mode not in ("active", "screen"):
                target_mode = "active"

            if output_path:
                out_file = safe_path(output_path)
                out_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_dir = Path.home() / ".copilot-desktop" / "screenshots"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_file = out_dir / f"snapshot_{int(time.time())}.png"

            window_title = ""
            if target_mode == "active":
                try:
                    import win32gui
                    hwnd = win32gui.GetForegroundWindow()
                    if hwnd and win32gui.IsWindowVisible(hwnd):
                        window_title = win32gui.GetWindowText(hwnd).strip()
                        rect = win32gui.GetWindowRect(hwnd)
                        x1, y1, x2, y2 = rect[0], rect[1], rect[2], rect[3]
                        if x2 > x1 and y2 > y1:
                            im = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
                        else:
                            im = ImageGrab.grab(all_screens=True)
                    else:
                        im = ImageGrab.grab(all_screens=True)
                except Exception:
                    im = ImageGrab.grab(all_screens=True)
            else:
                im = ImageGrab.grab(all_screens=True)

            im.save(str(out_file), format="PNG")
            return {
                "status": "success",
                "path": str(out_file),
                "width": im.width,
                "height": im.height,
                "target": target_mode,
                "window_title": window_title,
            }
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def read_image_text(path: str, languages: str = "eng+ind", max_chars: int = 20000) -> str:
        """Extract text from an image (.png/.jpg/.jpeg/.bmp/.webp) using OCR (Tesseract).
        Useful for reading screenshots, diagrams, and scanned forms."""
        p = safe_path(path, must_exist=True)
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"):
            raise ValueError("File must be an image (.png, .jpg, .jpeg, .bmp, .webp, .tiff)")
        if p.stat().st_size > max_read:
            raise ValueError("Image file exceeds maximum allowed read size")

        try:
            from PIL import Image
            import pytesseract

            if os.path.exists(tesseract_cmd):
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

            img = Image.open(str(p))
            text_out = pytesseract.image_to_string(img, lang=languages) or ""
            text_clean = text_out.strip()
            if not text_clean:
                return "=== OCR RESULT: No text detected in image ==="

            truncated = len(text_clean) > max_chars
            body = text_clean[:max_chars]
            result = f"=== OCR EXTRACTED TEXT ===\n{body}\n=== END OCR TEXT ==="
            if truncated:
                result += "\n\n[...content truncated by max_chars limit...]"
            return result
        except Exception as exc:
            return f"OCR processing unavailable or failed: {exc}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_clipboard(max_chars: int = 20000) -> dict[str, Any]:
        """Read text currently copied to the Windows clipboard."""
        try:
            import pyperclip

            content = pyperclip.paste() or ""
            limit = max(100, min(int(max_chars), 100000))
            is_truncated = len(content) > limit
            return {
                "text": content[:limit],
                "char_count": len(content),
                "truncated": is_truncated,
            }
        except Exception as exc:
            return {"error": f"Failed to read clipboard: {exc}", "text": "", "char_count": 0}

    @mcp.tool
    def set_clipboard(text: str) -> dict[str, Any]:
        """Copy the given text into the Windows clipboard."""
        try:
            import pyperclip

            pyperclip.copy(text)
            return {"status": "success", "copied_chars": len(text)}
        except Exception as exc:
            raise RuntimeError(f"Failed to copy to clipboard: {exc}") from exc

    @mcp.tool
    def notify_user(title: str, message: str) -> dict[str, Any]:
        """Display a native Windows Toast Notification popup in the bottom-right corner of the desktop."""
        _dispatch_toast_async(title, message)
        return {"status": "dispatched", "title": title, "message": message}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def run_diagnostic_ps(command: str, timeout_seconds: int = 20) -> dict[str, Any]:
        """Run safe, read-only diagnostic PowerShell queries (e.g. Get-Service, Get-Process,
        Get-NetIPAddress, Get-PSDrive, Test-NetConnection). Mutating commands and script injection are strictly blocked."""
        cmd = command.strip()
        if not _diagnostic_ps_is_safe(cmd):
            raise PermissionError(
                "Command rejected by security policy: only safe read-only queries "
                "(Get-*, Test-*, Resolve-DnsName, ipconfig, netstat, systeminfo) with standard "
                "formatters (Select-Object, Where-Object, Format-Table, etc.) are allowed."
            )

        timeout = max(3, min(int(timeout_seconds), 45))
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "command": cmd,
                "exit_code": result.returncode,
                "stdout": result.stdout[:20000],
                "stderr": result.stderr[:2000],
            }
        except subprocess.TimeoutExpired:
            return {
                "command": cmd,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Diagnostic command timed out after {timeout} seconds.",
            }
        except Exception as exc:
            return {
                "command": cmd,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}",
            }
