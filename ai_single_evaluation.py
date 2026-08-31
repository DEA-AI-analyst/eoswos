"""EOSWOS conversational UI for the remote single-candidate model API."""

from __future__ import annotations

import copy
import html
import inspect
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import agent_home_prompt_bridge as prompt_bridge
import chat_intent_router as chat_router
from chat_evaluation_context import (
    build_read_only_evaluation_context as _build_read_only_evaluation_context,
    safe_chat_history,
)
try:
    from chat_evaluation_context import classify_evaluation_response_mode
except ImportError:
    def classify_evaluation_response_mode(prompt: str) -> str:
        """Keep the app available during a mixed-version Streamlit refresh."""
        normalized = " ".join(str(prompt or "").split())
        if any(term in normalized for term in ("검토보고서", "평가보고서", "심사보고서", "보고서")):
            return "report"
        if any(term in normalized for term in ("검토의견", "평가의견", "심사의견")):
            return "opinion"
        return "explanation"


_CONTEXT_SUPPORTS_RESPONSE_MODE = (
    "response_mode" in inspect.signature(_build_read_only_evaluation_context).parameters
)


def build_read_only_evaluation_context(
    current_evaluation: dict[str, Any] | None,
    *,
    response_mode: str = "explanation",
) -> dict[str, Any] | None:
    """Call either the current or immediately preceding context helper safely."""
    if _CONTEXT_SUPPORTS_RESPONSE_MODE:
        return _build_read_only_evaluation_context(
            current_evaluation,
            response_mode=response_mode,
        )
    return _build_read_only_evaluation_context(current_evaluation)


from chat_state_guard import protect_evaluation_state
from chat_intent_router import (
    BLOCKED_SCOPE_RESPONSE,
    EVALUATION_FORM_RESPONSE,
    ChatRoute,
    route_chat_message,
)
from chatbase_client import (
    ChatbaseClient,
    ChatbaseConfigurationError,
    ChatbaseError,
)
from mezz_api_client import (
    MezzApiClient,
    MezzApiConfigurationError,
    MezzApiError,
)
from mezz_evaluation_contract import (
    CONTRACT_TTM_MAX_YEARS,
    CONTRACT_TTM_MIN_YEARS,
    CREDIT_RATINGS,
    FIELD_LABELS,
    SELF_STOCK_PRODUCT,
    THIRD_PARTY_PRODUCT,
    bps_provenance_display_rows,
    build_api_payload,
    missing_fields,
    validate_draft,
)


st.set_page_config(
    page_title="EosWos AI 단건평가",
    layout="centered",
    initial_sidebar_state="collapsed",
)

APP_DIR = Path(__file__).resolve().parent
CODE_PATH = APP_DIR / "code.xlsx"


@st.cache_data(show_spinner=False)
def _load_issuer_options(
    path_text: str,
    modified_ns: int,
) -> tuple[tuple[str, str], ...]:
    del modified_ns
    frame = pd.read_excel(path_text, sheet_name=0, dtype=str)
    frame.columns = [str(column).strip() for column in frame.columns]

    normalized_columns = {column.lower(): column for column in frame.columns}
    code_col = next(
        (
            normalized_columns[name.lower()]
            for name in ("stock_code", "Stock_code", "종목코드", "단축코드")
            if name.lower() in normalized_columns
        ),
        None,
    )
    name_col = next(
        (
            normalized_columns[name.lower()]
            for name in ("한글 종목약명", "회사명", "기업명", "종목명", "Company", "Name")
            if name.lower() in normalized_columns
        ),
        None,
    )
    if code_col is None:
        return ()

    options: list[tuple[str, str]] = []
    seen_codes: set[str] = set()
    for _, row in frame.iterrows():
        raw_code = str(row.get(code_col, "") or "").strip()
        if raw_code.lower() == "nan":
            continue
        if raw_code.endswith(".0"):
            raw_code = raw_code[:-2]
        if not raw_code.isdigit():
            continue
        stock_code = raw_code.zfill(6)
        if len(stock_code) != 6 or stock_code in seen_codes:
            continue

        raw_name = str(row.get(name_col, "") or "").strip() if name_col else ""
        company_name = "" if raw_name.lower() == "nan" else raw_name
        label = f"{company_name} | {stock_code}" if company_name else stock_code
        options.append((label, stock_code))
        seen_codes.add(stock_code)

    return tuple(sorted(options, key=lambda item: (item[0], item[1])))


def _issuer_options() -> tuple[tuple[str, str], ...]:
    if not CODE_PATH.exists():
        return ()
    try:
        return _load_issuer_options(str(CODE_PATH), CODE_PATH.stat().st_mtime_ns)
    except Exception:
        return ()


