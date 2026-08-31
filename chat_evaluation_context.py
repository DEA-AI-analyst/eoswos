"""Read-only, allow-listed evaluation context for Chatbase explanations."""

from __future__ import annotations

import copy
import json
from typing import Any, Iterable


_TOP_LEVEL_FIELDS = (
    "company",
    "issuer_company",
    "underlying_company",
    "stock_code",
    "m_grade",
    "m_score",
    "final_rank",
    "final_score",
    "selected_price_basis",
    "price_basis_date",
)

_BASIS_FIELDS = (
    "price",
    "m_grade",
    "m_score",
    "final_rank",
    "final_score",
    "reach_pk_strength",
    "timing_point",
)

_AXIS_FIELDS = ("grade", "score", "rank")

_ML_FEATURE_FIELDS = (
    ("TTM_years", "사용", "사용"),
    ("Final_Efficiency", "사용", "사용"),
    ("Debt_ratio", "사용", "사용"),
    ("BPS_inverse", "사용", "미사용"),
    ("Pre_Issue_inverse", "사용", "사용"),
    ("Return_6M", "사용", "사용"),
    ("Relative_HV_252_inverse", "사용", "사용"),
    ("Exercise_Period_Years_Cap365", "사용", "사용"),
)

_REPORT_TERMS = (
    "ai평가보고서",
    "검토보고서",
    "평가보고서",
    "심사보고서",
    "검토의견",
    "평가의견",
    "심사의견",
    "심사의견서",
    "보고서",
)


def classify_evaluation_response_mode(prompt: str) -> str:
    """Classify presentation intent without changing chat routing."""

    normalized = "".join(str(prompt or "").lower().split())
    if any(term in normalized for term in _REPORT_TERMS):
        return "report"
    return "explanation"


def latest_evaluation_result(messages: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Return an isolated copy of the latest confirmed API result."""

    for message in reversed(list(messages)):
        if message.get("kind") == "result" and isinstance(message.get("result"), dict):
            return copy.deepcopy(message["result"])
    return None


def build_read_only_evaluation_context(
    current_evaluation: dict[str, Any] | None,
    *,
    response_mode: str = "explanation",
) -> dict[str, Any] | None:
    """Create a minimal fact-only context without mutating the API result."""

    if not current_evaluation:
        return None

    facts = {
        field: _json_scalar(current_evaluation.get(field))
        for field in _TOP_LEVEL_FIELDS
        if current_evaluation.get(field) is not None
    }

    price_basis = current_evaluation.get("price_basis")
    basis_facts: dict[str, Any] = {}
    if isinstance(price_basis, dict):
        for basis in ("1D", "1W", "1M"):
            source = price_basis.get(basis)
            if not isinstance(source, dict):
                continue
            item = {
                field: _json_scalar(source.get(field))
                for field in _BASIS_FIELDS
                if source.get(field) is not None
            }
            for source_name, output_name in (
                ("e_m", "e_M"),
                ("p_m", "p_M"),
                ("s_m", "s_M"),
            ):
                axis = source.get(source_name)
                if isinstance(axis, dict):
                    item[output_name] = {
                        field: _json_scalar(axis.get(field))
                        for field in _AXIS_FIELDS
                        if axis.get(field) is not None
                    }
            basis_facts[basis] = item

    if basis_facts:
        facts["price_basis"] = basis_facts

    feature_snapshot = current_evaluation.get("ml_feature_snapshot")
    if isinstance(feature_snapshot, dict):
        feature_rows = []
        for feature, p_m_usage, s_m_usage in _ML_FEATURE_FIELDS:
            feature_rows.append(
                {
                    "feature": feature,
                    "value": _json_scalar(feature_snapshot.get(feature)),
                    "p_M": p_m_usage,
                    "s_M": s_m_usage,
                }
            )
        facts["ml_feature_snapshot"] = {
            "price_basis": _json_scalar(feature_snapshot.get("price_basis")),
            "features": feature_rows,
        }

    context = {
        "policy": (
            "확정된 모델 산출값이다. 값을 재계산·변경·추정하지 말고, 제공된 값만 설명한다. "
            "M Grade는 개별 성공확률이나 투자추천이 아니다. "
            "p_M과 s_M은 Final Score의 직접 구성축이고 e_M은 구조적 효율성 해석축이다. "
            "Final_Efficiency는 p_M·s_M 입력 Feature이지만 기업별 인과 기여량을 단정하지 않는다."
        ),
        "facts": facts,
    }

    if response_mode == "report":
        context["response_contract"] = {
            "mode": "report",
            "heading_level": "Markdown ### only",
            "section_order": [
                "1. 평가 개요",
                "2. 확정 평가결과",
                "3. ML 입력 Feature 표",
                "4. 직접 구성축(p_M·s_M)",
                "5. 구조적 효율성(e_M)",
                "6. 가격기준 일관성",
                "7. 검토의견",
                "8. 종합 결론",
            ],
            "ml_feature_table": {
                "columns": ["Feature", "값", "p_M", "s_M"],
                "rows_source": "facts.ml_feature_snapshot.features",
                "missing_value": "미제공",
            },
            "rules": [
                "위 섹션 순서를 유지한다.",
                "ML 입력 Feature 표에는 제공된 값만 그대로 표시한다.",
                "누락된 값은 추정하지 않고 미제공으로 표시한다.",
                "동일한 설명을 여러 섹션에서 반복하지 않는다.",
                "모든 문장은 존댓말로 작성한다.",
            ],
        }

    return context


def safe_chat_history(
    messages: Iterable[dict[str, Any]],
    *,
    limit: int = 12,
) -> list[dict[str, str]]:
    """Keep only recent plain user/assistant text suitable for Chatbase."""

    safe: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"} or message.get("kind") != "text":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            safe.append({"role": role, "content": content[:4_000]})
    return safe[-max(0, int(limit)) :]


def evaluation_fingerprint(value: dict[str, Any] | None) -> str:
    """Stable snapshot used to prove that chat handling did not alter results."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
