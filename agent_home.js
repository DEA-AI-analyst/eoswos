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
        initializeAgentHome();
    };

    initialize();
})();
