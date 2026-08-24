import json
import urllib.error

import pytest

import chatbase_client
from chatbase_client import (
    ChatbaseClient,
    ChatbaseConfigurationError,
    ChatbaseError,
)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int) -> bytes:
        return self.body[:size]


def test_chatbase_request_keeps_secret_in_authorization_header(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(json.dumps({"text": "확정 결과 설명"}).encode("utf-8"))

    monkeypatch.setattr(chatbase_client.urllib.request, "urlopen", fake_urlopen)
    secret = "cb-secret-value-that-must-not-leak"
    context = {"policy": "read-only", "facts": {"m_grade": "M3"}}
    context_before = json.loads(json.dumps(context))
    client = ChatbaseClient(api_key=secret, agent_id="agent-123")

    result = client.ask(
        "왜 M3야?",
        history=[{"role": "assistant", "content": "이전 답변"}],
        evaluation_context=context,
    )

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))
    assert result.text == "확정 결과 설명"
    assert request.headers["Authorization"] == f"Bearer {secret}"
    assert secret not in request.data.decode("utf-8")
    assert payload["chatbotId"] == "agent-123"
    assert payload["stream"] is False
    assert "M3" in payload["messages"][-1]["content"]
    assert context == context_before


def test_chatbase_configuration_fails_closed() -> None:
    with pytest.raises(ChatbaseConfigurationError):
        ChatbaseClient(api_key="", agent_id="agent-123")
    with pytest.raises(ChatbaseConfigurationError):
        ChatbaseClient(api_key="a" * 20, agent_id="")


def test_chatbase_http_error_is_sanitized(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "sensitive upstream traceback C:/private/file.py:99",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(chatbase_client.urllib.request, "urlopen", fake_urlopen)
    client = ChatbaseClient(api_key="a" * 20, agent_id="agent-123")

    with pytest.raises(ChatbaseError) as caught:
        client.ask("질문")

    public_message = str(caught.value)
    assert "sensitive" not in public_message
    assert "C:/" not in public_message
    assert "traceback" not in public_message.lower()


def test_invalid_chatbase_response_is_sanitized(monkeypatch) -> None:
    monkeypatch.setattr(
        chatbase_client.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse(b"not-json"),
    )
    client = ChatbaseClient(api_key="a" * 20, agent_id="agent-123")
    with pytest.raises(ChatbaseError, match="응답을 처리할 수 없습니다"):
        client.ask("질문")
