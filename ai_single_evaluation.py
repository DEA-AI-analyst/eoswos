"""EOSWOS conversational UI for the remote single-candidate model API."""

from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

from mezz_api_client import (
    MezzApiClient,
    MezzApiConfigurationError,
    MezzApiError,
)
from mezz_chat_parser import (
    FIELD_LABELS,
    SELF_STOCK_PRODUCT,
    THIRD_PARTY_PRODUCT,
    build_api_payload,
    missing_fields,
    parse_evaluation_prompt,
    validate_draft,
)


st.set_page_config(
    page_title="EOSWOS AI 단건평가",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container {
            max-width: 720px;
            padding-top: 0.8rem;
            padding-bottom: 6.5rem;
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
        }
        [data-testid="stChatInput"] textarea { letter-spacing: 0 !important; }
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
            margin: 0.2rem 0 0.7rem;
            color: #137333;
            font-size: 0.78rem;
            font-weight: 600;
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
    st.caption(f"요청 처리 {elapsed_ms / 1000.0:.2f}초")
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
            use_container_width=True,
            column_config={
                "가격": st.column_config.NumberColumn(format="localized"),
                "M Score": st.column_config.NumberColumn(format="%.6f"),
                "Final": st.column_config.NumberColumn(format="%.9f"),
            },
        )

    with st.expander("평가 식별정보"):
        st.write(f"요청 ID: `{result.get('request_id', '-')}`")
        st.write(f"평가기준일: `{result.get('price_basis_date', '-')}`")
        st.write(f"발행회사: {result.get('issuer_company', '-')}")
        st.write(f"기초자산: {result.get('underlying_company', '-')}")


def _initial_messages() -> list[dict[str, Any]]:
    return [
        {
            "role": "assistant",
            "kind": "text",
            "content": (
                "안녕하세요. 평가할 메자닌 조건을 알려주세요. "
                "종목명 뒤에 6자리 종목코드를 함께 적어주세요."
            ),
        }
    ]


def _ensure_session() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = _initial_messages()
    if "evaluation_draft" not in st.session_state:
        st.session_state["evaluation_draft"] = {}
    if "chat_stage" not in st.session_state:
        st.session_state["chat_stage"] = "collecting"


def _reset_conversation() -> None:
    st.session_state["chat_messages"] = _initial_messages()
    st.session_state["evaluation_draft"] = {}
    st.session_state["chat_stage"] = "collecting"


def _append_message(role: str, content: str, kind: str = "text", **extra: Any) -> None:
    message: dict[str, Any] = {"role": role, "kind": kind, "content": content}
    message.update(extra)
    st.session_state["chat_messages"].append(message)


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
        st.session_state["chat_stage"] = "complete"
    except ValueError as exc:
        _append_message("assistant", str(exc), kind="error")
        st.session_state["chat_stage"] = "collecting"
    except MezzApiError as exc:
        detail = str(exc)
        if exc.fields:
            detail = f"{detail} 확인 항목: {', '.join(exc.fields)}"
        _append_message("assistant", detail, kind="error")
        st.session_state["chat_stage"] = "collecting"


st.markdown(
    """
    <div class="chat-title">
        <strong>EOSWOS AI</strong>
        <span>메자닌 신규업체 단건평가</span>
    </div>
    """,
    unsafe_allow_html=True,
)

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
    f'<div class="api-ready">API ready · {_escape(health.get("model_mode", "-"))}</div>',
    unsafe_allow_html=True,
)

_ensure_session()
today_seoul = datetime.now(ZoneInfo("Asia/Seoul")).date()

for chat_message in st.session_state["chat_messages"]:
    _render_message(chat_message)

stage = st.session_state.get("chat_stage")

if stage == "confirming":
    _run_evaluation(client, today_seoul)
    st.rerun()

if stage == "complete":
    if st.button("새 평가", icon=":material/add:", use_container_width=True):
        _reset_conversation()
        st.rerun()

prompt = st.chat_input("평가 조건을 자연어로 입력해 주세요.")
if prompt:
    _append_message("user", prompt)
    if st.session_state.get("chat_stage") == "complete":
        st.session_state["evaluation_draft"] = {}
        st.session_state["chat_stage"] = "collecting"

    current_draft = dict(st.session_state.get("evaluation_draft") or {})
    outcome = parse_evaluation_prompt(prompt, current=current_draft)

    if outcome.blocked:
        _append_message(
            "assistant",
            "본 인터페이스는 메자닌 신규 평가 및 평가결과 설명 기능만 제공합니다.",
        )
    elif outcome.reset:
        _reset_conversation()
    elif outcome.confirm:
        missing = missing_fields(current_draft)
        errors = validate_draft(current_draft, today=today_seoul) if not missing else []
        if missing:
            _append_message("assistant", _missing_message(missing))
        elif errors:
            _append_message("assistant", " ".join(errors), kind="error")
        else:
            _run_evaluation(client, today_seoul)
    elif not outcome.updates:
        _append_message(
            "assistant",
            "평가조건을 확인하지 못했습니다. 상품유형과 종목코드부터 알려주세요.",
        )
    else:
        previous_product = current_draft.get("product_type")
        next_product = outcome.updates.get("product_type")
        if next_product == THIRD_PARTY_PRODUCT and previous_product == SELF_STOCK_PRODUCT:
            current_draft.pop("stock_code", None)
        current_draft.update(outcome.updates)
        if current_draft.get("product_type") == SELF_STOCK_PRODUCT and current_draft.get("issuer_stock_code"):
            current_draft["stock_code"] = current_draft["issuer_stock_code"]
        st.session_state["evaluation_draft"] = current_draft

        for warning in outcome.warnings:
            _append_message("assistant", warning)

        missing = missing_fields(current_draft)
        if missing:
            st.session_state["chat_stage"] = "collecting"
            _append_message("assistant", _missing_message(missing))
        else:
            errors = validate_draft(current_draft, today=today_seoul)
            if errors:
                st.session_state["chat_stage"] = "collecting"
                _append_message("assistant", " ".join(errors), kind="error")
            else:
                _run_evaluation(client, today_seoul)

    st.rerun()
