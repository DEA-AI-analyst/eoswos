"""EOSWOS conversational UI for the remote single-candidate model API."""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from mezz_api_client import (
    MezzApiClient,
    MezzApiConfigurationError,
    MezzApiError,
)
from mezz_chat_parser import (
    CREDIT_RATINGS,
    FIELD_LABELS,
    SELF_STOCK_PRODUCT,
    THIRD_PARTY_PRODUCT,
    build_api_payload,
    missing_fields,
    parse_evaluation_prompt,
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
            "content": "안녕하세요. EosWos AI입니다. 무엇을 도와드릴까요?",
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


def _reset_conversation() -> None:
    st.session_state["chat_messages"] = _initial_messages()
    st.session_state["evaluation_draft"] = {}
    st.session_state["chat_stage"] = "collecting"
    st.session_state["panel_mode"] = None


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
        f"잔존만기 `{draft.get('ttm_years')}년` · "
        f"발행일 `{draft.get('issue_date') or '-'}`"
    )


def _render_direct_input(client: MezzApiClient, today_seoul: Any) -> None:
    issuer_options = _issuer_options()
    issuer_labels = {code: label for label, code in issuer_options}

    product_type = st.segmented_control(
        "상품유형",
        options=(SELF_STOCK_PRODUCT, THIRD_PARTY_PRODUCT),
        default=None,
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
                "잔존만기(년)",
                min_value=0.0,
                max_value=5.0,
                value=None,
                step=0.25,
                format="%.2f",
                placeholder="잔존만기 입력",
                key="direct_ttm_years",
            )

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
            use_container_width=True,
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


st.markdown(
    """
    <div class="chat-title">
        <strong>EosWos AI</strong>
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

input_mode = st.session_state.get("panel_mode")
if stage != "complete":
    evaluation_col, chat_col, temp_col = st.columns(3, gap="small")
    with evaluation_col:
        if st.button(
            "메자닌 평가",
            icon=":material/analytics:",
            type="primary" if input_mode == "메자닌 평가" else "secondary",
            use_container_width=True,
            key="open_evaluation_mode",
        ):
            st.session_state["panel_mode"] = "메자닌 평가"
            st.rerun()
    with chat_col:
        if st.button(
            "자연어 질의",
            icon=":material/chat:",
            type="primary" if input_mode == "자연어 질의" else "secondary",
            use_container_width=True,
            key="open_chat_mode",
        ):
            st.session_state["panel_mode"] = "자연어 질의"
            st.rerun()
    with temp_col:
        if st.button(
            "Temp",
            icon=":material/widgets:",
            type="primary" if input_mode == "Temp" else "secondary",
            use_container_width=True,
            key="open_temp_mode",
        ):
            st.session_state["panel_mode"] = "Temp"
            st.rerun()

    if input_mode == "메자닌 평가":
        _render_direct_input(client, today_seoul)

prompt = (
    st.chat_input("질문을 입력해 주세요.")
    if input_mode == "자연어 질의"
    else None
)
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
