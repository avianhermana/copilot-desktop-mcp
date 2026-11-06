from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG: dict[str, Any] = {
    "server": {
        "name": "Copilot Desktop MCP",
        "host": "127.0.0.1",
        "port": 8765,
    },
    "workspace": {
        "allowed_roots": [
            str(Path.home()),
        ],
        "blocked_names": [
            ".env",
            ".env.local",
            "id_rsa",
            "id_ed25519",
            "client_secret.json",
        ],
        "blocked_parts": [
            ".git",
            ".ssh",
            ".venv",
            "__pycache__",
            "node_modules",
            "AppData",
            "Windows",
            "$Recycle.Bin",
            "System Volume Information",
        ],
        "max_read_bytes": 2_000_000,
        "max_write_bytes": 2_000_000,
    },
    "web": {
        "allowed_schemes": ["http", "https"],
        "blocked_hosts": ["localhost", "127.0.0.1", "0.0.0.0"],
        "max_response_bytes": 3_000_000,
        "max_return_chars": 8000,
        "timeout_seconds": 15,
    },
    "ocr": {
        "tesseract_cmd": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    },
}


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from config.yaml or fallback to defaults."""
    target_path = config_path or (BASE_DIR / "config.yaml")
    if not target_path.exists():
        example_path = BASE_DIR / "config.example.yaml"
        if example_path.exists():
            target_path = example_path

    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                # Merge loaded over default shallowly/deeply
                merged = DEFAULT_CONFIG.copy()
                for key, val in loaded.items():
                    if isinstance(val, dict) and key in merged and isinstance(merged[key], dict):
                        merged[key] = {**merged[key], **val}
                    else:
                        merged[key] = val
                return merged
        except Exception:
            return DEFAULT_CONFIG.copy()

    return DEFAULT_CONFIG.copy()
