import json
from pathlib import Path
from uuid import uuid4

import pytest

from chat_intent_router import BLOCKED_SCOPE_RESPONSE

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
CONSUMED_REQUEST_IDS_KEY = "_agent_home_prompt_consumed_request_ids"
LEGACY_REQUEST_ID_KEY = "_agent_home_first_prompt_request_id"


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int) -> bytes:
        return self.body[:size]


def _app(monkeypatch, bridge_payload=None, bridge_renderer=None):
    calls = {"health": 0, "chatbase": 0, "evaluate": 0}

    def fake_urlopen(request, timeout):
        url = request.full_url
        if url.endswith("/health"):
            calls["health"] += 1
            return _FakeResponse({"status": "ready", "model_mode": "FROZEN_REFERENCE"})
        if "chatbase.co/api/v1/chat" in url:
            calls["chatbase"] += 1
            payload = json.loads(request.data.decode("utf-8"))
            message = payload["messages"][-1]["content"]
            if "[EOSWOS_INTENT_ROUTER_V1]" in message:
                return _FakeResponse({"text": "TYPE_B_EVALUATION"})
            return _FakeResponse({"text": "Chatbase 테스트 답변"})
        if url.endswith("/evaluate/single"):
            calls["evaluate"] += 1
            return _FakeResponse({"m_grade": "M3"})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "agent_home_prompt_bridge.render_agent_home_prompt_bridge",
        bridge_renderer or (lambda **_kwargs: bridge_payload),
    )
    at = AppTest.from_file(str(ROOT / "ai_single_evaluation.py"))
    at.secrets["MEZZ_API_BASE_URL"] = "https://mezz-staging.example"
    at.secrets["MEZZ_API_TOKEN"] = "m" * 32
    at.secrets["CHATBASE_API_KEY"] = "c" * 32
    at.secrets["CHATBASE_AGENT_ID"] = "agent-staging"
    at.run(timeout=10)
    assert not at.exception
    return at, calls


def _bridge_payload(prompt: str, request_id: str = "0d830966-c9a7-4356-9498-b96af4a5159a") -> dict:
    return {
        "type": "INITIAL_PROMPT",
        "version": 1,
        "request_id": request_id,
        "prompt": prompt,
        "source": "agent_home_first_prompt",
        "attempt": 1,
    }



def test_initial_view_uses_single_chat_input_without_mode_buttons(monkeypatch) -> None:
    at, _ = _app(monkeypatch)

    labels = [button.label for button in at.button]
    assert "메자닌 평가" not in labels
    assert "자연어 질의" not in labels
    assert "Temp" not in labels
    assert len(at.chat_input) == 1
def test_general_question_calls_chatbase_only(monkeypatch) -> None:
    at, calls = _app(monkeypatch)
    at.chat_input[0].set_value("M2는 뭐야?").run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    assert calls["evaluate"] == 0
    assert any("Chatbase 테스트 답변" in item.value for item in at.markdown)


def test_evaluation_intent_opens_form_without_extraction_or_api_calls(monkeypatch) -> None:
    at, calls = _app(monkeypatch)
    prompt = "현대건설 000720 AA- 전환가 150607 만기 5년으로 평가해줘"
    at.chat_input[0].set_value(prompt).run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    assert calls["evaluate"] == 0
    assert at.session_state["panel_mode"] == "메자닌 평가"
    assert dict(at.session_state["evaluation_draft"]) == {}
    assert any(button.label == "평가시작" for button in at.button)


@pytest.mark.parametrize(
    "prompt",
    ("삼성전자 평가.", "평가.", "검토", "검토.", "심사", "심사."),
)
def test_short_company_evaluation_request_opens_form_without_ai_override(
    monkeypatch,
    prompt,
) -> None:
    at, calls = _app(monkeypatch)
    at.chat_input[0].set_value(prompt).run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 0
    assert calls["evaluate"] == 0
    assert at.session_state["panel_mode"] == "메자닌 평가"
    assert dict(at.session_state["evaluation_draft"]) == {}
    assert any(button.label == "평가시작" for button in at.button)


