#!/usr/bin/env python3
"""Valida se o cron do workflow está sincronizado com monitor.config.env."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "monitor" / "monitor.config.env"
WORKFLOW_FILE = ROOT / ".github" / "workflows" / "synthetic-smoke.yml"


def _read_config_cron() -> str:
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith("MONITOR_SMOKE_CRON="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("MONITOR_SMOKE_CRON não encontrado em monitor/monitor.config.env")


def _read_workflow_cron() -> str:
    content = WORKFLOW_FILE.read_text(encoding="utf-8")
    match = re.search(r"^\s*-\s*cron:\s*['\"]?([^'\"\n]+)['\"]?\s*$", content, re.MULTILINE)
    if not match:
        raise RuntimeError("Cron não encontrado em .github/workflows/synthetic-smoke.yml")
    return match.group(1).strip()


def main() -> int:
    config_cron = _read_config_cron()
    workflow_cron = _read_workflow_cron()
    if config_cron != workflow_cron:
        print(
            "Cron dessincronizado.\n"
            f"  monitor/monitor.config.env: {config_cron}\n"
            f"  synthetic-smoke.yml:      {workflow_cron}\n"
            "Atualize ambos para o mesmo valor."
        )
        return 1
    print(f"Cron sincronizado: {config_cron}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