st.markdown(
    """
    <style>
        html, body {
            height: 100%;
            margin: 0;
            overflow: hidden !important;
            scrollbar-width: none;
        }
        html::-webkit-scrollbar,
        body::-webkit-scrollbar,
        [data-testid="stAppViewContainer"]::-webkit-scrollbar {
            display: none;
        }
        [data-testid="stApp"],
        [data-testid="stAppViewContainer"] {
            height: 100dvh;
            overflow: hidden !important;
        }
        section[data-testid="stMain"] {
            height: 100dvh;
            overflow: hidden !important;
        }
        .block-container {
            max-width: 720px;
            max-height: 100dvh;
            padding-top: 0.8rem;
            padding-bottom: 6.5rem;
            overflow-x: hidden;
            overflow-y: scroll;
            scrollbar-width: thin;
            scrollbar-color: transparent transparent;
            scrollbar-gutter: stable both-edges;
            box-sizing: border-box;
        }
        .block-container::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        .block-container::-webkit-scrollbar-track {
            background: transparent;
        }
        .block-container::-webkit-scrollbar-thumb {
            border: 2px solid transparent;
            border-radius: 8px;
            background: transparent;
            background-clip: padding-box;
        }
        .block-container:hover {
            scrollbar-color: #98a2b3 transparent;
        }
        .block-container:hover::-webkit-scrollbar-thumb {
            background: #98a2b3;
        }
        h1, h2, h3 { letter-spacing: 0 !important; }
        [data-testid="stAppViewContainer"] { background: #f7f9fc; }
        footer,
        [data-testid="stFooter"] {
            display: none !important;
        }
        [data-testid="stChatMessage"] {
            border: 1px solid #e2e7ef;
            border-radius: 8px;
            background: #ffffff;
            gap: 0.45rem !important;
            padding-right: 0.75rem !important;
            padding-left: 0.75rem !important;
        }
        [data-testid="stChatMessageContent"] {
            flex: 1 1 auto;
            min-width: 0;
        }
        [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] {
            width: 100%;
        }
        [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] h1 {
            font-size: 1.3rem !important;
            line-height: 1.35 !important;
            margin: 1rem 0 0.55rem !important;
        }
        [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] h2 {
            font-size: 1.12rem !important;
            line-height: 1.4 !important;
            margin: 0.9rem 0 0.45rem !important;
        }
        [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] h3 {
            font-size: 1rem !important;
            line-height: 1.4 !important;
            margin: 0.8rem 0 0.4rem !important;
        }
        [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] ul,
        [data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] ol {
            margin-left: 0 !important;
            padding-left: 1.15rem !important;
        }
        .evaluation-report-marker { display: none; }
        [data-testid="stChatMessage"]:has(.evaluation-report-marker) {
            border-color: #cfd9e8;
            box-shadow: 0 2px 8px rgba(31, 79, 135, 0.06);
        }
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] {
            color: #202939;
            line-height: 1.65;
        }
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] h3 {
            color: #1f4f87;
            font-size: 1.02rem !important;
            line-height: 1.45 !important;
            margin: 1.05rem 0 0.45rem !important;
            padding-bottom: 0.28rem;
            border-bottom: 1px solid #dbe4f0;
        }
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] table {
            width: 100%;
            table-layout: fixed;
            border-collapse: collapse;
            margin: 0.55rem 0 0.85rem;
            font-size: 0.79rem;
        }
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] th,
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] td {
            overflow-wrap: anywhere;
            vertical-align: top;
            padding: 0.42rem 0.5rem;
            border: 1px solid #dbe4f0;
        }
        [data-testid="stChatMessage"]:has(.evaluation-report-marker)
        [data-testid="stMarkdownContainer"] th {
            color: #294e7a;
            background: #f2f6fb;
            font-weight: 650;
        }
        [data-testid="stChatInput"] textarea { letter-spacing: 0 !important; }
        [data-testid="stElementContainer"]:has([data-testid="stIFrame"]),
        [data-testid="stElementContainer"]:has([data-testid="stCustomComponentV1"]) {
            position: fixed !important;
            width: 0 !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }

        [data-testid="stElementContainer"]:has(.chat-panel-header) {
            margin-bottom: 0;
        }
        .chat-panel-header {
            padding-right: 5.4rem;
            padding-bottom: 0;
        }
        .chat-title {
            padding: 0.25rem 0 0.1rem;
        }
        .chat-title strong {
            display: block;
            color: #1f4f87;
            font-size: 1.35rem;
            line-height: 1.35;
        }
        .chat-title span {
            display: block;
            margin-top: 0.15rem;
            color: #667085;
            font-size: 0.82rem;
        }
        .api-ready {
            margin: 0.2rem 0 0;
            color: #137333;
            font-size: 0.78rem;
            font-weight: 600;
            line-height: 1.35;
        }
        .result-summary div { min-width: 0; }
        .result-summary span {
            display: block;
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.35;
        }
        .result-summary strong {
            display: block;
            overflow-wrap: anywhere;
            color: #172033;
            font-size: 0.9rem;
            line-height: 1.45;
        }
        .result-summary {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.5rem;
            margin: 0.65rem 0;
        }
        .result-summary div {
            padding: 0.65rem 0.7rem;
            border-top: 2px solid #3978c5;
            background: #f8fafc;
        }
        .result-summary strong { font-size: 1rem; }
        .result-summary .grade strong { font-size: 1.35rem; }
        .axis-summary {
            margin: 0.5rem 0 0.2rem;
            color: #344054;
            font-size: 0.82rem;
            line-height: 1.55;
        }
        @media (max-width: 520px) {
            .block-container {
                padding-top: 0.55rem;
                padding-right: 0.65rem;
                padding-left: 0.65rem;
            }
            .chat-title strong { font-size: 1.2rem; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def _setting(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except (FileNotFoundError, KeyError):
        value = ""
    return str(value or os.getenv(name, "") or "").strip()


@st.cache_resource(show_spinner=False)
def _build_client(base_url: str, token: str) -> MezzApiClient:
    return MezzApiClient(base_url=base_url, token=token)


@st.cache_resource(show_spinner=False)
def _build_chatbase_client(api_key: str, agent_id: str) -> ChatbaseClient:
    return ChatbaseClient(api_key=api_key, agent_id=agent_id)


@st.cache_data(ttl=30, show_spinner=False)
def _health(base_url: str, token_fingerprint: str) -> dict[str, Any]:
    del token_fingerprint
    client = _build_client(base_url, _setting("MEZZ_API_TOKEN"))
    return client.health().data


def _format_number(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:,.{digits}f}"


def _format_rank(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _escape(value: Any) -> str:
    return html.escape(str(value if value not in (None, "") else "-"))


def _render_result(result: dict[str, Any], elapsed_ms: float) -> None:
    company = str(result.get("company") or result.get("underlying_company") or "-")
    stock_code = str(result.get("stock_code") or "-")
    selected_basis = str(result.get("selected_price_basis") or "-")
    price_basis = result.get("price_basis", {})
    selected = price_basis.get(selected_basis, {}) if isinstance(price_basis, dict) else {}
    e_m = selected.get("e_m", {}) if isinstance(selected, dict) else {}
    p_m = selected.get("p_m", {}) if isinstance(selected, dict) else {}
    s_m = selected.get("s_m", {}) if isinstance(selected, dict) else {}

    st.markdown(f"**{company} · `{stock_code}` 평가가 완료되었습니다.**")
    st.caption(
        f"요청 처리 {elapsed_ms / 1000.0:.2f}초 · "
        "신속한 조회와 상세한 결과가 필요하신 분은 웹사이트 단건조회를 이용하세요."
    )
    st.markdown(
        f"""
        <div class="result-summary">
            <div class="grade"><span>M Grade</span><strong>{_escape(result.get('m_grade'))}</strong></div>
            <div><span>선택 가격기준</span><strong>{_escape(selected_basis)}</strong></div>
            <div><span>M Score</span><strong>{_escape(_format_number(result.get('m_score'), 3))}</strong></div>
            <div><span>M Rank</span><strong>{_escape(_format_rank(result.get('final_rank')))}</strong></div>
            <div><span>Final Score</span><strong>{_escape(_format_number(result.get('final_score'), 6))}</strong></div>
            <div><span>가격</span><strong>{_escape(_format_number(selected.get('price'), 0))}</strong></div>
        </div>
        <div class="axis-summary">
            e_M <strong>{_escape(e_m.get('grade'))}</strong> ·
            p_M <strong>{_escape(p_m.get('grade'))}</strong> ·
            s_M <strong>{_escape(s_m.get('grade'))}</strong><br>
            도달/PK강도 <strong>{_escape(selected.get('reach_pk_strength'))}</strong> ·
            도달지점 <strong>{_escape(selected.get('timing_point'))}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rows: list[dict[str, Any]] = []
    for basis in ("1D", "1W", "1M"):
        item = price_basis.get(basis, {}) if isinstance(price_basis, dict) else {}
        item_e = item.get("e_m", {}) if isinstance(item, dict) else {}
        item_p = item.get("p_m", {}) if isinstance(item, dict) else {}
        item_s = item.get("s_m", {}) if isinstance(item, dict) else {}
        rows.append(
            {
                "기준": basis,
                "가격": item.get("price"),
                "M": item.get("m_grade"),
                "M Score": item.get("m_score"),
                "Rank": item.get("final_rank"),
                "Final": item.get("final_score"),
                "e_M": item_e.get("grade"),
                "p_M": item_p.get("grade"),
                "s_M": item_s.get("grade"),
                "도달/PK": item.get("reach_pk_strength"),
                "도달지점": item.get("timing_point"),
            }
        )

    with st.expander("1D · 1W · 1M 세부 결과"):
        st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            column_config={
                "가격": st.column_config.NumberColumn(format="localized"),
                "M Score": st.column_config.NumberColumn(format="%.6f"),
                "Final": st.column_config.NumberColumn(format="%.9f"),
            },
        )

    with st.expander("상세 출처 보기"):
        st.write(f"요청 ID: `{result.get('request_id', '-')}`")
        st.write(f"평가기준일: `{result.get('price_basis_date', '-')}`")
        st.write(f"발행회사: {result.get('issuer_company', '-')}")
        underlying_company = result.get("underlying_company", "-")
        if str(underlying_company).strip() == "좌동":
            underlying_company = "상동"
        st.write(f"기초자산: {underlying_company}")
        st.markdown("**BPS 출처**")
        for label, value in bps_provenance_display_rows(result):
            st.write(f"{label}: {value}")


