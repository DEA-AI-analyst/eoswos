from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ai_panel_has_three_independent_resize_zones() -> None:
    source = (ROOT / "ai_widget.js").read_text(encoding="utf-8")

    assert 'data-resize-mode="width"' in source
    assert 'data-resize-mode="height"' in source
    assert 'data-resize-mode="both"' in source
    assert "activeResize.startWidth + activeResize.startX - event.clientX" in source
    assert "activeResize.startHeight + activeResize.startY - event.clientY" in source


def test_ai_panel_resize_preserves_anchor_and_default_size() -> None:
    source = (ROOT / "ai_widget.css").read_text(encoding="utf-8")

    assert "right: 16px;" in source
    assert "bottom: 132px;" in source
    assert "var(--ai-panel-width, 470px)" in source
    assert "var(--ai-panel-height, 760px)" in source
    assert ".ai-panel-resize-left" in source
    assert ".ai-panel-resize-top" in source
    assert ".ai-panel-resize-corner" in source


def test_ai_panel_resize_is_persistent_and_disabled_on_mobile() -> None:
    script = (ROOT / "ai_widget.js").read_text(encoding="utf-8")
    styles = (ROOT / "ai_widget.css").read_text(encoding="utf-8")

    assert 'PANEL_SIZE_STORAGE_KEY = "eoswos.aiPanelSize.v1"' in script
    assert "window.localStorage.setItem" in script
    assert 'window.matchMedia("(min-width: 641px)")' in script
    assert "@media (max-width: 640px)" in styles
    assert ".ai-panel-resize-handle {\n        display: none;\n    }" in styles


def test_mobile_panel_fills_available_viewport_from_fixed_edges() -> None:
    styles = (ROOT / "ai_widget.css").read_text(encoding="utf-8")

    assert "top: max(8px, env(safe-area-inset-top));" in styles
    assert "right: max(8px, env(safe-area-inset-right));" in styles
    assert "bottom: max(126px, calc(118px + env(safe-area-inset-bottom)));" in styles
    assert "left: max(8px, env(safe-area-inset-left));" in styles
    assert "max-width: none;" in styles
    assert "max-height: none;" in styles
    assert "min-width: 0;" in styles
    assert "min-height: 0;" in styles


def test_resize_drag_shield_keeps_pointer_events_out_of_the_iframe() -> None:
    script = (ROOT / "ai_widget.js").read_text(encoding="utf-8")
    styles = (ROOT / "ai_widget.css").read_text(encoding="utf-8")

    assert 'resizeShield.className = "ai-panel-resize-shield"' in script
    assert "resizeShield.hidden = false;" in script
    assert "resizeShield.hidden = true;" in script
    assert ".ai-panel-resize-shield {" in styles
    assert ".ai-panel-resize-shield[hidden]" in styles
    assert "z-index: 10030;" in styles
