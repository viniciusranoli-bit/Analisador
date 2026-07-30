"""Camada L1b — readiness das dependências operacionais."""

from __future__ import annotations

import httpx


def test_ready_reports_dependencies(http_client: httpx.Client, base_url: str) -> None:
    response = http_client.get(f"{base_url}/ready")
    assert response.status_code in (200, 503)
    payload = response.json()
    assert "checks" in payload
    assert payload.get("status") in ("ready", "not_ready")
