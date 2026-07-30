"""Camada L4 — fluxo caro de upload e análise com IA.

Executada apenas em workflow dedicado, nunca no smoke frequente.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_deep_analysis_flow(http_client, monitor_config, base_url) -> None:
    if not monitor_config.deep_enabled:
        pytest.skip("MONITOR_DEEP_ENABLED não está habilitado.")
    if not monitor_config.auth_configured:
        pytest.skip("Credenciais E2E não configuradas.")
    if not monitor_config.deep_zip_path:
        pytest.skip("MONITOR_DEEP_ZIP_PATH não configurado.")

    zip_path = Path(monitor_config.deep_zip_path)
    if not zip_path.exists():
        pytest.skip(f"ZIP de monitoramento não encontrado: {zip_path}")

    login = http_client.post(
        f"{base_url}/auth/login",
        json={
            "email": monitor_config.e2e_email,
            "password": monitor_config.e2e_password,
        },
    )
    assert login.status_code == 200, login.text
    token = login.json().get("token")
    assert token

    with zip_path.open("rb") as zip_file:
        response = http_client.post(
            f"{base_url}/analisar",
            headers={"Authorization": f"Bearer {token}"},
            files={"arquivo": (zip_path.name, zip_file, "application/zip")},
            data={
                "especialidade": "Monitoramento sintético",
                "senioridade": "Sênior",
                "objetivo": "Validar o fluxo crítico de análise",
                "cargo_alvo": "",
                "contexto": "Execução controlada de monitoramento.",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json().get("score") is not None
