/** @odoo-module **/

/**
 * Isolate the portal Activity dialog from unrelated document-level click
 * delegates (the latter may try to parse a non-link as an absolute URL).
 * Native label/radio behaviour and native POST form submission remain intact.
 */
function setupActivityDialog() {
    const modal = document.getElementById("scheduleActivityModal");
    if (!modal || modal.dataset.fakirClickIsolated === "1") return;
    modal.dataset.fakirClickIsolated = "1";

    // Let the event reach its button, label, input and form handlers, but not
    // the global document handler that is unrelated to this portal dialog.
    modal.addEventListener("click", (event) => {
        const dismiss = event.target.closest('[data-bs-dismiss="modal"]');
        if (dismiss && modal.contains(dismiss)) {
            event.preventDefault();
            // We stop document-level click delegation, so handle dismissal here.
            const instance = window.bootstrap?.Modal?.getInstance(modal);
            if (instance) {
                instance.hide();
            } else {
                modal.classList.remove("show");
                modal.style.display = "none";
                modal.setAttribute("aria-hidden", "true");
                document.body.classList.remove("modal-open");
                document.querySelectorAll(".modal-backdrop").forEach((el) => el.remove());
            }
        }
        event.stopPropagation();
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupActivityDialog, { once: true });
} else {
    setupActivityDialog();
}
