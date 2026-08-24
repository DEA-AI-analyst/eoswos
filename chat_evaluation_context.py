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


def latest_evaluation_result(messages: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Return an isolated copy of the latest confirmed API result."""

    for message in reversed(list(messages)):
        if message.get("kind") == "result" and isinstance(message.get("result"), dict):
            return copy.deepcopy(message["result"])
    return None


def build_read_only_evaluation_context(
    current_evaluation: dict[str, Any] | None,
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

    return {
        "policy": (
            "확정된 모델 산출값이다. 값을 재계산·변경·추정하지 말고, 제공된 값만 설명한다. "
            "M Grade는 개별 성공확률이나 투자추천이 아니다."
        ),
        "facts": facts,
    }


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