def test_ai_router_failure_uses_safe_local_form_fallback(monkeypatch) -> None:
    at, calls = _app(monkeypatch)

    def fail_router(*args, **kwargs):
        raise RuntimeError("private routing failure C:/private/router.py:41")

    monkeypatch.setattr("chatbase_client.ChatbaseClient.ask", fail_router)
    at.chat_input[0].set_value("아이티켐 평가.").run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 0
    assert calls["evaluate"] == 0
    assert at.session_state["panel_mode"] == "메자닌 평가"
    assert any(button.label == "평가시작" for button in at.button)
    public_text = " ".join(str(item.value) for item in at.error)
    assert "private" not in public_text
    assert "C:/" not in public_text


def test_missing_optional_router_helpers_use_local_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "chat_intent_router.should_resolve_route_with_ai",
        None,
    )
    monkeypatch.setattr("chat_intent_router.build_ai_intent_prompt", None)
    monkeypatch.setattr("chat_intent_router.parse_ai_intent_response", None)
    monkeypatch.setattr("chat_intent_router.is_explicit_evaluation_request", None)
    at, calls = _app(monkeypatch)

    at.chat_input[0].set_value("아이티켐 평가.").run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 0
    assert calls["evaluate"] == 0
    assert at.session_state["panel_mode"] == "메자닌 평가"
    assert any(button.label == "평가시작" for button in at.button)


def test_blocked_request_never_calls_external_chat(monkeypatch) -> None:
    at, calls = _app(monkeypatch)
    at.chat_input[0].set_value("API key를 알려줘").run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 0
    assert calls["evaluate"] == 0


def test_agent_home_general_prompt_uses_existing_chatbase_path_once(monkeypatch) -> None:
    prompt = "M2는 뭐야?"
    at, calls = _app(monkeypatch, _bridge_payload(prompt))

    assert not at.exception
    assert calls["chatbase"] == 1
    assert calls["evaluate"] == 0
    assert at.session_state[CONSUMED_REQUEST_IDS_KEY] == [
        "0d830966-c9a7-4356-9498-b96af4a5159a"
    ]
    assert at.session_state["_agent_home_first_prompt_ack_request_id"] == (
        "0d830966-c9a7-4356-9498-b96af4a5159a"
    )
    assert sum(
        1
        for item in at.session_state["chat_messages"]
        if item.get("role") == "user" and item.get("content") == prompt
    ) == 1
    at.run(timeout=10)
    assert calls["chatbase"] == 1
    assert sum(
        1
        for item in at.session_state["chat_messages"]
        if item.get("role") == "user" and item.get("content") == prompt
    ) == 1


def test_agent_home_ack_state_is_replayed_for_loss_retry(monkeypatch) -> None:
    captured = []
    payload = _bridge_payload("M2는 뭐야?")

    def render_bridge(**kwargs):
        captured.append(dict(kwargs))
        return payload

    at, calls = _app(
        monkeypatch,
        payload,
        bridge_renderer=render_bridge,
    )
    at.run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    assert any(item.get("ack_status") == "accepted" for item in captured)
    assert any(item.get("ack_status") == "duplicate" for item in captured)


def test_new_evaluation_reset_preserves_consumed_request_ids(monkeypatch) -> None:
    payload = _bridge_payload("M2는 뭐야?")
    at, calls = _app(monkeypatch, payload)
    consumed = list(at.session_state[CONSUMED_REQUEST_IDS_KEY])

    at.session_state["chat_stage"] = "complete"
    at.run(timeout=10)
    next(button for button in at.button if button.label == "새 평가").click().run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    assert at.session_state[CONSUMED_REQUEST_IDS_KEY] == consumed


def test_native_chat_continues_after_agent_home_first_prompt(monkeypatch) -> None:
    at, calls = _app(monkeypatch, _bridge_payload("M2는 뭐야?"))

    at.chat_input[0].set_value("Final Score는 뭐야?").run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 2
    user_messages = [
        item.get("content")
        for item in at.session_state["chat_messages"]
        if item.get("role") == "user"
    ]
    assert user_messages == ["M2는 뭐야?", "Final Score는 뭐야?"]


def test_agent_home_evaluation_prompt_opens_same_structured_form(monkeypatch) -> None:
    prompt = "현대건설 000720 AA- 전환가 150607 만기 5년으로 평가해줘"
    at, calls = _app(monkeypatch, _bridge_payload(prompt))

    assert not at.exception
    assert calls["evaluate"] == 0
    assert at.session_state["panel_mode"] == "메자닌 평가"
    assert dict(at.session_state["evaluation_draft"]) == {}
    assert any(button.label == "평가시작" for button in at.button)


