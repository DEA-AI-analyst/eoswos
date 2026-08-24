"""Server-side Chatbase REST client for the EOSWOS custom AI panel."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


CHATBASE_CHAT_URL = "https://www.chatbase.co/api/v1/chat"
MAX_RESPONSE_BYTES = 1_000_000


class ChatbaseConfigurationError(RuntimeError):
    """Raised when Chatbase server-side settings are incomplete."""


class ChatbaseError(RuntimeError):
    """Sanitized Chatbase error safe to display in the public UI."""

    def __init__(self, message: str, *, code: str = "CHATBASE_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ChatbaseCallResult:
    text: str
    elapsed_ms: float


@dataclass(frozen=True)
class ChatbaseClient:
    api_key: str
    agent_id: str
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        api_key = str(self.api_key or "").strip()
        agent_id = str(self.agent_id or "").strip()
        if len(api_key) < 16:
            raise ChatbaseConfigurationError("Chatbase API 인증 설정이 필요합니다.")
        if len(agent_id) < 3:
            raise ChatbaseConfigurationError("Chatbase Agent ID 설정이 필요합니다.")
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "agent_id", agent_id)

    def ask(
        self,
        message: str,
        *,
        history: Iterable[dict[str, str]] = (),
        evaluation_context: dict[str, Any] | None = None,
    ) -> ChatbaseCallResult:
        prompt = str(message or "").strip()
        if not prompt:
            raise ChatbaseError("질문을 입력해 주세요.", code="EMPTY_MESSAGE")

        messages = _normalized_history(history)
        if evaluation_context:
            context_text = json.dumps(
                evaluation_context,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            prompt = (
                "[읽기 전용 확정 평가결과]\n"
                f"{context_text}\n"
                "[사용자 질문]\n"
                f"{prompt}\n"
                "위 확정값을 변경하거나 재계산하지 말고 설명만 하세요."
            )
        messages.append({"role": "user", "content": prompt[:12_000]})

        payload = {
            "chatbotId": self.agent_id,
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            CHATBASE_CHAT_URL,
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "eoswos-ai-panel/1.1",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            _raise_http_error(exc.code)
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            raise ChatbaseError(
                "자연어 질의 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
                code="SERVICE_UNAVAILABLE",
            ) from None

        elapsed_ms = round((time.perf_counter() - started) * 1_000.0, 1)
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise ChatbaseError(
                "자연어 질의 응답을 처리할 수 없습니다.",
                code="INVALID_RESPONSE",
            )
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ChatbaseError(
                "자연어 질의 응답을 처리할 수 없습니다.",
                code="INVALID_RESPONSE",
            ) from None
        text = decoded.get("text") if isinstance(decoded, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ChatbaseError(
                "자연어 질의 응답을 처리할 수 없습니다.",
                code="INVALID_RESPONSE",
            )
        return ChatbaseCallResult(text=text.strip(), elapsed_ms=elapsed_ms)


def _normalized_history(history: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:4_000]})
    return messages[-12:]


def _raise_http_error(status_code: int) -> None:
    if status_code == 401:
        message = "자연어 질의 서비스 인증 설정을 확인해 주세요."
        code = "AUTHENTICATION_FAILED"
    elif status_code in {402, 429}:
        message = "자연어 질의 사용량 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."
        code = "RATE_LIMITED"
    elif status_code == 404:
        message = "자연어 질의 Agent 설정을 확인해 주세요."
        code = "AGENT_NOT_FOUND"
    elif status_code >= 500:
        message = "자연어 질의 서비스가 일시적으로 응답하지 않습니다."
        code = "SERVICE_UNAVAILABLE"
    else:
        message = "자연어 질의 요청을 완료하지 못했습니다."
        code = "CHATBASE_ERROR"
    raise ChatbaseError(message, code=code) from None
