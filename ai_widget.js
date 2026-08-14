(function () {
    "use strict";

    const panel = document.createElement("section");
    panel.id = "ai-evaluation-panel";
    panel.className = "ai-evaluation-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "EOSWOS AI 메자닌 단건평가");
    panel.setAttribute("aria-hidden", "true");
    panel.innerHTML = [
        '<button id="ai-panel-close" class="ai-panel-close" type="button" aria-label="AI 단건평가 닫기" title="닫기">',
        '<span aria-hidden="true">&times;</span>',
        '</button>',
        '<div id="ai-panel-loading" class="ai-panel-loading">AI 평가 화면을 불러오는 중입니다.</div>',
        '<iframe id="ai-evaluation-frame"',
        ' title="EOSWOS AI 메자닌 단건평가"',
        ' data-src="https://ai-contest-win.streamlit.app/?embed=true&amp;embed_options=hide_loading_screen"',
        ' loading="lazy"',
        ' referrerpolicy="strict-origin-when-cross-origin"></iframe>'
    ].join("");

    const launcher = document.createElement("button");
    launcher.id = "ai-evaluation-launcher";
    launcher.className = "ai-evaluation-launcher";
    launcher.type = "button";
    launcher.setAttribute("aria-label", "AI 단건평가 열기");
    launcher.setAttribute("aria-controls", panel.id);
    launcher.setAttribute("aria-expanded", "false");
    launcher.title = "AI 단건평가";
    launcher.innerHTML = [
        '<svg class="icon-chat" viewBox="0 0 24 24" aria-hidden="true">',
        '<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path>',
        '</svg>',
        '<svg class="icon-close" viewBox="0 0 24 24" aria-hidden="true">',
        '<path d="M18 6 6 18"></path><path d="m6 6 12 12"></path>',
        '</svg>'
    ].join("");

    document.body.append(panel, launcher);

    const frame = document.getElementById("ai-evaluation-frame");
    const loading = document.getElementById("ai-panel-loading");
    const closeButton = document.getElementById("ai-panel-close");

    function setPanelOpen(open) {
        launcher.setAttribute("aria-expanded", String(open));
        launcher.setAttribute("aria-label", open ? "AI 단건평가 닫기" : "AI 단건평가 열기");
        panel.setAttribute("aria-hidden", String(!open));
        panel.classList.toggle("is-open", open);

        if (open && !frame.src) {
            frame.src = frame.dataset.src;
        }
    }

    launcher.addEventListener("click", function () {
        setPanelOpen(launcher.getAttribute("aria-expanded") !== "true");
    });

    closeButton.addEventListener("click", function () {
        setPanelOpen(false);
        launcher.focus();
    });

    frame.addEventListener("load", function () {
        loading.hidden = true;
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && launcher.getAttribute("aria-expanded") === "true") {
            setPanelOpen(false);
            launcher.focus();
        }
    });
}());
