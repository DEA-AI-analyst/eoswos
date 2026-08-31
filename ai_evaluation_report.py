"""Canonical, read-only data contract for the EOSWOS AI evaluation report."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime
from typing import Any, Mapping

from mezz_evaluation_contract import bps_provenance_display_rows


REPORT_REQUEST_TERMS = (
    "ai 평가보고서",
    "ai평가보고서",
    "검토의견",
    "검토 의견",
    "검토보고서",
    "검토 보고서",
    "평가의견",
    "평가 의견",
    "평가보고서",
    "평가 보고서",
    "심사의견",
    "심사 의견",
    "심사의견서",
    "심사 의견서",
    "심사보고서",
    "심사 보고서",
    "보고서",
)

AI_REPORT_GENERATION_REQUEST = (
    "확정 평가결과를 근거로 AI 평가의견 초안만 작성하세요. "
    "제목, 표, 번호 목록 없이 5~7개의 짧은 존댓말 문장으로 작성하세요. "
    "핵심 해석, 상대적 강점·제한축, 추가 검토사항을 포함하되 제공되지 않은 사실이나 "
    "수치·등급을 만들지 마세요. 확정 정량값과 등급은 고정 결과 영역에 이미 표시되므로 "
    "본문에서 M Grade, M Score, M Rank, Final Score 또는 다른 숫자를 직접 반복하지 말고 "
    "질적 해석만 작성하세요. M Grade를 성공확률, 투자추천, 승인 또는 부결로 표현하지 "
    "말고 M5는 후순위 검토영역으로 표현하세요. ITM 도달을 투자수익 보장으로 표현하지 마세요. "
    "timing_point의 '당일'은 p_M/s_M 분류에서 생성된 보조 라벨이며 행사개시일, 실제 First_ITM "
    "날짜 또는 경과기간으로 바꾸어 쓰지 마세요."
)

AI_REPORT_GROUNDING_RETRY_REQUEST = (
    "AI 평가의견을 다시 작성하세요. 이전 답변을 인용하거나 수정 사유를 설명하지 마세요. "
    "timing_point, 실제 사건 시점, 날짜 및 경과기간은 언급하지 마세요. "
    "확정 정량값과 등급을 반복하지 않고 제공된 사실의 질적 해석만 사용하여 "
    "5~7개의 짧은 존댓말 문장으로 작성하세요. 투자추천·승인·부결 의견은 작성하지 마세요."
)

_MONITORING_ALIASES = {
    "actual_issue_date": ("actual_issue_date", "Actual_Issue_Date", "Actual Issue Date"),
    "monitoring_date": ("monitoring_date", "Monitoring_Date", "Monitoring Date"),
    "fs_target_date": ("fs_target_date", "FS_Target_Date", "FS Target Date"),
    "original_ttm_years": (
        "original_ttm_years",
        "Original_TTM_years",
        "Original TTM",
    ),
    "rebased_ttm_years": (
        "rebased_ttm_years",
        "Rebased_TTM_years_raw",
        "Rebased TTM",
    ),
    "model_ttm_years": (
        "model_ttm_years",
        "Rebased_TTM_years_model",
        "Model TTM",
    ),
}

_STATUS_LABELS = {
    "CANONICAL_CFS": "연결재무제표 기준 (비지배지분 차감)",
    "OWNERS_EQUITY_CONTROLLED": "지배기업 소유주지분 통제 대체",
    "EXPLICIT_OFS": "별도재무제표 기준",
}
_ENTITY_LABELS = {
    "issuer": "발행사",
    "underlying_issuer": "기초자산 발행사",
}
_SCORING_SOURCE_LABELS = {
    "DART_KRX": "DART 재무정보 + 검증된 KRX 상장주식수",
}


def is_ai_report_request(prompt: str) -> bool:
    normalized = " ".join(str(prompt or "").lower().split())
    compact = normalized.replace(" ", "")
    return any(term in normalized or term.replace(" ", "") in compact for term in REPORT_REQUEST_TERMS)


def build_canonical_report_context(
    current_evaluation: Mapping[str, Any] | None,
    *,
    submitted_input: Mapping[str, Any] | None = None,
    model_mode: str | None = None,
) -> dict[str, Any] | None:
    """Build the single report source without recalculating scoring values."""

    if not isinstance(current_evaluation, Mapping) or not current_evaluation:
        return None

    result = copy.deepcopy(dict(current_evaluation))
    submitted = copy.deepcopy(dict(submitted_input or {}))
    monitoring_fields = _monitoring_fields(result)
    explicit_type = str(result.get("evaluation_type") or "").strip().lower()
    is_monitoring = bool(monitoring_fields) or explicit_type in {
        "monitoring",
        "monitoring_revaluation",
        "사후관리 재평가",
    }
    evaluation_type = "사후관리 재평가" if is_monitoring else "신규평가"

    selected_basis = str(result.get("selected_price_basis") or "").upper()
    price_basis_source = result.get("price_basis")
    price_basis = price_basis_source if isinstance(price_basis_source, Mapping) else {}
    selected = price_basis.get(selected_basis)
    selected = selected if isinstance(selected, Mapping) else {}

    common_info = _without_empty(
        {
            "company": result.get("company") or result.get("underlying_company"),
            "issuer_company": result.get("issuer_company"),
            "underlying_company": _same_entity_label(result.get("underlying_company")),
            "product_type": result.get("product_type") or submitted.get("product_type"),
            "evaluation_type": evaluation_type,
            "price_basis_date": result.get("price_basis_date"),
            "issue_date": result.get("issue_date") or submitted.get("issue_date"),
            "issuer_stock_code": result.get("issuer_stock_code") or submitted.get("issuer_stock_code"),
            "stock_code": result.get("stock_code") or submitted.get("stock_code"),
            "credit_rating": result.get("credit_rating") or submitted.get("credit_rating"),
            "conversion_price": result.get("conversion_price") or submitted.get("conversion_price"),
            "call_rate": result.get("call_rate") if result.get("call_rate") is not None else submitted.get("call_rate"),
            "contract_ttm_years": result.get("ttm_years") if result.get("ttm_years") is not None else submitted.get("ttm_years"),
            "model_ttm_years": _nested_value(result, "ml_feature_snapshot", "TTM_years"),
        }
    )

    evaluation_result = _without_empty(
        {
            "m_grade": result.get("m_grade"),
            "m_score": result.get("m_score"),
            "m_rank": result.get("final_rank"),
            "final_score": result.get("final_score"),
            "selected_price_basis": selected_basis or None,
        }
    )
    axis_results = {
        output_name: _copy_axis(selected.get(source_name))
        for source_name, output_name in (("e_m", "e_M"), ("p_m", "p_M"), ("s_m", "s_M"))
    }
    axis_results = {key: value for key, value in axis_results.items() if value}

    price_rows = []
    for basis in ("1D", "1W", "1M"):
        source = price_basis.get(basis)
        if not isinstance(source, Mapping):
            continue
        price_rows.append(
            _without_empty(
                {
                    "price_basis": basis,
                    "price": source.get("price"),
                    "m_grade": source.get("m_grade"),
                    "m_score": source.get("m_score"),
                    "m_rank": source.get("final_rank"),
                    "final_score": source.get("final_score"),
                    "e_M": _copy_axis(source.get("e_m")),
                    "p_M": _copy_axis(source.get("p_m")),
                    "s_M": _copy_axis(source.get("s_m")),
                    "reach_pk_strength": source.get("reach_pk_strength"),
                    "timing_point": source.get("timing_point"),
                }
            )
        )

    provenance = _provenance(result, model_mode=model_mode)
    context = {
        "schema_version": 1,
        "evaluation_type": evaluation_type,
        "request_id": _scalar(result.get("request_id")),
        "common_info": common_info,
        "evaluation_result": evaluation_result,
        "axis_results": axis_results,
        "price_basis_results": price_rows,
        "provenance": provenance,
        "ai_grounding": {
            "ml_feature_snapshot": _safe_mapping(result.get("ml_feature_snapshot")),
            "reach_pk_strength": _scalar(result.get("reach_pk_strength")),
            "timing_point": _scalar(result.get("timing_point")),
            "timing_point_semantics": (
                "p_M/s_M 분류에서 생성된 보조 라벨이며 실제 행사개시일, "
                "First_ITM 날짜 또는 경과기간이 아님"
            ),
            "verified_event_timing": False,
            "review_area": _scalar(result.get("review_area")),
        },
    }
    if monitoring_fields:
        context["monitoring_fields"] = monitoring_fields
    return context


def build_ai_report_generation_context(canonical_context: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap canonical facts in a strict narrative-only Chatbase contract."""

    return {
        "policy": (
            "확정된 M-CORE/API 산출값이다. 값을 재계산·변경·추정하지 말고 제공된 사실만 해석한다. "
            "M Grade는 상대적 검토 우선순위이며 성공확률·투자추천·승인·부결이 아니다. "
            "Final Score의 직접 구성축은 p_M과 s_M이고 e_M은 구조적 효율성 축이다. "
            "M5는 후순위 검토영역이며 ITM 도달은 투자수익 보장을 뜻하지 않는다. "
            "timing_point는 p_M/s_M 분류의 보조 라벨이며 실제 행사개시일·First_ITM 날짜·경과기간이 아니다."
        ),
        "facts": copy.deepcopy(dict(canonical_context)),
        "response_contract": {
            "mode": "ai_evaluation_report_commentary",
            "output": "AI 평가의견 본문만",
            "sentence_count": "5~7",
            "required_topics": ["핵심 해석", "상대적 강점·제한축", "추가 검토사항"],
            "forbidden": [
                "새 수치 또는 등급 생성",
                "확정 정량값 또는 등급의 본문 반복",
                "성공확률 표현",
                "투자추천",
                "승인 또는 부결 판단",
                "제공되지 않은 provenance 추정",
                "timing_point 보조 라벨을 행사개시일·실제 First_ITM 날짜·경과기간으로 해석",
            ],
        },
    }


