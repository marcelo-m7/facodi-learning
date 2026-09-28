/** @odoo-module **/

function applyFacodiForumPrefill() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("facodi_context") !== "1") {
        return;
    }

    const form = document.querySelector("form.js_wforum_submit_form");
    if (!form) {
        return;
    }

    const title = form.querySelector('input[name="post_name"]');
    const content = form.querySelector('textarea[name="content"]');
    const proposedTitle = params.get("facodi_title") || "";
    const proposedContent = params.get("facodi_content") || "";

    // Never overwrite something the learner has already typed.
    if (title && !title.value.trim() && proposedTitle) {
        title.value = proposedTitle;
        title.dispatchEvent(new Event("input", { bubbles: true }));
        title.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (content && !content.value.trim() && proposedContent) {
        content.value = proposedContent;
        content.textContent = proposedContent;
        content.dispatchEvent(new Event("input", { bubbles: true }));
        content.dispatchEvent(new Event("change", { bubbles: true }));
    }

    const label = params.get("facodi_label");
    if (label && !form.querySelector(".facodi-forum-context-note")) {
        const note = document.createElement("div");
        note.className = "facodi-forum-context-note alert alert-info mb-4";
        note.setAttribute("role", "status");
        note.innerHTML = "<strong>Contexto FACODI pré-preenchido.</strong> " +
            "A publicação ficará no fórum normal; revê e adapta o texto antes de publicar.";
        form.prepend(note);
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyFacodiForumPrefill, { once: true });
} else {
    applyFacodiForumPrefill();
}