def _initial_messages() -> list[dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "kind": "text",
            "content": "안녕하세요. EosWos AI Agent입니다. 무엇을 도와드릴까요?",
        }
    ]


def _ensure_session() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = _initial_messages()
    if "evaluation_draft" not in st.session_state:
        st.session_state["evaluation_draft"] = {}
    if "chat_stage" not in st.session_state:
        st.session_state["chat_stage"] = "collecting"
    if "panel_mode" not in st.session_state:
        st.session_state["panel_mode"] = None
    if "current_evaluation" not in st.session_state:
        st.session_state["current_evaluation"] = None
    if "_agent_home_first_prompt_request_id" not in st.session_state:
        st.session_state["_agent_home_first_prompt_request_id"] = None
    if "_agent_home_first_prompt_ack_request_id" not in st.session_state:
        st.session_state["_agent_home_first_prompt_ack_request_id"] = None
    if "_agent_home_first_prompt_ack_status" not in st.session_state:
        st.session_state["_agent_home_first_prompt_ack_status"] = None
    if "_agent_home_first_prompt_pending" not in st.session_state:
        st.session_state["_agent_home_first_prompt_pending"] = None


def _reset_conversation() -> None:
    st.session_state["chat_messages"] = _initial_messages()
    st.session_state["evaluation_draft"] = {}
    st.session_state["chat_stage"] = "collecting"
    st.session_state["panel_mode"] = None
    st.session_state["current_evaluation"] = None
    st.session_state.pop("_chat_force_follow_after_submit", None)


