from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import httpx
from mcp.types import ToolAnnotations
from .tools_workspace import get_workspace_helpers


def register_telegram_tools(mcp: Any, config: dict[str, Any]) -> None:
    safe_path, _, _, _, _, _, _ = get_workspace_helpers(config)

    telegram_cfg = config.get("telegram", {})
    default_token = os.getenv("TELEGRAM_BOT_TOKEN") or telegram_cfg.get("bot_token", "")
    default_chat_id = os.getenv("TELEGRAM_CHAT_ID") or telegram_cfg.get("default_chat_id", "")

    def _get_credentials(token_arg: str, chat_arg: str) -> tuple[str, str]:
        token = token_arg.strip() if token_arg else default_token
        chat_id = chat_arg.strip() if chat_arg else default_chat_id
        if not token:
            raise ValueError(
                "Telegram Bot Token not configured. Set TELEGRAM_BOT_TOKEN in .env or pass bot_token parameter."
            )
        if not chat_id:
            raise ValueError(
                "Telegram Chat ID not specified. Set TELEGRAM_CHAT_ID in .env or pass chat_id parameter."
            )
        return token, chat_id

    @mcp.tool
    def send_telegram_message(
        message: str,
        chat_id: str = "",
        bot_token: str = "",
        parse_mode: str = "HTML",
    ) -> dict[str, Any]:
        """Send a notification, report, or meeting summary directly to a Telegram user or group chat."""
        token, target_chat = _get_credentials(bot_token, chat_id)
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    url,
                    json={
                        "chat_id": target_chat,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                )
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"Telegram API error: {data.get('description', 'Unknown error')}")
                return {
                    "status": "sent",
                    "message_id": data["result"]["message_id"],
                    "recipient_chat_id": target_chat,
                }
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Network error communicating with Telegram API: {exc}")

    @mcp.tool
    def send_telegram_document(
        file_path: str,
        caption: str = "",
        chat_id: str = "",
        bot_token: str = "",
    ) -> dict[str, Any]:
        """Send a generated document (Excel .xlsx, Word .docx, PowerPoint .pptx, or PDF) directly to Telegram."""
        token, target_chat = _get_credentials(bot_token, chat_id)
        p = safe_path(file_path, must_exist=True)
        if not p.is_file():
            raise ValueError(f"Target path is not a file: {file_path}")

        url = f"https://api.telegram.org/bot{token}/sendDocument"

        try:
            with httpx.Client(timeout=60.0) as client:
                with open(p, "rb") as f:
                    files = {"document": (p.name, f)}
                    data = {"chat_id": target_chat, "caption": caption}
                    resp = client.post(url, data=data, files=files)

                resp_data = resp.json()
                if not resp_data.get("ok"):
                    raise RuntimeError(f"Telegram API error: {resp_data.get('description', 'Unknown error')}")
                return {
                    "status": "document_sent",
                    "file_name": p.name,
                    "file_size_bytes": p.stat().st_size,
                    "recipient_chat_id": target_chat,
                }
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Network error dispatching document to Telegram: {exc}")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def test_telegram_connection(bot_token: str = "") -> dict[str, Any]:
        """Verify Telegram Bot credentials and connection status."""
        token = bot_token.strip() if bot_token else default_token
        if not token:
            return {"connected": False, "error": "No bot token configured. Set TELEGRAM_BOT_TOKEN in .env."}

        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url)
                data = resp.json()
                if data.get("ok"):
                    bot_info = data["result"]
                    return {
                        "connected": True,
                        "bot_name": bot_info.get("first_name"),
                        "username": f"@{bot_info.get('username')}",
                    }
                return {"connected": False, "error": data.get("description")}
        except Exception as exc:
            return {"connected": False, "error": str(exc)}
