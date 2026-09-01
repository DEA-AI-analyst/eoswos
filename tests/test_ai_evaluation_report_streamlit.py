import copy
from pathlib import Path

import pytest

from chatbase_client import ChatbaseCallResult
from ai_evaluation_report_ui import (
    _build_price_basis_detail_rows,
    _display_number,
    _display_rank,
    _report_table_html,
)
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




def test_report_key_result_display_matches_evaluation_card_precision() -> None:
    assert _display_number(74.05451, 0) == "74"
    assert _display_number(74.05451, 3) == "74.055"
    assert _display_number(1.478863, 3) == "1.479"
    assert _display_rank(1261) == "1,261"


def test_report_table_alignment_and_axis_score_precision() -> None:
    axes = _report_table_html(
        [{"축": "e_M", "역할": "구조적 효율성", "Grade": "E1", "Score": "0.900", "Rank": "396"}],
        centered_columns=("축", "Grade", "Score", "Rank"),
    )
    assert axes.count('<th scope="col" style="text-align:center">') == 5
    for value in ("e_M", "E1", "0.900", "396"):
        assert f'<td style="text-align:center">{value}</td>' in axes
    assert '<td style="text-align:left">구조적 효율성</td>' in axes
    assert _display_number(0.9, 3) == "0.900"

    details = _build_price_basis_detail_rows(
        {
            basis: {
                "price": 10850,
                "m_grade": "M1",
                "m_score": 74.05451,
                "final_rank": 396,
                "final_score": 1.478863,
                "e_m": {"grade": "E1"},
                "p_m": {"grade": "P2"},
                "s_m": {"grade": "S1"},
                "reach_pk_strength": "PK 상위",
                "timing_point": "당일",
            }
            for basis in ("1D", "1W", "1M")
        }
    )
    assert [row["기준"] for row in details] == ["1D", "1W", "1M"]
    assert all(row["가격"] == "10,850" for row in details)
    assert all(row["M Score"] == "74" for row in details)
    assert all(row["Final Score"] == "1.479" for row in details)
    detail_html = _report_table_html(details, center_all=True)
    assert "eoswos-data-table--wide" in detail_html
    assert "text-align:left" not in detail_html
    assert detail_html.count('<td style="text-align:center">') == len(details) * len(details[0])

    price_html = _report_table_html(
        [{"가격기준": "1D", "M Grade": "M1", "e_M": "E1", "p_M": "P2", "s_M": "S1"}],
        center_all=True,
    )
    assert "text-align:left" not in price_html
    assert price_html.count('<td style="text-align:center">') == 5

    overview_html = _report_table_html([{"항목": "회사", "값": "현대건설"}])
    assert overview_html.count('<th scope="col" style="text-align:center">') == 2
    assert '<td style="text-align:left">회사</td>' in overview_html
    assert '<td style="text-align:left">현대건설</td>' in overview_html

    escaped = _report_table_html([{"항목": "안전", "값": "<script>alert(1)</script>"}])
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped


def test_chat_input_width_tracks_report_width() -> None:
    source = Path("ai_single_evaluation.py").read_text(encoding="utf-8")
    assert '[data-testid="stBottomBlockContainer"]' in source
    assert "max-width: 720px !important" in source
    assert "max-width: 794px !important" in source
    assert "eoswos-source-details-marker" in source
    assert "font-size: 0.875rem !important" in source


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


def test_ungrounded_first_draft_is_rewritten_once(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    confirmed = _confirmed_result()
    _show_confirmed(at, confirmed)
    responses = iter(
        (
            "행사개시일 당일 도달 특성이 나타납니다.",
            "확정 결과의 상대적 강점과 제한축을 함께 검토해야 합니다.",
        )
    )
    call_count = {"value": 0}

    def answer(*_args, **_kwargs):
        call_count["value"] += 1
        return ChatbaseCallResult(text=next(responses), elapsed_ms=1.0)

    monkeypatch.setattr("chatbase_client.ChatbaseClient.ask", answer)
    next(button for button in at.button if button.label == "AI 평가보고서").click().run(timeout=10)

    assert not at.exception
    assert call_count["value"] == 2
    assert at.session_state["current_evaluation"] == confirmed
    assert at.session_state["ai_report_state"]["ai_draft"] == (
        "확정 결과의 상대적 강점과 제한축을 함께 검토해야 합니다."
    )
    assert not at.error

def test_ungrounded_timing_claim_fails_report_only_and_preserves_result(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    confirmed = _confirmed_result()
    _show_confirmed(at, confirmed)

    monkeypatch.setattr(
        "chatbase_client.ChatbaseClient.ask",
        lambda *_args, **_kwargs: ChatbaseCallResult(
            text="행사개시일 당일 도달 특성이 나타납니다.",
            elapsed_ms=1.0,
        ),
    )
    next(button for button in at.button if button.label == "AI 평가보고서").click().run(timeout=10)

    assert not at.exception
    assert at.session_state["ai_report_state"] is None
    assert at.session_state["current_evaluation"] == confirmed
    public = " ".join(str(item.value) for item in at.error)
    assert "AI 평가보고서 생성에 실패했습니다" in public
    assert "행사개시일" not in public

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
