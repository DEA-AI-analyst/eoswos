"""Test-only Streamlit wrapper that delays each script run before loading E-AGENT."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

from _cold_start_delay import wait_once


DELAY_SECONDS = float(os.getenv("EOSWOS_E2E_STARTUP_DELAY_SECONDS", "8"))
APP_PATH = Path(__file__).resolve().parents[2] / "ai_single_evaluation.py"

wait_once(DELAY_SECONDS)
runpy.run_path(str(APP_PATH), run_name="__main__")
