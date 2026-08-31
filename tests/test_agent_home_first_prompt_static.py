from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
HOME_JS = (ROOT / "agent_home.js").read_text(encoding="utf-8")
CONTRACT_JS = (ROOT / "agent_home_first_prompt.js").read_text(encoding="utf-8")
WIDGET_JS = (ROOT / "ai_widget.js").read_text(encoding="utf-8")


def test_home_exposes_one_plain_text_prompt_without_get_field_name() -> None:
    assert 'id="agent-home-first-prompt-form"' in HTML
    assert 'id="agent-home-first-prompt-input"' in HTML
    assert 'maxlength="500"' in HTML
    input_markup = HTML.split('id="agent-home-first-prompt-input"', 1)[1].split("/>", 1)[0]
    assert "name=" not in input_markup
    assert 'autocomplete="off"' in input_markup
    assert "인증정보·계좌정보 등 민감정보는 입력하지 마세요." in HTML


def test_home_one_shot_state_stores_only_used_and_request_id() -> None:
    assert "window.sessionStorage" in HOME_JS
    assert "window.localStorage" not in HOME_JS
    assert "used: true" in CONTRACT_JS
    assert "request_id:" in CONTRACT_JS
    assert "storage.setItem(STORAGE_KEY, JSON.stringify(state))" in CONTRACT_JS
    storage_block = CONTRACT_JS.split("function writeTabState", 1)[1].split("function createInitialPromptEnvelope", 1)[0]
    assert "prompt" not in storage_block


def test_home_submit_handles_ime_and_locks_immediately() -> None:
    assert 'input.addEventListener("compositionstart"' in HOME_JS
    assert 'input.addEventListener("compositionend"' in HOME_JS
    assert "event.isComposing" in CONTRACT_JS
    assert "event.keyCode !== 229" in CONTRACT_JS
    assert "event.repeat" in CONTRACT_JS
    assert "input.disabled = true" in HOME_JS
    assert "submitButton.disabled = true" in HOME_JS
    assert "질문을 AI 패널로 전달했습니다. 이후 대화는 AI 패널에서 계속해 주세요." in HOME_JS


def test_manual_panel_open_disables_home_prompt() -> None:
    assert 'event.detail?.reason !== "manual"' in HOME_JS
    assert 'detail: { reason: reason || "programmatic" }' in WIDGET_JS
    assert 'setPanelOpen(shouldOpen, shouldOpen ? "manual" : "manual_close")' in WIDGET_JS


def test_prompt_never_enters_url_history_referer_or_analytics() -> None:
    assert "searchParams.set" not in WIDGET_JS + CONTRACT_JS
    assert "location.hash" not in WIDGET_JS + CONTRACT_JS
    assert "document.referrer" not in WIDGET_JS + CONTRACT_JS
    assert "gtag(" not in HOME_JS + WIDGET_JS + CONTRACT_JS
    assert "dataLayer" not in HOME_JS + WIDGET_JS + CONTRACT_JS
    assert "console." not in HOME_JS + WIDGET_JS + CONTRACT_JS


def test_widget_queues_until_ready_and_retries_same_request_once() -> None:
    assert "createDeliveryController" in WIDGET_JS
    assert "deliveryController.markReady" in WIDGET_JS
    assert "deliveryController?.markNotReady" in WIDGET_JS
    assert "pending.attempts >= 2" in CONTRACT_JS
    assert "pending.attempts += 1" in CONTRACT_JS
    assert "Object.assign({}, pending.envelope" in CONTRACT_JS


def test_existing_five_routes_and_clean_iframe_source_remain() -> None:
    for route in ("overview", "dea", "ml", "new_evaluation", "monitoring"):
        assert f'"{route}"' in HOME_JS
    iframe_source = WIDGET_JS.split('id="ai-evaluation-frame"', 1)[1].split("].join", 1)[0]
    assert "INITIAL_PROMPT" not in iframe_source
    assert "prompt=" not in WIDGET_JS
    assert "ai-contest-win.streamlit.app" in WIDGET_JS


def test_widget_accepts_only_bounded_descendants_of_agent_frame() -> None:
    assert "source.top !== window" in WIDGET_JS
    assert "current === frame.contentWindow" in WIDGET_JS
    assert "depth < 5" in WIDGET_JS
    assert "parent === current" in WIDGET_JS
