from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import PureWindowsPath
from typing import Any

import psutil


def collect_metrics() -> dict[str, Any]:
    """Collect a bounded, read-only system snapshot. No command lines or file content."""
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(system_root())
    return {
        "observed_at": now,
        "cpu_percent": psutil.cpu_percent(interval=0.15),
        "memory_percent": vm.percent,
        "memory_used_bytes": vm.used,
        "memory_total_bytes": vm.total,
        "disk_percent": disk.percent,
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
    }


def system_root() -> str:
    return os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"


def disk_usage(path: str | None = None) -> dict[str, Any]:
    path = path or system_root()
    usage = psutil.disk_usage(path)
    return {"path": path, "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free, "used_percent": usage.percent, "free_percent": round(100 - usage.percent, 2), "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def list_processes(limit: int = 20, sort: str = "memory") -> list[dict[str, Any]]:
    """Return resource-ranked process metadata without command-line arguments."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if sort not in {"memory", "cpu"}:
        raise ValueError("sort must be 'memory' or 'cpu'")
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "exe"]):
        try:
            info = proc.info
            cpu = proc.cpu_percent(interval=None)
            rows.append({
                "pid": info.get("pid"), "name": (info.get("name") or "unknown")[:128],
                "memory_rss_bytes": getattr(info.get("memory_info"), "rss", None),
                "cpu_percent": cpu,
                "executable": _safe_executable(info.get("exe")),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    key = "cpu_percent" if sort == "cpu" else "memory_rss_bytes"
    return sorted(rows, key=lambda p: p[key] or 0, reverse=True)[:limit]


def get_process_details(pid: int) -> dict[str, Any]:
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            try:
                memory = proc.memory_info()
            except psutil.Error:
                memory = None
            try:
                exe = proc.exe()
            except psutil.Error:
                exe = None
            return {"pid": pid, "name": proc.name()[:128], "status": proc.status(), "memory_rss_bytes": memory.rss if memory else None, "cpu_percent": proc.cpu_percent(interval=0.1), "executable": _safe_executable(exe), "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
        raise RuntimeError(f"Process {pid} is no longer available or access was denied") from exc


def _safe_executable(path: str | None) -> str | None:
    # Preserve the executable identity while excluding user and directory names.
    return PureWindowsPath(path).name if path else None
