"""Fixtures compartilhadas dos smoke tests."""

from __future__ import annotations

import pytest
import httpx

from config import MonitorConfig


@pytest.fixture(scope="session")
def monitor_config() -> MonitorConfig:
    return MonitorConfig.load()


@pytest.fixture(scope="session")
def base_url(monitor_config: MonitorConfig) -> str:
    return monitor_config.base_url


@pytest.fixture(scope="session")
def http_client(monitor_config: MonitorConfig) -> httpx.Client:
    timeout = httpx.Timeout(monitor_config.http_timeout_seconds)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        yield client


@pytest.fixture(scope="session")
def auth_token(http_client: httpx.Client, monitor_config: MonitorConfig) -> str:
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
    token = payload.get("token")
    assert token, "Resposta de login sem token."
    return str(token)