def _append_message(role: str, content: str, kind: str = "text", **extra: Any) -> None:
    message: dict[str, Any] = {"role": role, "kind": kind, "content": content}
    message.update(extra)
    st.session_state["chat_messages"].append(message)


def _render_script_iframe(source: str) -> None:
    """Run a trusted UI script without adding visible page content."""
    html = getattr(st, "html", None)
    if callable(html):
        try:
            html(
                source,
                width="content",
                unsafe_allow_javascript=True,
            )
            return
        except TypeError:
            # Streamlit < 1.56 does not expose unsafe JavaScript in st.html.
            pass

    iframe = getattr(st, "iframe", None)
    if callable(iframe):
        iframe(source, width=1, height=1, tab_index=-1)
        return

    # Compatibility for local Streamlit versions released before st.iframe.
    import streamlit.components.v1 as legacy_components

    legacy_components.html(source, height=0, width=0)

def _render_hybrid_chat_scroll(
    target_mode: str,
    *,
    force_follow: bool = False,
) -> None:
    """Follow new output near the bottom and preserve deliberate upward reading."""
    mode = "status" if target_mode == "status" else "completed"
    _render_script_iframe(
        f"""
        <script>
        (() => {{
            const candidateDocuments = [document];
            try {{
                if (window.parent && window.parent !== window && window.parent.document) {{
                    candidateDocuments.push(window.parent.document);
                }}
            }} catch (error) {{
                // Cross-origin parents are intentionally ignored.
            }}
            const doc = candidateDocuments.find((candidate) =>
                candidate.querySelector('.block-container')
            ) || candidateDocuments.find((candidate) =>
                candidate.querySelector('[data-testid="stMain"]')
            ) || document;
            const hostWindow = doc.defaultView || window;
            const targetMode = {mode!r};
            const forceFollow = {str(force_follow).lower()};
            const stateKey = '__eoswosHybridChatScrollV2';
            const buttonId = 'eoswos-latest-answer-button';
            const threshold = 24;
            const blockContainer = doc.querySelector('.block-container');
            const container = blockContainer
                || doc.querySelector('[data-testid="stMain"]')
                || doc.scrollingElement;
            if (!container) return;

            let state = hostWindow[stateKey];
            if (!state) {{
                state = {{
                    autoFollow: true,
                    lastTop: Number(container.scrollTop || 0),
                    programmaticUntil: 0,
                }};
                hostWindow[stateKey] = state;
            }}

            if (state.container && state.scrollHandler) {{
                state.container.removeEventListener('scroll', state.scrollHandler);
            }}
            if (state.observer) state.observer.disconnect();
            state.container = container;

            let button = doc.getElementById(buttonId);
            if (!button) {{
                button = doc.createElement('button');
                button.id = buttonId;
                button.type = 'button';
                button.textContent = '↓';
                button.title = '최신 답변으로 이동';
                button.setAttribute('aria-label', '최신 답변으로 이동');
                Object.assign(button.style, {{
                    position: 'fixed',
                    left: '50%',
                    right: 'auto',
                    bottom: '84px',
                    transform: 'translateX(-50%)',
                    width: '40px',
                    height: '40px',
                    borderRadius: '50%',
                    border: '1px solid #cbd5e1',
                    background: '#ffffff',
                    color: '#2563eb',
                    fontSize: '22px',
                    lineHeight: '1',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    boxShadow: '0 5px 16px rgba(15, 23, 42, 0.18)',
                    zIndex: '2147483647',
                    display: 'none',
                    padding: '0',
                }});
                doc.body.appendChild(button);
            }}
            Object.assign(button.style, {{
                left: '50%',
                right: 'auto',
                bottom: '84px',
                transform: 'translateX(-50%)',
            }});

            const distanceFromBottom = () => Math.max(
                0,
                container.scrollHeight - container.clientHeight - container.scrollTop
            );
            const canScroll = () => container.scrollHeight > container.clientHeight + 8;
            const nearBottom = () => distanceFromBottom() <= threshold;
            const syncButton = () => {{
                const visible = canScroll() && !nearBottom();
                button.style.setProperty('display', visible ? 'flex' : 'none', 'important');
                button.style.setProperty('visibility', visible ? 'visible' : 'hidden', 'important');
                button.style.setProperty('opacity', visible ? '1' : '0', 'important');
            }};
            const scrollBottom = (behavior = 'smooth') => {{
                state.programmaticUntil = Date.now() + 1000;
                if (typeof container.scrollTo === 'function') {{
                    container.scrollTo({{ top: container.scrollHeight, behavior }});
                }} else {{
                    container.scrollTop = container.scrollHeight;
                }}
                state.lastTop = Number(container.scrollTop || 0);
                syncButton();
            }};

            state.scrollHandler = () => {{
                const currentTop = Number(container.scrollTop || 0);
                const userMovedUp = currentTop < state.lastTop - 2;
                if (Date.now() > state.programmaticUntil && userMovedUp && !nearBottom()) {{
                    state.autoFollow = false;
                }} else if (nearBottom()) {{
                    state.autoFollow = true;
                }}
                state.lastTop = currentTop;
                syncButton();
            }};
            container.addEventListener('scroll', state.scrollHandler, {{ passive: true }});

            button.onclick = () => {{
                state.autoFollow = true;
                scrollBottom('smooth');
            }};

            const followIfAllowed = () => {{
                if (state.autoFollow || nearBottom()) {{
                    state.autoFollow = true;
                    scrollBottom('smooth');
                }} else {{
                    syncButton();
                }}
            }};
            if (forceFollow) {{
                state.autoFollow = true;
                scrollBottom('auto');
            }}
            const followDelays = forceFollow
                ? [0, 80, 220, 500, 900]
                : [0, 80, 220, 500];
            followDelays.forEach((delay) =>
                window.setTimeout(
                    forceFollow ? () => scrollBottom('auto') : followIfAllowed,
                    delay,
                )
            );

            state.observer = new MutationObserver(followIfAllowed);
            state.observer.observe(container, {{ childList: true, subtree: true }});
            window.setTimeout(
                () => state.observer && state.observer.disconnect(),
                targetMode === 'status' ? 2400 : 1800,
            );
            syncButton();
        }})();
        </script>
        """,
    )


