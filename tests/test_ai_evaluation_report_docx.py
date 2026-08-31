from io import BytesIO

from docx import Document

from ai_evaluation_report import build_canonical_report_context
from ai_evaluation_report_docx import build_report_docx, report_filename
from test_ai_evaluation_report import _result, _submitted


def _document_text(document: Document) -> str:
    chunks = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            chunks.extend(cell.text for cell in row.cells)
    for section in document.sections:
        chunks.extend(paragraph.text for paragraph in section.footer.paragraphs)
    return "\n".join(chunks)


def _body_runs(document: Document):
    for paragraph in document.paragraphs:
        yield from paragraph.runs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield from paragraph.runs


def test_docx_is_deterministic_a4_report_with_confirmed_values() -> None:
    context = build_canonical_report_context(
        _result(),
        submitted_input=_submitted(),
        model_mode="FROZEN_REFERENCE",
    )
    output = build_report_docx(
        context,
        ai_commentary="확정결과상 M Grade는 M4입니다. p_M과 s_M을 함께 확인해야 합니다. 추가 재무 및 시장정보를 검토해 주세요.",
        reviewer_comment="담당자 최종 검토의견입니다.",
    )
    assert output.startswith(b"PK")
    document = Document(BytesIO(output))
    section = document.sections[0]
    assert abs(section.page_width.mm - 210) < 0.1
    assert abs(section.page_height.mm - 297) < 0.1
    text = _document_text(document)
    for expected in (
        "EosWos AI 평가보고서",
        "AI Evaluation Report",
        "신규평가",
        "M4",
        "34.133",
        "1,261",
        "0.681641",
        "DART 재무정보 + 검증된 KRX 상장주식수",
        "2026-06-30",
        "FROZEN_REFERENCE",
        "담당자 최종 검토의견입니다.",
        "개별 성공확률이나 투자승인·부결을 의미하지 않습니다",
    ):
        assert expected in text
    assert "EOSWOS" not in text
    for run in _body_runs(document):
        if not run.text:
            continue
        expected_size = 16.5 if run.text == "EosWos AI 평가보고서" else 10.0
        assert abs(run.font.size.pt - expected_size) < 0.01
    for section in document.sections:
        for paragraph in section.footer.paragraphs:
            for run in paragraph.runs:
                if run.text:
                    assert abs(run.font.size.pt - 8.0) < 0.01
    assert "999999" not in text


def test_report_filename_is_safe_and_docx_only() -> None:
    context = build_canonical_report_context(_result(), submitted_input=_submitted())
    filename = report_filename(context)
    assert filename.startswith("EosWos_AI_평가보고서_현대건설_")
    assert filename.endswith(".docx")
    assert "/" not in filename and "\\" not in filename


def test_monitoring_uses_same_template_with_optional_fields() -> None:
    result = _result()
    result.update(
        {
            "Monitoring_Date": "2026-06-30",
            "Actual_Issue_Date": "2024-07-05",
            "FS_Target_Date": "2026-06-30",
            "Original_TTM_years": 5.0,
            "Rebased_TTM_years_raw": 3.01,
        }
    )
    context = build_canonical_report_context(result, model_mode="FROZEN_REFERENCE")
    output = build_report_docx(context, ai_commentary="사후관리 결과를 확인했습니다.", reviewer_comment="")
    text = _document_text(Document(BytesIO(output)))
    assert "사후관리 재평가" in text
    assert "Actual 2024-07-05" in text
    assert "Rebased 3.01" in text
    assert "별도의 독립 Monitoring Model을 의미하지 않습니다" in text
