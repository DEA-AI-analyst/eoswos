import json

import pytest

from mezz_api_client import MezzApiClient, MezzApiError


def test_bps_canonical_unavailable_uses_fixed_safe_public_message() -> None:
    response_body = json.dumps(
        {
            "status": "error",
            "error": {
                "code": "BPS_CANONICAL_UNAVAILABLE",
                "message": (
                    "sensitive account_id ifrs-full_Secret "
                    "C:/private/runtime.py:99"
                ),
                "fields": ["ifrs-full_Secret", "C:/private/runtime.py"],
            },
        }
    ).encode("utf-8")

    with pytest.raises(MezzApiError) as caught:
        MezzApiClient._raise_api_error(422, response_body)

    public_message = str(caught.value)
    assert caught.value.code == "BPS_CANONICAL_UNAVAILABLE"
    assert caught.value.fields == []
    assert public_message == (
        "BPS 기준정보를 확인할 수 없어 평가를 완료하지 못했습니다. "
        "잠시 후 다시 시도해 주세요."
    )
    assert "sensitive" not in public_message
    assert "ifrs-full" not in public_message
    assert "C:/" not in public_message


def test_other_api_error_messages_remain_sanitized() -> None:
    response_body = json.dumps(
        {
            "error": {
                "code": "EVALUATION_FAILED",
                "message": "private traceback C:/private/service.py:41",
            }
        }
    ).encode("utf-8")

    with pytest.raises(MezzApiError) as caught:
        MezzApiClient._raise_api_error(500, response_body)

    assert str(caught.value) == "평가 처리 중 오류가 발생했습니다."
    assert "private" not in str(caught.value)
    assert "C:/" not in str(caught.value)