def _scroll_to_latest_chat_status() -> None:
    """Move to a pending answer after the user submits a new question."""
    _render_hybrid_chat_scroll("status", force_follow=True)


def _scroll_to_chat_bottom_after_render(*, force_follow: bool = False) -> None:
    """Follow completed output or expose a latest-answer control."""
    _render_hybrid_chat_scroll("completed", force_follow=force_follow)

def _render_message(message: dict[str, Any]) -> None:
    role = str(message.get("role") or "assistant")
    with st.chat_message(role):
        kind = message.get("kind")
        if kind == "result":
            _render_result(
                dict(message.get("result") or {}),
                float(message.get("elapsed_ms") or 0.0),
            )
        elif kind == "error":
            st.error(str(message.get("content") or "요청을 처리하지 못했습니다."))
        else:
            if message.get("presentation") == "report":
                st.markdown(
                    '<span class="evaluation-report-marker"></span>',
                    unsafe_allow_html=True,
                )
            st.markdown(str(message.get("content") or ""))



def _missing_message(fields: list[str]) -> str:
    if fields == ["product_type"]:
        return "EB가 자기주식인지 타사주식인지 알려주세요."
    labels = ", ".join(FIELD_LABELS[field] for field in fields)
    return f"추가로 확인할 정보가 있습니다: **{labels}**"


def _run_evaluation(client: MezzApiClient, today_seoul: Any) -> None:
    draft = dict(st.session_state.get("evaluation_draft") or {})
    try:
        payload = build_api_payload(draft, today=today_seoul)
        with st.spinner("평가 중입니다."):
            api_result = client.evaluate_single(payload)
        _append_message(
            "assistant",
            "",
            kind="result",
            result=api_result.data,
            elapsed_ms=api_result.elapsed_ms,
        )
        st.session_state["current_evaluation"] = copy.deepcopy(api_result.data)
        st.session_state["chat_stage"] = "complete"
        st.session_state["panel_mode"] = None
    except ValueError as exc:
        _append_message("assistant", str(exc), kind="error")
        st.session_state["chat_stage"] = "collecting"
    except MezzApiError as exc:
        detail = str(exc)
        if exc.fields:
            detail = f"{detail} 확인 항목: {', '.join(exc.fields)}"
        _append_message("assistant", detail, kind="error")
        st.session_state["chat_stage"] = "collecting"


