const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const contract = require("../../agent_home_first_prompt.js");


function fakeStorage() {
    const values = new Map();
    return {
        getItem(key) {
            return values.has(key) ? values.get(key) : null;
        },
        setItem(key, value) {
            values.set(key, String(value));
        },
        value(key) {
            return values.get(key);
        },
    };
}


function fakeClock() {
    let nextId = 1;
    const callbacks = new Map();
    return {
        schedule(callback) {
            const id = nextId++;
            callbacks.set(id, callback);
            return id;
        },
        cancel(id) {
            callbacks.delete(id);
        },
        fireNext() {
            const item = callbacks.entries().next().value;
            assert.ok(item, "expected a pending timer");
            callbacks.delete(item[0]);
            item[1]();
        },
        count() {
            return callbacks.size;
        },
    };
}


test("custom component application script compiles", () => {
    const componentPath = path.join(
        __dirname,
        "..",
        "..",
        "initial_prompt_bridge",
        "index.html",
    );
    const html = fs.readFileSync(componentPath, "utf8");
    const script = html.match(/<script>([\s\S]*?)<\/script>/);
    assert.ok(script, "expected one inline component script");
    assert.doesNotThrow(() => new Function(script[1]));
});


test("validates blank, 500 and 501 UTF-16 code units", () => {
    assert.equal(contract.normalizePrompt("  ").ok, false);
    assert.equal(contract.normalizePrompt("가".repeat(500)).ok, true);
    assert.equal(contract.normalizePrompt("가".repeat(501)).code, "PROMPT_TOO_LONG");
    assert.equal(contract.normalizePrompt("😀".repeat(250)).ok, true);
    assert.equal(contract.normalizePrompt("😀".repeat(251)).ok, false);
});


test("IME composition and repeated Enter never submit", () => {
    const base = { key: "Enter", repeat: false, isComposing: false, keyCode: 13 };
    assert.equal(contract.shouldSubmitEnter(base, false), true);
    assert.equal(contract.shouldSubmitEnter({ ...base, isComposing: true }, false), false);
    assert.equal(contract.shouldSubmitEnter({ ...base, keyCode: 229 }, false), false);
    assert.equal(contract.shouldSubmitEnter({ ...base, repeat: true }, false), false);
    assert.equal(contract.shouldSubmitEnter(base, true), false);
});


test("tab state persists only used and request_id", () => {
    const storage = fakeStorage();
    const requestId = "0d830966-c9a7-4356-9498-b96af4a5159a";
    assert.deepEqual(contract.readTabState(storage), {
        available: true,
        used: false,
        request_id: null,
    });
    contract.writeTabState(storage, requestId);
    assert.deepEqual(Object.keys(JSON.parse(storage.value(contract.STORAGE_KEY))).sort(), [
        "request_id",
        "used",
    ]);
    assert.equal(storage.value(contract.STORAGE_KEY).includes("prompt"), false);
    assert.equal(contract.readTabState(storage).used, true);
});


test("page reload stays locked while an independent tab starts unused", () => {
    const tabStorage = fakeStorage();
    contract.writeTabState(tabStorage, "0d830966-c9a7-4356-9498-b96af4a5159a");

    assert.equal(contract.readTabState(tabStorage).used, true);
    assert.deepEqual(contract.readTabState(fakeStorage()), {
        available: true,
        used: false,
        request_id: null,
    });
});


test("manual panel open records one-shot use without a prompt or request ID", () => {
    const storage = fakeStorage();
    contract.writeTabState(storage, null);

    assert.deepEqual(contract.readTabState(storage), {
        available: true,
        used: true,
        request_id: null,
    });
    assert.equal(storage.value(contract.STORAGE_KEY).includes("prompt"), false);
});


test("submit before READY queues, duplicate READY does not duplicate send", () => {
    const clock = fakeClock();
    const sends = [];
    const controller = contract.createDeliveryController({
        send: (source, payload) => sends.push({ source, payload }),
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
    });
    const envelope = contract.createInitialPromptEnvelope("request-1", "M2는 뭐야?");
    controller.queue(envelope);
    assert.equal(sends.length, 0);
    controller.markReady("bridge-a");
    controller.markReady("bridge-a");
    assert.equal(sends.length, 1);
    assert.equal(sends[0].payload.attempt, 1);
});


