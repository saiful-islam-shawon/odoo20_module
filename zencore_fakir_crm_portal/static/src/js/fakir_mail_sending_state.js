/** @odoo-module **/

// The portal sends mail through a regular HTML POST. Handle its native submit
// event without relying on a legacy publicWidget being mounted inside a modal.
const MAIL_FORM_SELECTOR = "#sendMailModal form.fpm-send-mail-form";

function resetMailForm(form) {
    if (form.dataset.fakirMailSending !== "true") {
        return;
    }
    const button = form.querySelector(".fpm-send-mail-submit");
    form.dataset.fakirMailSending = "false";
    if (button) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        if (button.dataset.originalHtml) {
            button.innerHTML = button.dataset.originalHtml;
        }
    }
}

// Capture works for forms rendered with the page or inserted later. It runs
// on native submission (including Enter), after the browser has validated
// required fields, and does not replace the POST or backend redirect.
document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches(MAIL_FORM_SELECTOR)) {
        return;
    }

    if (form.dataset.fakirMailSending === "true") {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
    }

    const button = form.querySelector(".fpm-send-mail-submit");
    if (!button) {
        return;
    }

    // Leave native validation and submission mechanics untouched.
    if (!form.checkValidity() || event.defaultPrevented) {
        return;
    }

    form.dataset.fakirMailSending = "true";
    button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.innerHTML = '<i class="fa fa-spinner fa-spin me-1" aria-hidden="true"></i>Sending...';
}, true);

// Restore the button if the browser returns to a previously cached form.
window.addEventListener("pageshow", () => {
    document.querySelectorAll(MAIL_FORM_SELECTOR).forEach(resetMailForm);
});
