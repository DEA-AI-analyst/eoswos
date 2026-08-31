(() => {
    "use strict";

    const ALLOWED_ROUTES = new Set([
        "overview",
        "dea",
        "ml",
        "new_evaluation",
        "monitoring",
    ]);

    const normalizeRoute = (route) => (
        ALLOWED_ROUTES.has(route) ? route : "overview"
    );

    const initializeFirstPrompt = () => {
        const contract = window.EoswosFirstPromptContract;
        const form = document.getElementById("agent-home-first-prompt-form");
        const input = document.getElementById("agent-home-first-prompt-input");
        const submitButton = document.getElementById("agent-home-first-prompt-submit");
        const status = document.getElementById("agent-home-first-prompt-status");
        if (!contract || !form || !input || !submitButton || !status) {
            return;
        }

        let compositionActive = false;
        let locked = false;

        const setStatus = (message, isError = false) => {
            status.textContent = message;
            status.classList.toggle("is-error", isError);
        };

        const lockInput = (message) => {
            locked = true;
            input.value = "";
            input.disabled = true;
            submitButton.disabled = true;
            form.setAttribute("aria-disabled", "true");
            setStatus(message);
        };

        const persistUse = (requestId) => {
            try {
                contract.writeTabState(window.sessionStorage, requestId);
                return true;
            } catch (error) {
                lockInput("브라우저 탭 상태를 보호할 수 없어 최초 질문 기능을 사용할 수 없습니다. AI 패널에서 질문해 주세요.");
                return false;
            }
        };

        const initialState = contract.readTabState(window.sessionStorage);
        if (!initialState.available || initialState.used) {
            lockInput("이 탭의 최초 질문 기능은 종료되었습니다. 이후 대화는 AI 패널에서 계속해 주세요.");
        }

        const submitFirstPrompt = () => {
            if (locked) {
                return;
            }
            const normalized = contract.normalizePrompt(input.value);
            if (!normalized.ok) {
                setStatus(
                    normalized.code === "PROMPT_TOO_LONG"
                        ? "질문은 500자 이하로 입력해 주세요."
                        : "질문을 입력해 주세요.",
                    true,
                );
                input.focus();
                return;
            }

            let requestId;
            try {
                requestId = contract.createRequestId(window.crypto);
            } catch (error) {
                lockInput("안전한 요청 식별자를 만들 수 없습니다. AI 패널에서 질문해 주세요.");
                return;
            }
            if (!persistUse(requestId)) {
                return;
            }

            const prompt = normalized.prompt;
            lockInput("질문을 AI 패널로 전달했습니다. 이후 대화는 AI 패널에서 계속해 주세요.");
            const widget = window.EoswosAiWidget;
            if (!widget || typeof widget.openForInitialPrompt !== "function") {
                setStatus("AI 패널 연결을 준비하지 못했습니다. 열린 AI 패널에서 질문해 주세요.", true);
                return;
            }
            widget.openForInitialPrompt({
                requestId: requestId,
                prompt: prompt,
            });
        };

        input.addEventListener("compositionstart", () => {
            compositionActive = true;
        });
        input.addEventListener("compositionend", () => {
            compositionActive = false;
        });
        input.addEventListener("keydown", (event) => {
            if (event.key !== "Enter") {
                return;
            }
            event.preventDefault();
            if (contract.shouldSubmitEnter(event, compositionActive)) {
                submitFirstPrompt();
            }
        });
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            if (compositionActive) {
                return;
            }
            submitFirstPrompt();
        });

        document.addEventListener("eoswos:ai-panel-opened", (event) => {
            if (locked || event.detail?.reason !== "manual") {
                return;
            }
            if (persistUse(null)) {
                lockInput("AI 패널이 열렸습니다. 이후 질문은 AI 패널에서 입력해 주세요.");
            }
        });

        document.addEventListener("eoswos:initial-prompt-delivery-failed", () => {
            if (locked) {
                setStatus("질문 전달 확인이 지연되고 있습니다. 열린 AI 패널에서 질문을 입력해 주세요.", true);
            }
        });
    };

    const renderIcons = () => {
        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons({
                attrs: {
                    "aria-hidden": "true",
                },
            });
        }
    };

    const initializeAgentHome = () => {
        const home = document.getElementById("agent-home");
        const frameWrap = document.getElementById("mcore-frame-wrap");
        const frame = document.getElementById("mcore-frame");
        const frameLoading = document.getElementById("mcore-frame-loading");
        const returnButton = document.getElementById("agent-home-return");
        const routeButtons = document.querySelectorAll("[data-mcore-route]");

        if (!home || !frameWrap || !frame || !frameLoading || !returnButton) {
            return;
        }

        let readySource = "";
        let loadingSettleTimer = null;

        const setFrameLoading = (isLoading) => {
            frameLoading.hidden = !isLoading;
            frameWrap.setAttribute("aria-busy", String(isLoading));
        };

        frame.addEventListener("load", () => {
            window.clearTimeout(loadingSettleTimer);
            const loadedSource = frame.src;
            readySource = loadedSource;
            loadingSettleTimer = window.setTimeout(() => {
                if (frame.src === loadedSource) {
                    setFrameLoading(false);
                }
            }, 180);
        });

        const buildMcoreUrl = (route) => {
            const baseSource = frame.dataset.baseSrc || frame.src;
            const url = new URL(baseSource, window.location.href);
            url.searchParams.set("view", normalizeRoute(route));
            return url.toString();
        };

        const showHome = ({ updateHistory = true } = {}) => {
            home.hidden = false;
            frameWrap.hidden = true;
            frameWrap.setAttribute("aria-hidden", "true");
            setFrameLoading(false);
            returnButton.hidden = true;
            document.body.classList.add("agent-home-active");
            document.body.classList.remove("mcore-active");

            if (updateHistory) {
                window.history.pushState(
                    { surface: "home" },
                    "",
                    "#home",
                );
            }
        };

        const showMcore = (route, { updateHistory = true } = {}) => {
            const safeRoute = normalizeRoute(route);
            const targetSource = buildMcoreUrl(safeRoute);

            if (frame.src !== targetSource) {
                readySource = "";
                setFrameLoading(true);
                frame.src = targetSource;
            } else {
                setFrameLoading(readySource !== targetSource);
            }

            home.hidden = true;
            frameWrap.hidden = false;
            frameWrap.setAttribute("aria-hidden", "false");
            returnButton.hidden = false;
            document.body.classList.remove("agent-home-active");
            document.body.classList.add("mcore-active");

            if (updateHistory) {
                window.history.pushState(
                    { surface: "mcore", route: safeRoute },
                    "",
                    `#mcore=${safeRoute}`,
                );
            }
        };

        routeButtons.forEach((button) => {
            button.addEventListener("click", () => {
                showMcore(button.dataset.mcoreRoute);
            });
        });

        returnButton.addEventListener("click", () => {
            showHome();
        });

        window.addEventListener("popstate", (event) => {
            const state = event.state;
            if (state?.surface === "mcore") {
                showMcore(state.route, { updateHistory: false });
                return;
            }
            showHome({ updateHistory: false });
        });

        showHome({ updateHistory: false });
        window.history.replaceState({ surface: "home" }, "", "#home");
    };

    const initialize = () => {
        renderIcons();
        initializeFirstPrompt();
        initializeAgentHome();
    };

    initialize();
})();
