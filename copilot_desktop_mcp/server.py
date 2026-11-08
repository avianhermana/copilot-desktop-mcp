from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

from .config import BASE_DIR, load_config
from .tools_desktop import register_desktop_tools
from .tools_document import register_document_tools
from .tools_meeting import register_meeting_tools
from .tools_self_upgrade import register_self_upgrade_tools
from .tools_telegram import register_telegram_tools
from .tools_utilities import register_utility_tools
from .tools_workspace import register_workspace_tools

load_dotenv(BASE_DIR / ".env")

# --- Audit Logging Setup ---
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
audit_logger = logging.getLogger("copilot_desktop_mcp.audit")
audit_logger.setLevel(logging.INFO)
_handler = logging.FileHandler(LOG_DIR / "audit.log", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s\t%(levelname)s\t%(message)s"))
audit_logger.addHandler(_handler)


class AuditLoggingMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        tool_name = getattr(context.message, "name", "?")
        args = getattr(context.message, "arguments", {}) or {}

        # Redact secrets before writing to audit log
        if isinstance(args, dict):
            args = {
                k: ("***" if re.search(r"token|secret|password|key|auth", str(k), re.I) else v)
                for k, v in args.items()
            }
        args_preview = json.dumps(args, ensure_ascii=False, default=str)[:300]
        try:
            result = await call_next(context)
            audit_logger.info(f"OK\ttool={tool_name}\targs={args_preview}")
            return result
        except Exception as e:
            audit_logger.error(f"ERROR\ttool={tool_name}\targs={args_preview}\terror={e}")
            raise


def create_app(config: dict[str, Any] | None = None) -> FastMCP:
    cfg = config or load_config()
    server_name = cfg.get("server", {}).get("name", "Copilot Desktop MCP")
    mcp = FastMCP(server_name)
    mcp.add_middleware(AuditLoggingMiddleware())

    # Register modular tools
    register_workspace_tools(mcp, cfg)
    register_document_tools(mcp, cfg)
    register_desktop_tools(mcp, cfg)
    register_meeting_tools(mcp, cfg)
    register_telegram_tools(mcp, cfg)
    register_self_upgrade_tools(mcp, cfg)
    register_utility_tools(mcp, cfg)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Copilot Desktop MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport layer protocol (default: stdio for Copilot / Cursor)",
    )
    parser.add_argument("--host", default=None, help="Host to bind for SSE/HTTP")
    parser.add_argument("--port", type=int, default=None, help="Port to bind for SSE/HTTP")
    args = parser.parse_args()

    cfg = load_config()
    mcp = create_app(cfg)

    host = args.host or cfg.get("server", {}).get("host", "127.0.0.1")
    port = args.port or cfg.get("server", {}).get("port", 8765)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    elif args.transport == "http":
        mcp.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
