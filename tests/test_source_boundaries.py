from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_natural_language_evaluation_parser_is_removed() -> None:
    assert not (ROOT / "mezz_chat_parser.py").exists()
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")
    assert "parse_evaluation_prompt" not in source
    assert "from mezz_chat_parser" not in source


def test_router_contains_no_evaluation_field_extraction_contract() -> None:
    source = (ROOT / "chat_intent_router.py").read_text(encoding="utf-8")
    forbidden = (
        "conversion_price",
        "call_rate",
        "ttm_years",
        "issue_date",
        "issuer_stock_code",
        "stock_code",
        "evaluation_draft",
        "build_api_payload",
    )
    for token in forbidden:
        assert token not in source


def test_chatbase_client_has_no_mezz_api_dependency() -> None:
    source = (ROOT / "chatbase_client.py").read_text(encoding="utf-8")
    assert "mezz_api_client" not in source
    assert "evaluate" not in source.lower()
