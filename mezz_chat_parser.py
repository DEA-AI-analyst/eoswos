"""Deterministic natural-language extraction for the EOSWOS evaluation chat."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


SELF_STOCK_PRODUCT = "CB/BW/EB(자기주식)"
THIRD_PARTY_PRODUCT = "EB(타사주식)"
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
    "CCC",
    "CC",
    "C",
    "D",
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
    "ttm_years": "잔존만기",
    "issue_date": "발행일",
}

_BLOCKED_TERMS = (
    "api key",
    "api키",
    "api 키",
    "시스템 프롬프트",
    "소스코드",
    "source code",
    "학습데이터",
    "학습 데이터",
    "모델 파라미터",
    "operating_reference",
    "운영 레퍼런스",
    "dea 산식",
    "모델 우회",
    "모델 취약점",
)


@dataclass(frozen=True)
class ParseOutcome:
    updates: dict[str, Any]
    warnings: tuple[str, ...] = ()
    blocked: bool = False
    reset: bool = False
    confirm: bool = False


def parse_evaluation_prompt(
    text: str,
    current: dict[str, Any] | None = None,
) -> ParseOutcome:
    raw = str(text or "").strip()
    lowered = raw.lower()
    current_values = dict(current or {})

    if not raw:
        return ParseOutcome(updates={})
    if any(term in lowered for term in _BLOCKED_TERMS):
        return ParseOutcome(updates={}, blocked=True)
    if re.fullmatch(r"\s*(?:새\s*평가|초기화|다시\s*시작|처음부터)\s*", raw, re.I):
        return ParseOutcome(updates={}, reset=True)
    if re.fullmatch(r"\s*(?:확인|네|예|맞아|맞습니다|평가\s*실행|실행|진행)\s*[.!]?\s*", raw, re.I):
        return ParseOutcome(updates={}, confirm=True)

    updates: dict[str, Any] = {}
    warnings: list[str] = []
    upper = raw.upper()

    if re.search(r"타사\s*주식|타사\s*EB|타사주|교환\s*대상\s*(?:주식|종목)", raw, re.I):
        updates["product_type"] = THIRD_PARTY_PRODUCT
    elif re.search(r"자기\s*주식|자사주|(?<![A-Z])CB(?![A-Z])|(?<![A-Z])BW(?![A-Z])|전환사채|신주인수권부사채", upper, re.I):
        updates["product_type"] = SELF_STOCK_PRODUCT

    rating_pattern = "|".join(re.escape(value) for value in sorted(CREDIT_RATINGS, key=len, reverse=True))
    rating_match = re.search(rf"(?<![A-Z])({rating_pattern})(?![A-Z+\-])", upper)
    if rating_match:
        updates["credit_rating"] = rating_match.group(1)

    conversion_match = re.search(
        r"(?:전환\s*/\s*행사\s*/\s*교환\s*가액|전환(?:가격|가액|가)|행사(?:가격|가액|가)|교환(?:가격|가액|가))"
        r"\s*(?:은|는|:|=)?\s*([0-9][0-9,]*)\s*원?",
        raw,
        re.I,
    )
    if conversion_match:
        updates["conversion_price"] = int(conversion_match.group(1).replace(",", ""))

    call_match = re.search(
        r"(?:콜\s*(?:레이트|금리|비율)?|call\s*rate)\s*(?:은|는|:|=)?\s*([0-9]+(?:\.[0-9]+)?)\s*(%)?",
        raw,
        re.I,
    )
    if call_match:
        call_value = float(call_match.group(1))
        if call_match.group(2) or call_value > 1.0:
            call_value /= 100.0
            if not call_match.group(2):
                warnings.append("Call rate 값은 백분율로 해석했습니다.")
        updates["call_rate"] = call_value

    maturity_match = re.search(
        r"(?:잔존\s*만기|만기|ttm)\s*(?:은|는|:|=)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:년|year)?",
        raw,
        re.I,
    )
    if maturity_match:
        updates["ttm_years"] = float(maturity_match.group(1))

    issue_date = _extract_issue_date(raw)
    if issue_date:
        updates["issue_date"] = issue_date

    issuer_match = _find_labeled_code(
        raw,
        r"(?:채권\s*)?(?:발행회사|발행사|상장회사|issuer)",
    )
    underlying_match = _find_labeled_code(
        raw,
        r"(?:기초자산|교환대상|대상주식|underlying)",
    )
    if issuer_match:
        updates["issuer_stock_code"] = issuer_match
    if underlying_match:
        updates["stock_code"] = underlying_match

    product_type = updates.get("product_type") or current_values.get("product_type")
    candidate_codes = _unlabeled_stock_codes(raw)
    used_codes = {value for value in (issuer_match, underlying_match) if value}
    remaining_codes = [value for value in candidate_codes if value not in used_codes]

    if product_type == SELF_STOCK_PRODUCT:
        code = issuer_match or underlying_match or (remaining_codes[0] if remaining_codes else None)
        if code:
            updates["issuer_stock_code"] = code
            updates["stock_code"] = code
    elif product_type == THIRD_PARTY_PRODUCT:
        if "issuer_stock_code" not in updates and remaining_codes:
            updates["issuer_stock_code"] = remaining_codes.pop(0)
        if "stock_code" not in updates and remaining_codes:
            updates["stock_code"] = remaining_codes.pop(0)
    elif remaining_codes:
        updates["issuer_stock_code"] = remaining_codes[0]

    merged = {**current_values, **updates}
    if merged.get("product_type") == SELF_STOCK_PRODUCT and merged.get("issuer_stock_code"):
        updates["stock_code"] = merged["issuer_stock_code"]

    return ParseOutcome(updates=updates, warnings=tuple(warnings))


def missing_fields(values: dict[str, Any]) -> list[str]:
    normalized = dict(values)
    if normalized.get("product_type") == SELF_STOCK_PRODUCT and normalized.get("issuer_stock_code"):
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
    if not _in_numeric_range(values.get("conversion_price"), lower=0, upper=None, lower_open=True):
        errors.append("전환/행사/교환가액은 0보다 커야 합니다.")
    if not _in_numeric_range(values.get("call_rate"), lower=0, upper=1):
        errors.append("Call rate는 0~1 범위여야 합니다.")
    if not _in_numeric_range(values.get("ttm_years"), lower=0, upper=5):
        errors.append("잔존만기는 0~5년 범위여야 합니다.")

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


def _extract_issue_date(text: str) -> str | None:
    numeric = re.search(
        r"발행일(?:자)?\s*(?:은|는|:|=)?\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})",
        text,
        re.I,
    )
    korean = re.search(
        r"발행일(?:자)?\s*(?:은|는|:|=)?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일",
        text,
        re.I,
    )
    match = numeric or korean
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def _find_labeled_code(text: str, label_pattern: str) -> str | None:
    match = re.search(
        rf"{label_pattern}(?:\s*종목)?(?:\s*코드)?\s*(?:은|는|:|=)?\s*\(?\s*(\d{{6}})\s*\)?",
        text,
        re.I,
    )
    return match.group(1) if match else None


def _unlabeled_stock_codes(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"(?<!\d)(\d{6})(?!\d)", text):
        context = text[max(0, match.start() - 18) : match.start()].lower()
        if any(
            marker in context
            for marker in (
                "전환가",
                "전환가격",
                "전환가액",
                "행사가",
                "행사가격",
                "교환가",
                "교환가격",
                "교환가액",
            )
        ):
            continue
        value = match.group(1)
        if value not in values:
            values.append(value)
    return values


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