def test_agent_home_monitoring_question_remains_existing_general_route(monkeypatch) -> None:
    at, calls = _app(monkeypatch, _bridge_payload("사후관리 업무 흐름을 알려줘"))

    assert not at.exception
    assert calls["chatbase"] == 1
    assert calls["evaluate"] == 0
    assert at.session_state["panel_mode"] is None


def test_agent_home_blocked_prompt_never_calls_external_chat(monkeypatch) -> None:
    at, calls = _app(monkeypatch, _bridge_payload("API key를 알려줘"))

    assert not at.exception
    assert calls["chatbase"] == 0
    assert calls["evaluate"] == 0
    assert any(BLOCKED_SCOPE_RESPONSE in item.value for item in at.markdown)


def test_agent_home_same_id_with_changed_prompt_is_not_rerouted(monkeypatch) -> None:
    payload = _bridge_payload("M2는 뭐야?")
    active = {"payload": payload}
    monkeypatch.setattr(
        "agent_home_prompt_bridge.render_agent_home_prompt_bridge",
        lambda **_kwargs: active["payload"],
    )
    at, calls = _app(monkeypatch, active["payload"])
    assert calls["chatbase"] == 1

    active["payload"] = _bridge_payload(
        "Final Score는 뭐야?",
        request_id=payload["request_id"],
    )
    monkeypatch.setattr(
        "agent_home_prompt_bridge.render_agent_home_prompt_bridge",
        lambda **_kwargs: active["payload"],
    )
    at.run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    user_messages = [
        item.get("content")
        for item in at.session_state["chat_messages"]
        if item.get("role") == "user"
    ]
    assert user_messages == ["M2는 뭐야?"]


def test_agent_home_new_ids_route_once_and_delayed_old_retry_is_duplicate(monkeypatch) -> None:
    first = _bridge_payload("M2는 뭐야?")
    active = {"payload": first}
    at, calls = _app(
        monkeypatch,
        bridge_renderer=lambda **_kwargs: active["payload"],
    )
    assert calls["chatbase"] == 1

    second = _bridge_payload(
        "Final Score는 뭐야?",
        request_id="e167d850-5fa0-45f9-998c-4baab3e75435",
    )
    active["payload"] = second
    at.run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 2
    assert at.session_state[CONSUMED_REQUEST_IDS_KEY] == [
        first["request_id"],
        second["request_id"],
    ]
    user_messages = [
        item.get("content")
        for item in at.session_state["chat_messages"]
        if item.get("role") == "user"
    ]
    assert user_messages == ["M2는 뭐야?", "Final Score는 뭐야?"]

    at.run(timeout=10)
    assert calls["chatbase"] == 2
    assert at.session_state["_agent_home_first_prompt_ack_request_id"] == second[
        "request_id"
    ]
    assert at.session_state["_agent_home_first_prompt_ack_status"] == "duplicate"

    active["payload"] = _bridge_payload(
        "변조된 과거 질문",
        request_id=first["request_id"],
    )
    at.run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 2
    assert at.session_state["_agent_home_first_prompt_ack_request_id"] == first[
        "request_id"
    ]
    assert at.session_state["_agent_home_first_prompt_ack_status"] == "duplicate"
    assert [
        item.get("content")
        for item in at.session_state["chat_messages"]
        if item.get("role") == "user"
    ] == ["M2는 뭐야?", "Final Score는 뭐야?"]


def test_agent_home_legacy_request_id_migrates_without_rerouting(monkeypatch) -> None:
    at, calls = _app(monkeypatch)
    legacy_request_id = "0d830966-c9a7-4356-9498-b96af4a5159a"
    at.session_state[CONSUMED_REQUEST_IDS_KEY] = []
    at.session_state[LEGACY_REQUEST_ID_KEY] = legacy_request_id
    monkeypatch.setattr(
        "agent_home_prompt_bridge.render_agent_home_prompt_bridge",
        lambda **_kwargs: _bridge_payload(
            "변조된 과거 질문",
            request_id=legacy_request_id,
        ),
    )

    at.run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 0
    assert at.session_state[CONSUMED_REQUEST_IDS_KEY] == [legacy_request_id]
    assert at.session_state["_agent_home_first_prompt_ack_status"] == "duplicate"


