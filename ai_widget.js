(function () {
    "use strict";

    const PANEL_SIZE_STORAGE_KEY = "eoswos.aiPanelSize.v1";
    const DESKTOP_RESIZE_MEDIA = window.matchMedia(
        "(min-width: 769px) and (hover: hover) and (pointer: fine)"
    );
    const MIN_PANEL_WIDTH = 360;
    const MIN_PANEL_HEIGHT = 420;
    const PANEL_HORIZONTAL_GAP = 32;
    const PANEL_VERTICAL_GAP = 160;
    const promptContract = window.EoswosFirstPromptContract;

    const panel = document.createElement("section");
    panel.id = "ai-evaluation-panel";
    panel.className = "ai-evaluation-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "EOSWOS AI 메자닌 단건평가");
    panel.setAttribute("aria-hidden", "true");
    panel.innerHTML = [
        '<div class="ai-panel-resize-handle ai-panel-resize-left" data-resize-mode="width" title="패널 가로 크기 조절" aria-hidden="true"></div>',
        '<div class="ai-panel-resize-handle ai-panel-resize-top" data-resize-mode="height" title="패널 세로 크기 조절" aria-hidden="true"></div>',
        '<div class="ai-panel-resize-handle ai-panel-resize-corner" data-resize-mode="both" title="패널 크기 조절" aria-hidden="true"></div>',
        '<button id="ai-panel-refresh" class="ai-panel-control ai-panel-refresh" type="button" aria-label="AI 패널 새로고침" title="AI 패널 새로고침">',
        '<span aria-hidden="true">&#x21bb;</span>',
        '</button>',
        '<button id="ai-panel-close" class="ai-panel-control ai-panel-close" type="button" aria-label="AI 단건평가 닫기" title="닫기">',
        '<span aria-hidden="true">&times;</span>',
        '</button>',
        '<div id="ai-panel-loading" class="ai-panel-loading">AI 평가 화면을 불러오는 중입니다.</div>',
        '<iframe id="ai-evaluation-frame"',
        ' title="EOSWOS AI 메자닌 단건평가"',
        ' data-src="https://ai-contest-win.streamlit.app/?embed=true&amp;embed_options=hide_loading_screen"',
        ' loading="lazy"',
        ' scrolling="no"',
        ' referrerpolicy="strict-origin-when-cross-origin"></iframe>'
    ].join("");

    const launcher = document.createElement("button");
    launcher.id = "ai-evaluation-launcher";
    launcher.className = "ai-evaluation-launcher";
    launcher.type = "button";
    launcher.setAttribute("aria-label", "AI Agent 열기");
    launcher.setAttribute("aria-controls", panel.id);
    launcher.setAttribute("aria-expanded", "false");
    launcher.title = "AI Agent";
    launcher.innerHTML = [
        '<span class="ai-launcher-label ai-launcher-label-desktop">AI Agent</span>',
        '<span class="ai-launcher-label ai-launcher-label-mobile">AI</span>',
        '<svg class="icon-close" viewBox="0 0 24 24" aria-hidden="true">',
        '<path d="M18 6 6 18"></path><path d="m6 6 12 12"></path>',
        '</svg>'
    ].join("");

    const resizeShield = document.createElement("div");
    resizeShield.className = "ai-panel-resize-shield";
    resizeShield.hidden = true;
    resizeShield.setAttribute("aria-hidden", "true");

    document.body.append(panel, launcher, resizeShield);

    const frame = document.getElementById("ai-evaluation-frame");
    const loading = document.getElementById("ai-panel-loading");
    const closeButton = document.getElementById("ai-panel-close");
    const refreshButton = document.getElementById("ai-panel-refresh");
    const resizeHandles = panel.querySelectorAll(".ai-panel-resize-handle");
    let preferredPanelSize = readPreferredPanelSize();
    let activeResize = null;
    let bridgeSource = null;

    const childOrigin = (() => {
        try {
            return new URL(frame.dataset.src, window.location.href).origin;
        } catch (error) {
            return "";
        }
    })();

    const deliveryController = promptContract && childOrigin
        ? promptContract.createDeliveryController({
            send: function (target, payload) {
                target.postMessage(payload, childOrigin);
            },
            schedule: function (callback, delay) {
                return window.setTimeout(callback, delay);
            },
            cancel: function (timerId) {
                window.clearTimeout(timerId);
            },
            timeoutMs: promptContract.ACK_TIMEOUT_MS,
            readyTimeoutMs: promptContract.READY_TIMEOUT_MS,
            onAck: function (requestId) {
                refreshButton.disabled = false;
                document.dispatchEvent(new CustomEvent("eoswos:initial-prompt-ack", {
                    detail: { requestId: requestId },
                }));
            },
            onFailure: function (requestId) {
                refreshButton.disabled = false;
                document.dispatchEvent(new CustomEvent("eoswos:initial-prompt-delivery-failed", {
                    detail: { requestId: requestId },
                }));
            },
        })
        : null;

    function readPreferredPanelSize() {
        try {
            const parsed = JSON.parse(window.localStorage.getItem(PANEL_SIZE_STORAGE_KEY) || "{}");
            const size = {};

            if (Number.isFinite(Number(parsed.width))) {
                size.width = Math.max(MIN_PANEL_WIDTH, Math.round(Number(parsed.width)));
            }
            if (Number.isFinite(Number(parsed.height))) {
                size.height = Math.max(MIN_PANEL_HEIGHT, Math.round(Number(parsed.height)));
            }
            return size;
        } catch (error) {
            return {};
        }
    }

    function savePreferredPanelSize() {
        try {
            window.localStorage.setItem(PANEL_SIZE_STORAGE_KEY, JSON.stringify(preferredPanelSize));
        } catch (error) {
            // The panel still resizes when browser storage is unavailable.
        }
    }

    function applyPreferredPanelSize() {
        if (Number.isFinite(preferredPanelSize.width)) {
            panel.style.setProperty("--ai-panel-width", preferredPanelSize.width + "px");
        }
        if (Number.isFinite(preferredPanelSize.height)) {
            panel.style.setProperty("--ai-panel-height", preferredPanelSize.height + "px");
        }
    }

    function clamp(value, minimum, maximum) {
        return Math.min(Math.max(value, minimum), maximum);
    }

    function panelSizeLimits() {
        return {
            maxWidth: Math.max(MIN_PANEL_WIDTH, window.innerWidth - PANEL_HORIZONTAL_GAP),
            maxHeight: Math.max(MIN_PANEL_HEIGHT, window.innerHeight - PANEL_VERTICAL_GAP)
        };
    }

    function resizeCursor(mode) {
        if (mode === "width") {
            return "ew-resize";
        }
        if (mode === "height") {
            return "ns-resize";
        }
        return "nwse-resize";
    }

    function finishPanelResize(event) {
        if (!activeResize || (event && event.pointerId !== activeResize.pointerId)) {
            return;
        }


        window.removeEventListener("pointermove", movePanelResize);
        window.removeEventListener("pointerup", finishPanelResize);
        window.removeEventListener("pointercancel", finishPanelResize);
        document.documentElement.classList.remove(
            "ai-panel-resizing",
            "ai-panel-resizing-width",
            "ai-panel-resizing-height",
            "ai-panel-resizing-both"
        );
        panel.classList.remove("is-resizing");
        resizeShield.hidden = true;
        resizeShield.style.removeProperty("cursor");
        document.documentElement.style.removeProperty("--ai-panel-resize-cursor");
        activeResize = null;
        savePreferredPanelSize();
    }

    function movePanelResize(event) {
        if (!activeResize || event.pointerId !== activeResize.pointerId) {
            return;
        }

        event.preventDefault();
        const limits = panelSizeLimits();
        const width = clamp(
            activeResize.startWidth + activeResize.startX - event.clientX,
            MIN_PANEL_WIDTH,
            limits.maxWidth
        );
        const height = clamp(
            activeResize.startHeight + activeResize.startY - event.clientY,
            MIN_PANEL_HEIGHT,
            limits.maxHeight
        );

        if (activeResize.mode === "width" || activeResize.mode === "both") {
            preferredPanelSize.width = Math.round(width);
            panel.style.setProperty("--ai-panel-width", preferredPanelSize.width + "px");
        }
        if (activeResize.mode === "height" || activeResize.mode === "both") {
            preferredPanelSize.height = Math.round(height);
            panel.style.setProperty("--ai-panel-height", preferredPanelSize.height + "px");
        }
    }

    function startPanelResize(event) {
        if (!DESKTOP_RESIZE_MEDIA.matches || event.button !== 0) {
            return;
        }

        event.preventDefault();
        const handle = event.currentTarget;
        const mode = handle.dataset.resizeMode;
        const bounds = panel.getBoundingClientRect();

        activeResize = {
            mode: mode,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            startWidth: bounds.width,
            startHeight: bounds.height
        };


        panel.classList.add("is-resizing");
        document.documentElement.classList.add("ai-panel-resizing", "ai-panel-resizing-" + mode);
        document.documentElement.style.setProperty("--ai-panel-resize-cursor", resizeCursor(mode));
        resizeShield.style.cursor = resizeCursor(mode);
        resizeShield.hidden = false;
        window.addEventListener("pointermove", movePanelResize, { passive: false });
        window.addEventListener("pointerup", finishPanelResize);
        window.addEventListener("pointercancel", finishPanelResize);
    }

    applyPreferredPanelSize();
    resizeHandles.forEach(function (handle) {
        handle.addEventListener("pointerdown", startPanelResize);
    });

    function loadFrame(forceRefresh) {
        if (forceRefresh && deliveryController?.hasPending()) {
            return false;
        }
        let source = frame.dataset.src;

        if (forceRefresh) {
            const separator = source.includes("?") ? "&" : "?";
            source += separator + "refresh=" + Date.now();
        }

        loading.hidden = false;
        panel.setAttribute("aria-busy", "true");
        refreshButton.classList.add("is-loading");
        bridgeSource = null;
        deliveryController?.markNotReady();
        frame.src = source;
        return true;
    }

    function setPanelOpen(open, reason) {
        const wasOpen = launcher.getAttribute("aria-expanded") === "true";
        launcher.setAttribute("aria-expanded", String(open));
        launcher.setAttribute("aria-label", open ? "AI Agent 닫기" : "AI Agent 열기");
        panel.setAttribute("aria-hidden", String(!open));
        panel.classList.toggle("is-open", open);

        if (open && !frame.getAttribute("src")) {
            loadFrame(false);
        }
        if (open && !wasOpen) {
            document.dispatchEvent(new CustomEvent("eoswos:ai-panel-opened", {
                detail: { reason: reason || "programmatic" },
            }));
        }
        if (!open && wasOpen) {
            document.dispatchEvent(new CustomEvent("eoswos:ai-panel-closed", {
                detail: { reason: reason || "programmatic" },
            }));
        }
    }

    launcher.addEventListener("click", function () {
        const shouldOpen = launcher.getAttribute("aria-expanded") !== "true";
        setPanelOpen(shouldOpen, shouldOpen ? "manual" : "manual_close");
    });

    closeButton.addEventListener("click", function () {
        setPanelOpen(false, "close_button");
        launcher.focus();
    });

    refreshButton.addEventListener("click", function () {
        loadFrame(true);
    });

    frame.addEventListener("load", function () {
        bridgeSource = null;
        deliveryController?.markNotReady();
        loading.hidden = true;
        panel.setAttribute("aria-busy", "false");
        refreshButton.classList.remove("is-loading");
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && launcher.getAttribute("aria-expanded") === "true") {
            setPanelOpen(false, "escape");
            launcher.focus();
        }
    });

    function isExpectedBridgeSource(source) {
        if (!source) {
            return false;
        }
        try {
            if (source.top !== window) {
                return false;
            }

            // Streamlit Community Cloud adds a streamlitApp wrapper iframe
            // between the public app iframe and custom components. Accept only
            // sources whose bounded parent chain terminates at our exact app
            // iframe; sibling or unrelated frames still fail closed.
            let current = source;
            for (let depth = 0; depth < 5; depth += 1) {
                if (current === frame.contentWindow) {
                    return true;
                }
                const parent = current.parent;
                if (!parent || parent === current) {
                    return false;
                }
                current = parent;
            }
            return false;
        } catch (error) {
            return false;
        }
    }

    window.addEventListener("message", function (event) {
        if (!promptContract || !deliveryController || event.origin !== childOrigin) {
            return;
        }
        if (promptContract.isReadyMessage(event.data)) {
            if (!isExpectedBridgeSource(event.source)) {
                return;
            }
            bridgeSource = event.source;
            deliveryController.markReady(bridgeSource);
            return;
        }
        if (!bridgeSource || event.source !== bridgeSource) {
            return;
        }
        const pendingRequestId = event.data?.request_id;
        if (promptContract.isAckMessage(event.data, pendingRequestId)) {
            deliveryController.acknowledge(pendingRequestId);
        }
    });

    window.EoswosAiWidget = Object.freeze({
        openPanel: function () {
            setPanelOpen(true, "programmatic");
        },
        openForInitialPrompt: function (request) {
            if (!promptContract || !deliveryController) {
                document.dispatchEvent(new CustomEvent("eoswos:initial-prompt-delivery-failed", {
                    detail: { requestId: request?.requestId || null },
                }));
                setPanelOpen(true, "initial_prompt");
                return false;
            }
            const normalized = promptContract.normalizePrompt(request?.prompt);
            if (!normalized.ok || typeof request?.requestId !== "string") {
                document.dispatchEvent(new CustomEvent("eoswos:initial-prompt-delivery-failed", {
                    detail: { requestId: request?.requestId || null },
                }));
                return false;
            }
            const envelope = promptContract.createInitialPromptEnvelope(
                request.requestId,
                normalized.prompt,
            );
            if (!deliveryController.queue(envelope)) {
                document.dispatchEvent(new CustomEvent("eoswos:initial-prompt-delivery-failed", {
                    detail: { requestId: request.requestId },
                }));
                return false;
            }
            refreshButton.disabled = true;
            setPanelOpen(true, "initial_prompt");
            return true;
        },
    });
}());
