"""Camada L2 — autenticação e rotas protegidas."""

from __future__ import annotations

import httpx
import pytest

from config import MonitorConfig


def test_login_returns_token(http_client: httpx.Client, monitor_config: MonitorConfig) -> None:
    if not monitor_config.auth_configured:
        pytest.skip("MONITOR_E2E_EMAIL e MONITOR_E2E_PASSWORD não configurados.")

    response = http_client.post(
        f"{monitor_config.base_url}/auth/login",
        json={
            "email": monitor_config.e2e_email,
            "password": monitor_config.e2e_password,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("token")
    assert payload.get("email") == monitor_config.e2e_email.lower()


def test_auth_me_with_valid_token(
    http_client: httpx.Client,
    base_url: str,
    auth_token: str,
    monitor_config: MonitorConfig,
) -> None:
    response = http_client.get(
        f"{base_url}/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("email") == monitor_config.e2e_email.lower()


def test_historico_with_valid_token(
    http_client: httpx.Client,
    base_url: str,
    auth_token: str,
) -> None:
    response = http_client.get(
        f"{base_url}/historico",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload, list)


def test_auth_me_rejects_invalid_token(http_client: httpx.Client, base_url: str) -> None:
    response = http_client.get(
        f"{base_url}/auth/me",
        headers={"Authorization": "Bearer token-invalido"},
    )
    assert response.status_code == 401
