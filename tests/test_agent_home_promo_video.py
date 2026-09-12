from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "agent_home.css").read_text(encoding="utf-8")
HOME_JS = (ROOT / "agent_home.js").read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _css_block(selector: str) -> str:
    return HOME_CSS.split(f"{selector} {{", 1)[1].split("}", 1)[0]


def test_promo_artwork_uses_the_approved_white_background_asset() -> None:
    image = ROOT / "assets" / "EosWos_Promo_Button.png"
    video = ROOT / "assets" / "EosWos_Demo.mp4"

    assert image.stat().st_size == 94_237
    assert video.stat().st_size == 12_008_438
    assert _sha256(image) == "9441CC6446CE417A7BD300B05344371011F18437DD7B51325C1AF16ACCCFA5BB"
    assert _sha256(video) == "189BC695B1817444480CEE8AAC5672909679047731BCF7108FCC27468277D6BD"


def test_promo_button_is_inside_the_home_prompt_card() -> None:
    home_start = HTML.index('<section class="agent-home"')
    home_end = HTML.index('<button class="agent-home-return"', home_start)
    home = HTML[home_start:home_end]
    prompt_start = home.index('<section class="agent-home__first-prompt"')
    prompt_end = home.index("</section>", prompt_start)
    prompt = home[prompt_start:prompt_end]

    assert 'id="agent-home-promo-trigger"' in prompt
    assert 'aria-label="EosWos 홍보영상 재생"' in prompt
    assert 'src="./assets/EosWos_Promo_Button.png?v=20260912-white-background"' in prompt
    assert '<span>🎞️</span>' in prompt
    assert '<span>Video</span>' in prompt
    assert "data-mcore-route" not in prompt
    assert HTML.count('id="agent-home-promo-trigger"') == 1


def test_outer_card_and_input_heights_remain_the_release_values() -> None:
    card = _css_block(".agent-home__first-prompt")
    input_style = _css_block(".agent-home__first-prompt input")
    submit = _css_block(".agent-home__first-prompt-submit")

    assert "width: min(820px, 100%);" in card
    assert "margin: -10px auto 34px;" in card
    assert "padding: 18px;" in card
    assert "border: 1px solid #c8d9ee;" in card
    assert "border-radius: 14px;" in card
    assert "height:" not in card
    assert "height: 50px;" in input_style
    assert "width: 50px;" in submit
    assert "min-width: 50px;" in submit
    assert "height: 50px;" in submit


def test_prompt_guidance_uses_a_non_interactive_marquee_overlay() -> None:
    input_markup = HTML.split(
        '<div class="agent-home__first-prompt-input-shell">',
        1,
    )[1].split('<button class="agent-home__first-prompt-submit"', 1)[0]

    assert 'aria-describedby="agent-home-first-prompt-guidance"' in input_markup
    assert 'class="agent-home__sr-only" id="agent-home-first-prompt-guidance"' in input_markup
    assert 'placeholder=" "' in input_markup
    assert 'class="agent-home__prompt-marquee" aria-hidden="true"' in input_markup
    assert "대화는 AI 패널에서 진행됩니다. 인증정보 • 계좌정보 등 민감정보는 입력하지 마세요." in input_markup
    assert "pointer-events: none;" in _css_block(".agent-home__prompt-marquee")
    assert "overflow: hidden;" in _css_block(".agent-home__prompt-marquee")
    assert "@keyframes agent-home-prompt-marquee" in HOME_CSS
    assert "input:not(:placeholder-shown) + .agent-home__prompt-marquee" in HOME_CSS
    assert "input:disabled + .agent-home__prompt-marquee" in HOME_CSS
    assert "animation-play-state: paused;" in HOME_CSS
    assert "color: #64748b;" in _css_block(".agent-home__prompt-marquee")
    assert "@media (prefers-reduced-motion: reduce)" in HOME_CSS


def test_only_the_prompt_width_is_reallocated_for_the_promo_image() -> None:
    shared_heading_grid = HOME_CSS.split(
        ".agent-home__first-prompt-heading,",
        1,
    )[1].split("}", 1)[0]
    layout = _css_block(".agent-home__first-prompt-layout")
    trigger = _css_block(".agent-home__promo-trigger")
    image = _css_block(".agent-home__promo-trigger img")

    assert "grid-template-columns: minmax(0, 1fr) 1px 130px;" in shared_heading_grid
    assert "grid-template-columns: minmax(0, 1fr) 1px 130px;" in layout
    assert "width: 130px;" in trigger
    assert "height: 50px;" in trigger
    assert "background: #ffffff;" in trigger
    assert "object-fit: contain;" in image
    assert "transform: scale(1.02);" in HOME_CSS


def test_modal_uses_the_supplied_video_and_required_controls() -> None:
    modal = HTML.split('id="agent-home-promo-modal"', 1)[1].split("</dialog>", 1)[0]

    assert 'id="agent-home-promo-video"' in modal
    assert "controls" in modal
    assert "playsinline" in modal
    assert 'preload="metadata"' in modal
    assert 'src="./assets/EosWos_Demo.mp4"' in modal
    assert 'aria-label="홍보영상 닫기"' in modal
    assert ".agent-home__promo-modal::backdrop" in HOME_CSS


def test_modal_is_larger_on_desktop_and_keeps_the_mobile_fit_rule() -> None:
    modal = _css_block(".agent-home__promo-modal")

    assert "width: min(1200px, calc(100vw - 48px));" in modal
    assert "width: calc(100vw - 32px);" in HOME_CSS
    assert "aspect-ratio: 16 / 9;" in HOME_CSS


def test_modal_close_pauses_resets_and_handles_escape() -> None:
    assert "modal.showModal()" in HOME_JS
    assert "video.play()" in HOME_JS
    assert "video.pause()" in HOME_JS
    assert "video.currentTime = 0" in HOME_JS
    assert 'event.key !== "Escape" || !modal.open' in HOME_JS
    assert "event.stopImmediatePropagation()" in HOME_JS
    assert "trigger.setAttribute(\"aria-expanded\", \"false\")" in HOME_JS


def test_leaving_home_closes_and_resets_an_open_promo_video() -> None:
    show_mcore = HOME_JS.split("const showMcore", 1)[1].split(
        "routeButtons.forEach",
        1,
    )[0]

    assert "closePromoVideo();" in show_mcore
    assert "const closePromoVideo = initializePromoVideo();" in HOME_JS
    assert "initializeAgentHome(closePromoVideo);" in HOME_JS


def test_existing_home_routes_are_unchanged() -> None:
    routes = re.findall(r'data-mcore-route="([^"]+)"', HTML)
    assert routes == ["new_evaluation", "monitoring", "overview", "dea", "ml"]
