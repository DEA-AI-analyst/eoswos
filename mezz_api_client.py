"""Server-side client for the EOSWOS single-candidate evaluation API."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


MAX_RESPONSE_BYTES = 2_000_000

_SAFE_ERROR_MESSAGES = {
    "BPS_CANONICAL_UNAVAILABLE": (
        "BPS 기준정보를 확인할 수 없어 평가를 완료하지 못했습니다. "
        "잠시 후 다시 시도해 주세요."
    ),
}


class MezzApiConfigurationError(RuntimeError):
    """Raised when the server-side API configuration is incomplete."""


class MezzApiError(RuntimeError):
    """A sanitized API error safe to show in the UI."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str = "API_ERROR",
        fields: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.fields = list(fields or [])


@dataclass(frozen=True)
class ApiCallResult:
    data: dict[str, Any]
    elapsed_ms: float


@dataclass(frozen=True)
class MezzApiClient:
    base_url: str
    token: str
    timeout_seconds: float = 180.0

    def __post_init__(self) -> None:
        normalized_url = str(self.base_url or "").strip().rstrip("/")
        normalized_token = str(self.token or "").strip()
        parsed = urlparse(normalized_url)

        if parsed.scheme != "https" or not parsed.netloc:
            raise MezzApiConfigurationError("API 연결 주소가 올바르지 않습니다.")
        if len(normalized_token) < 24:
            raise MezzApiConfigurationError("API 인증 설정이 필요합니다.")

        object.__setattr__(self, "base_url", normalized_url)
        object.__setattr__(self, "token", normalized_token)

    def health(self) -> ApiCallResult:
        return self._request("GET", "/health", authenticated=False)

    def evaluate_single(self, payload: dict[str, Any]) -> ApiCallResult:
        return self._request(
            "POST",
            "/evaluate/single",
            payload=payload,
            authenticated=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        authenticated: bool,
    ) -> ApiCallResult:
        headers = {
            "Accept": "application/json",
            "User-Agent": "eoswos-ai-ui/1.0",
        }
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        started = time.perf_counter()

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read(MAX_RESPONSE_BYTES + 1)
                status_code = response.status
        except urllib.error.HTTPError as exc:
            response_body = exc.read(MAX_RESPONSE_BYTES + 1)
            self._raise_api_error(exc.code, response_body)
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            raise MezzApiError(
                "평가 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
                code="SERVICE_UNAVAILABLE",
            ) from None

        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise MezzApiError("평가 서버 응답을 처리할 수 없습니다.", code="INVALID_RESPONSE")

        data = self._decode_json(response_body)
        if not 200 <= status_code < 300:
            self._raise_api_error(status_code, response_body)
        return ApiCallResult(data=data, elapsed_ms=elapsed_ms)

    @staticmethod
    def _decode_json(response_body: bytes) -> dict[str, Any]:
        try:
            data = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise MezzApiError(
                "평가 서버 응답을 처리할 수 없습니다.",
                code="INVALID_RESPONSE",
            ) from None
        if not isinstance(data, dict):
            raise MezzApiError(
                "평가 서버 응답을 처리할 수 없습니다.",
                code="INVALID_RESPONSE",
            )
        return data

    @classmethod
    def _raise_api_error(cls, status_code: int, response_body: bytes) -> None:
        code = "API_ERROR"
        fields: list[str] = []
        try:
            data = cls._decode_json(response_body)
            error = data.get("error", {})
            if isinstance(error, dict):
                code = str(error.get("code") or code)
                raw_fields = error.get("fields", [])
                if isinstance(raw_fields, list):
                    fields = [str(field) for field in raw_fields]
        except MezzApiError:
            pass

        if code in _SAFE_ERROR_MESSAGES:
            # Ignore API detail text and show only a reviewed public message.
            fields = []
            message = _SAFE_ERROR_MESSAGES[code]
        elif status_code == 401:
            message = "API 인증에 실패했습니다."
        elif status_code == 422:
            message = "입력값을 확인해 주세요."
        elif status_code == 503:
            message = "평가 서비스를 준비 중입니다. 잠시 후 다시 시도해 주세요."
        elif status_code >= 500:
            message = "평가 처리 중 오류가 발생했습니다."
        else:
            message = "평가 요청을 완료하지 못했습니다."

        raise MezzApiError(
            message,
            status_code=status_code,
            code=code,
            fields=fields,
        )
