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
    assert "flex-wrap: wrap;" in css
