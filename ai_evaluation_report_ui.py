"""Streamlit workflow for generating, reviewing, and downloading an AI report."""

from __future__ import annotations

import copy
import html
import logging
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import streamlit as st

from ai_evaluation_report import (
    AI_REPORT_GENERATION_REQUEST,
    build_ai_report_generation_context,
    build_canonical_report_context,
    new_report_state,
    report_source_fingerprint,
    validate_generated_quantitative_parity,
)
from ai_evaluation_report_docx import (
    ReportDocumentError,
    build_report_docx,
    report_filename,
)
from chat_state_guard import protect_evaluation_state
from chatbase_client import ChatbaseClient, ChatbaseError


REPORT_FAILURE_MESSAGE = "AI 평가보고서 생성에 실패했습니다."
LOGGER = logging.getLogger(__name__)


def ensure_report_session() -> None:
    defaults = {
        "current_evaluation_input": None,
        "ai_report_state": None,
        "ai_report_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_report_session() -> None:
    st.session_state["current_evaluation_input"] = None
    st.session_state["ai_report_state"] = None
    st.session_state["ai_report_error"] = None
    st.session_state.pop("ai_report_commentary_editor", None)
    st.session_state.pop("ai_report_reviewer_editor", None)


def generate_ai_report(*, api_key: str, agent_id: str, model_mode: str | None) -> bool:
    """Generate only narrative text while preserving the confirmed scoring state."""

    current = copy.deepcopy(st.session_state.get("current_evaluation"))
    submitted = copy.deepcopy(st.session_state.get("current_evaluation_input"))
    canonical = build_canonical_report_context(
        current,
        submitted_input=submitted,
        model_mode=model_mode,
    )
    if canonical is None:
        st.session_state["ai_report_error"] = REPORT_FAILURE_MESSAGE
        return False

    try:
        client = ChatbaseClient(api_key=api_key, agent_id=agent_id)
        with st.spinner("AI 평가보고서를 작성 중입니다."):
            response = client.ask(
                AI_REPORT_GENERATION_REQUEST,
                history=(),
                evaluation_context=build_ai_report_generation_context(canonical),
            )
        protected, changed = protect_evaluation_state(
            current,
            st.session_state.get("current_evaluation"),
        )
        if changed:
            st.session_state["current_evaluation"] = protected
            raise ChatbaseError(
                "확정 평가결과 상태를 보호하기 위해 보고서 생성을 중단했습니다.",
                code="STATE_INTEGRITY_ERROR",
            )
        parity_errors = validate_generated_quantitative_parity(response.text, canonical)
        if parity_errors:
            raise ChatbaseError(
                "AI 평가의견의 확정값 일치 여부를 확인하지 못했습니다.",
                code="REPORT_PARITY_ERROR",
            )
        fingerprint = report_source_fingerprint(current, submitted)
        state = new_report_state(
            canonical_context=canonical,
            ai_commentary=response.text,
            source_fingerprint=fingerprint,
            generated_at=datetime.now(ZoneInfo("Asia/Seoul")),
        )
        st.session_state["ai_report_state"] = state
        st.session_state["ai_report_commentary_editor"] = state["ai_commentary"]
        st.session_state["ai_report_reviewer_editor"] = state["reviewer_comment"]
        st.session_state["ai_report_error"] = None
        return True
    except Exception as exc:
        error_code = str(getattr(exc, "code", type(exc).__name__))[:64]
        LOGGER.warning("AI report generation failed (code=%s)", error_code)
        protected, changed = protect_evaluation_state(
            current,
            st.session_state.get("current_evaluation"),
        )
        if changed:
            st.session_state["current_evaluation"] = protected
        st.session_state["ai_report_error"] = REPORT_FAILURE_MESSAGE
        return False


def render_ai_report_workflow(*, api_key: str, agent_id: str, model_mode: str | None) -> None:
    current = st.session_state.get("current_evaluation")
    if not isinstance(current, dict):
        return
    submitted = st.session_state.get("current_evaluation_input")
    expected_fingerprint = report_source_fingerprint(current, submitted)
    report_state = st.session_state.get("ai_report_state")
    if isinstance(report_state, dict) and report_state.get("source_fingerprint") != expected_fingerprint:
        st.session_state["ai_report_state"] = None
        st.session_state["ai_report_error"] = None
        report_state = None

    if not isinstance(report_state, dict):
        if st.button("AI 평가보고서", icon=":material/description:", width="stretch"):
            generate_ai_report(api_key=api_key, agent_id=agent_id, model_mode=model_mode)
            st.rerun()
        error = st.session_state.get("ai_report_error")
        if error:
            st.error(str(error))
        return

    _render_report_draft(report_state)


def _render_report_draft(report_state: dict[str, Any]) -> None:
    canonical = report_state.get("canonical_context")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    st.markdown("### AI 평가보고서 · Draft")
    st.caption("확정 평가결과를 기반으로 생성된 AI 초안입니다. AI 서술 영역은 검토 후 수정할 수 있습니다.")

    _render_overview(canonical)
    _render_key_results(canonical)
    _render_axes(canonical)
    _render_price_basis(canonical)
    _render_provenance(canonical)

    st.markdown("#### 6. AI 평가의견")
    st.text_area(
        "AI 평가의견",
        key="ai_report_commentary_editor",
        height=150,
        max_chars=1400,
        label_visibility="collapsed",
    )
    st.markdown("#### 7. 최종 검토의견")
    st.text_area(
        "최종 검토의견",
        key="ai_report_reviewer_editor",
        height=110,
        max_chars=800,
        placeholder="담당자의 최종 검토의견을 입력해 주세요.",
        label_visibility="collapsed",
    )

    if st.button("수정 반영", icon=":material/check:", width="stretch"):
        ai_commentary = str(st.session_state.get("ai_report_commentary_editor") or "").strip()
        reviewer_comment = str(st.session_state.get("ai_report_reviewer_editor") or "").strip()
        updated = copy.deepcopy(report_state)
        updated["ai_commentary"] = ai_commentary
        updated["reviewer_comment"] = reviewer_comment
        updated["reviewer_final"] = reviewer_comment
        updated["changed"] = bool(
            ai_commentary != str(updated.get("ai_draft") or "") or reviewer_comment
        )
        updated["updated_at"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        st.session_state["ai_report_state"] = updated
        st.success("수정 내용을 반영했습니다.")
        report_state = updated

    try:
        document_bytes = build_report_docx(
            canonical,
            ai_commentary=str(report_state.get("ai_commentary") or ""),
            reviewer_comment=str(report_state.get("reviewer_comment") or ""),
        )
        st.download_button(
            "DOCX 다운로드",
            data=document_bytes,
            file_name=report_filename(canonical),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            icon=":material/download:",
            width="stretch",
        )
    except ReportDocumentError:
        st.error("AI 평가보고서 DOCX를 생성하지 못했습니다.")


def _render_overview(context: Mapping[str, Any]) -> None:
    common = _mapping(context.get("common_info"))
    st.markdown("#### 1. 평가 개요")
    rows = [
        {"항목": "평가대상", "값": common.get("company", "-")},
        {"항목": "상품유형", "값": common.get("product_type", "-")},
        {"항목": "평가유형", "값": context.get("evaluation_type", "-")},
        {"항목": "평가기준일", "값": common.get("price_basis_date", "-")},
        {"항목": "기초자산", "값": common.get("underlying_company") or common.get("stock_code", "-")},
    ]
    for key, label in (
        ("credit_rating", "신용등급"),
        ("conversion_price", "전환/행사/교환가"),
        ("call_rate", "Call Rate"),
        ("contract_ttm_years", "계약 TTM"),
        ("model_ttm_years", "모델 TTM"),
        ("issue_date", "Issue Date"),
    ):
        if key in common:
            rows.append({"항목": label, "값": common[key]})
    monitoring = _mapping(context.get("monitoring_fields"))
    for key, label in (
        ("actual_issue_date", "Actual Issue Date"),
        ("monitoring_date", "Monitoring Date"),
        ("fs_target_date", "FS Target Date"),
        ("original_ttm_years", "Original TTM"),
        ("rebased_ttm_years", "Rebased TTM"),
    ):
        if key in monitoring:
            rows.append({"항목": label, "값": monitoring[key]})
    _render_report_table(rows)


def _render_key_results(context: Mapping[str, Any]) -> None:
    result = _mapping(context.get("evaluation_result"))
    st.markdown("#### 2. 핵심 평가결과")
    columns = st.columns(4)
    metrics = (
        ("M Grade", _display(result.get("m_grade"))),
        ("M Score", _display_number(result.get("m_score"), 0)),
        ("M Rank", _display_rank(result.get("m_rank"))),
        ("Final Score", _display_number(result.get("final_score"), 6)),
    )
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)


def _render_axes(context: Mapping[str, Any]) -> None:
    axes = _mapping(context.get("axis_results"))
    st.markdown("#### 3. 핵심 평가축")
    rows = []
    for key, meaning in (
        ("e_M", "구조적 효율성"),
        ("p_M", "ITM 도달가능성 + PK 강도"),
        ("s_M", "First_ITM Timing / 도달속도"),
    ):
        axis = _mapping(axes.get(key))
        rows.append(
            {
                "축": key,
                "역할": meaning,
                "Grade": axis.get("grade", "-"),
                "Score": _display_number(axis.get("score"), 3),
                "Rank": _display_rank(axis.get("rank")),
            }
        )
    _render_report_table(rows, centered_columns=("축", "Grade", "Score", "Rank"))


def _render_price_basis(context: Mapping[str, Any]) -> None:
    raw_rows = context.get("price_basis_results")
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    st.markdown("#### 4. 가격기준별 평가")
    rows = []
    for raw in raw_rows:
        item = _mapping(raw)
        rows.append(
            {
                "가격기준": item.get("price_basis", "-"),
                "M Grade": item.get("m_grade", "-"),
                "e_M": _mapping(item.get("e_M")).get("grade", "-"),
                "p_M": _mapping(item.get("p_M")).get("grade", "-"),
                "s_M": _mapping(item.get("s_M")).get("grade", "-"),
            }
        )
    _render_report_table(rows, center_all=True)


def _render_provenance(context: Mapping[str, Any]) -> None:
    provenance = _mapping(context.get("provenance"))
    st.markdown("#### 5. 데이터 및 평가근거")
    rows = [
        {"항목": "재무·상장주식수 Source", "값": provenance.get("scoring_source_label") or provenance.get("scoring_source", "미제공")},
        {"항목": "FS 기준일", "값": provenance.get("fs_selected_date", "미제공")},
        {"항목": "FS Type", "값": provenance.get("fs_type", "미제공")},
        {"항목": "Financial Entity", "값": provenance.get("financial_entity_label") or provenance.get("financial_entity", "미제공")},
        {"항목": "BPS Provenance", "값": provenance.get("status_label") or provenance.get("status", "미제공")},
        {"항목": "Frozen 적용", "값": provenance.get("model_mode", "미제공")},
        {"항목": "Request ID", "값": context.get("request_id", "미제공")},
    ]
    if provenance.get("source_note"):
        rows.append({"항목": "Source Note", "값": provenance["source_note"]})
    _render_report_table(rows)


def _build_price_basis_detail_rows(price_basis: Any) -> list[dict[str, str]]:
    source = price_basis if isinstance(price_basis, Mapping) else {}
    rows: list[dict[str, str]] = []
    for basis in ("1D", "1W", "1M"):
        item = _mapping(source.get(basis))
        item_e = _mapping(item.get("e_m"))
        item_p = _mapping(item.get("p_m"))
        item_s = _mapping(item.get("s_m"))
        rows.append(
            {
                "기준": basis,
                "가격": _display_number(item.get("price"), 0),
                "M": _display(item.get("m_grade")),
                "M Score": _display_number(item.get("m_score"), 0),
                "Rank": _display_rank(item.get("final_rank")),
                "Final Score": _display_number(item.get("final_score"), 6),
                "e_M": _display(item_e.get("grade")),
                "p_M": _display(item_p.get("grade")),
                "s_M": _display(item_s.get("grade")),
                "도달/PK": _display(item.get("reach_pk_strength")),
                "도달지점": _display(item.get("timing_point")),
            }
        )
    return rows


def _report_table_html(
    rows: list[dict[str, Any]],
    *,
    centered_columns: tuple[str, ...] = (),
    center_all: bool = False,
) -> str:
    if not rows:
        return '<div class="eoswos-table-empty">표시할 결과가 없습니다.</div>'
    columns = list(rows[0].keys())
    table_class = "eoswos-data-table"
    if len(columns) > 5:
        table_class += " eoswos-data-table--wide"
    header = "".join(
        f'<th scope="col" style="text-align:center">{html.escape(str(column))}</th>'
        for column in columns
    )
    body_rows = []
    for row in rows:
        cells = []
        for column in columns:
            alignment = "center" if center_all or column in centered_columns else "left"
            value = html.escape(str(row.get(column, "-")))
            cells.append(f'<td style="text-align:{alignment}">{value}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<div class="eoswos-table-scroll">'
        f'<table class="{table_class}">'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def _render_report_table(
    rows: list[dict[str, Any]],
    *,
    centered_columns: tuple[str, ...] = (),
    center_all: bool = False,
) -> None:
    st.markdown(
        _report_table_html(
            rows,
            centered_columns=centered_columns,
            center_all=center_all,
        ),
        unsafe_allow_html=True,
    )

def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _display(value: Any) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, float):
        return f"{value:,.6f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _display_number(value: Any, digits: int) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _display_rank(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)
