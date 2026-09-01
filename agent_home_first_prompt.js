(function (root, factory) {
    "use strict";

    const api = factory();
    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.EoswosFirstPromptContract = Object.freeze(api);
    }
}(typeof window !== "undefined" ? window : globalThis, function () {
    "use strict";

    const VERSION = 1;
    const SOURCE = "agent_home_first_prompt";
    const STORAGE_KEY = "eoswos.agentHomeFirstPrompt.v1";
    const MAX_PROMPT_LENGTH = 500;
    const ACK_TIMEOUT_MS = 6000;
    const READY_TIMEOUT_MS = 90000;
    const TYPE_READY = "READY";
    const TYPE_INITIAL_PROMPT = "INITIAL_PROMPT";
    const TYPE_ACK = "ACK";

    function promptLength(value) {
        return String(value || "").length;
    }

    function normalizePrompt(value) {
        const prompt = typeof value === "string" ? value.trim() : "";
        if (!prompt) {
            return { ok: false, code: "EMPTY_PROMPT", prompt: "" };
        }
        if (promptLength(prompt) > MAX_PROMPT_LENGTH) {
            return { ok: false, code: "PROMPT_TOO_LONG", prompt: "" };
        }
        return { ok: true, code: "OK", prompt: prompt };
    }

    function shouldSubmitEnter(event, compositionActive) {
        return Boolean(
            event
            && event.key === "Enter"
            && !event.repeat
            && !compositionActive
            && !event.isComposing
            && event.keyCode !== 229
        );
    }

    function createRequestId(cryptoApi) {
        if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
            return cryptoApi.randomUUID();
        }
        if (!cryptoApi || typeof cryptoApi.getRandomValues !== "function") {
            throw new Error("Secure request ID generation is unavailable.");
        }
        const bytes = new Uint8Array(16);
        cryptoApi.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = Array.from(bytes, function (item) {
            return item.toString(16).padStart(2, "0");
        }).join("");
        return [
            hex.slice(0, 8),
            hex.slice(8, 12),
            hex.slice(12, 16),
            hex.slice(16, 20),
            hex.slice(20),
        ].join("-");
    }

    function readTabState(storage) {
        try {
            const raw = storage.getItem(STORAGE_KEY);
            if (!raw) {
                return { available: true, used: false, request_id: null };
            }
            const parsed = JSON.parse(raw);
            if (
                !parsed
                || parsed.used !== true
                || !(parsed.request_id === null || typeof parsed.request_id === "string")
                || Object.keys(parsed).some(function (key) {
                    return key !== "used" && key !== "request_id";
                })
            ) {
                return { available: false, used: true, request_id: null };
            }
            return {
                available: true,
                used: true,
                request_id: parsed.request_id,
            };
        } catch (error) {
            return { available: false, used: true, request_id: null };
        }
    }

    function writeTabState(storage, requestId) {
        const state = {
            used: true,
            request_id: typeof requestId === "string" ? requestId : null,
        };
        storage.setItem(STORAGE_KEY, JSON.stringify(state));
        return state;
    }

    function createInitialPromptEnvelope(requestId, prompt) {
        return {
            type: TYPE_INITIAL_PROMPT,
            version: VERSION,
            request_id: requestId,
            prompt: prompt,
            source: SOURCE,
        };
    }

    function isReadyMessage(value) {
        return Boolean(
            value
            && value.type === TYPE_READY
            && value.version === VERSION
            && value.source === SOURCE
            && value.request_id === null
            && value.prompt === null
        );
    }

    function isAckMessage(value, requestId) {
        return Boolean(
            value
            && value.type === TYPE_ACK
            && value.version === VERSION
            && value.source === SOURCE
            && value.request_id === requestId
            && value.prompt === null
            && (value.status === "accepted" || value.status === "duplicate")
        );
    }

    function createDeliveryController(options) {
        const send = options.send;
        const schedule = options.schedule;
        const cancel = options.cancel;
        const onAck = options.onAck || function () {};
        const onFailure = options.onFailure || function () {};
        const timeoutMs = options.timeoutMs || ACK_TIMEOUT_MS;
        const readyTimeoutMs = options.readyTimeoutMs || READY_TIMEOUT_MS;
        let bridgeSource = null;
        let ready = false;
        let pending = null;
        let timer = null;
        let readyTimer = null;
        let retryDue = false;

        function clearTimer() {
            if (timer !== null) {
                cancel(timer);
                timer = null;
            }
        }

        function clearReadyTimer() {
            if (readyTimer !== null) {
                cancel(readyTimer);
                readyTimer = null;
            }
        }

        function clearSensitivePending() {
            if (pending && pending.envelope) {
                pending.envelope.prompt = "";
            }
            pending = null;
            bridgeSource = null;
            retryDue = false;
            clearTimer();
            clearReadyTimer();
        }

        function failDelivery() {
            const requestId = pending ? pending.envelope.request_id : null;
            clearSensitivePending();
            onFailure(requestId);
        }

        function armTimer() {
            clearTimer();
            timer = schedule(function () {
                timer = null;
                if (!pending) {
                    return;
                }
                if (pending.attempts >= 2) {
                    failDelivery();
                    return;
                }
                if (ready && bridgeSource) {
                    deliver();
                    return;
                }
                if (retryDue) {
                    failDelivery();
                    return;
                }
                retryDue = true;
                armTimer();
            }, timeoutMs);
        }

        function armReadyTimer() {
            if (readyTimer !== null || !pending || ready) {
                return;
            }
            readyTimer = schedule(function () {
                readyTimer = null;
                if (pending && !ready) {
                    failDelivery();
                }
            }, readyTimeoutMs);
        }

        function deliver() {
            if (!pending || !ready || !bridgeSource || pending.attempts >= 2) {
                return false;
            }
            pending.attempts += 1;
            if (!pending.deliverySource) {
                pending.deliverySource = bridgeSource;
            }
            retryDue = false;
            clearReadyTimer();
            const payload = Object.assign({}, pending.envelope, {
                attempt: pending.attempts,
            });
            send(bridgeSource, payload);
            armTimer();
            return true;
        }

        return {
            queue: function (envelope) {
                if (pending) {
                    return false;
                }
                pending = {
                    envelope: Object.assign({}, envelope),
                    attempts: 0,
                    deliverySource: null,
                };
                if (ready && bridgeSource) {
                    deliver();
                } else {
                    armReadyTimer();
                }
                return true;
            },
            markReady: function (source) {
                if (
                    pending
                    && pending.attempts > 0
                    && pending.deliverySource
                    && source !== pending.deliverySource
                ) {
                    failDelivery();
                    return;
                }
                bridgeSource = source;
                ready = true;
                clearReadyTimer();
                if (!pending) {
                    return;
                }
                if (pending.attempts === 0 || retryDue) {
                    deliver();
                }
            },
            markNotReady: function () {
                ready = false;
                bridgeSource = null;
                if (pending && pending.attempts === 0) {
                    armReadyTimer();
                }
            },
            acknowledge: function (requestId) {
                if (!pending || pending.envelope.request_id !== requestId) {
                    return false;
                }
                clearSensitivePending();
                onAck(requestId);
                return true;
            },
            hasPending: function () {
                return Boolean(pending);
            },
            attempts: function () {
                return pending ? pending.attempts : 0;
            },
        };
    }

    return {
        VERSION: VERSION,
        SOURCE: SOURCE,
        STORAGE_KEY: STORAGE_KEY,
        MAX_PROMPT_LENGTH: MAX_PROMPT_LENGTH,
        ACK_TIMEOUT_MS: ACK_TIMEOUT_MS,
        READY_TIMEOUT_MS: READY_TIMEOUT_MS,
        TYPE_READY: TYPE_READY,
        TYPE_INITIAL_PROMPT: TYPE_INITIAL_PROMPT,
        TYPE_ACK: TYPE_ACK,
        normalizePrompt: normalizePrompt,
        promptLength: promptLength,
        shouldSubmitEnter: shouldSubmitEnter,
        createRequestId: createRequestId,
        readTabState: readTabState,
        writeTabState: writeTabState,
        createInitialPromptEnvelope: createInitialPromptEnvelope,
        isReadyMessage: isReadyMessage,
        isAckMessage: isAckMessage,
        createDeliveryController: createDeliveryController,
    };
}));