def _run_chatbase_query(
    prompt: str,
    *,
    route: ChatRoute,
    history: list[dict[str, str]],
) -> None:
    api_key = _setting("CHATBASE_API_KEY")
    agent_id = _setting("CHATBASE_AGENT_ID") or _setting("CHATBASE_CHATBOT_ID")
    current_evaluation = copy.deepcopy(
        st.session_state.get("current_evaluation")
    )
    response_mode = classify_evaluation_response_mode(prompt)
    context = (
        build_read_only_evaluation_context(
            current_evaluation,
            response_mode=response_mode,
        )
        if route is ChatRoute.TYPE_C_EVALUATION_EXPLANATION
        else None
    )

    try:
        chatbase = _build_chatbase_client(api_key, agent_id)
        with st.spinner("답변을 준비 중입니다."):
            _scroll_to_latest_chat_status()
            response = chatbase.ask(
                prompt,
                history=history,
                evaluation_context=context,
            )
        protected_evaluation, changed = protect_evaluation_state(
            current_evaluation,
            st.session_state.get("current_evaluation"),
        )
        if changed:
            st.session_state["current_evaluation"] = protected_evaluation
            raise ChatbaseError(
                "확정 평가결과 상태를 보호하기 위해 답변을 중단했습니다.",
                code="STATE_INTEGRITY_ERROR",
            )
        message_metadata: dict[str, Any] = {
            "response_mode": response_mode,
        }
        if context is not None and response_mode == "report":
            message_metadata["presentation"] = "report"
        _append_message("assistant", response.text, **message_metadata)
    except ChatbaseConfigurationError:
        _append_message(
            "assistant",
            "자연어 질의 서비스 연결 설정을 확인해 주세요.",
            kind="error",
        )
    except ChatbaseError as exc:
        _append_message("assistant", str(exc), kind="error")
    except Exception:
        _append_message(
            "assistant",
            "\ub2f5\ubcc0\uc744 \uc900\ube44\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694.",
            kind="error",
        )


def _resolve_chat_route(
    prompt: str,
    *,
    has_current_evaluation: bool,
):
    """Resolve A/B ambiguity with AI and fail closed to local routing."""

    fallback = route_chat_message(
        prompt,
        has_current_evaluation=has_current_evaluation,
    )
    should_resolve = getattr(
        chat_router,
        "should_resolve_route_with_ai",
        None,
    )
    build_prompt = getattr(chat_router, "build_ai_intent_prompt", None)
    parse_response = getattr(chat_router, "parse_ai_intent_response", None)
    if not all(
        callable(item)
        for item in (should_resolve, build_prompt, parse_response)
    ):
        return fallback
    if not should_resolve(prompt, fallback):
        return fallback

    api_key = _setting("CHATBASE_API_KEY")
    agent_id = _setting("CHATBASE_AGENT_ID") or _setting("CHATBASE_CHATBOT_ID")
    current_evaluation = copy.deepcopy(
        st.session_state.get("current_evaluation")
    )
    resolved = None
    try:
        chatbase = _build_chatbase_client(api_key, agent_id)
        with st.spinner("요청 유형을 확인 중입니다."):
            _scroll_to_latest_chat_status()
            response = chatbase.ask(
                build_prompt(
                    prompt,
                    has_current_evaluation=has_current_evaluation,
                )
            )
        resolved = parse_response(
            response.text,
            has_current_evaluation=has_current_evaluation,
        )
    except (ChatbaseConfigurationError, ChatbaseError):
        resolved = None
    except Exception:
        resolved = None

    protected_evaluation, changed = protect_evaluation_state(
        current_evaluation,
        st.session_state.get("current_evaluation"),
    )
    if changed:
        st.session_state["current_evaluation"] = protected_evaluation
        return fallback
    return resolved or fallback


def _handle_chat_prompt(prompt: str) -> ChatRoute:
    """Route both native chat and Agent Home prompts through one path."""

    history = safe_chat_history(st.session_state["chat_messages"])
    _append_message("user", prompt)
    st.session_state["_chat_force_follow_after_submit"] = True
    current_evaluation = st.session_state.get("current_evaluation")
    has_current_evaluation = isinstance(current_evaluation, dict)
    local_decision = route_chat_message(
        prompt,
        has_current_evaluation=has_current_evaluation,
    )
    explicit_request_check = getattr(
        chat_router,
        "is_explicit_evaluation_request",
        None,
    )
    if callable(explicit_request_check):
        is_explicit_request = bool(explicit_request_check(prompt))
    else:
        is_explicit_request = local_decision.route == ChatRoute.TYPE_B_EVALUATION

    if is_explicit_request:
        decision = local_decision
    else:
        decision = _resolve_chat_route(
            prompt,
            has_current_evaluation=has_current_evaluation,
        )

    if decision.route == ChatRoute.TYPE_D_BLOCKED:
        st.session_state["panel_mode"] = None
        _append_message("assistant", BLOCKED_SCOPE_RESPONSE)
    elif decision.route == ChatRoute.TYPE_B_EVALUATION:
        st.session_state["panel_mode"] = "메자닌 평가"
        if st.session_state.get("chat_stage") == "complete":
            st.session_state["chat_stage"] = "collecting"
        _append_message("assistant", EVALUATION_FORM_RESPONSE)
    else:
        st.session_state["panel_mode"] = None
        _run_chatbase_query(prompt, route=decision.route, history=history)
    return decision.route


