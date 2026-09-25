/** @odoo-module **/

function primaryLanguage(value) {
    const normalized = String(value || "").trim().toLowerCase().replace("_", "-");
    if (!normalized) {
        return "";
    }
    return normalized.split("-", 1)[0];
}

function formatDuration(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) {
        return "";
    }
    const total = Math.round(value);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hours) {
        return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }
    return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function setupSubmissionDiscovery(form) {
    const urlInput = form.querySelector("#facodi_submission_url");
    const titleInput = form.querySelector("#facodi_submission_name");
    const languageInput = form.querySelector("#facodi_submission_language");
    const csrfInput = form.querySelector('input[name="csrf_token"]');
    const discoverButton = form.querySelector("[data-facodi-discover-button]");
    const status = form.querySelector("[data-facodi-discovery-status]");
    const preview = form.querySelector("[data-facodi-metadata-preview]");
    const previewTitle = form.querySelector("[data-facodi-metadata-title]");
    const previewAuthor = form.querySelector("[data-facodi-metadata-author]");
    const previewThumbnail = form.querySelector("[data-facodi-metadata-thumbnail]");

    if (!urlInput || !titleInput || !languageInput || !csrfInput || !discoverButton || !status) {
        return;
    }

    const endpoint = form.dataset.metadataEndpoint;
    const message = (name, fallback) =>
        form.querySelector(`[data-facodi-message="${name}"]`)?.textContent?.trim() || fallback;
    const messages = {
        discovering: message("discovering", "Detecting…"),
        detected: message("detected", "Details detected."),
        unavailable: message("unavailable", "Automatic detection unavailable."),
        unsupported: message("unsupported", "Automatic detection is unavailable for this URL."),
    };

    let lastRequestedUrl = "";
    let lastAutoTitle = "";
    let lastAutoLanguage = "";
    let requestSerial = 0;
    let pasteTimer = null;

    function setStatus(message, kind = "muted") {
        status.textContent = message || "";
        status.classList.remove("text-muted", "text-success", "text-warning", "text-danger");
        status.classList.add(
            kind === "success"
                ? "text-success"
                : kind === "warning"
                  ? "text-warning"
                  : kind === "danger"
                    ? "text-danger"
                    : "text-muted"
        );
    }

    function clearPreview() {
        if (preview) {
            preview.classList.add("d-none");
        }
        if (previewThumbnail) {
            previewThumbnail.classList.add("d-none");
            previewThumbnail.removeAttribute("src");
        }
        if (previewTitle) {
            previewTitle.textContent = "";
        }
        if (previewAuthor) {
            previewAuthor.textContent = "";
        }
    }

    function applyMetadata(metadata, requestUrl) {
        if (!metadata || urlInput.value.trim() !== requestUrl) {
            return;
        }

        const canonicalUrl = String(metadata.canonical_url || "").trim();
        if (canonicalUrl) {
            urlInput.value = canonicalUrl;
            lastRequestedUrl = canonicalUrl;
        }

        const detectedTitle = String(metadata.title || "").trim();
        if (detectedTitle && (!titleInput.value.trim() || titleInput.value === lastAutoTitle)) {
            titleInput.value = detectedTitle;
            lastAutoTitle = detectedTitle;
        }

        const detectedLanguage = primaryLanguage(metadata.language);
        if (detectedLanguage) {
            const option = Array.from(languageInput.options).find(
                (item) => item.value === detectedLanguage
            );
            if (
                option &&
                (!languageInput.value || languageInput.value === lastAutoLanguage)
            ) {
                languageInput.value = detectedLanguage;
                lastAutoLanguage = detectedLanguage;
            }
        }

        if (previewTitle) {
            previewTitle.textContent = detectedTitle || canonicalUrl;
        }
        if (previewAuthor) {
            const author = String(metadata.author_name || "").trim();
            const duration = formatDuration(metadata.duration_seconds);
            previewAuthor.textContent = [author, duration].filter(Boolean).join(" · ");
        }
        if (
            previewThumbnail &&
            typeof metadata.thumbnail_url === "string" &&
            metadata.thumbnail_url.startsWith("https://")
        ) {
            previewThumbnail.src = metadata.thumbnail_url;
            previewThumbnail.classList.remove("d-none");
        }
        if (preview) {
            preview.classList.remove("d-none");
        }
    }

    async function discover({ force = false } = {}) {
        const requestUrl = urlInput.value.trim();
        if (!requestUrl || !endpoint) {
            clearPreview();
            setStatus("");
            return;
        }
        if (!force && requestUrl === lastRequestedUrl) {
            return;
        }

        const serial = ++requestSerial;
        lastRequestedUrl = requestUrl;
        discoverButton.disabled = true;
        setStatus(messages.discovering);

        const body = new FormData();
        body.append("csrf_token", csrfInput.value);
        body.append("source_url", requestUrl);

        try {
            const response = await fetch(endpoint, {
                method: "POST",
                body,
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    Accept: "application/json",
                },
            });
            const payload = await response.json();
            if (serial !== requestSerial) {
                return;
            }
            if (!response.ok || payload.success !== true) {
                setStatus(messages.unavailable, "warning");
                clearPreview();
                return;
            }
            if (payload.supported !== true) {
                setStatus(messages.unsupported, "muted");
                clearPreview();
                return;
            }

            applyMetadata(payload, requestUrl);
            setStatus(messages.detected, "success");
        } catch (_error) {
            if (serial === requestSerial) {
                setStatus(messages.unavailable, "warning");
                clearPreview();
            }
        } finally {
            if (serial === requestSerial) {
                discoverButton.disabled = false;
            }
        }
    }

    discoverButton.addEventListener("click", () => discover({ force: true }));
    urlInput.addEventListener("change", () => discover());
    urlInput.addEventListener("blur", () => discover());
    urlInput.addEventListener("paste", () => {
        window.clearTimeout(pasteTimer);
        pasteTimer = window.setTimeout(() => discover({ force: true }), 120);
    });

    if (urlInput.value.trim()) {
        window.setTimeout(() => discover(), 50);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    for (const form of document.querySelectorAll("[data-facodi-resource-submission]")) {
        setupSubmissionDiscovery(form);
    }
});
