from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "ai_single_evaluation.py").read_text(encoding="utf-8")


def test_eagent_promo_uses_the_shared_local_assets() -> None:
    assert 'PROMO_IMAGE_PATH = APP_DIR / "assets" / "EosWos_Promo_Button.png"' in SOURCE
    assert 'PROMO_VIDEO_PATH = APP_DIR / "assets" / "EosWos_Demo.mp4"' in SOURCE
    assert "_image_data_uri(PROMO_IMAGE_PATH)" in SOURCE
    assert "str(PROMO_VIDEO_PATH)" in SOURCE


def test_eagent_promo_button_is_bottom_aligned_with_api_status() -> None:
    assert ".st-key-eagent_promo_header {{" in SOURCE
    assert "position: relative;" in SOURCE
    assert "padding-right: calc(5.4rem + 138px);" in SOURCE
    assert ".st-key-eagent_promo_trigger {{" in SOURCE
    assert "position: absolute !important;" in SOURCE
    assert "right: 5.4rem;" in SOURCE
    assert "bottom: -0.65rem;" in SOURCE
    assert "width: 130px !important;" in SOURCE
    assert "background-size: contain !important;" in SOURCE
    assert "transform: scale(1.02);" in SOURCE
    assert "width: 88px !important;" in SOURCE


def test_eagent_promo_dialog_uses_native_accessible_controls() -> None:
    assert "@st.dialog(" in SOURCE
    assert '"EosWos 홍보영상"' in SOURCE
    assert "dismissible=True" in SOURCE
    assert 'on_dismiss="rerun"' in SOURCE
    assert 'format="video/mp4"' in SOURCE
    assert "start_time=0" in SOURCE
    assert "autoplay=True" in SOURCE
    assert '"EosWos 홍보영상 재생"' in SOURCE
    assert 'help="EosWos 홍보영상 재생"' in SOURCE


def test_eagent_api_status_and_single_header_are_preserved() -> None:
    assert 'API ready · {_escape(health.get("model_mode", "-"))}' in SOURCE
    assert SOURCE.count('class="chat-panel-header"') == 1
