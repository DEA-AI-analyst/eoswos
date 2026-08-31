"""Process-local one-time delay used only by the cold-start E2E wrapper."""

from __future__ import annotations

import time


_delayed = False


def wait_once(seconds: float) -> None:
    global _delayed
    if _delayed:
        return
    _delayed = True
    time.sleep(max(0.0, seconds))
