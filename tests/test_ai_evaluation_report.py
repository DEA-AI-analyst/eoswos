import copy
from datetime import datetime, timezone

import pytest

from ai_evaluation_report import (
    AI_REPORT_GENERATION_REQUEST,
    build_ai_report_generation_context,
    build_canonical_report_context,
    is_ai_report_request,
    new_report_state,
    report_source_fingerprint,
    validate_generated_grounding,
    validate_generated_quantitative_parity,
)


def _result() -> dict:
    return {
        "request_id": "req-report-001",
        "company": "현대건설",
        "issuer_company": "현대건설",
        "underlying_company": "현대건설",
        "product_type": "CB/BW/EB(자기주식)",
        "issuer_stock_code": "000720",
        "stock_code": "000720",
        "issue_date": "2026-07-07",
        "price_basis_date": "2026-06-30",
        "selected_price_basis": "1D",
        "m_grade": "M4",
        "m_score": 34.133,
        "final_rank": 1261,
        "final_score": 0.681641,
        "review_area": "상대적 검토영역",
        "reach_pk_strength": "PK 하위",
        "timing_point": "당일",
        "price_basis": {
            basis: {
                "price": price,
                "m_grade": "M4",
                "m_score": 34.133,
                "final_rank": 1261,
                "final_score": 0.681641,
                "e_m": {"grade": "E2", "score": 0.88, "rank": 400},
                "p_m": {"grade": "P4", "score": 0.95, "rank": 1400},
                "s_m": {"grade": "S3", "score": 1.35, "rank": 900},
                "reach_pk_strength": "PK 하위",
                "timing_point": "당일",
            }
            for basis, price in (("1D", 71200), ("1W", 71800), ("1M", 70500))
        },
        "ml_feature_snapshot": {
            "price_basis": "1D",
            "TTM_years": 5.0,
            "Final_Efficiency": 0.88,
            "BPS_inverse": 0.72,
        },
        "bps_provenance": {
            "status": "CANONICAL_CFS",
            "fs_selected_date": "2026-06-30",
            "fs_type": "CFS",
            "financial_entity": "issuer",
            "scoring_source": "DART_KRX",
            "source_note": "DART/KRX canonical source",
        },
        "naver_bps": 999999,
        "secret": "must-not-leak",
    }


def _submitted() -> dict:
    return {
        "product_type": "CB/BW/EB(자기주식)",
        "issuer_stock_code": "000720",
        "stock_code": "000720",
        "credit_rating": "AA-",
        "conversion_price": 150607,
        "call_rate": 0.0,
        "ttm_years": 30.0,
        "issue_date": "2026-07-07",
    }


def test_canonical_context_copies_api_values_and_safe_provenance_only() -> None:
    result = _result()
    submitted = _submitted()
    before = copy.deepcopy(result)

    context = build_canonical_report_context(
        result,
        submitted_input=submitted,
        model_mode="FROZEN_REFERENCE",
    )

    assert result == before
    assert context["evaluation_type"] == "신규평가"
    assert context["evaluation_result"] == {
        "m_grade": "M4",
        "m_score": 34.133,
        "m_rank": 1261,
        "final_score": 0.681641,
        "selected_price_basis": "1D",
    }
    assert context["common_info"]["contract_ttm_years"] == 30.0
    assert context["common_info"]["model_ttm_years"] == 5.0
    assert context["provenance"]["scoring_source"] == "DART_KRX"
    assert "검증된 KRX 상장주식수" in context["provenance"]["scoring_source_label"]
    serialized = str(context)
    assert "naver_bps" not in serialized
    assert "must-not-leak" not in serialized


def test_monitoring_fields_are_optional_and_never_fabricated() -> None:
    new_context = build_canonical_report_context(_result(), submitted_input=_submitted())
    assert "monitoring_fields" not in new_context

    monitoring = _result()
    monitoring.update(
        {
            "Actual_Issue_Date": "2024-07-05",
            "Monitoring_Date": "2026-06-30",
            "FS_Target_Date": "2026-06-30",
            "Original_TTM_years": 5.0,
            "Rebased_TTM_years_raw": 3.01,
            "Rebased_TTM_years_model": 3.01,
        }
    )
    context = build_canonical_report_context(monitoring)
    assert context["evaluation_type"] == "사후관리 재평가"
    assert context["monitoring_fields"] == {
        "actual_issue_date": "2024-07-05",
        "monitoring_date": "2026-06-30",
        "fs_target_date": "2026-06-30",
        "original_ttm_years": 5.0,
        "rebased_ttm_years": 3.01,
        "model_ttm_years": 3.01,
    }


