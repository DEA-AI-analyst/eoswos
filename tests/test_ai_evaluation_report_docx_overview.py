from io import BytesIO

from docx import Document

from ai_evaluation_report import build_canonical_report_context
from ai_evaluation_report_docx import build_report_docx
from test_ai_evaluation_report import _result, _submitted


def test_new_evaluation_docx_includes_issue_date_and_contract_model_ttm() -> None:
    context = build_canonical_report_context(_result(), submitted_input=_submitted())
    output = build_report_docx(
        context,
        ai_commentary="확정 평가결과를 검토했습니다.",
        reviewer_comment="",
    )
    document = Document(BytesIO(output))
    text = "\n".join(
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )

    assert "Issue Date" in text
    assert "2026-07-07" in text
    assert "계약 30.00" in text
    assert "모델 5.00" in text
