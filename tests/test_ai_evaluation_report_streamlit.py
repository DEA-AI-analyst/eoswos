import copy

import pytest

from chatbase_client import ChatbaseCallResult
from test_streamlit_chat_routing import _app, _provenance_result, _show_result


def _confirmed_result() -> dict:
    result = _provenance_result(
        {
            "status": "CANONICAL_CFS",
            "fs_selected_date": "2026-06-30",
            "fs_type": "CFS",
            "financial_entity": "issuer",
            "scoring_source": "DART_KRX",
            "source_note": "API canonical receipt",
        }
    )
    result.update(
        {
            "m_grade": "M3",
            "m_score": 50.0,
            "final_rank": 100,
            "final_score": 0.5,
            "selected_price_basis": "1D",
            "price_basis": {
                basis: {
                    "price": 10000,
                    "m_grade": "M3",
                    "m_score": 50.0,
                    "final_rank": 100,
                    "final_score": 0.5,
                    "e_m": {"grade": "E2", "score": 0.9, "rank": 300},
                    "p_m": {"grade": "P3", "score": 0.8, "rank": 500},
                    "s_m": {"grade": "S2", "score": 1.2, "rank": 400},
                }
                for basis in ("1D", "1W", "1M")
            },
            "ml_feature_snapshot": {"price_basis": "1D", "TTM_years": 5.0},
        }
    )
    return result
def _show_confirmed(at, result: dict):
    at.session_state["current_evaluation"] = copy.deepcopy(result)
    at.session_state["current_evaluation_input"] = {"ttm_years": 5.0}
    return _show_result(at, result)




def test_report_button_generates_dedicated_editable_draft(monkeypatch) -> None:
    at, calls = _app(monkeypatch)
    confirmed = _confirmed_result()
    _show_confirmed(at, confirmed)

    next(button for button in at.button if button.label == "AI 평가보고서").click().run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    assert at.session_state["current_evaluation"] == confirmed
    state = dict(at.session_state["ai_report_state"])
    assert state["ai_draft"] == "Chatbase 테스트 답변"
    assert len(at.text_area) == 2
    assert any(button.label == "수정 반영" for button in at.button)
    assert any("AI 평가보고서 · Draft" in item.value for item in at.markdown)


def test_report_edits_are_saved_without_changing_scoring(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    confirmed = _confirmed_result()
    _show_confirmed(at, confirmed)
    next(button for button in at.button if button.label == "AI 평가보고서").click().run(timeout=10)
    at.text_area[0].set_value("수정된 AI 평가의견입니다.")
    at.text_area[1].set_value("담당자 최종 검토의견입니다.")
    next(button for button in at.button if button.label == "수정 반영").click().run(timeout=10)

    assert not at.exception
    state = dict(at.session_state["ai_report_state"])
    assert state["ai_commentary"] == "수정된 AI 평가의견입니다."
    assert state["reviewer_comment"] == "담당자 최종 검토의견입니다."
    assert state["changed"] is True
    assert at.session_state["current_evaluation"] == confirmed


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
def test_natural_language_report_requests_use_same_draft_generator(monkeypatch, prompt) -> None:
    at, calls = _app(monkeypatch)
    confirmed = _confirmed_result()
    _show_confirmed(at, confirmed)

    at.chat_input[0].set_value(prompt).run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    assert at.session_state["ai_report_state"]["ai_draft"] == "Chatbase 테스트 답변"
    assert at.session_state["current_evaluation"] == confirmed


def test_quantitative_drift_fails_report_only_and_preserves_result(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    confirmed = _confirmed_result()
    _show_confirmed(at, confirmed)

    monkeypatch.setattr(
        "chatbase_client.ChatbaseClient.ask",
        lambda *_args, **_kwargs: ChatbaseCallResult(
            text="M Grade는 M5이며 Final Score는 0.9입니다.",
            elapsed_ms=1.0,
        ),
    )
    next(button for button in at.button if button.label == "AI 평가보고서").click().run(timeout=10)

    assert not at.exception
    assert at.session_state["ai_report_state"] is None
    assert at.session_state["current_evaluation"] == confirmed
    assert any("AI 평가보고서 생성에 실패했습니다" in item.value for item in at.error)


def test_chatbase_failure_does_not_turn_evaluation_into_failure(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    confirmed = _confirmed_result()
    before = copy.deepcopy(confirmed)
    _show_confirmed(at, confirmed)

    def fail(*_args, **_kwargs):
        raise RuntimeError("private traceback C:/secret/report.py")

    monkeypatch.setattr("chatbase_client.ChatbaseClient.ask", fail)
    next(button for button in at.button if button.label == "AI 평가보고서").click().run(timeout=10)

    assert not at.exception
    assert at.session_state["current_evaluation"] == before
    public = " ".join(str(item.value) for item in at.error)
    assert "AI 평가보고서 생성에 실패했습니다" in public
    assert "private" not in public
    assert "C:/" not in public
