import copy

from chat_evaluation_context import (
    build_read_only_evaluation_context,
    classify_evaluation_response_mode,
    evaluation_fingerprint,
    latest_evaluation_result,
    safe_chat_history,
)


def _result_fixture() -> dict:
    return {
        "company": "현대건설",
        "stock_code": "000720",
        "m_grade": "M3",
        "m_score": 36.785235,
        "final_rank": 1200,
        "final_score": 0.734598552,
        "selected_price_basis": "1D",
        "price_basis": {
            "1D": {
                "price": 115000,
                "m_grade": "M3",
                "m_score": 36.785235,
                "final_rank": 1200,
                "final_score": 0.734598552,
                "reach_pk_strength": "PK 하위",
                "timing_point": "당일",
                "e_m": {"grade": "E1", "score": 0.899, "rank": 60},
                "p_m": {"grade": "P4", "score": 0.970, "rank": 1407},
                "s_m": {"grade": "S1", "score": 2.105, "rank": 336},
                "model_pack": "must-not-leak",
            }
        },
        "ml_feature_snapshot": {
            "price_basis": "1D",
            "TTM_years": 5.0,
            "Final_Efficiency": 0.8988,
            "Debt_ratio": 1.25,
            "BPS_inverse": 0.72,
            "Pre_Issue_inverse": 0.76,
            "Return_6M": 0.11,
            "Relative_HV_252_inverse": 1.08,
            "Exercise_Period_Years_Cap365": 4.0,
        },
        "DART_API_KEY": "must-not-leak",
        "local_path": "C:/private/operating_reference.pkl",
    }


def test_context_is_allow_listed_and_does_not_mutate_result() -> None:
    result = _result_fixture()
    before = copy.deepcopy(result)

    context = build_read_only_evaluation_context(result)

    assert result == before
    assert context is not None
    serialized = str(context)
    assert "현대건설" in serialized
    assert "must-not-leak" not in serialized
    assert "DART_API_KEY" not in serialized
    assert "operating_reference" not in serialized
    assert context["facts"]["price_basis"]["1D"]["e_M"]["grade"] == "E1"


def test_latest_result_is_an_isolated_copy() -> None:
    original = _result_fixture()
    messages = [
        {"role": "assistant", "kind": "result", "result": original},
    ]

    copied = latest_evaluation_result(messages)
    assert copied == original
    assert copied is not original
    copied["m_grade"] = "M5"
    assert original["m_grade"] == "M3"


def test_safe_history_excludes_results_and_limits_plain_text() -> None:
    messages = [
        {"role": "assistant", "kind": "result", "result": _result_fixture()},
        {"role": "user", "kind": "text", "content": "질문"},
        {"role": "assistant", "kind": "error", "content": "내부 오류"},
        {"role": "assistant", "kind": "text", "content": "답변"},
    ]
    assert safe_chat_history(messages) == [
        {"role": "user", "content": "질문"},
        {"role": "assistant", "content": "답변"},
    ]


def test_fingerprint_detects_state_changes() -> None:
    result = _result_fixture()
    before = evaluation_fingerprint(result)
    result["m_grade"] = "M4"
    assert evaluation_fingerprint(result) != before


def test_response_mode_classifier_only_targets_reports_and_opinions() -> None:
    assert classify_evaluation_response_mode("심사보고서 작성해줘") == "report"
    assert classify_evaluation_response_mode("검토 의견을 작성해줘") == "report"
    assert classify_evaluation_response_mode("M3인 이유를 알려줘") == "explanation"


def test_report_context_contains_ordered_feature_table_contract() -> None:
    result = _result_fixture()
    before = copy.deepcopy(result)

    context = build_read_only_evaluation_context(
        result,
        response_mode="report",
    )

    assert result == before
    assert context is not None
    contract = context["response_contract"]
    assert contract["mode"] == "report"
    assert contract["section_order"][2] == "3. ML 입력 Feature 표"
    features = context["facts"]["ml_feature_snapshot"]["features"]
    assert [row["feature"] for row in features] == [
        "TTM_years",
        "Final_Efficiency",
        "Debt_ratio",
        "BPS_inverse",
        "Pre_Issue_inverse",
        "Return_6M",
        "Relative_HV_252_inverse",
        "Exercise_Period_Years_Cap365",
    ]
    bps_row = next(row for row in features if row["feature"] == "BPS_inverse")
    assert bps_row["p_M"] == "사용"
    assert bps_row["s_M"] == "미사용"


def test_default_context_does_not_force_report_presentation() -> None:
    context = build_read_only_evaluation_context(_result_fixture())
    assert context is not None
    assert "response_contract" not in context