@pytest.mark.parametrize(
    "prompt",
    (
        "검토의견 생성해줘",
        "검토의견 작성해줘",
        "보고서 생성해줘",
        "평가보고서 작성해줘",
        "AI 평가보고서 만들어줘",
        "심사의견 정리해줘",
        "심사의견서 작성해줘",
    ),
)
def test_all_report_phrases_share_one_intent(prompt: str) -> None:
    assert is_ai_report_request(prompt) is True


def test_generation_context_limits_ai_to_narrative() -> None:
    canonical = build_canonical_report_context(_result(), submitted_input=_submitted())
    context = build_ai_report_generation_context(canonical)
    assert context["facts"] == canonical
    assert context["response_contract"]["output"] == "AI 평가의견 본문만"
    assert "새 수치 또는 등급 생성" in context["response_contract"]["forbidden"]
    assert "확정 정량값 또는 등급의 본문 반복" in context["response_contract"]["forbidden"]
    assert "M Score" in AI_REPORT_GENERATION_REQUEST
    assert "직접 반복하지 말고" in AI_REPORT_GENERATION_REQUEST
    assert canonical["ai_grounding"]["verified_event_timing"] is False
    assert "분류에서 생성된 보조 라벨" in canonical["ai_grounding"]["timing_point_semantics"]
    assert (
        "timing_point 보조 라벨을 행사개시일·실제 First_ITM 날짜·경과기간으로 해석"
        in context["response_contract"]["forbidden"]
    )
    assert "실제 First_ITM" in AI_REPORT_GENERATION_REQUEST


def test_report_context_uses_standard_same_entity_label() -> None:
    result = _result()
    result["underlying_company"] = "좌동"

    context = build_canonical_report_context(result, submitted_input=_submitted())

    assert context["common_info"]["underlying_company"] == "상동"
    assert result["underlying_company"] == "좌동"


def test_quantitative_parity_accepts_confirmed_values_and_rejects_drift() -> None:
    canonical = build_canonical_report_context(_result(), submitted_input=_submitted())
    valid = "M Grade는 M4이며 M Score는 34.133, M Rank는 1,261입니다. Final Score는 0.681641입니다."
    invalid = "M Grade는 M3이며 M Score는 34.999, M Rank는 1,200입니다. Final Score는 0.7입니다."
    assert validate_generated_quantitative_parity(valid, canonical) == []
    assert validate_generated_quantitative_parity(invalid, canonical) == [
        "M Grade",
        "M Score",
        "M Rank",
        "Final Score",
    ]


def test_timing_grounding_allows_auxiliary_label_and_rejects_event_claims() -> None:
    canonical = build_canonical_report_context(_result(), submitted_input=_submitted())

    assert validate_generated_grounding("도달지점 보조 라벨은 당일입니다.", canonical) == []
    for invalid in (
        "행사개시일 당일 도달 특성이 나타납니다.",
        "First_ITM 날짜는 당일입니다.",
        "실제 도달 날짜는 평가일입니다.",
        "도달까지 1일이 소요되었습니다.",
    ):
        assert validate_generated_grounding(invalid, canonical) == ["도달시점 grounding"]

def test_report_state_preserves_draft_and_source_fingerprint() -> None:
    result = _result()
    submitted = _submitted()
    canonical = build_canonical_report_context(result, submitted_input=submitted)
    fingerprint = report_source_fingerprint(result, submitted)
    state = new_report_state(
        canonical_context=canonical,
        ai_commentary="확정 결과를 바탕으로 한 초안입니다.",
        source_fingerprint=fingerprint,
        generated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    assert state["ai_draft"] == state["ai_commentary"]
    assert state["reviewer_comment"] == ""
    assert state["changed"] is False
    assert state["source_fingerprint"] == fingerprint
