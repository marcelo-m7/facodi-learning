/** @odoo-module **/

/**
 * Progressive enhancement for the public Explore landing.
 * The cards remain ordinary links and stay visible when JavaScript is unavailable.
 * No catalogue fetch, credentials or private learner data are involved.
 */
function setupExplore(root) {
    if (root.dataset.facodiExploreEnhanced === "1") {
        return;
    }

    const toolbar = root.querySelector("[data-facodi-path-toolbar]");
    const grid = root.querySelector("[data-facodi-explore-grid]");
    const count = root.querySelector("[data-facodi-path-count]");
    if (!toolbar || !grid || !count) {
        return;
    }

    const buttons = Array.from(toolbar.querySelectorAll("[data-facodi-path-filter]"));
    const cards = Array.from(grid.querySelectorAll("[data-facodi-path-category]"));
    if (!buttons.length || !cards.length) {
        return;
    }

    const filters = new Set(buttons.map((button) => button.dataset.facodiPathFilter));
    root.dataset.facodiExploreEnhanced = "1";

    function choosePath(filter) {
        const active = filters.has(filter) ? filter : "all";
        let visible = 0;

        for (const card of cards) {
            const categories = (card.dataset.facodiPathCategory || "").split(/\s+/);
            const show = active === "all" || categories.includes(active);
            card.hidden = !show;
            if (show) {
                visible += 1;
            }
        }

        for (const button of buttons) {
            const selected = button.dataset.facodiPathFilter === active;
            button.setAttribute("aria-pressed", String(selected));
            button.classList.toggle("is-active", selected);
        }
        count.textContent = String(visible);
    }

    toolbar.addEventListener("click", (event) => {
        const button = event.target.closest("[data-facodi-path-filter]");
        if (!button || !toolbar.contains(button)) {
            return;
        }
        choosePath(button.dataset.facodiPathFilter);
    });

    toolbar.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            return;
        }
        const current = buttons.indexOf(document.activeElement);
        if (current < 0) {
            return;
        }
        event.preventDefault();
        let next = current;
        if (event.key === "Home") {
            next = 0;
        } else if (event.key === "End") {
            next = buttons.length - 1;
        } else {
            next = (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
        }
        buttons[next].focus();
        choosePath(buttons[next].dataset.facodiPathFilter);
    });

    choosePath("all");
}

function initializeExplore() {
    for (const root of document.querySelectorAll("[data-facodi-explore-map]")) {
        setupExplore(root);
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeExplore, { once: true });
} else {
    initializeExplore();
}
