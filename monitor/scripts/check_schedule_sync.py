#!/usr/bin/env python3
"""Valida se o cron do workflow está sincronizado com monitor.config.env."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "monitor" / "monitor.config.env"
WORKFLOWS = {
    "MONITOR_SMOKE_CRON": ROOT / ".github" / "workflows" / "synthetic-smoke.yml",
    "MONITOR_DEEP_CRON": ROOT / ".github" / "workflows" / "synthetic-deep.yml",
}


def _read_config_cron(name: str) -> str:
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith(f"{name}="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"{name} não encontrado em monitor/monitor.config.env")


def _read_workflow_cron(workflow_file: Path) -> str:
    content = workflow_file.read_text(encoding="utf-8")
    match = re.search(r"^\s*-\s*cron:\s*['\"]?([^'\"\n]+)['\"]?\s*$", content, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Cron não encontrado em {workflow_file}")
    return match.group(1).strip()


def main() -> int:
    mismatches = []
    for name, workflow_file in WORKFLOWS.items():
        config_cron = _read_config_cron(name)
        workflow_cron = _read_workflow_cron(workflow_file)
        if config_cron != workflow_cron:
            mismatches.append((name, config_cron, workflow_cron))
        else:
            print(f"{name} sincronizado: {config_cron}")
    if mismatches:
        print("Crons dessincronizados:")
        for name, config_cron, workflow_cron in mismatches:
            print(f"  {name}: config={config_cron} workflow={workflow_cron}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
