from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations

logger = logging.getLogger("copilot_desktop_mcp.self_upgrade")

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _delayed_restart(delay: float = 1.5) -> None:
    time.sleep(delay)
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    server_module = "copilot_desktop_mcp.server"
    cmd = [sys.executable, "-m", server_module]
    subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        creationflags=creationflags,
        close_fds=True,
    )
    os._exit(0)


def register_self_upgrade_tools(mcp: Any, config: dict[str, Any]) -> None:
    apps_allowed = config.get("apps", {}).get("allowed", {
        "vscode": "code",
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "excel": "excel.exe",
        "word": "winword.exe",
        "powerpoint": "powerpnt.exe",
        "terminal": "wt.exe",
    })

    @mcp.tool
    def backup_self() -> dict[str, Any]:
        """Create a timestamped backup snapshot of the server codebase and configuration before applying edits."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = BACKUP_DIR / ts
        dest.mkdir(parents=True, exist_ok=True)

        copied = []
        # Copy core python files
        src_pkg = BASE_DIR / "copilot_desktop_mcp"
        dest_pkg = dest / "copilot_desktop_mcp"
        dest_pkg.mkdir(exist_ok=True)
        for py_file in src_pkg.glob("*.py"):
            shutil.copy2(py_file, dest_pkg / py_file.name)
            copied.append(f"copilot_desktop_mcp/{py_file.name}")

        for root_file in ("pyproject.toml", "config.yaml", "README.md"):
            src_f = BASE_DIR / root_file
            if src_f.exists():
                shutil.copy2(src_f, dest / root_file)
                copied.append(root_file)

        return {
            "status": "success",
            "backup_id": ts,
            "backup_path": str(dest),
            "files_backed_up": copied,
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_backups() -> list[dict[str, Any]]:
        """List available local codebase backups in reverse chronological order."""
        if not BACKUP_DIR.exists():
            return []

        out = []
        for d in sorted(BACKUP_DIR.iterdir(), key=lambda x: x.name, reverse=True):
            if d.is_dir():
                files = []
                for p in d.rglob("*"):
                    if p.is_file():
                        files.append(str(p.relative_to(d)))
                out.append({"backup_id": d.name, "files_count": len(files), "files": files})
        return out

    @mcp.tool
    def restore_backup(backup_id: str) -> dict[str, Any]:
        """Restore codebase and configuration from a given backup_id. Call restart_self afterward."""
        src_dir = BACKUP_DIR / backup_id
        if not src_dir.is_dir():
            raise ValueError(f"Backup ID '{backup_id}' does not exist. Call list_backups to view options.")

        restored = []
        # Restore package files
        backup_pkg = src_dir / "copilot_desktop_mcp"
        if backup_pkg.is_dir():
            target_pkg = BASE_DIR / "copilot_desktop_mcp"
            for f in backup_pkg.glob("*.py"):
                shutil.copy2(f, target_pkg / f.name)
                restored.append(f"copilot_desktop_mcp/{f.name}")

        for root_file in ("pyproject.toml", "config.yaml", "README.md"):
            src_f = src_dir / root_file
            if src_f.exists():
                shutil.copy2(src_f, BASE_DIR / root_file)
                restored.append(root_file)

        return {
            "status": "restored",
            "backup_id": backup_id,
            "restored_files": restored,
            "next_step": "Run validate_pending_changes and restart_self to apply.",
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def validate_pending_changes() -> dict[str, Any]:
        """Verify that on-disk code is syntactically valid and compiles cleanly without affecting running process."""
        result = subprocess.run(
            [sys.executable, "-m", "compileall", str(BASE_DIR / "copilot_desktop_mcp")],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
            errors="replace",
        )
        is_valid = result.returncode == 0
        return {
            "valid": is_valid,
            "output": result.stdout.strip() or result.stderr.strip(),
            "note": "Syntax is clean and ready for restart." if is_valid else "Syntax errors detected! Do not restart.",
        }

    @mcp.tool
    def restart_self() -> dict[str, Any]:
        """Gracefully hot-restart the MCP server process so code changes or newly installed tools take effect immediately."""
        threading.Thread(target=_delayed_restart, daemon=True).start()
        return {
            "status": "restarting",
            "delay_seconds": 1.5,
            "message": "Server process is restarting in the background. Tools will reload automatically.",
        }

    @mcp.tool
    def apply_self_update(reason: str = "Code update") -> dict[str, Any]:
        """Atomic safe upgrade: creates a backup snapshot, validates syntax, and restarts the server if valid."""
        backup = backup_self()
        validation = validate_pending_changes()

        if not validation["valid"]:
            return {
                "applied": False,
                "backup_id": backup["backup_id"],
                "validation_error": validation["output"],
                "message": "Validation failed. Server NOT restarted. Current code continues running unharmed.",
            }

        logger.info("Applying self update: %s (Backup: %s)", reason, backup["backup_id"])
        restart_self()
        return {
            "applied": True,
            "backup_id": backup["backup_id"],
            "reason": reason,
            "message": "Changes validated successfully. Server is hot-restarting now.",
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_git_updates() -> dict[str, Any]:
        """Check if there are newer commits or updates available on the remote GitHub repository."""
        try:
            # Fetch latest remote references
            subprocess.run(["git", "fetch", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, timeout=15)
            # Compare HEAD against origin/main
            res = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=10,
            )
            counts = res.stdout.strip().split()
            ahead = int(counts[0]) if len(counts) > 0 else 0
            behind = int(counts[1]) if len(counts) > 1 else 0

            return {
                "up_to_date": behind == 0,
                "commits_behind": behind,
                "commits_ahead": ahead,
                "recommendation": "Run pull_git_update to upgrade" if behind > 0 else "Up to date with GitHub",
            }
        except Exception as exc:
            return {"error": f"Failed to check git updates: {exc}"}

    @mcp.tool
    def pull_git_update(auto_restart: bool = True) -> dict[str, Any]:
        """Pull the latest updates from the GitHub repository (`git pull origin main`) with automatic rollback protection."""
        backup = backup_self()
        try:
            res = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode != 0:
                return {"success": False, "git_output": res.stderr.strip(), "backup_id": backup["backup_id"]}

            validation = validate_pending_changes()
            if not validation["valid"]:
                # Revert if remote code fails compilation
                restore_backup(backup["backup_id"])
                return {
                    "success": False,
                    "error": "Pulled code failed compilation check. Rolled back automatically.",
                    "validation_output": validation["output"],
                }

            if auto_restart:
                restart_self()

            return {
                "success": True,
                "git_output": res.stdout.strip(),
                "backup_id": backup["backup_id"],
                "restarted": auto_restart,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "backup_id": backup["backup_id"]}

    @mcp.tool
    def open_app(name: str) -> dict[str, Any]:
        """Launch an approved desktop productivity application (vscode, notepad, calc, excel, word, powerpoint, terminal)."""
        key = name.strip().lower()
        target = apps_allowed.get(key)
        if not target:
            valid_apps = ", ".join(sorted(apps_allowed.keys()))
            raise PermissionError(f"Application '{name}' is not in the approved app list. Allowed: {valid_apps}")

        resolved = shutil.which(target) or target
        try:
            if hasattr(os, "startfile") and Path(resolved).exists():
                os.startfile(resolved)
            else:
                subprocess.Popen([resolved], shell=False)
            return {"status": "launched", "app": key, "executable": resolved}
        except Exception as exc:
            raise RuntimeError(f"Failed to launch application '{name}': {exc}")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def git_status(project_path: str = "") -> dict[str, Any]:
        """Get git status for an approved workspace directory (defaults to current project)."""
        target_dir = Path(project_path).resolve() if project_path else BASE_DIR
        try:
            res = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {"path": str(target_dir), "output": res.stdout.strip()}
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def git_diff(project_path: str = "") -> dict[str, Any]:
        """Get git diff unstaged and staged changes for an approved workspace directory."""
        target_dir = Path(project_path).resolve() if project_path else BASE_DIR
        try:
            res = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {"path": str(target_dir), "stat": res.stdout.strip()}
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def git_log(project_path: str = "", max_commits: int = 15) -> list[dict[str, Any]]:
        """Get recent git commit history for an approved workspace repository."""
        target_dir = Path(project_path).resolve() if project_path else BASE_DIR
        n = max(1, min(int(max_commits), 50))
        try:
            res = subprocess.run(
                ["git", "log", f"-{n}", "--pretty=format:%h|%an|%ar|%s"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=10,
            )
            commits = []
            for line in res.stdout.strip().splitlines():
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3],
                    })
            return commits
        except Exception as exc:
            return [{"error": str(exc)}]