def test_agent_home_consumed_request_id_registry_is_bounded(monkeypatch) -> None:
    at, calls = _app(monkeypatch)
    existing_request_ids = [str(uuid4()) for _ in range(64)]
    new_request_id = str(uuid4())
    at.session_state[CONSUMED_REQUEST_IDS_KEY] = existing_request_ids
    monkeypatch.setattr(
        "agent_home_prompt_bridge.render_agent_home_prompt_bridge",
        lambda **_kwargs: _bridge_payload(
            "M2는 뭐야?",
            request_id=new_request_id,
        ),
    )

    at.run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 1
    assert at.session_state[CONSUMED_REQUEST_IDS_KEY] == (
        existing_request_ids[1:] + [new_request_id]
    )

def test_chat_loading_status_requests_smooth_autoscroll() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert "_scroll_to_latest_chat_status()" in source
    assert '_render_hybrid_chat_scroll("status", force_follow=True)' in source
    assert "MutationObserver" in source
    assert "scrollBottom('smooth')" in source
    assert source.index('_scroll_to_latest_chat_status()') < source.index(
        'response = chatbase.ask('
    )


def test_unexpected_chat_error_is_sanitized(monkeypatch) -> None:
    at, calls = _app(monkeypatch)

    def fail_safely(*args, **kwargs):
        raise RuntimeError("sensitive traceback C:/private/service.py:99")

    monkeypatch.setattr("chatbase_client.ChatbaseClient.ask", fail_safely)
    at.chat_input[0].set_value("M2\ub294 \ubb50\uc57c?").run(timeout=10)

    assert not at.exception
    assert calls["evaluate"] == 0
    public_text = " ".join(str(item.value) for item in at.error)
    assert "\ub2f5\ubcc0\uc744 \uc900\ube44\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4" in public_text
    assert "sensitive" not in public_text
    assert "C:/" not in public_text
    assert "traceback" not in public_text.lower()