test("READY before submit sends immediately", () => {
    const clock = fakeClock();
    const sends = [];
    const controller = contract.createDeliveryController({
        send: (source, payload) => sends.push({ source, payload }),
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
    });
    controller.markReady("bridge-a");
    controller.queue(contract.createInitialPromptEnvelope("request-1", "질문"));
    assert.equal(sends.length, 1);
});


test("missing READY fails closed after the bounded cold-start wait", () => {
    const clock = fakeClock();
    const failures = [];
    const controller = contract.createDeliveryController({
        send() {},
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
        onFailure: (requestId) => failures.push(requestId),
    });
    controller.queue(contract.createInitialPromptEnvelope("request-1", "질문"));

    clock.fireNext();

    assert.deepEqual(failures, ["request-1"]);
    assert.equal(controller.hasPending(), false);
});


test("ACK loss retries once with the same request ID and then fails closed", () => {
    const clock = fakeClock();
    const sends = [];
    const failures = [];
    const controller = contract.createDeliveryController({
        send: (source, payload) => sends.push({ source, payload }),
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
        onFailure: (requestId) => failures.push(requestId),
    });
    controller.queue(contract.createInitialPromptEnvelope("request-1", "민감하지 않은 질문"));
    controller.markReady("bridge-a");
    clock.fireNext();
    assert.equal(sends.length, 2);
    assert.equal(sends[0].payload.request_id, sends[1].payload.request_id);
    assert.equal(sends[1].payload.attempt, 2);
    clock.fireNext();
    assert.deepEqual(failures, ["request-1"]);
    assert.equal(controller.hasPending(), false);
});


test("bridge loss after first send has a bounded reconnect deadline", () => {
    const clock = fakeClock();
    const failures = [];
    const controller = contract.createDeliveryController({
        send() {},
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
        onFailure: (requestId) => failures.push(requestId),
    });
    controller.queue(contract.createInitialPromptEnvelope("request-1", "질문"));
    controller.markReady("bridge-a");
    controller.markNotReady();

    clock.fireNext();
    assert.deepEqual(failures, []);
    clock.fireNext();
    assert.deepEqual(failures, ["request-1"]);
});


test("a new bridge browsing context before ACK fails without rerouting", () => {
    const clock = fakeClock();
    const sends = [];
    const failures = [];
    const controller = contract.createDeliveryController({
        send: (source, payload) => sends.push({ source, payload }),
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
        onFailure: (requestId) => failures.push(requestId),
    });
    controller.queue(contract.createInitialPromptEnvelope("request-1", "질문"));
    controller.markReady("bridge-a");
    controller.markNotReady();
    controller.markReady("bridge-b");

    assert.equal(sends.length, 1);
    assert.deepEqual(failures, ["request-1"]);
    assert.equal(controller.hasPending(), false);
});


test("matching ACK clears pending while wrong ACK is ignored", () => {
    const clock = fakeClock();
    const acknowledgements = [];
    const controller = contract.createDeliveryController({
        send() {},
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
        onAck: (requestId) => acknowledgements.push(requestId),
    });
    controller.queue(contract.createInitialPromptEnvelope("request-1", "질문"));
    controller.markReady("bridge-a");
    assert.equal(controller.acknowledge("request-2"), false);
    assert.equal(controller.hasPending(), true);
    assert.equal(controller.acknowledge("request-1"), true);
    assert.equal(controller.hasPending(), false);
    assert.deepEqual(acknowledgements, ["request-1"]);
    assert.equal(clock.count(), 0);
});


test("iframe reload after ACK never resends", () => {
    const clock = fakeClock();
    let sends = 0;
    const controller = contract.createDeliveryController({
        send: () => { sends += 1; },
        schedule: (callback) => clock.schedule(callback),
        cancel: (id) => clock.cancel(id),
    });
    controller.queue(contract.createInitialPromptEnvelope("request-1", "질문"));
    controller.markReady("bridge-a");
    controller.acknowledge("request-1");
    controller.markNotReady();
    controller.markReady("bridge-b");
    assert.equal(sends, 1);
});
