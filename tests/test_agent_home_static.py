from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "agent_home.css").read_text(encoding="utf-8")
HOME_JS = (ROOT / "agent_home.js").read_text(encoding="utf-8")


def _home_markup() -> str:
    start = INDEX.index('<section class="agent-home"')
    end = INDEX.index('<button class="agent-home-return"', start)
    return INDEX[start:end]


def test_agent_home_is_the_initial_surface() -> None:
    assert '<body class="agent-home-active">' in INDEX
    assert 'id="agent-home"' in INDEX
    assert 'id="mcore-frame-wrap" hidden aria-hidden="true"' in INDEX


def test_agent_home_exposes_exactly_five_allowlisted_routes() -> None:
    routes = re.findall(r'data-mcore-route="([^"]+)"', _home_markup())
    assert routes == ["new_evaluation", "monitoring", "overview", "dea", "ml"]


def test_agent_home_uses_only_confirmed_engine_copy() -> None:
    home = _home_markup()
    assert "M-CORE AI Evaluation Engine" in home
    assert "DEA · Dual ML · Frozen Reference 기반" in home

    unsupported_claims = (
        "Connected",
        "Ready",
        "Verified",
        "Human Approval",
        "Golden Eval",
        "Verification",
        "Trace",
        "Grounding",
    )
    for claim in unsupported_claims:
        assert claim not in home


def test_existing_mcore_iframe_and_ai_widget_assets_are_preserved() -> None:
    assert "https://eoswos.streamlit.app/?embed=true&embed_options=hide_loading_screen" in INDEX
    assert 'id="mcore-frame"' in INDEX
    assert "./ai_widget.css" in INDEX
    assert "./ai_widget.js" in INDEX


def test_agent_home_has_desktop_and_mobile_layouts() -> None:
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in HOME_CSS
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in HOME_CSS
    assert "@media (max-width: 840px)" in HOME_CSS
    assert "@media (max-width: 560px)" in HOME_CSS
    assert "grid-template-columns: 1fr" in HOME_CSS


def test_first_commit_script_only_initializes_icons() -> None:
    assert "lucide.createIcons" in HOME_JS
    assert "data-mcore-route" not in HOME_JS
    assert "searchParams" not in HOME_JS
