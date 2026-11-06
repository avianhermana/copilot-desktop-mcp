from __future__ import annotations

import ast
import operator
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from mcp.types import ToolAnnotations
from .tools_workspace import get_workspace_helpers

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported mathematical expression element: {ast.dump(node)}")


_UNIT_TABLE = {
    ("km", "mi"): 0.621371,
    ("mi", "km"): 1.60934,
    ("m", "ft"): 3.28084,
    ("ft", "m"): 0.3048,
    ("kg", "lb"): 2.20462,
    ("lb", "kg"): 0.453592,
    ("l", "gal"): 0.264172,
    ("gal", "l"): 3.78541,
    ("cm", "in"): 0.393701,
    ("in", "cm"): 2.54,
}


def register_utility_tools(mcp: Any, config: dict[str, Any]) -> None:
    safe_path, _, _, _, _, _, _ = get_workspace_helpers(config)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def calculate(expression: str) -> dict[str, Any]:
        """Evaluate an arithmetic expression safely using abstract syntax tree (AST).
        Supports +, -, *, /, //, %, ** and parentheses. No arbitrary code execution."""
        try:
            tree = ast.parse(expression, mode="eval")
            res = _safe_eval(tree)
            return {"expression": expression, "result": res}
        except Exception as e:
            raise ValueError(f"Failed to evaluate expression: {e}")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def system_status() -> dict[str, Any]:
        """Report CPU utilization, RAM usage, primary disk capacity, and machine uptime."""
        try:
            import psutil

            vm = psutil.virtual_memory()
            root_drive = str(Path.home().anchor or "C:\\")
            du = psutil.disk_usage(root_drive)
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "ram_used_gb": round(vm.used / 1e9, 2),
                "ram_total_gb": round(vm.total / 1e9, 2),
                "disk_free_gb": round(du.free / 1e9, 2),
                "disk_total_gb": round(du.total / 1e9, 2),
                "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
            }
        except ImportError:
            return {"error": "psutil library required for system metrics."}
        except Exception as exc:
            return {"error": str(exc)}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def disk_usage_report(path: str, top_n: int = 10) -> list[dict[str, Any]]:
        """Report the largest immediate subfolders under a given path to help find disk hogs."""
        root = safe_path(path, must_exist=True)
        if not root.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        entries = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            total = 0
            for dirpath, _, files in os.walk(child, onerror=lambda e: None):
                for name in files:
                    try:
                        total += (Path(dirpath) / name).stat().st_size
                    except OSError:
                        pass
            entries.append({"folder": str(child), "size_gb": round(total / 1e9, 3)})

        entries.sort(key=lambda e: e["size_gb"], reverse=True)
        return entries[: max(1, min(int(top_n), 50))]

    @mcp.tool
    def create_qrcode(data: str, path: str, overwrite: bool = False) -> dict[str, Any]:
        """Generate a QR code image (PNG) from text or URL."""
        import qrcode

        out = safe_path(path)
        if out.exists() and not overwrite:
            raise FileExistsError(f"File '{path}' already exists; set overwrite=True.")
        out.parent.mkdir(parents=True, exist_ok=True)
        img = qrcode.make(data)
        img.save(str(out))
        return {"path": str(out), "data_length": len(data), "status": "success"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def unit_convert(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
        """Convert numbers between common units (length: km/mi/m/ft/cm/in, weight: kg/lb, volume: l/gal, temperature: c/f/k)."""
        f, t = from_unit.strip().lower(), to_unit.strip().lower()
        if f == t:
            return {"result": value, "unit": t}

        temp_units = {"c", "f", "k"}
        if f in temp_units and t in temp_units:
            celsius = value if f == "c" else (value - 32) * 5 / 9 if f == "f" else value - 273.15
            result = celsius if t == "c" else celsius * 9 / 5 + 32 if t == "f" else celsius + 273.15
            return {"result": round(result, 4), "unit": t}

        factor = _UNIT_TABLE.get((f, t))
        if factor is None:
            raise ValueError(f"Unsupported conversion: '{from_unit}' -> '{to_unit}'")
        return {"result": round(value * factor, 6), "unit": t}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def ping_host(host: str, count: int = 4) -> dict[str, Any]:
        """Ping a host (IP or domain name) and report latency and packet loss."""
        n = max(1, min(int(count), 10))
        result = subprocess.run(
            ["ping", "-n", str(n), str(host)],
            capture_output=True,
            text=True,
            timeout=n * 3 + 10,
        )
        out = result.stdout or result.stderr or ""
        loss = re.search(r"\((\d+)% loss\)", out)
        avg = re.search(r"Average = (\d+)ms", out)
        return {
            "host": host,
            "reachable": "Received = 0" not in out and result.returncode == 0,
            "packet_loss_percent": int(loss.group(1)) if loss else None,
            "avg_latency_ms": int(avg.group(1)) if avg else None,
            "raw_output": out[-1000:],
        }

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def tcp_port_check(host: str, port: int, timeout: float = 3.0) -> dict[str, Any]:
        """Check whether a TCP port is open and listening on a target host."""
        start = time.monotonic()
        try:
            with socket.create_connection((host, int(port)), timeout=float(timeout)):
                elapsed = (time.monotonic() - start) * 1000
            return {"host": host, "port": int(port), "open": True, "latency_ms": round(elapsed, 1)}
        except OSError as e:
            return {"host": host, "port": int(port), "open": False, "error": str(e)}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def dns_lookup(hostname: str) -> dict[str, Any]:
        """Resolve a hostname into its corresponding IP addresses."""
        try:
            name, aliases, addrs = socket.gethostbyname_ex(hostname)
            return {"hostname": hostname, "canonical_name": name, "addresses": addrs, "aliases": aliases}
        except socket.gaierror as e:
            raise ValueError(f"Failed to resolve hostname '{hostname}': {e}")
