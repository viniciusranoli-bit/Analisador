#!/usr/bin/env python3
"""Executa smoke tests usando parâmetros de monitor/monitor.config.env."""

from __future__ import annotations

import subprocess
import sys
import argparse
import random
import time
from pathlib import Path

MONITOR_DIR = Path(__file__).resolve().parents[1]
if str(MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(MONITOR_DIR))

from config import MonitorConfig


LAYERS = {
    "availability": "tests/test_l1_availability.py",
    "readiness": "tests/test_l1_readiness.py",
    "auth": "tests/test_l2_auth_flow.py",
    "deep": "tests/test_l4_deep_flow.py",
}


def _retry_delay_seconds(cfg: MonitorConfig, retry_number: int) -> float:
    delay_ms = min(
        cfg.retry_backoff_base_ms * (2 ** max(0, retry_number - 1)),
        cfg.retry_backoff_max_ms,
    )
    jitter = random.uniform(
        1 - cfg.retry_jitter_factor,
        1 + cfg.retry_jitter_factor,
    )
    return max(0.0, delay_ms * jitter / 1000)


def _run_layer(name: str, cfg: MonitorConfig) -> int:
    test_file = LAYERS[name]
    cmd = [sys.executable, "-m", "pytest", test_file, "-v"]
    attempts = 1 + cfg.retry_count
    for attempt in range(1, attempts + 1):
        print(f"\n== Camada {name.upper()} == tentativa {attempt}/{attempts}")
        result = subprocess.run(cmd, cwd=MONITOR_DIR)
        if result.returncode == 0:
            return 0
        if attempt < attempts:
            delay = _retry_delay_seconds(cfg, attempt)
            print(f"Falha na camada {name}; nova tentativa em {delay:.2f}s.")
            time.sleep(delay)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layer",
        choices=[*LAYERS, "all"],
        default="all",
        help="Camada isolada ou pipeline completo com gate entre camadas.",
    )
    args = parser.parse_args()
    cfg = MonitorConfig.load()
    layers = list(LAYERS) if args.layer == "all" else [args.layer]
    for layer in layers:
        result_code = _run_layer(layer, cfg)
        if result_code != 0:
            print(f"Pipeline interrompido na camada {layer}.")
            return result_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