def report_source_fingerprint(
    current_evaluation: Mapping[str, Any] | None,
    submitted_input: Mapping[str, Any] | None,
) -> str:
    payload = {"evaluation": current_evaluation, "submitted_input": submitted_input}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_generated_quantitative_parity(
    commentary: str,
    canonical_context: Mapping[str, Any],
) -> list[str]:
    """Reject explicitly labelled quantitative claims that conflict with API facts."""

    text = str(commentary or "").strip()
    if not text:
        return ["AI 평가의견이 비어 있습니다."]
    facts = canonical_context.get("evaluation_result")
    facts = facts if isinstance(facts, Mapping) else {}
    errors: list[str] = []

    expected_grade = str(facts.get("m_grade") or "").upper()
    for found in re.findall(
        r"(?:M\s*Grade|M\s*등급|M등급)\s*(?:은|는|이|가|:|=)?\s*(M[1-5])",
        text,
        re.IGNORECASE,
    ):
        if expected_grade and found.upper() != expected_grade:
            errors.append("M Grade")

    _validate_number_claims(
        text,
        patterns=(r"M\s*Score", r"M\s*점수"),
        expected=facts.get("m_score"),
        digits=3,
        label="M Score",
        errors=errors,
    )
    _validate_number_claims(
        text,
        patterns=(r"M\s*Rank", r"M\s*순위"),
        expected=facts.get("m_rank"),
        digits=0,
        label="M Rank",
        errors=errors,
    )
    _validate_number_claims(
        text,
        patterns=(r"Final\s*Score", r"최종\s*점수"),
        expected=facts.get("final_score"),
        digits=6,
        label="Final Score",
        errors=errors,
    )
    return list(dict.fromkeys(errors))


