"""Carrega parâmetros do monitor a partir de monitor.config.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_MONITOR_DIR = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _MONITOR_DIR / "monitor.config.env"
_LOCAL_CONFIG = _MONITOR_DIR / "monitor.config.local.env"


def _load_config_files() -> None:
    load_dotenv(_DEFAULT_CONFIG, override=False)
    if _LOCAL_CONFIG.exists():
        load_dotenv(_LOCAL_CONFIG, override=True)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


@dataclass(frozen=True)
class MonitorConfig:
    base_url: str
    http_timeout_seconds: float
    l1_max_latency_ms: int
    retry_count: int
    alert_failure_threshold: int
    smoke_cron: str
    e2e_email: str
    e2e_password: str

    @classmethod
    def load(cls) -> "MonitorConfig":
        _load_config_files()
        base_url = os.getenv("MONITOR_BASE_URL", "http://localhost:8000").strip().rstrip("/")
        return cls(
            base_url=base_url,
            http_timeout_seconds=float(os.getenv("MONITOR_HTTP_TIMEOUT_SECONDS", "15")),
            l1_max_latency_ms=_env_int("MONITOR_L1_MAX_LATENCY_MS", 10_000),
            retry_count=_env_int("MONITOR_RETRY_COUNT", 1),
            alert_failure_threshold=_env_int("MONITOR_ALERT_FAILURE_THRESHOLD", 3),
            smoke_cron=os.getenv("MONITOR_SMOKE_CRON", "*/5 * * * *").strip(),
            e2e_email=os.getenv("MONITOR_E2E_EMAIL", "").strip(),
            e2e_password=os.getenv("MONITOR_E2E_PASSWORD", "").strip(),
        )

    @property
    def auth_configured(self) -> bool:
        return bool(self.e2e_email and self.e2e_password)
