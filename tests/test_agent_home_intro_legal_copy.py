from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_home_intro_uses_requested_framework_and_legal_copy() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "AI Decision Support Framework" in html
    assert "AI Decision Platform" not in html
    assert "컴퓨터프로그램저작물 제C-2026-036575호" in html
    assert "risk DEA • dual ML • Hybrid" in html
    assert "Copyright 2026. All rights reserved." in html
    assert "agent-home__registration" in html
    assert "agent-home__engine-copyright" in html


def test_agent_home_legal_copy_has_desktop_and_mobile_layout_rules() -> None:
    css = (ROOT / "agent_home.css").read_text(encoding="utf-8")

    assert ".agent-home__registration" in css
    assert "text-align: right;" in css
    assert ".agent-home__engine-copyright" in css
    copyright_block = css.split(".agent-home__engine .agent-home__engine-copyright", 1)[1].split("}", 1)[0]
    assert "font-weight: 700;" in copyright_block
    assert "flex-wrap: wrap;" in css


def test_agent_home_return_matches_ai_launcher_stack_and_compacts_label() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "agent_home.css").read_text(encoding="utf-8")

    assert "agent-home-return__label--desktop" in html
    assert ">Agent Home</span>" in html
    assert "agent-home-return__label--compact" in html
    assert ">Home</span>" in html
    assert "right: 16px;" in css
    assert "bottom: 124px;" in css
    assert "min-width: 112px;" in css
    assert "border-radius: 999px;" in css
    assert (
        "@media (max-width: 768px), "
        "(hover: none) and (pointer: coarse) and (max-width: 1024px)"
    ) in css
    assert ".agent-home-return__label--compact" in css
