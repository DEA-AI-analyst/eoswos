from pathlib import Path
from uuid import uuid4

import pytest

import agent_home_prompt_bridge as bridge


ROOT = Path(__file__).resolve().parents[1]


def _payload(prompt: str = "M2는 뭐야?", **overrides):
    value = {
        "type": "INITIAL_PROMPT",
        "version": 1,
        "request_id": str(uuid4()),
        "prompt": prompt,
        "source": "agent_home_first_prompt",
        "attempt": 1,
    }
    value.update(overrides)
    return value


def test_valid_payload_preserves_plain_prompt_exactly() -> None:
    prompt = "<script>alert('x')</script> **M Grade**"
    request = bridge.validate_initial_prompt_payload(_payload(prompt))

    assert request is not None
    assert request.prompt == prompt
    assert request.attempt == 1


@pytest.mark.parametrize(
    "overrides",
    (
        {"type": "OTHER"},
        {"version": 2},
        {"source": "staging"},
        {"request_id": "not-a-uuid"},
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": " leading"},
        {"prompt": "trailing "},
        {"prompt": "line\nbreak"},
        {"attempt": 0},
        {"attempt": 3},
    ),
)
def test_invalid_contract_payload_is_rejected(overrides) -> None:
    assert bridge.validate_initial_prompt_payload(_payload(**overrides)) is None


def test_prompt_limit_matches_browser_utf16_length() -> None:
    assert bridge.validate_initial_prompt_payload(_payload("가" * 500)) is not None
    assert bridge.validate_initial_prompt_payload(_payload("가" * 501)) is None
    assert bridge.validate_initial_prompt_payload(_payload("😀" * 250)) is not None
    assert bridge.validate_initial_prompt_payload(_payload("😀" * 251)) is None


def test_parent_origin_is_one_exact_origin() -> None:
    assert bridge.normalize_parent_origin(None) == "https://eoswos.com"
    assert bridge.normalize_parent_origin(
        "https://home-staging.example",
        deployment_environment="staging",
    ) == "https://home-staging.example"
    assert bridge.normalize_parent_origin(
        "http://localhost:8000",
        deployment_environment="local",
    ) == "http://localhost:8000"

    with pytest.raises(bridge.PromptBridgeConfigurationError):
        bridge.normalize_parent_origin("https://home-staging.example")
    with pytest.raises(bridge.PromptBridgeConfigurationError):
        bridge.normalize_parent_origin(
            "http://localhost:8000",
            deployment_environment="production",
        )

    for invalid in (
        "https://eoswos.com/path",
        "https://eoswos.com?next=staging",
        "https://eoswos.com,https://staging.example",
        "http://eoswos.com",
        "javascript:alert(1)",
    ):
        with pytest.raises(bridge.PromptBridgeConfigurationError):
            bridge.normalize_parent_origin(invalid)


def test_component_call_contains_no_prompt_or_staging_origin(monkeypatch) -> None:
    captured = {}

    def fake_component(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(bridge, "_BRIDGE_COMPONENT", fake_component)
    bridge.render_agent_home_prompt_bridge(
        parent_origin="https://eoswos.com",
        deployment_environment="production",
        ack_request_id="0d830966-c9a7-4356-9498-b96af4a5159a",
        ack_status="accepted",
    )

    assert captured["parent_origin"] == "https://eoswos.com"
    assert captured["ack_status"] == "accepted"
    assert captured["key"] == bridge.COMPONENT_KEY
    assert "prompt" not in captured
    assert "staging" not in repr(captured).lower()


def test_application_bridge_uses_exact_postmessage_origins() -> None:
    component = (ROOT / "initial_prompt_bridge" / "index.html").read_text(encoding="utf-8")
    widget = (ROOT / "ai_widget.js").read_text(encoding="utf-8")

    assert 'postMessage(message, streamlitOrigin)' in component
    assert 'postMessage(message, parentOrigin)' in component
    assert 'target.postMessage(payload, childOrigin)' in widget
    assert 'postMessage(message, "*")' not in component
    assert "postMessage(payload, \"*\")" not in widget
    assert "event.origin !== parentOrigin" in component
    assert "event.source !== window.top" in component
    assert "source.top !== window" in widget
    assert "current === frame.contentWindow" in widget
    assert "depth < 5" in widget
    assert "parent === current" in widget


def test_component_allows_http_only_for_exact_loopback_e2e_origins() -> None:
    component = (ROOT / "initial_prompt_bridge" / "index.html").read_text(encoding="utf-8")

    assert 'parsed.protocol === "https:"' in component
    assert 'parsed.protocol === "http:" && isLoopback' in component
    assert 'parsed.hostname === "localhost"' in component
    assert 'parsed.hostname === "127.0.0.1"' in component


def test_component_replays_idempotent_ack_after_ack_loss() -> None:
    component = (ROOT / "initial_prompt_bridge" / "index.html").read_text(encoding="utf-8")

    assert "lastAckKey" not in component
    ack_block = component.split("typeof args.ack_request_id", 1)[1].split(
        "postToAgentHome(readyMessage())",
        1,
    )[0]
    assert "postToAgentHome({" in ack_block
    assert "args.ack_request_id" in ack_block


def test_component_sends_ready_before_ack_to_pin_the_new_source() -> None:
    component = (ROOT / "initial_prompt_bridge" / "index.html").read_text(encoding="utf-8")
    render_block = component.split("const handleRender", 1)[1].split(
        "const handleInitialPrompt",
        1,
    )[0]

    assert render_block.index("postToAgentHome(readyMessage())") < render_block.index(
        "request_id: args.ack_request_id"
    )


def test_production_component_has_no_staging_parent_fallback() -> None:
    component = (ROOT / "initial_prompt_bridge" / "index.html").read_text(encoding="utf-8")
    module = (ROOT / "agent_home_prompt_bridge.py").read_text(encoding="utf-8")

    assert "eoswos-mcore-bps-stg" not in component + module
    assert "eoswos-agent-bps-stg" not in component + module
    assert "fabulous-lokum" not in component + module
