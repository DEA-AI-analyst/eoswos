from datetime import date

import pytest

from mezz_evaluation_contract import (
    SELF_STOCK_PRODUCT,
    THIRD_PARTY_PRODUCT,
    build_api_payload,
    missing_fields,
    validate_draft,
)


def _valid_self_stock() -> dict:
    return {
        "product_type": SELF_STOCK_PRODUCT,
        "issuer_stock_code": "000720",
        "stock_code": "000720",
        "credit_rating": "AA-",
        "conversion_price": 150607,
        "call_rate": 0.0,
        "ttm_years": 5.0,
        "issue_date": "2026-07-07",
    }


def test_structured_self_stock_payload_is_preserved() -> None:
    values = _valid_self_stock()
    assert validate_draft(values, today=date(2026, 8, 24)) == []
    assert build_api_payload(values, today=date(2026, 8, 24)) == values


def test_third_party_contract_requires_distinct_codes() -> None:
    values = _valid_self_stock()
    values.update(
        {
            "product_type": THIRD_PARTY_PRODUCT,
            "stock_code": "005930",
        }
    )
    assert validate_draft(values, today=date(2026, 8, 24)) == []
    values["stock_code"] = values["issuer_stock_code"]
    assert "타사주식 EB의 발행회사와 기초자산은 달라야 합니다." in validate_draft(
        values,
        today=date(2026, 8, 24),
    )


def test_structured_validation_rejects_invalid_ranges() -> None:
    values = _valid_self_stock()
    values.update({"conversion_price": 0, "call_rate": 1.1, "ttm_years": 5.1})
    errors = validate_draft(values, today=date(2026, 8, 24))
    assert len(errors) == 3


def test_self_stock_missing_underlying_is_normalized() -> None:
    values = _valid_self_stock()
    values["stock_code"] = None
    assert "stock_code" not in missing_fields(values)


def test_invalid_payload_is_never_sent() -> None:
    values = _valid_self_stock()
    values["issuer_stock_code"] = "720"
    with pytest.raises(ValueError):
        build_api_payload(values, today=date(2026, 8, 24))
