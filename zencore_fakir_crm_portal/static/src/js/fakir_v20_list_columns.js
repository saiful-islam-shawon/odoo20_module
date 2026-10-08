/** @odoo-module **/
// Native portal-only interaction. No dependency on the backend list controller.
const LIST = "#fpmCrmOpportunityList";
const STORE = "zencore_fakir_crm_portal.columns.v20";
function initializeList() {
    const root = document.querySelector(LIST);
    if (!root || root.dataset.columnsInitialized) return;
    root.dataset.columnsInitialized = "1";
    const table = root.querySelector("#fpmCrmOpportunityTable");
    const button = root.querySelector("#fpmCrmOptionalColumnsButton");
    const menu = root.querySelector(".fpm-crm-optional-menu");
    if (!table || !button || !menu) return;
    const toggles = [...menu.querySelectorAll(".fpm-crm-column-toggle")];
    const available = new Set(toggles.map((item) => item.value));
    let selected = [];
    try {
        const stored = JSON.parse(localStorage.getItem(STORE) || "[]");
        if (Array.isArray(stored)) selected = stored.filter((name) => available.has(name));
    } catch (_) { /* storage can be unavailable */ }
    const sync = () => {
        for (const node of table.querySelectorAll("[data-column]")) {
            node.hidden = !selected.includes(node.dataset.column);
            node.style.display = node.hidden ? "none" : "table-cell";
        }
        for (const input of toggles) input.checked = selected.includes(input.value);
    };
    sync();
    const place = () => {
        const r = button.getBoundingClientRect();
        const width = Math.min(270, window.innerWidth - 24);
        menu.style.width = `${width}px`;
        menu.style.left = `${Math.max(12, Math.min(r.right - width, window.innerWidth - width - 12))}px`;
        menu.style.top = `${Math.min(r.bottom + 6, window.innerHeight - 40)}px`;
    };
    let open = false;
    const close = () => {
        open = false;
        menu.hidden = true;
        button.setAttribute("aria-expanded", "false");
    };
    button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        open = !open;
        menu.hidden = !open;
        button.setAttribute("aria-expanded", String(open));
        if (open) {
            document.body.appendChild(menu);
            place();
        }
    });
    menu.addEventListener("change", (event) => {
        const input = event.target;
        if (!input.matches(".fpm-crm-column-toggle")) return;
        selected = toggles.filter((t) => t.checked).map((t) => t.value);
        sync();
        try { localStorage.setItem(STORE, JSON.stringify(selected)); } catch (_) {}
    });
    document.addEventListener("click", (event) => {
        if (open && !menu.contains(event.target) && !button.contains(event.target)) close();
    });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
    window.addEventListener("resize", () => { if (open) place(); });
    window.addEventListener("scroll", () => { if (open) place(); }, true);
    const selectAll = table.querySelector("#fpmCrmSelectAll");
    if (selectAll) selectAll.addEventListener("change", () => {
        for (const box of table.querySelectorAll(".fpm-crm-row-checkbox")) box.checked = selectAll.checked;
    });
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initializeList);
else initializeList();
