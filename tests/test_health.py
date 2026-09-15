from __future__ import annotations

import pathlib

import pytest

from nvis_integration.health import node_health, run_probe, systemd_health


def test_probe_reports_failures_without_raising() -> None:
    times = iter([1.0, 1.125])

    def failure() -> str:
        raise OSError("offline")

    result = run_probe(failure, started=lambda: next(times))
    assert result.status == "unhealthy"
    assert result.latency_ms == 125
    assert result.detail == "OSError: offline"


def test_node_health_has_bounded_numeric_metrics(tmp_path: pathlib.Path) -> None:
    result = node_health(tmp_path)
    assert result["cpu_count"]
    assert result["disk"]["total"] > 0  # type: ignore[index]


def test_systemd_rejects_service_argument_injection() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        systemd_health(["service;whoami"])
