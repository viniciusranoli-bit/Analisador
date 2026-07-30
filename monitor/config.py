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


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return float(raw)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MonitorConfig:
    base_url: str
    http_timeout_seconds: float
    l1_max_latency_ms: int
    retry_count: int
    retry_backoff_base_ms: int
    retry_backoff_max_ms: int
    retry_jitter_factor: float
    alert_failure_threshold: int
    alert_webhook_url: str
    alert_recovery_notify: bool
    alert_state_file: str
    smoke_cron: str
    e2e_cron: str
    deep_cron: str
    e2e_email: str
    e2e_password: str
    deep_enabled: bool
    deep_zip_path: str

    @classmethod
    def load(cls) -> "MonitorConfig":
        _load_config_files()
        base_url = os.getenv("MONITOR_BASE_URL", "http://localhost:8000").strip().rstrip("/")
        return cls(
            base_url=base_url,
            http_timeout_seconds=float(os.getenv("MONITOR_HTTP_TIMEOUT_SECONDS", "15")),
            l1_max_latency_ms=_env_int("MONITOR_L1_MAX_LATENCY_MS", 10_000),
            retry_count=_env_int("MONITOR_RETRY_COUNT", 1),
            retry_backoff_base_ms=_env_int("MONITOR_RETRY_BACKOFF_BASE_MS", 500),
            retry_backoff_max_ms=_env_int("MONITOR_RETRY_BACKOFF_MAX_MS", 30_000),
            retry_jitter_factor=_env_float("MONITOR_RETRY_JITTER_FACTOR", 0.2),
            alert_failure_threshold=_env_int("MONITOR_ALERT_FAILURE_THRESHOLD", 3),
            alert_webhook_url=os.getenv("MONITOR_ALERT_WEBHOOK_URL", "").strip(),
            alert_recovery_notify=_env_bool("MONITOR_ALERT_RECOVERY_NOTIFY", True),
            alert_state_file=os.getenv(
                "MONITOR_ALERT_STATE_FILE",
                str(_MONITOR_DIR / ".state" / "alert_state.json"),
            ).strip(),
            smoke_cron=os.getenv("MONITOR_SMOKE_CRON", "*/5 * * * *").strip(),
            e2e_cron=os.getenv("MONITOR_E2E_CRON", "*/30 * * * *").strip(),
            deep_cron=os.getenv("MONITOR_DEEP_CRON", "0 8,20 * * *").strip(),
            e2e_email=os.getenv("MONITOR_E2E_EMAIL", "").strip(),
            e2e_password=os.getenv("MONITOR_E2E_PASSWORD", "").strip(),
            deep_enabled=_env_bool("MONITOR_DEEP_ENABLED"),
            deep_zip_path=os.getenv("MONITOR_DEEP_ZIP_PATH", "").strip(),
        )

    @property
    def auth_configured(self) -> bool:
        return bool(self.e2e_email and self.e2e_password)
