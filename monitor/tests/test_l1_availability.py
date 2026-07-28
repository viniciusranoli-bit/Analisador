"""Camada L1 — disponibilidade e latência básica."""

from __future__ import annotations

import httpx
import pytest

from config import MonitorConfig


@pytest.fixture(scope="module")
def cfg() -> MonitorConfig:
    return MonitorConfig.load()


def test_health_returns_ok(http_client: httpx.Client, base_url: str) -> None:
    response = http_client.get(f"{base_url}/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "ok"
    assert payload.get("service") == "analisador-linkedin"
    assert payload.get("version")


def test_ready_reports_dependencies(http_client: httpx.Client, base_url: str) -> None:
    response = http_client.get(f"{base_url}/ready")
    assert response.status_code in (200, 503)
    payload = response.json()
    assert "checks" in payload
    assert payload.get("status") in ("ready", "not_ready")


def test_landing_page_is_reachable(http_client: httpx.Client, base_url: str) -> None:
    response = http_client.get(f"{base_url}/")
    assert response.status_code == 200
    assert "Analisador" in response.text


def test_app_page_is_reachable(http_client: httpx.Client, base_url: str) -> None:
    response = http_client.get(f"{base_url}/app")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/health", "/", "/app"],
)
def test_l1_latency_within_threshold(
    http_client: httpx.Client,
    base_url: str,
    cfg: MonitorConfig,
    path: str,
) -> None:
    response = http_client.get(f"{base_url}{path}")
    assert response.status_code == 200
    elapsed_ms = response.elapsed.total_seconds() * 1000
    assert elapsed_ms <= cfg.l1_max_latency_ms, (
        f"{path} demorou {elapsed_ms:.0f}ms (limite: {cfg.l1_max_latency_ms}ms)"
    )
