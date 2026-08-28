(() => {
    "use strict";

    const renderIcons = () => {
        if (window.lucide && typeof window.lucide.createIcons === "function") {
            window.lucide.createIcons({
                attrs: {
                    "aria-hidden": "true",
                },
            });
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", renderIcons, { once: true });
    } else {
        renderIcons();
    }
})();
