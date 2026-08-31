"""Structured input contract for the EOSWOS single-candidate evaluation form."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal, TypedDict, cast


SELF_STOCK_PRODUCT = "CB/BW/EB(자기주식)"
THIRD_PARTY_PRODUCT = "EB(타사주식)"
CONTRACT_TTM_MIN_YEARS = 0.25
CONTRACT_TTM_MAX_YEARS = 30.0
PRODUCT_TYPES = (SELF_STOCK_PRODUCT, THIRD_PARTY_PRODUCT)

CREDIT_RATINGS = (
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
    "B-",
    "CCC+",
    "CCC",
    "CCC-",
    "CC+",
    "CC",
    "CC-",
    "C+",
    "C",
    "C-",
    "무등급",
    "UNRATED",
    "N/R",
    "NR",
)

REQUIRED_FIELDS = (
    "product_type",
    "issuer_stock_code",
    "stock_code",
    "credit_rating",
    "conversion_price",
    "call_rate",
    "ttm_years",
    "issue_date",
)

FIELD_LABELS = {
    "product_type": "상품유형",
    "issuer_stock_code": "발행회사 종목코드",
    "stock_code": "기초자산 종목코드",
    "credit_rating": "신용등급",
    "conversion_price": "전환/행사/교환가액",
    "call_rate": "Call rate",
    "ttm_years": "최초 계약 TTM",
    "issue_date": "발행일",
}


class BpsProvenanceReceipt(TypedDict, total=False):
    """Optional API receipt copied without calculating or inferring any source."""

    status: Literal[
        "CANONICAL_CFS",
        "OWNERS_EQUITY_CONTROLLED",
        "EXPLICIT_OFS",
    ]
    fs_selected_date: str
    fs_type: str
    financial_entity: Literal["issuer", "underlying_issuer"]
    scoring_source: Literal["DART_KRX"]
    source_note: str


_BPS_STATUS_LABELS = {
    "CANONICAL_CFS": "연결재무제표 기준 (비지배지분 차감)",
    "OWNERS_EQUITY_CONTROLLED": "지배기업 소유주지분 기준 (통제 대체)",
    "EXPLICIT_OFS": "별도재무제표 기준",
}
_BPS_FS_TYPE_LABELS = {
    "CFS": "연결재무제표(CFS)",
    "OFS": "별도재무제표(OFS)",
}
_BPS_FINANCIAL_ENTITY_LABELS = {
    "issuer": "발행사",
    "underlying_issuer": "기초자산 발행사",
}
_BPS_SCORING_SOURCE_LABELS = {
    "DART_KRX": "DART 재무 + 검증된 KRX 상장주",
}


def bps_provenance_receipt(
    response: Mapping[str, Any] | None,
) -> BpsProvenanceReceipt | None:
    """Return the optional API receipt unchanged; never derive missing fields."""

    if not isinstance(response, Mapping):
        return None
    raw_receipt = response.get("bps_provenance")
    if not isinstance(raw_receipt, Mapping):
        return None
    return cast(BpsProvenanceReceipt, dict(raw_receipt))


def bps_provenance_display_rows(
    response: Mapping[str, Any] | None,
) -> list[tuple[str, str]]:
    """Translate only documented receipt enums into user-facing labels."""

    receipt = bps_provenance_receipt(response)
    if receipt is None:
        return [("BPS 기준", "BPS 기준정보 미제공")]

    def _enum_label(field: str, labels: Mapping[str, str]) -> str:
        value = str(receipt.get(field) or "").strip()
        return labels.get(value, "미제공")

    def _value(field: str) -> str:
        value = str(receipt.get(field) or "").strip()
        return value or "미제공"

    return [
        ("BPS 적용 기준", _enum_label("status", _BPS_STATUS_LABELS)),
        ("재무정보 기준일", _value("fs_selected_date")),
        ("재무제표", _enum_label("fs_type", _BPS_FS_TYPE_LABELS)),
        (
            "재무정보 대상",
            _enum_label("financial_entity", _BPS_FINANCIAL_ENTITY_LABELS),
        ),
        (
            "평가 사용 출처",
            _enum_label("scoring_source", _BPS_SCORING_SOURCE_LABELS),
        ),
        ("출처 상세", _value("source_note")),
    ]


def missing_fields(values: dict[str, Any]) -> list[str]:
    normalized = dict(values)
    if normalized.get("product_type") == SELF_STOCK_PRODUCT and normalized.get(
        "issuer_stock_code"
    ):
        normalized["stock_code"] = normalized["issuer_stock_code"]
    return [field for field in REQUIRED_FIELDS if normalized.get(field) in (None, "")]


def validate_draft(values: dict[str, Any], today: date | None = None) -> list[str]:
    errors: list[str] = []
    product_type = values.get("product_type")
    issuer = str(values.get("issuer_stock_code") or "")
    stock = str(values.get("stock_code") or "")

    if product_type not in PRODUCT_TYPES:
        errors.append("상품유형을 확인해 주세요.")
    if not re.fullmatch(r"\d{6}", issuer):
        errors.append("발행회사 종목코드는 6자리 숫자여야 합니다.")
    if not re.fullmatch(r"\d{6}", stock):
        errors.append("기초자산 종목코드는 6자리 숫자여야 합니다.")
    if product_type == SELF_STOCK_PRODUCT and issuer and stock and issuer != stock:
        errors.append("자기주식 상품의 두 종목코드는 같아야 합니다.")
    if product_type == THIRD_PARTY_PRODUCT and issuer and stock and issuer == stock:
        errors.append("타사주식 EB의 발행회사와 기초자산은 달라야 합니다.")
    if values.get("credit_rating") not in CREDIT_RATINGS:
        errors.append("신용등급을 확인해 주세요.")
    if not _in_numeric_range(
        values.get("conversion_price"), lower=0, upper=None, lower_open=True
    ):
        errors.append("전환/행사/교환가액은 0보다 커야 합니다.")
    if not _in_numeric_range(values.get("call_rate"), lower=0, upper=1):
        errors.append("Call rate는 0~1 범위여야 합니다.")
    if not _in_numeric_range(
        values.get("ttm_years"),
        lower=CONTRACT_TTM_MIN_YEARS,
        upper=CONTRACT_TTM_MAX_YEARS,
    ):
        errors.append(
            f"최초 계약 TTM은 {CONTRACT_TTM_MIN_YEARS:g}~"
            f"{CONTRACT_TTM_MAX_YEARS:g}년 범위여야 합니다."
        )

    try:
        issue_date = date.fromisoformat(str(values.get("issue_date") or ""))
        if issue_date > (today or date.today()):
            errors.append("발행일은 오늘 이후일 수 없습니다.")
    except ValueError:
        errors.append("발행일은 YYYY-MM-DD 형식이어야 합니다.")

    return errors


def build_api_payload(
    values: dict[str, Any],
    today: date | None = None,
) -> dict[str, Any]:
    errors = validate_draft(values, today=today)
    if errors:
        raise ValueError(" ".join(errors))
    return {
        "product_type": str(values["product_type"]),
        "issuer_stock_code": str(values["issuer_stock_code"]),
        "stock_code": str(values["stock_code"]),
        "credit_rating": str(values["credit_rating"]),
        "conversion_price": int(values["conversion_price"]),
        "call_rate": float(values["call_rate"]),
        "ttm_years": float(values["ttm_years"]),
        "issue_date": str(values["issue_date"]),
    }


def _in_numeric_range(
    value: Any,
    *,
    lower: float,
    upper: float | None,
    lower_open: bool = False,
) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if lower_open and number <= lower:
        return False
    if not lower_open and number < lower:
        return False
    return upper is None or number <= upper
