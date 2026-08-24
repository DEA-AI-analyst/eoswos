import copy

from chat_evaluation_context import (
    build_read_only_evaluation_context,
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