def _claim_agent_home_first_prompt(value: Any) -> bool:
    """Claim one request ID before routing and ACK duplicates without rerouting."""

    request = prompt_bridge.validate_initial_prompt_payload(value)
    if request is None:
        return False
    claimed_request_id = st.session_state.get("_agent_home_first_prompt_request_id")
    if claimed_request_id is None:
        st.session_state["_agent_home_first_prompt_request_id"] = request.request_id
        st.session_state["_agent_home_first_prompt_ack_request_id"] = request.request_id
        st.session_state["_agent_home_first_prompt_ack_status"] = "accepted"
        st.session_state["_agent_home_first_prompt_pending"] = {
            "request_id": request.request_id,
            "prompt": request.prompt,
        }
        return True
    if claimed_request_id == request.request_id:
        st.session_state["_agent_home_first_prompt_ack_request_id"] = request.request_id
        st.session_state["_agent_home_first_prompt_ack_status"] = "duplicate"
    return False


def _direct_submission_message(draft: dict[str, Any]) -> str:
    product_label = {
        SELF_STOCK_PRODUCT: "CB / BW / EB(자기주식)",
        THIRD_PARTY_PRODUCT: THIRD_PARTY_PRODUCT,
    }.get(draft.get("product_type"), "-")
    return (
        f"**{product_label} 직접입력**  \n"
        f"발행회사 `{draft.get('issuer_stock_code') or '-'}` · "
        f"기초자산 `{draft.get('stock_code') or '-'}` · "
        f"신용등급 `{draft.get('credit_rating') or '-'}`  \n"
        f"전환/행사/교환가액 `{draft.get('conversion_price') or '-'}` · "
        f"Call rate `{draft.get('call_rate')}` · "
        f"최초 계약 TTM `{draft.get('ttm_years')}년` · "
        f"발행일 `{draft.get('issue_date') or '-'}`"
    )


def _render_direct_input(client: MezzApiClient, today_seoul: Any) -> None:
    issuer_options = _issuer_options()
    issuer_labels = {code: label for label, code in issuer_options}

    if st.session_state.get("direct_product_type") not in (
        SELF_STOCK_PRODUCT,
        THIRD_PARTY_PRODUCT,
    ):
        st.session_state["direct_product_type"] = SELF_STOCK_PRODUCT

    product_type = st.segmented_control(
        "상품유형",
        options=(SELF_STOCK_PRODUCT, THIRD_PARTY_PRODUCT),
        format_func=lambda value: (
            "CB / BW / EB(자기주식)" if value == SELF_STOCK_PRODUCT else value
        ),
        key="direct_product_type",
    )
    is_self_stock = product_type == SELF_STOCK_PRODUCT
    is_third_party = product_type == THIRD_PARTY_PRODUCT

    with st.form("direct_evaluation_form", clear_on_submit=False, border=True):
        code_left, code_right = st.columns(2)
        with code_left:
            issuer_stock_code = st.selectbox(
                "발행사 종목코드",
                options=[code for _, code in issuer_options],
                index=None,
                placeholder="회사명 또는 종목코드 선택",
                format_func=lambda value: issuer_labels.get(value, value),
                key="direct_issuer_stock_code_select_v2",
                disabled=not issuer_options,
            )
            if not issuer_options:
                st.caption("종목 목록을 불러올 수 없습니다.")
        with code_right:
            if not is_third_party:
                st.selectbox(
                    "기초자산 종목코드",
                    options=[code for _, code in issuer_options],
                    index=None,
                    placeholder=(
                        "발행사와 동일"
                        if is_self_stock
                        else "상품유형을 먼저 선택"
                    ),
                    format_func=lambda value: issuer_labels.get(value, value),
                    disabled=True,
                    key="direct_stock_code_locked_select_v2",
                )
                stock_code = issuer_stock_code if is_self_stock else None
            else:
                stock_code = st.selectbox(
                    "기초자산 종목코드",
                    options=[code for _, code in issuer_options],
                    index=None,
                    placeholder="회사명 또는 종목코드 선택",
                    format_func=lambda value: issuer_labels.get(value, value),
                    key="direct_stock_code_select_v2",
                    disabled=not issuer_options,
                )

        rating_col, price_col = st.columns(2)
        with rating_col:
            credit_rating = st.selectbox(
                "신용등급",
                options=CREDIT_RATINGS,
                index=None,
                placeholder="신용등급 선택",
                key="direct_credit_rating",
            )
        with price_col:
            conversion_price = st.number_input(
                "전환/행사/교환가액",
                min_value=1,
                value=None,
                step=10,
                placeholder="금액 입력",
                key="direct_conversion_price",
            )

        call_col, maturity_col = st.columns(2)
        with call_col:
            call_rate = st.number_input(
                "Call rate",
                min_value=0.0,
                max_value=1.0,
                value=None,
                step=0.01,
                format="%.2f",
                placeholder="Call rate 입력",
                key="direct_call_rate",
            )
        with maturity_col:
            ttm_years = st.number_input(
                "최초 계약 TTM(년)",
                min_value=CONTRACT_TTM_MIN_YEARS,
                max_value=CONTRACT_TTM_MAX_YEARS,
                value=None,
                step=0.25,
                format="%.2f",
                placeholder="계약상 만기년수 입력",
                key="direct_contract_ttm_years_v2",
            )
            st.caption("모델 계산에는 최대 5.00년 cap이 자동 적용됩니다.")

        issue_date = st.date_input(
            "발행일",
            value=None,
            max_value=today_seoul,
            format="YYYY-MM-DD",
            key="direct_issue_date",
        )
        submitted = st.form_submit_button(
            "평가시작",
            icon=":material/analytics:",
            width="stretch",
        )

    if not submitted:
        return

    issuer_stock_code = str(issuer_stock_code or "").strip()
    stock_code = issuer_stock_code if is_self_stock else str(stock_code or "").strip()
    draft = {
        "product_type": product_type,
        "issuer_stock_code": issuer_stock_code,
        "stock_code": stock_code,
        "credit_rating": credit_rating,
        "conversion_price": conversion_price,
        "call_rate": call_rate,
        "ttm_years": ttm_years,
        "issue_date": issue_date.isoformat() if issue_date else None,
    }
    st.session_state["evaluation_draft"] = draft
    _append_message("user", _direct_submission_message(draft))

    missing = missing_fields(draft)
    if missing:
        st.session_state["chat_stage"] = "collecting"
        _append_message("assistant", _missing_message(missing))
    else:
        errors = validate_draft(draft, today=today_seoul)
        if errors:
            st.session_state["chat_stage"] = "collecting"
            _append_message("assistant", " ".join(errors), kind="error")
        else:
            _run_evaluation(client, today_seoul)
    st.rerun()


