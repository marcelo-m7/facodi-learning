"use strict";

(() => {
    const boot = () => {
        const form = document.querySelector('form[data-facodi-resource-submission="1"]');
        if (!form) {
            return;
        }

        const urlInput = form.querySelector("#facodi_submission_url");
        const titleInput = form.querySelector("#facodi_submission_name");
        const languageInput = form.querySelector("#facodi_submission_language");
        const detectButton = form.querySelector("#facodi_submission_detect_metadata");
        const statusNode = form.querySelector("#facodi_submission_metadata_status");
        const preview = form.querySelector("#facodi_submission_metadata_preview");
        const previewTitle = form.querySelector("#facodi_submission_metadata_title");
        const previewDetails = form.querySelector("#facodi_submission_metadata_details");
        const previewThumbnail = form.querySelector("#facodi_submission_metadata_thumbnail");
        const messagesRoot = form.querySelector("#facodi_submission_metadata_messages");
        const csrfInput = form.querySelector('input[name="csrf_token"]');

        if (
            !urlInput ||
            !titleInput ||
            !languageInput ||
            !detectButton ||
            !statusNode ||
            !preview ||
            !messagesRoot ||
            !csrfInput
        ) {
            return;
        }

        const messages = {};
        for (const node of messagesRoot.querySelectorAll("[data-key]")) {
            messages[node.dataset.key] = node.textContent.trim();
        }

        let timer = null;
        let controller = null;
        let lastLookupUrl = "";
        let autoTitle = "";
        let autoLanguage = "";

        const message = (key, fallback = "") => messages[key] || fallback;

        const isHttpUrl = (value) => {
            try {
                const parsed = new URL(value);
                return (
                    (parsed.protocol === "http:" || parsed.protocol === "https:") &&
                    Boolean(parsed.hostname) &&
                    !parsed.username &&
                    !parsed.password
                );
            } catch (_error) {
                return false;
            }
        };

        const setStatus = (text, tone = "muted") => {
            statusNode.textContent = text || "";
            statusNode.classList.remove(
                "text-muted",
                "text-success",
                "text-danger",
                "text-warning"
            );
            const className = {
                success: "text-success",
                danger: "text-danger",
                warning: "text-warning",
                muted: "text-muted",
            }[tone] || "text-muted";
            statusNode.classList.add(className);
        };

        const formatDuration = (seconds) => {
            const total = Number(seconds);
            if (!Number.isFinite(total) || total <= 0) {
                return "";
            }
            const rounded = Math.floor(total);
            const hours = Math.floor(rounded / 3600);
            const minutes = Math.floor((rounded % 3600) / 60);
            const secs = rounded % 60;
            if (hours) {
                return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
            }
            return `${minutes}:${String(secs).padStart(2, "0")}`;
        };

        const renderPreview = (metadata) => {
            const title = String(metadata.title || "").trim();
            const details = [];
            const author = String(metadata.author_name || "").trim();
            const duration = formatDuration(metadata.duration_seconds);
            const published = String(metadata.published_at || "").trim();

            if (author) {
                details.push(`${message("author_prefix", "By")} ${author}`);
            }
            if (duration) {
                details.push(`${message("duration_prefix", "Duration")} ${duration}`);
            }
            if (published) {
                details.push(`${message("published_prefix", "Published")} ${published}`);
            }

            previewTitle.textContent = title;
            previewDetails.textContent = details.join(" · ");

            const thumbnail = String(metadata.thumbnail_url || "").trim();
            if (thumbnail.startsWith("https://")) {
                previewThumbnail.src = thumbnail;
                previewThumbnail.classList.remove("d-none");
            } else {
                previewThumbnail.removeAttribute("src");
                previewThumbnail.classList.add("d-none");
            }

            if (title || details.length || thumbnail.startsWith("https://")) {
                preview.classList.remove("d-none");
            } else {
                preview.classList.add("d-none");
            }
        };

        const canReplaceAutoValue = (input, autoValue) =>
            !input.value.trim() || (autoValue && input.value === autoValue);

        const applyMetadata = (metadata, requestedUrl) => {
            if (urlInput.value.trim() !== requestedUrl) {
                return;
            }

            const canonicalUrl = String(metadata.canonical_url || "").trim();
            if (canonicalUrl && isHttpUrl(canonicalUrl)) {
                urlInput.value = canonicalUrl;
            }

            const title = String(metadata.title || "").trim();
            if (title && canReplaceAutoValue(titleInput, autoTitle)) {
                titleInput.value = title.slice(0, 200);
                autoTitle = titleInput.value;
            }

            const language = String(metadata.language || "").trim().toLowerCase();
            if (
                language &&
                [...languageInput.options].some((option) => option.value === language) &&
                canReplaceAutoValue(languageInput, autoLanguage)
            ) {
                languageInput.value = language;
                autoLanguage = language;
            }

            renderPreview(metadata);
        };

        const invalidateDiscoveredMetadata = () => {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            if (controller) {
                controller.abort();
                controller = null;
            }

            lastLookupUrl = "";
            renderPreview({});
            setStatus("");

            if (autoTitle && titleInput.value === autoTitle) {
                titleInput.value = "";
            }
            if (autoLanguage && languageInput.value === autoLanguage) {
                languageInput.value = "";
            }
            autoTitle = "";
            autoLanguage = "";
            detectButton.disabled = false;
        };

        const discover = async ({ force = false } = {}) => {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            const requestedUrl = urlInput.value.trim();
            if (!isHttpUrl(requestedUrl)) {
                return;
            }
            if (!force && requestedUrl === lastLookupUrl) {
                return;
            }

            if (controller) {
                controller.abort();
            }
            const activeController = new AbortController();
            controller = activeController;
            detectButton.disabled = true;
            setStatus(message("loading", "Looking up resource details…"), "muted");

            const body = new URLSearchParams();
            body.set("csrf_token", csrfInput.value);
            body.set("source_url", requestedUrl);

            try {
                const response = await fetch("/contribuir/recurso/metadata", {
                    method: "POST",
                    body,
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    signal: activeController.signal,
                });
                const payload = await response.json();
                if (!response.ok || payload.success !== true) {
                    throw new Error("metadata_unavailable");
                }
                if (urlInput.value.trim() !== requestedUrl) {
                    return;
                }

                const metadata = payload.metadata || {};
                lastLookupUrl = String(metadata.canonical_url || requestedUrl).trim();
                if (payload.available) {
                    applyMetadata(metadata, requestedUrl);
                    lastLookupUrl = urlInput.value.trim();
                    setStatus(
                        payload.message || message("found", "Resource details found."),
                        "success"
                    );
                } else {
                    renderPreview({});
                    setStatus(
                        payload.message ||
                            message(
                                "not_found",
                                "No automatic details were found. Complete the fields manually."
                            ),
                        "warning"
                    );
                }
            } catch (error) {
                if (error && error.name === "AbortError") {
                    return;
                }
                setStatus(
                    message(
                        "unavailable",
                        "Automatic details are temporarily unavailable. You can continue manually."
                    ),
                    "warning"
                );
            } finally {
                if (controller === activeController) {
                    controller = null;
                    detectButton.disabled = false;
                }
            }
        };

        const scheduleDiscovery = () => {
            if (timer) {
                clearTimeout(timer);
            }
            const value = urlInput.value.trim();
            if (!isHttpUrl(value)) {
                return;
            }
            timer = setTimeout(() => {
                timer = null;
                discover();
            }, 750);
        };

        titleInput.addEventListener("input", () => {
            if (autoTitle && titleInput.value !== autoTitle) {
                autoTitle = "";
            }
        });
        languageInput.addEventListener("change", () => {
            if (autoLanguage && languageInput.value !== autoLanguage) {
                autoLanguage = "";
            }
        });
        urlInput.addEventListener("input", () => {
            invalidateDiscoveredMetadata();
            scheduleDiscovery();
        });
        urlInput.addEventListener("change", () => {
            if (timer) {
                clearTimeout(timer);
                timer = null;
            }
            discover();
        });
        detectButton.addEventListener("click", () => discover({ force: true }));
        form.addEventListener("submit", () => {
            if (controller) {
                controller.abort();
            }
        });

        if (isHttpUrl(urlInput.value.trim())) {
            timer = setTimeout(() => {
                timer = null;
                discover();
            }, 250);
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