def validate_generated_grounding(
    commentary: str,
    canonical_context: Mapping[str, Any],
) -> list[str]:
    """Reject event-timing claims that the canonical report facts do not establish."""

    text = str(commentary or "").strip()
    grounding = canonical_context.get("ai_grounding")
    grounding = grounding if isinstance(grounding, Mapping) else {}
    if bool(grounding.get("verified_event_timing")):
        return []

    prohibited_patterns = (
        r"행사\s*개시일",
        r"First[_\s-]*ITM\s*(?:date|날짜|일자)",
        r"실제\s*(?:도달일|도달\s*날짜)",
        r"도달\s*(?:까지|소요)[^.\n]*?\d+\s*일",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in prohibited_patterns):
        return ["도달시점 grounding"]
    return []


def new_report_state(
    *,
    canonical_context: Mapping[str, Any],
    ai_commentary: str,
    source_fingerprint: str,
    generated_at: datetime,
) -> dict[str, Any]:
    draft = str(ai_commentary or "").strip()
    return {
        "request_id": canonical_context.get("request_id"),
        "source_fingerprint": source_fingerprint,
        "canonical_context": copy.deepcopy(dict(canonical_context)),
        "ai_draft": draft,
        "ai_commentary": draft,
        "reviewer_comment": "",
        "changed": False,
        "generated_at": generated_at.isoformat(),
        "updated_at": None,
    }