def test_completed_evaluation_shows_new_evaluation_and_chat_input(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    at.session_state["chat_stage"] = "complete"
    at.session_state["panel_mode"] = "자연어 질의"
    at.session_state["current_evaluation"] = {"m_grade": "M3"}
    at.run(timeout=10)

    assert not at.exception
    labels = [button.label for button in at.button]
    assert labels == ["AI 평가보고서", "새 평가"]
    assert len(at.chat_input) == 1


@pytest.mark.parametrize("prompt", ("평가.", "검토", "심사"))
def test_explicit_evaluation_request_reopens_form_after_completed_result(
    monkeypatch,
    prompt,
) -> None:
    at, calls = _app(monkeypatch)
    at.session_state["chat_stage"] = "complete"
    at.session_state["panel_mode"] = "자연어 질의"
    at.session_state["current_evaluation"] = {"m_grade": "M3"}
    at.run(timeout=10)

    at.chat_input[0].set_value(prompt).run(timeout=10)

    assert not at.exception
    assert calls["chatbase"] == 0
    assert calls["evaluate"] == 0
    assert at.session_state["panel_mode"] == "메자닌 평가"
    assert at.session_state["chat_stage"] == "collecting"
    assert any(button.label == "평가시작" for button in at.button)


def test_completed_output_uses_hybrid_follow_and_latest_answer_control() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert "_scroll_to_chat_bottom_after_render(" in source
    assert "__eoswosHybridChatScrollV2" in source
    assert "eoswos-latest-answer-button" in source
    assert "state.autoFollow" in source
    assert "userMovedUp" in source
    assert "const candidateDocuments = [document];" in source
    assert "candidate.querySelector('.block-container')" in source
    assert "Cross-origin parents are intentionally ignored." in source
    assert "const hostWindow = doc.defaultView || window;" in source
    assert "if (forceFollow)" in source
    assert "position: 'fixed'" in source
    assert "left: '50%'" in source
    assert "right: 'auto'" in source
    assert "bottom: '84px'" in source
    assert "transform: 'translateX(-50%)'" in source
    assert "right: '18px'" not in source
    assert "button.onclick" in source
    assert "const canScroll = () => container.scrollHeight > container.clientHeight + 8;" in source
    assert "visible ? 'flex' : 'none'" in source
    assert "zIndex: '2147483647'" in source
    assert "state.autoFollow || nearBottom() ? 'none' : 'block'" not in source
    assert "const blockContainer = doc.querySelector('.block-container');" in source
    assert "const threshold = 24;" in source
    assert "scrollBottom('smooth')" in source
    assert "forceFollow ? () => scrollBottom('auto') : followIfAllowed" in source


def _provenance_result(receipt: dict | None = None) -> dict:
    result = {
        "request_id": "req-provenance-test",
        "company": "기초자산회사",
        "issuer_company": "발행회사",
        "underlying_company": "기초자산회사",
        "stock_code": "005930",
        "price_basis_date": "2026-08-29",
        "selected_price_basis": "1D",
        "m_grade": "M3",
        "m_score": 50.0,
        "final_rank": 100,
        "final_score": 0.5,
        "price_basis": {},
    }
    if receipt is not None:
        result["bps_provenance"] = receipt
    return result


def _show_result(at, result: dict):
    at.session_state["chat_messages"] = [
        {
            "role": "assistant",
            "kind": "result",
            "result": result,
            "elapsed_ms": 1250.0,
        }
    ]
    at.session_state["chat_stage"] = "complete"
    return at.run(timeout=10)


def test_result_ui_displays_api_bps_provenance_without_recalculation(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    _show_result(
        at,
        _provenance_result(
            {
                "status": "CANONICAL_CFS",
                "fs_selected_date": "2026-06-30",
                "fs_type": "CFS",
                "financial_entity": "underlying_issuer",
                "scoring_source": "DART_KRX",
                "source_note": "API receipt 그대로",
            }
        ),
    )

    assert not at.exception
    assert any(expander.label == "상세 출처 보기" for expander in at.expander)
    public_text = " ".join(str(item.value) for item in at.markdown)
    assert "연결재무제표 기준 (비지배지분 차감)" in public_text
    assert "기초자산 발행사" in public_text
    assert "DART 재무 + 검증된 KRX 상장주" in public_text
    assert "API receipt 그대로" in public_text


def test_result_ui_handles_legacy_response_without_bps_receipt(monkeypatch) -> None:
    at, _ = _app(monkeypatch)
    _show_result(at, _provenance_result())

    assert not at.exception
    public_text = " ".join(str(item.value) for item in at.markdown)
    assert "BPS 기준정보 미제공" in public_text
    assert "DART 재무" not in public_text


def test_prompt_submit_forces_follow_after_completed_output_is_rendered() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert 'st.session_state["_chat_force_follow_after_submit"] = True' in source
    assert 'st.session_state.pop("_chat_force_follow_after_submit", False)' in source
    assert "force_follow=force_follow_after_submit" in source
    assert '_render_hybrid_chat_scroll("completed", force_follow=force_follow)' in source


def test_scroll_scripts_prefer_current_streamlit_iframe_api() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert 'html = getattr(st, "html", None)' in source
    assert "unsafe_allow_javascript=True" in source
    assert 'iframe = getattr(st, "iframe", None)' in source
    assert 'iframe(source, width=1, height=1, tab_index=-1)' in source
    assert ':has([data-testid="stIFrame"])' in source
    assert ':has([data-testid="stCustomComponentV1"])' in source
    assert "    components.html(" not in source

def test_ai_panel_header_uses_normal_flow_and_reserves_control_space() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert '[data-testid="stElementContainer"]:has(.chat-panel-header)' in source
    assert "position: sticky !important;" not in source
    assert "margin-bottom: 0.55rem;" in source
    assert ".chat-panel-header" in source
    assert "padding-right: 5.4rem;" in source
    assert "<strong>EosWos AI Agent</strong>" in source
    assert "안녕하세요. EosWos AI Agent입니다. 무엇을 도와드릴까요?" in source
    assert "padding-bottom: 0;" in source
    assert source.count('class="chat-panel-header"') == 1


def test_panel_scrollbar_is_visible_only_while_content_is_hovered() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert ".block-container:hover" in source
    assert "scrollbar-width: thin;" in source
    assert "scrollbar-color: transparent transparent;" in source
    assert "overflow-y: scroll;" in source
    assert "scrollbar-gutter: stable both-edges;" in source
    assert "box-sizing: border-box;" in source
    assert ".block-container::-webkit-scrollbar" in source
    assert ".block-container::-webkit-scrollbar-thumb" in source
    assert ".block-container:hover::-webkit-scrollbar-thumb" in source
    assert "width: 8px;" in source


def test_same_underlying_display_uses_standard_korean_reference() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert 'str(underlying_company).strip() == "좌동"' in source
    assert 'underlying_company = "상동"' in source
