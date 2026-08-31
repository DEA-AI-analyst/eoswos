"""Opt-in real-browser E2E for the cross-origin Agent Home prompt bridge."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import pytest


HOME_URL = os.getenv("EOSWOS_HOME_E2E_URL", "").strip()
EAGENT_ORIGIN = os.getenv(
    "EOSWOS_EAGENT_E2E_ORIGIN",
    "http://127.0.0.1:8511",
).strip()
if not HOME_URL:
    pytest.skip(
        "Set EOSWOS_HOME_E2E_URL to run the real-browser first-prompt E2E.",
        allow_module_level=True,
    )

selenium = pytest.importorskip("selenium")
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


STORAGE_KEY = "eoswos.agentHomeFirstPrompt.v1"
SCREENSHOT_DIR = Path(
    os.getenv("EOSWOS_E2E_SCREENSHOT_DIR", Path.cwd() / ".e2e-screenshots")
)
COLD_START_GATE = os.getenv("EOSWOS_E2E_COLD_START", "") == "1"


@pytest.fixture(scope="module")
def driver():
    options = webdriver.ChromeOptions()
    chrome_binary = os.getenv(
        "EOSWOS_E2E_CHROME_BINARY",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
    if Path(chrome_binary).exists():
        options.binary_location = chrome_binary
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-background-networking")
    options.add_argument("--window-size=1440,1000")
    browser = webdriver.Chrome(options=options)
    browser.set_page_load_timeout(60)
    yield browser
    browser.quit()


def _open_new_tab(driver, *, width: int = 1440, height: int = 1000) -> None:
    if driver.current_url != "data:,":
        driver.switch_to.new_window("tab")
    driver.set_window_size(width, height)
    driver.get(HOME_URL)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "agent-home-first-prompt-input"))
    )


def _tab_state(driver) -> dict:
    raw = driver.execute_script(
        "return window.sessionStorage.getItem(arguments[0]);",
        STORAGE_KEY,
    )
    return json.loads(raw) if raw else {}


def _wait_for_evaluation_form(driver, prompt: str) -> None:
    frame = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "ai-evaluation-frame"))
    )
    WebDriverWait(driver, 10).until(
        lambda _driver: frame.get_attribute("src")
        and "prompt=" not in frame.get_attribute("src")
    )
    driver.switch_to.frame(frame)
    WebDriverWait(driver, 90).until(
        lambda child: "EosWos AI Agent" in child.find_element(By.TAG_NAME, "body").text
    )
    WebDriverWait(driver, 30).until(
        lambda child: "평가시작" in child.find_element(By.TAG_NAME, "body").text
    )
    user_occurrences = [
        item
        for item in driver.find_elements(By.CSS_SELECTOR, '[data-testid="stChatMessage"]')
        if prompt in item.text
    ]
    assert len(user_occurrences) == 1
    driver.switch_to.default_content()


@pytest.mark.skipif(not COLD_START_GATE, reason="cold-start gate is opt-in")
def test_cold_start_keeps_prompt_queued_until_ready(driver) -> None:
    _open_new_tab(driver)
    prompt = "평가."
    prompt_input = driver.find_element(By.ID, "agent-home-first-prompt-input")
    started = time.perf_counter()
    prompt_input.send_keys(prompt, Keys.ENTER)
    WebDriverWait(driver, 3).until(
        lambda _driver: driver.find_element(
            By.ID,
            "ai-evaluation-panel",
        ).get_attribute("aria-hidden") == "false"
    )
    panel_open_seconds = time.perf_counter() - started
    assert panel_open_seconds < 3

    _wait_for_evaluation_form(driver, prompt)
    ready_seconds = time.perf_counter() - started
    assert ready_seconds < 90
    print(
        f"cold_start_panel_open_seconds={panel_open_seconds:.3f} "
        f"cold_start_ready_seconds={ready_seconds:.3f}"
    )


def test_desktop_one_shot_cross_origin_reload_and_independent_new_tab(driver) -> None:
    _open_new_tab(driver)
    prompt = "평가."
    prompt_input = driver.find_element(By.ID, "agent-home-first-prompt-input")
    prompt_input.send_keys(prompt, Keys.ENTER, Keys.ENTER)

    WebDriverWait(driver, 10).until(lambda _driver: prompt_input.get_attribute("disabled"))
    assert driver.find_element(By.ID, "ai-evaluation-panel").get_attribute("aria-hidden") == "false"
    assert "질문을 AI 패널로 전달했습니다" in driver.find_element(
        By.ID,
        "agent-home-first-prompt-status",
    ).text
    state = _tab_state(driver)
    assert set(state) == {"used", "request_id"}
    assert state["used"] is True
    request_id = state["request_id"]
    assert isinstance(request_id, str) and len(request_id) == 36
    assert prompt not in driver.current_url
    assert quote(prompt) not in driver.current_url
    _wait_for_evaluation_form(driver, prompt)

    driver.find_element(By.ID, "ai-panel-refresh").click()
    frame = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "ai-evaluation-frame"))
    )
    driver.switch_to.frame(frame)
    WebDriverWait(driver, 90).until(
        lambda child: "EosWos AI Agent" in child.find_element(By.TAG_NAME, "body").text
    )
    assert prompt not in driver.find_element(By.TAG_NAME, "body").text
    driver.switch_to.default_content()

    driver.refresh()
    reloaded_input = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "agent-home-first-prompt-input"))
    )
    assert reloaded_input.get_attribute("disabled")
    assert _tab_state(driver)["request_id"] == request_id

    _open_new_tab(driver)
    assert not driver.find_element(
        By.ID,
        "agent-home-first-prompt-input",
    ).get_attribute("disabled")
    assert _tab_state(driver) == {}


def test_manual_panel_open_consumes_home_entry_without_prompt(driver) -> None:
    _open_new_tab(driver)
    driver.find_element(By.ID, "ai-evaluation-launcher").click()

    prompt_input = driver.find_element(By.ID, "agent-home-first-prompt-input")
    WebDriverWait(driver, 10).until(lambda _driver: prompt_input.get_attribute("disabled"))
    assert _tab_state(driver) == {"used": True, "request_id": None}
    assert "AI 패널이 열렸습니다" in driver.find_element(
        By.ID,
        "agent-home-first-prompt-status",
    ).text


def test_malicious_origin_and_wrong_source_cannot_release_queued_prompt(driver) -> None:
    _open_new_tab(driver)
    prompt_input = driver.find_element(By.ID, "agent-home-first-prompt-input")
    driver.execute_script(
        """
        const frame = document.getElementById("ai-evaluation-frame");
        frame.dataset.src = "http://127.0.0.1:8999/unavailable";
        window.__eoswosUnexpectedBridgeSends = 0;
        const originalPostMessage = window.postMessage.bind(window);
        window.postMessage = (...args) => {
            window.__eoswosUnexpectedBridgeSends += 1;
            return originalPostMessage(...args);
        };
        """,
    )
    prompt_input.send_keys("평가.", Keys.ENTER)
    WebDriverWait(driver, 10).until(lambda _driver: prompt_input.get_attribute("disabled"))

    driver.execute_script(
        """
        const message = {
            type: "READY",
            version: 1,
            request_id: null,
            prompt: null,
            source: "agent_home_first_prompt",
        };
        window.dispatchEvent(new MessageEvent("message", {
            origin: "https://malicious.example",
            source: window,
            data: message,
        }));
        window.dispatchEvent(new MessageEvent("message", {
            origin: arguments[0],
            source: window,
            data: message,
        }));
        """,
        EAGENT_ORIGIN,
    )
    assert driver.execute_script("return window.__eoswosUnexpectedBridgeSends;") == 0


def test_ime_guard_length_limit_and_mobile_panel_layout(driver) -> None:
    _open_new_tab(driver, width=390, height=844)
    prompt_input = driver.find_element(By.ID, "agent-home-first-prompt-input")
    form = driver.find_element(By.ID, "agent-home-first-prompt-form")
    driver.execute_script(
        """
        const input = arguments[0];
        const form = arguments[1];
        input.value = "평가.";
        input.dispatchEvent(new CompositionEvent("compositionstart", {bubbles: true}));
        input.dispatchEvent(new KeyboardEvent("keydown", {
            key: "Enter",
            keyCode: 229,
            isComposing: true,
            bubbles: true,
            cancelable: true,
        }));
        form.dispatchEvent(new Event("submit", {bubbles: true, cancelable: true}));
        """,
        prompt_input,
        form,
    )
    assert not prompt_input.get_attribute("disabled")

    driver.execute_script(
        """
        arguments[0].dispatchEvent(new CompositionEvent("compositionend", {bubbles: true}));
        arguments[0].value = "가".repeat(501);
        """,
        prompt_input,
    )
    driver.find_element(By.ID, "agent-home-first-prompt-submit").click()
    assert not prompt_input.get_attribute("disabled")
    assert "500자 이하" in driver.find_element(
        By.ID,
        "agent-home-first-prompt-status",
    ).text

    driver.execute_script("arguments[0].value = '평가.';", prompt_input)
    driver.find_element(By.ID, "agent-home-first-prompt-submit").click()
    WebDriverWait(driver, 10).until(lambda _driver: prompt_input.get_attribute("disabled"))

    panel = driver.find_element(By.ID, "ai-evaluation-panel")
    WebDriverWait(driver, 10).until(lambda _driver: panel.get_attribute("aria-hidden") == "false")
    rect = driver.execute_script(
        """
        const rect = arguments[0].getBoundingClientRect();
        return {
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
            width: rect.width,
            viewportWidth: window.innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
        };
        """,
        panel,
    )
    assert rect["left"] >= -1
    assert rect["right"] <= rect["viewportWidth"] + 1
    assert rect["scrollWidth"] <= rect["viewportWidth"] + 1
    _wait_for_evaluation_form(driver, "평가.")

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(SCREENSHOT_DIR / "agent-home-first-prompt-mobile.png"))


def test_existing_five_agent_home_routes_remain_available(driver) -> None:
    _open_new_tab(driver)
    for route in ("overview", "dea", "ml", "new_evaluation", "monitoring"):
        driver.find_element(By.CSS_SELECTOR, f'[data-mcore-route="{route}"]').click()
        frame = driver.find_element(By.ID, "mcore-frame")
        WebDriverWait(driver, 10).until(
            lambda _driver: f"view={route}" in frame.get_attribute("src")
        )
        driver.find_element(By.ID, "agent-home-return").click()
        WebDriverWait(driver, 10).until(
            lambda _driver: driver.find_element(By.ID, "agent-home").is_displayed()
        )
