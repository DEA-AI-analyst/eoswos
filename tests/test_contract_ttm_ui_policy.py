from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_direct_input_uses_contract_ttm_range_and_model_cap_notice() -> None:
    source = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")

    assert '"최초 계약 TTM(년)"' in source
    assert "min_value=CONTRACT_TTM_MIN_YEARS" in source
    assert "max_value=CONTRACT_TTM_MAX_YEARS" in source
    assert 'key="direct_contract_ttm_years_v2"' in source
    assert "모델 계산에는 최대 5.00년 cap이 자동 적용됩니다." in source


def test_contract_constants_are_point_25_to_30() -> None:
    source = (ROOT / "mezz_evaluation_contract.py").read_text(encoding="utf-8")

    assert "CONTRACT_TTM_MIN_YEARS = 0.25" in source
    assert "CONTRACT_TTM_MAX_YEARS = 30.0" in source
