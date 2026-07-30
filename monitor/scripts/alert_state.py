#!/usr/bin/env python3
"""Aplica limiar, deduplicação e recuperação às falhas do monitor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MONITOR_DIR = Path(__file__).resolve().parents[1]
if str(MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(MONITOR_DIR))

from config import MonitorConfig


DEFAULT_STATE: dict[str, Any] = {
    "consecutive_failures": 0,
    "alert_active": False,
    "updated_at": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.token = os.getenv("GITHUB_TOKEN", "").strip()
        self.repository = os.getenv("GITHUB_REPOSITORY", "").strip()
        self.variable_name = os.getenv("MONITOR_ALERT_STATE_VARIABLE", "MONITOR_ALERT_STATE")

    @property
    def github_url(self) -> str | None:
        if not self.token or not self.repository:
            return None
        return (
            f"https://api.github.com/repos/{self.repository}/actions/variables/"
            f"{self.variable_name}"
        )

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def load(self) -> dict[str, Any]:
        if self.github_url:
            try:
                payload = self._request("GET", self.github_url)
                return {**DEFAULT_STATE, **json.loads(payload.get("value", "{}"))}
            except HTTPError as error:
                if error.code != 404:
                    raise
            except (URLError, json.JSONDecodeError):
                raise

        path = Path(self.config.alert_state_file)
        if not path.exists():
            return dict(DEFAULT_STATE)
        return {**DEFAULT_STATE, **json.loads(path.read_text(encoding="utf-8"))}

    def save(self, state: dict[str, Any]) -> None:
        state["updated_at"] = _now()
        if self.github_url:
            body = {"name": self.variable_name, "value": json.dumps(state, separators=(",", ":"))}
            try:
                self._request("PATCH", self.github_url, body)
            except HTTPError as error:
                if error.code != 404:
                    raise
                base_url = self.github_url.rsplit("/", 2)[0]
                self._request("POST", base_url, body)
            return

        path = Path(self.config.alert_state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _send_webhook(config: MonitorConfig, message: str) -> bool:
    if not config.alert_webhook_url:
        print("MONITOR_ALERT_WEBHOOK_URL não configurado; alerta registrado sem envio.")
        return False
    request = Request(
        config.alert_webhook_url,
        data=json.dumps({"text": message}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15):
            return True
    except (HTTPError, URLError) as error:
        print(f"Falha ao enviar webhook de alerta: {error}")
        return False


def process(status: str, config: MonitorConfig, store: StateStore) -> int:
    state = store.load()
    if status == "failure":
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        threshold_reached = state["consecutive_failures"] >= config.alert_failure_threshold
        if threshold_reached and not state.get("alert_active", False):
            sent = _send_webhook(
                config,
                f"🚨 Monitoramento: {state['consecutive_failures']} falhas consecutivas "
                f"em {config.base_url}.",
            )
            state["alert_active"] = True
            state["last_notification_sent"] = sent
            print("Alerta de indisponibilidade emitido." if sent else "Alerta deduplicado no estado.")
        else:
            print(
                f"Falha registrada ({state['consecutive_failures']}/"
                f"{config.alert_failure_threshold}); alerta ativo={state.get('alert_active', False)}."
            )
    else:
        was_active = bool(state.get("alert_active", False))
        if was_active and config.alert_recovery_notify:
            sent = _send_webhook(config, f"✅ Monitoramento recuperado: {config.base_url}.")
            print("Alerta de recuperação emitido." if sent else "Recuperação registrada sem envio.")
        state["consecutive_failures"] = 0
        state["alert_active"] = False
        state["last_notification_sent"] = False
    store.save(state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=("success", "failure"), required=True)
    args = parser.parse_args()
    config = MonitorConfig.load()
    return process(args.status, config, StateStore(config))


if __name__ == "__main__":
    raise SystemExit(main())
