/** @odoo-module **/

// Page-scoped handler; never submits the Opportunity edit form.
(function () {
    "use strict";
    function showToast(status, message) {
        const old = document.querySelector(".fakir-assignment-toast");
        if (old) old.remove();
        const toast = document.createElement("div");
        toast.className = "fakir-assignment-toast alert alert-" +
            (status === "success" ? "success" : status === "warning" ? "warning" : "danger");
        toast.setAttribute("role", "alert");
        const messageEl = document.createElement("span");
        messageEl.textContent = message;
        const close = document.createElement("button");
        close.type = "button";
        close.className = "btn-close";
        close.setAttribute("aria-label", "Close");
        close.addEventListener("click", () => toast.remove());
        toast.append(messageEl, close);
        document.body.appendChild(toast);
        window.setTimeout(() => toast.remove(), 5000);
    }
    document.addEventListener("click", async function (event) {
        const button = event.target.closest(".fakir-odoo20-assigned .fakir-auto-assign");
        if (!button) return;
        event.preventDefault();
        if (button.disabled) return;
        const form = document.getElementById(button.getAttribute("form"));
        if (!form) { showToast("error", "Automatic Assignment form was not found."); return; }
        button.disabled = true;
        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                credentials: "same-origin",
                headers: {"Accept": "application/json"},
            });
            if (!response.ok) throw new Error("HTTP " + response.status);
            const data = await response.json();
            showToast(data.status || "error", data.message || "Assignment failed.");
            if (data.status === "success") {
                const tab = document.querySelector(".fakir-odoo20-assigned");
                const lat = tab?.querySelector('[name="partner_latitude"]');
                const lon = tab?.querySelector('[name="partner_longitude"]');
                const partner = tab?.querySelector('[name="partner_assigned_id"]');
                if (lat) lat.value = Number(data.latitude || 0).toFixed(7);
                if (lon) lon.value = Number(data.longitude || 0).toFixed(7);
                if (partner) {
                    let option = Array.from(partner.options).find(o => o.value === String(data.partner_id || ""));
                    if (!option && data.partner_id) {
                        option = new Option(data.partner_name, String(data.partner_id));
                        partner.add(option);
                    }
                    partner.value = data.partner_id ? String(data.partner_id) : "";
                    partner.dispatchEvent(new Event("change", {bubbles: true}));
                }
            }
        } catch (error) {
            showToast("error", "Could not complete automatic assignment. Check server logs and try again.");
        } finally { button.disabled = false; }
    });
})();
