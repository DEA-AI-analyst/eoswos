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
        const returnButton = document.getElementById("agent-home-return");
        const routeButtons = document.querySelectorAll("[data-mcore-route]");

        if (!home || !frameWrap || !frame || !returnButton) {
            return;
        }

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
                frame.src = targetSource;
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

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialize, { once: true });
    } else {
        initialize();
    }
})();
