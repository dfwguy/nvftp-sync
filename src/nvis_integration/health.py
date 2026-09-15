"""Bounded, read-only integration and node health probes."""

from __future__ import annotations

import dataclasses
import os
import pathlib
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable


@dataclasses.dataclass(frozen=True)
class ProbeResult:
    status: str
    latency_ms: int
    detail: str


def run_probe(
    probe: Callable[[], str], *, started: Callable[[], float] = time.monotonic
) -> ProbeResult:
    before = started()
    try:
        detail = probe()
        status = "healthy"
    except Exception as exc:  # health boundary must remain available
        detail = f"{type(exc).__name__}: {exc}"[:300]
        status = "unhealthy"
    return ProbeResult(status, round((started() - before) * 1000), detail)


def node_health(data_path: pathlib.Path) -> dict[str, object]:
    disk = shutil.disk_usage(data_path)
    load = os.getloadavg()
    memory: dict[str, int] = {}
    try:
        values = {
            line.split(":", 1)[0]: int(line.split()[1]) * 1024
            for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
            if ":" in line and len(line.split()) >= 2
        }
        memory = {
            "total": values.get("MemTotal", 0),
            "available": values.get("MemAvailable", 0),
            "used": max(0, values.get("MemTotal", 0) - values.get("MemAvailable", 0)),
        }
    except (OSError, ValueError):
        memory = {"total": 0, "available": 0, "used": 0}
    return {
        "hostname": os.uname().nodename,
        "load_average": [round(item, 2) for item in load],
        "cpu_count": os.cpu_count(),
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "memory": memory,
    }


def systemd_health(services: Iterable[str]) -> list[dict[str, str]]:
    results = []
    for service in services:
        if not service or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789@_.-" for character in service
        ):
            raise ValueError("unsafe systemd service name")
        completed = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        state = completed.stdout.strip() or "unknown"
        results.append({"name": service, "state": state})
    return results
