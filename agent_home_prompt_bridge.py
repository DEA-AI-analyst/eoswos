"""One-shot Agent Home prompt bridge for the existing E-AGENT chat path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import streamlit.components.v1 as components


BRIDGE_VERSION = 1
BRIDGE_SOURCE = "agent_home_first_prompt"
BRIDGE_MESSAGE_TYPE = "INITIAL_PROMPT"
MAX_PROMPT_LENGTH = 500
PRODUCTION_PARENT_ORIGIN = "https://eoswos.com"
PRODUCTION_ENVIRONMENT = "production"
STAGING_ENVIRONMENT = "staging"
LOCAL_ENVIRONMENT = "local"
COMPONENT_KEY = "eoswos-agent-home-first-prompt-v1"

_COMPONENT_PATH = Path(__file__).resolve().parent / "initial_prompt_bridge"
_BRIDGE_COMPONENT = components.declare_component(
    "eoswos_agent_home_first_prompt",
    path=str(_COMPONENT_PATH),
)


class PromptBridgeConfigurationError(ValueError):
    """Raised when the exact parent origin is unsafe or malformed."""


@dataclass(frozen=True)
class InitialPromptRequest:
    request_id: str
    prompt: str
    attempt: int


def prompt_utf16_length(prompt: str) -> int:
    """Match the browser maxlength definition, including astral characters."""

    return len(prompt.encode("utf-16-le")) // 2


def normalize_parent_origin(
    value: str | None,
    *,
    deployment_environment: str = PRODUCTION_ENVIRONMENT,
) -> str:
    """Return the one exact origin allowed by the active deployment profile."""

    environment = str(deployment_environment or PRODUCTION_ENVIRONMENT).strip().lower()
    if environment not in {
        PRODUCTION_ENVIRONMENT,
        STAGING_ENVIRONMENT,
        LOCAL_ENVIRONMENT,
    }:
        raise PromptBridgeConfigurationError(
            "Agent Home deployment environment is not approved."
        )
    raw = str(value or PRODUCTION_PARENT_ORIGIN).strip()
    parsed = urlsplit(raw)
    is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (parsed.scheme != "https" and not (is_local and parsed.scheme == "http"))
    ):
        raise PromptBridgeConfigurationError(
            "Agent Home parent origin must be one exact HTTPS origin."
        )
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if environment == PRODUCTION_ENVIRONMENT and origin != PRODUCTION_PARENT_ORIGIN:
        raise PromptBridgeConfigurationError(
            "Production accepts only the approved Agent Home origin."
        )
    if environment == STAGING_ENVIRONMENT and parsed.scheme != "https":
        raise PromptBridgeConfigurationError(
            "Staging accepts one exact HTTPS Agent Home origin."
        )
    if environment == LOCAL_ENVIRONMENT and not (
        is_local and parsed.scheme == "http"
    ):
        raise PromptBridgeConfigurationError(
            "Local testing accepts only an exact loopback HTTP origin."
        )
    return origin


def validate_initial_prompt_payload(value: Any) -> InitialPromptRequest | None:
    """Validate the public bridge contract without logging or transforming text."""

    if not isinstance(value, dict):
        return None
    if value.get("type") != BRIDGE_MESSAGE_TYPE:
        return None
    if value.get("version") != BRIDGE_VERSION:
        return None
    if value.get("source") != BRIDGE_SOURCE:
        return None

    request_id = value.get("request_id")
    prompt = value.get("prompt")
    attempt = value.get("attempt", 1)
    if not isinstance(request_id, str) or not isinstance(prompt, str):
        return None
    try:
        parsed_request_id = UUID(request_id)
    except (ValueError, AttributeError):
        return None
    if str(parsed_request_id) != request_id.lower():
        return None
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt not in {1, 2}:
        return None
    if not prompt.strip() or prompt != prompt.strip():
        return None
    if any(ord(character) < 32 for character in prompt):
        return None
    try:
        if prompt_utf16_length(prompt) > MAX_PROMPT_LENGTH:
            return None
    except UnicodeEncodeError:
        return None
    return InitialPromptRequest(
        request_id=request_id.lower(),
        prompt=prompt,
        attempt=attempt,
    )


def render_agent_home_prompt_bridge(
    *,
    parent_origin: str,
    deployment_environment: str = PRODUCTION_ENVIRONMENT,
    ack_request_id: str | None,
    ack_status: str | None,
) -> Any:
    """Render the zero-height component and return a validated-candidate payload."""

    safe_origin = normalize_parent_origin(
        parent_origin,
        deployment_environment=deployment_environment,
    )
    safe_ack_status = ack_status if ack_status in {"accepted", "duplicate"} else None
    return _BRIDGE_COMPONENT(
        parent_origin=safe_origin,
        version=BRIDGE_VERSION,
        source=BRIDGE_SOURCE,
        ack_request_id=ack_request_id,
        ack_status=safe_ack_status,
        default=None,
        key=COMPONENT_KEY,
        tab_index=-1,
    )