base_url = _setting("MEZZ_API_BASE_URL")
token = _setting("MEZZ_API_TOKEN")

try:
    client = _build_client(base_url, token)
    health = _health(base_url, str(hash(token)))
except (MezzApiConfigurationError, MezzApiError):
    st.error("평가 API 연결 설정을 확인해 주세요.")
    st.stop()

if health.get("status") != "ready":
    st.warning("평가 서비스를 준비 중입니다. 잠시 후 다시 확인해 주세요.")
    st.stop()

st.markdown(
    f"""
    <div class="chat-panel-header">
        <div class="chat-title">
            <strong>EosWos AI Agent</strong>
            <span>메자닌 신규업체 단건평가</span>
        </div>
        <div class="api-ready">
            API ready · {_escape(health.get("model_mode", "-"))}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

_ensure_session()
today_seoul = datetime.now(ZoneInfo("Asia/Seoul")).date()

try:
    bridge_value = prompt_bridge.render_agent_home_prompt_bridge(
        parent_origin=_setting("AGENT_HOME_PARENT_ORIGIN"),
        deployment_environment=(
            _setting("AGENT_HOME_DEPLOYMENT_ENVIRONMENT") or "production"
        ),
        ack_request_id=st.session_state.get(
            "_agent_home_first_prompt_ack_request_id"
        ),
        ack_status=st.session_state.get("_agent_home_first_prompt_ack_status"),
    )
except prompt_bridge.PromptBridgeConfigurationError:
    bridge_value = None
    st.error("Agent Home 연결 설정을 확인해 주세요.")

if _claim_agent_home_first_prompt(bridge_value):
    st.rerun()

pending_first_prompt = st.session_state.pop(
    "_agent_home_first_prompt_pending",
    None,
)
if isinstance(pending_first_prompt, dict):
    pending_prompt = pending_first_prompt.get("prompt")
    if isinstance(pending_prompt, str):
        _handle_chat_prompt(pending_prompt)
    st.rerun()

for chat_message in st.session_state["chat_messages"]:
    _render_message(chat_message)

force_follow_after_submit = bool(
    st.session_state.pop("_chat_force_follow_after_submit", False)
)
if len(st.session_state["chat_messages"]) > 1:
    _scroll_to_chat_bottom_after_render(
        force_follow=force_follow_after_submit,
    )

stage = st.session_state.get("chat_stage")

if stage == "confirming":
    _run_evaluation(client, today_seoul)
    st.rerun()

if stage == "complete":
    if st.button("새 평가", icon=":material/add:", width="stretch"):
        _reset_conversation()
        st.rerun()
input_mode = st.session_state.get("panel_mode")
if stage != "complete" and input_mode == "메자닌 평가":
    _render_direct_input(client, today_seoul)

prompt = st.chat_input("질문을 입력해 주세요.")
if prompt:
    _handle_chat_prompt(prompt)
    st.rerun()
