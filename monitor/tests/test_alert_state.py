"""Testes do limiar, deduplicação e recuperação de alertas."""

from __future__ import annotations

from dataclasses import replace

from config import MonitorConfig
from scripts.alert_state import StateStore, process


def test_alert_requires_threshold_and_recovers(tmp_path) -> None:
    config = replace(
        MonitorConfig.load(),
        alert_failure_threshold=3,
        alert_webhook_url="",
        alert_state_file=str(tmp_path / "alert_state.json"),
    )
    store = StateStore(config)

    process("failure", config, store)
    assert store.load()["alert_active"] is False
    process("failure", config, store)
    assert store.load()["alert_active"] is False
    process("failure", config, store)
    active_state = store.load()
    assert active_state["alert_active"] is True
    assert active_state["consecutive_failures"] == 3

    process("failure", config, store)
    assert store.load()["consecutive_failures"] == 4
    process("success", config, store)
    recovered_state = store.load()
    assert recovered_state["alert_active"] is False
    assert recovered_state["consecutive_failures"] == 0
