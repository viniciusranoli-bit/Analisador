#!/usr/bin/env python3
"""Exporta a configuração do monitor para o ambiente do GitHub Actions.

O workflow não usa ``source``: este script interpreta o arquivo .env com
Python e grava apenas parâmetros não sensíveis no arquivo GITHUB_ENV.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "monitor.config.env"
LOCAL_CONFIG_FILE = ROOT / "monitor.config.local.env"
EXPORTED_KEYS = {
    "MONITOR_BASE_URL",
    "MONITOR_HTTP_TIMEOUT_SECONDS",
    "MONITOR_L1_MAX_LATENCY_MS",
    "MONITOR_RETRY_COUNT",
    "MONITOR_RETRY_BACKOFF_BASE_MS",
    "MONITOR_RETRY_BACKOFF_MAX_MS",
    "MONITOR_RETRY_JITTER_FACTOR",
    "MONITOR_ALERT_FAILURE_THRESHOLD",
    "MONITOR_ALERT_RECOVERY_NOTIFY",
    "MONITOR_ALERT_STATE_FILE",
    "MONITOR_SMOKE_CRON",
    "MONITOR_E2E_CRON",
    "MONITOR_DEEP_CRON",
    "MONITOR_DEEP_ENABLED",
    "MONITOR_DEEP_ZIP_PATH",
}


def main() -> int:
    github_env = os.getenv("GITHUB_ENV")
    if not github_env:
        raise RuntimeError("GITHUB_ENV não está definido.")

    values = dict(dotenv_values(CONFIG_FILE))
    if LOCAL_CONFIG_FILE.exists():
        values.update({k: v for k, v in dotenv_values(LOCAL_CONFIG_FILE).items() if v is not None})

    with Path(github_env).open("a", encoding="utf-8") as output:
        for key in sorted(EXPORTED_KEYS):
            value = values.get(key)
            if value is None:
                continue
            output.write(f"{key}<<MONITOR_ENV_EOF\n{value}\nMONITOR_ENV_EOF\n")
            print(f"Exportado: {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
