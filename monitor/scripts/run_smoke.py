#!/usr/bin/env python3
"""Executa smoke tests usando parâmetros de monitor/monitor.config.env."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from config import MonitorConfig

MONITOR_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    cfg = MonitorConfig.load()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_l1_availability.py",
        "tests/test_l2_auth_flow.py",
        "-v",
    ]
    attempts = 1 + cfg.retry_count
    last_code = 1
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            print(f"Retentativa {attempt - 1}/{cfg.retry_count}...")
        result = subprocess.run(cmd, cwd=MONITOR_DIR)
        last_code = result.returncode
        if last_code == 0:
            return 0
    return last_code


if __name__ == "__main__":
    sys.exit(main())