def _provenance(result: Mapping[str, Any], *, model_mode: str | None) -> dict[str, Any]:
    raw = result.get("bps_provenance")
    receipt = raw if isinstance(raw, Mapping) else {}
    provenance = _without_empty(
        {
            "status": receipt.get("status"),
            "status_label": _STATUS_LABELS.get(str(receipt.get("status") or "")),
            "fs_selected_date": receipt.get("fs_selected_date"),
            "fs_type": receipt.get("fs_type"),
            "financial_entity": receipt.get("financial_entity"),
            "financial_entity_label": _ENTITY_LABELS.get(str(receipt.get("financial_entity") or "")),
            "scoring_source": receipt.get("scoring_source"),
            "scoring_source_label": _SCORING_SOURCE_LABELS.get(str(receipt.get("scoring_source") or "")),
            "source_note": receipt.get("source_note"),
            "model_mode": model_mode,
        }
    )
    if receipt:
        provenance["display_rows"] = [
            {"label": label, "value": value}
            for label, value in bps_provenance_display_rows(dict(result))
        ]
    return provenance


def _monitoring_fields(result: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for output_name, aliases in _MONITORING_ALIASES.items():
        value = next((result.get(name) for name in aliases if result.get(name) is not None), None)
        if value not in (None, ""):
            values[output_name] = _scalar(value)
    return values


def _copy_axis(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _without_empty({key: value.get(key) for key in ("grade", "score", "rank")})


def _nested_value(source: Mapping[str, Any], outer: str, inner: str) -> Any:
    nested = source.get(outer)
    return nested.get(inner) if isinstance(nested, Mapping) else None


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _scalar(item) for key, item in value.items()}


def _same_entity_label(value: Any) -> Any:
    if str(value or "").strip() == "좌동":
        return "상동"
    return value


def _without_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _scalar(item) if not isinstance(item, Mapping) else copy.deepcopy(dict(item))
        for key, item in value.items()
        if item not in (None, "", {})
    }


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _validate_number_claims(
    text: str,
    *,
    patterns: tuple[str, ...],
    expected: Any,
    digits: int,
    label: str,
    errors: list[str],
) -> None:
    if expected is None:
        return
    try:
        expected_number = float(expected)
    except (TypeError, ValueError):
        return
    joined = "|".join(patterns)
    pattern = rf"(?:{joined})\s*(?:은|는|이|가|:|=)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)"
    for found in re.findall(pattern, text, re.IGNORECASE):
        try:
            actual = float(found.replace(",", ""))
        except ValueError:
            continue
        if round(actual, digits) != round(expected_number, digits):
            errors.append(label)
