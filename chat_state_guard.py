"""Pure state-integrity guard for confirmed evaluation results."""

from __future__ import annotations

import copy
from typing import Any

from chat_evaluation_context import evaluation_fingerprint


def protect_evaluation_state(
    snapshot: dict[str, Any] | None,
    current_value: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    """Restore the original snapshot when chat-side mutation is detected."""

    changed = evaluation_fingerprint(snapshot) != evaluation_fingerprint(current_value)
    protected = snapshot if changed else current_value
    return copy.deepcopy(protected), changed
