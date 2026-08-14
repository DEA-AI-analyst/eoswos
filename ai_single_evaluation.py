"""EOSWOS Streamlit UI for the remote single-candidate model API."""

from __future__ import annotations

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import streamlit as st

from mezz_api_client import (
    MezzApiClient,
    MezzApiConfigurationError,
    MezzApiError,
)


SELF_STOCK_PRODUCT = "CB/BW/EB(자기주식)"
THIRD_PARTY_PRODUCT = "EB(타사주식)"
PRODUCT_TYPES = (SELF_STOCK_PRODUCT, THIRD_PARTY_PRODUCT)
CREDIT_RATINGS = (
    "AAA",
    "AA+",
    "AA",
    "AA-",
    "A+",
    "A",
    "A-",
    "BBB+",
    "BBB",
    "BBB-",
    "BB+",
    "BB",
    "BB-",
    "B+",
    "B",
    "B-",
    "CCC",
    "CC",
    "C",
    "D",
)


st.set_page_config(
    page_title="EOSWOS AI 단건평가",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container {
            max-width: 1180px;
            padding-top: 1.4rem;
            padding-bottom: 3rem;
        }
        h1, h2, h3 { letter-spacing: 0 !important; }
        h1 { font-size: 2rem !important; }
        h2 { font-size: 1.35rem !important; }
        [data-testid="stMetric"] {
            border-top: 2px solid #3b82c4;
            padding-top: 0.65rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.65rem;
        }
        .api-ready {
            color: #137333;
            font-size: 0.86rem;
            font-weight: 600;
        }
        @media (max-width: 700px) {
            .block-container { padding-top: 2.5rem; }
            h1 { font-size: 1.65rem !important; }
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


def _clear_result() -> None:
    st.session_state.pop("evaluation_result", None)
    st.session_state.pop("evaluation_elapsed_ms", None)


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


def _validate_stock_code(value: str, label: str) -> str | None:
    if not re.fullmatch(r"\d{6}", value):
        return f"{label}는 6자리 숫자로 입력해 주세요."
    return None


def _render_result(result: dict[str, Any], elapsed_ms: float) -> None:
    st.divider()
    st.subheader("평가 결과")

    company = str(result.get("company") or "-")
    stock_code = str(result.get("stock_code") or "-")
    st.caption(f"{company} | {stock_code} | 요청 처리 {elapsed_ms / 1000.0:.2f}초")

    metrics = st.columns(5)
    metrics[0].metric("M Grade", str(result.get("m_grade") or "-"))
    metrics[1].metric("M Score", _format_number(result.get("m_score"), 3))
    metrics[2].metric("M Rank", _format_rank(result.get("final_rank")))
    metrics[3].metric("Final Score", _format_number(result.get("final_score"), 6))
    metrics[4].metric("선택 가격기준", str(result.get("selected_price_basis") or "-"))

    price_basis = result.get("price_basis", {})
    rows: list[dict[str, Any]] = []
    for basis in ("1D", "1W", "1M"):
        item = price_basis.get(basis, {}) if isinstance(price_basis, dict) else {}
        e_m = item.get("e_m", {}) if isinstance(item, dict) else {}
        p_m = item.get("p_m", {}) if isinstance(item, dict) else {}
        s_m = item.get("s_m", {}) if isinstance(item, dict) else {}
        rows.append(
            {
                "가격기준": basis,
                "가격": item.get("price"),
                "M Grade": item.get("m_grade"),
                "M Score": item.get("m_score"),
                "M Rank": item.get("final_rank"),
                "Final Score": item.get("final_score"),
                "e_M Grade": e_m.get("grade"),
                "e_M Score": e_m.get("score"),
                "e_M Rank": e_m.get("rank"),
                "p_M Grade": p_m.get("grade"),
                "p_M Score": p_m.get("score"),
                "p_M Rank": p_m.get("rank"),
                "s_M Grade": s_m.get("grade"),
                "s_M Score": s_m.get("score"),
                "s_M Rank": s_m.get("rank"),
                "도달/PK강도": item.get("reach_pk_strength"),
                "도달지점": item.get("timing_point"),
            }
        )

    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        column_config={
            "가격": st.column_config.NumberColumn(format="localized"),
            "M Score": st.column_config.NumberColumn(format="%.6f"),
            "Final Score": st.column_config.NumberColumn(format="%.9f"),
            "e_M Score": st.column_config.NumberColumn(format="%.6f"),
            "p_M Score": st.column_config.NumberColumn(format="%.6f"),
            "s_M Score": st.column_config.NumberColumn(format="%.6f"),
        },
    )

    with st.expander("평가 식별정보"):
        detail_columns = st.columns(2)
        detail_columns[0].write(f"요청 ID: `{result.get('request_id', '-')}`")
        detail_columns[0].write(f"평가기준일: `{result.get('price_basis_date', '-')}`")
        detail_columns[1].write(f"발행회사: {result.get('issuer_company', '-')}")
        detail_columns[1].write(f"기초자산: {result.get('underlying_company', '-')}")


st.title("메자닌 AI 단건평가")

base_url = _setting("MEZZ_API_BASE_URL")
token = _setting("MEZZ_API_TOKEN")

try:
    client = _build_client(base_url, token)
    token_fingerprint = str(hash(token))
    health = _health(base_url, token_fingerprint)
except (MezzApiConfigurationError, MezzApiError):
    st.error("평가 API 연결 설정을 확인해 주세요.")
    st.stop()

if health.get("status") != "ready":
    st.warning("평가 서비스를 준비 중입니다. 잠시 후 다시 확인해 주세요.")
    st.stop()

st.markdown(
    f'<div class="api-ready">API ready · {health.get("model_mode", "-")}</div>',
    unsafe_allow_html=True,
)

st.subheader("평가 조건")
today_seoul = datetime.now(ZoneInfo("Asia/Seoul")).date()
product_type = st.segmented_control(
    "상품유형",
    PRODUCT_TYPES,
    default=SELF_STOCK_PRODUCT,
    selection_mode="single",
    on_change=_clear_result,
    key="product_type",
    width="stretch",
)

with st.form("single_candidate_form", clear_on_submit=False):
    first_row = st.columns(3)
    if product_type == THIRD_PARTY_PRODUCT:
        issuer_stock_code = first_row[0].text_input(
            "발행회사 종목코드",
            max_chars=6,
            placeholder="000720",
        ).strip()
        stock_code = first_row[1].text_input(
            "기초자산 종목코드",
            max_chars=6,
            placeholder="005930",
        ).strip()
    else:
        issuer_stock_code = first_row[0].text_input(
            "상장회사 종목코드",
            max_chars=6,
            placeholder="000720",
        ).strip()
        stock_code = issuer_stock_code
        first_row[1].text_input(
            "기초자산 종목코드",
            placeholder="발행회사와 동일",
            disabled=True,
        )

    credit_rating = first_row[2].selectbox(
        "신용등급",
        CREDIT_RATINGS,
        index=CREDIT_RATINGS.index("AA-"),
    )

    second_row = st.columns(4)
    conversion_price = second_row[0].number_input(
        "전환/행사/교환가액",
        min_value=1,
        max_value=10**12,
        value=100_000,
        step=1_000,
    )
    call_rate = second_row[1].number_input(
        "Call rate",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.01,
        format="%.2f",
    )
    ttm_years = second_row[2].number_input(
        "잔존만기(년)",
        min_value=0.0,
        max_value=5.0,
        value=3.0,
        step=0.25,
        format="%.2f",
    )
    issue_date = second_row[3].date_input(
        "발행일",
        value=today_seoul,
        max_value=today_seoul,
    )

    submitted = st.form_submit_button(
        "평가 실행",
        type="primary",
        icon=":material/analytics:",
        use_container_width=True,
    )

if submitted:
    errors = [
        error
        for error in (
            _validate_stock_code(issuer_stock_code, "발행회사 종목코드"),
            _validate_stock_code(stock_code, "기초자산 종목코드"),
        )
        if error
    ]
    if product_type == SELF_STOCK_PRODUCT and issuer_stock_code != stock_code:
        errors.append("자기주식 상품은 발행회사와 기초자산 종목코드가 같아야 합니다.")
    if product_type == THIRD_PARTY_PRODUCT and issuer_stock_code == stock_code:
        errors.append("타사주식 EB는 발행회사와 기초자산 종목코드가 달라야 합니다.")

    if errors:
        _clear_result()
        st.error("\n".join(errors))
    else:
        payload = {
            "product_type": product_type,
            "issuer_stock_code": issuer_stock_code,
            "stock_code": stock_code,
            "credit_rating": credit_rating,
            "conversion_price": int(conversion_price),
            "call_rate": float(call_rate),
            "ttm_years": float(ttm_years),
            "issue_date": issue_date.isoformat(),
        }
        try:
            with st.spinner("평가 중입니다."):
                api_result = client.evaluate_single(payload)
            st.session_state["evaluation_result"] = api_result.data
            st.session_state["evaluation_elapsed_ms"] = api_result.elapsed_ms
        except MezzApiError as exc:
            _clear_result()
            if exc.fields:
                st.error(f"{exc} 확인 항목: {', '.join(exc.fields)}")
            else:
                st.error(str(exc))

result = st.session_state.get("evaluation_result")
if isinstance(result, dict):
    _render_result(
        result,
        float(st.session_state.get("evaluation_elapsed_ms", 0.0)),
    )
