import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_direct_issue_date_widget_caps_calendar_at_seoul_today() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    issue_date_widgets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "date_input"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "발행일"
    ]

    assert len(issue_date_widgets) == 1
    max_value_keywords = [
        keyword
        for keyword in issue_date_widgets[0].keywords
        if keyword.arg == "max_value"
    ]
    assert len(max_value_keywords) == 1
    assert isinstance(max_value_keywords[0].value, ast.Name)
    assert max_value_keywords[0].value.id == "today_seoul"


def test_contract_has_no_eagent_future_date_rejection() -> None:
    source = (ROOT / "mezz_evaluation_contract.py").read_text(encoding="utf-8")

    assert "발행일은 오늘 이후일 수 없습니다." not in source
