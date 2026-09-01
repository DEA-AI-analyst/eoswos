from datetime import date

import pytest

from mezz_evaluation_contract import (
    SELF_STOCK_PRODUCT,
    THIRD_PARTY_PRODUCT,
    bps_provenance_display_rows,
    bps_provenance_receipt,
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
    values.update({"conversion_price": 0, "call_rate": 1.1, "ttm_years": 30.1})
    errors = validate_draft(values, today=date(2026, 8, 24))
    assert len(errors) == 3
    assert "최초 계약 TTM" in " ".join(errors)


def test_contract_ttm_range_is_point_25_to_30_and_payload_keeps_raw_value() -> None:
    values = _valid_self_stock()
    values["ttm_years"] = 30.0

    assert validate_draft(values, today=date(2026, 8, 31)) == []
    assert build_api_payload(values, today=date(2026, 8, 31))["ttm_years"] == 30.0

    values["ttm_years"] = 0.24
    assert "최초 계약 TTM" in " ".join(
        validate_draft(values, today=date(2026, 8, 31))
    )


def test_self_stock_missing_underlying_is_normalized() -> None:
    values = _valid_self_stock()
    values["stock_code"] = None
    assert "stock_code" not in missing_fields(values)


def test_invalid_payload_is_never_sent() -> None:
    values = _valid_self_stock()
    values["issuer_stock_code"] = "720"
    with pytest.raises(ValueError):
        build_api_payload(values, today=date(2026, 8, 24))


def test_optional_bps_provenance_receipt_is_preserved_without_inference() -> None:
    raw_receipt = {
        "status": "CANONICAL_CFS",
        "fs_selected_date": "2026-06-30",
        "fs_type": "CFS",
        "financial_entity": "underlying_issuer",
        "scoring_source": "DART_KRX",
        "source_note": "API-approved source note",
        "future_optional_field": "preserved",
    }

    receipt = bps_provenance_receipt({"bps_provenance": raw_receipt})

    assert receipt == raw_receipt
    assert receipt is not raw_receipt


def test_bps_provenance_display_translates_only_documented_enums() -> None:
    rows = dict(
        bps_provenance_display_rows(
            {
                "bps_provenance": {
                    "status": "OWNERS_EQUITY_CONTROLLED",
                    "fs_selected_date": "2026-06-30",
                    "fs_type": "CFS",
                    "financial_entity": "underlying_issuer",
                    "scoring_source": "DART_KRX",
                    "source_note": "지배기업 소유주지분 검증 완료",
                }
            }
        )
    )

    assert rows == {
        "BPS 적용 기준": "지배기업 소유주지분 기준 (통제 대체)",
        "재무정보 기준일": "2026-06-30",
        "재무제표": "연결재무제표(CFS)",
        "재무정보 대상": "기초자산 발행사",
        "평가 사용 출처": "DART 재무 + 검증된 KRX 상장주",
        "출처 상세": "지배기업 소유주지분 검증 완료",
    }


@pytest.mark.parametrize(
    ("status", "fs_type", "financial_entity", "expected_status", "expected_entity"),
    (
        (
            "CANONICAL_CFS",
            "CFS",
            "issuer",
            "연결재무제표 기준 (비지배지분 차감)",
            "발행사",
        ),
        (
            "OWNERS_EQUITY_CONTROLLED",
            "CFS",
            "underlying_issuer",
            "지배기업 소유주지분 기준 (통제 대체)",
            "기초자산 발행사",
        ),
        (
            "EXPLICIT_OFS",
            "OFS",
            "issuer",
            "별도재무제표 기준",
            "발행사",
        ),
    ),
)
def test_all_documented_status_and_entity_enums_have_explicit_labels(
    status,
    fs_type,
    financial_entity,
    expected_status,
    expected_entity,
) -> None:
    rows = dict(
        bps_provenance_display_rows(
            {
                "bps_provenance": {
                    "status": status,
                    "fs_type": fs_type,
                    "financial_entity": financial_entity,
                    "scoring_source": "DART_KRX",
                }
            }
        )
    )

    assert rows["BPS 적용 기준"] == expected_status
    assert rows["재무정보 대상"] == expected_entity


@pytest.mark.parametrize(
    "response",
    (None, {}, {"bps_provenance": None}, {"bps_provenance": "legacy"}),
)
def test_missing_or_legacy_bps_provenance_has_safe_backcompat_message(response) -> None:
    assert bps_provenance_display_rows(response) == [
        ("BPS 기준", "BPS 기준정보 미제공")
    ]


def test_unknown_provenance_enums_are_not_inferred() -> None:
    rows = dict(
        bps_provenance_display_rows(
            {
                "bps_provenance": {
                    "status": "UNKNOWN",
                    "fs_type": "UNKNOWN",
                    "financial_entity": "UNKNOWN",
                    "scoring_source": "UNKNOWN",
                }
            }
        )
    )

    assert rows["BPS 적용 기준"] == "미제공"
    assert rows["재무제표"] == "미제공"
    assert rows["재무정보 대상"] == "미제공"
    assert rows["평가 사용 출처"] == "미제공"
