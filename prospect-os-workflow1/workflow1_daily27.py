#!/usr/bin/env python3
"""Unified Prospect OS Workflow 1 Daily Runner (aligned with PR #11: 15 WA + 2 TG + 10 FB = 27).

Replaces legacy 27 WA + 3 TG = 30 quota with the active MultiHub Daily 27 standard.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_daily27_pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
