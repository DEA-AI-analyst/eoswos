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
    assert "risk DEA • dual ML • Hybrid" in home

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
    assert "margin: 0 auto clamp(29px, 4.5vh, 42px)" in HOME_CSS
    assert "margin-bottom: 23px" in HOME_CSS


def test_floating_launcher_is_the_only_agent_panel_entry_point() -> None:
    assert "agent-home__agent-label" not in INDEX


def test_monitoring_card_uses_a_supported_line_icon() -> None:
    home = _home_markup()
    assert 'data-lucide="refresh-cw"' in home
    assert 'data-lucide="monitor-search"' not in home


def test_mobile_agent_home_launcher_uses_reserved_bottom_space() -> None:
    widget_css = (ROOT / "ai_widget.css").read_text(encoding="utf-8")
    assert 'body.agent-home-active .ai-evaluation-launcher[aria-expanded="false"]' in widget_css
    assert "right: max(6px, env(safe-area-inset-right));" in widget_css
    assert "bottom: max(10px, env(safe-area-inset-bottom));" in widget_css


def test_navigation_uses_the_same_five_route_allowlist() -> None:
    route_block = re.search(
        r"const ALLOWED_ROUTES = new Set\(\[(.*?)\]\);",
        HOME_JS,
        flags=re.DOTALL,
    )
    assert route_block is not None
    routes = re.findall(r'"([a-z_]+)"', route_block.group(1))
    assert routes == ["overview", "dea", "ml", "new_evaluation", "monitoring"]


def test_navigation_forwards_only_normalized_routes_to_mcore() -> None:
    assert "lucide.createIcons" in HOME_JS
    assert 'ALLOWED_ROUTES.has(route) ? route : "overview"' in HOME_JS
    assert 'document.querySelectorAll("[data-mcore-route]")' in HOME_JS
    assert 'url.searchParams.set("view", normalizeRoute(route))' in HOME_JS
    assert "showMcore(button.dataset.mcoreRoute)" in HOME_JS


def test_navigation_preserves_home_return_and_browser_history() -> None:
    assert 'returnButton.addEventListener("click"' in HOME_JS
    assert 'window.addEventListener("popstate"' in HOME_JS
    assert 'window.history.replaceState({ surface: "home" }, "", "#home")' in HOME_JS
    assert "frameWrap.hidden = false" in HOME_JS
    assert "frameWrap.hidden = true" in HOME_JS
