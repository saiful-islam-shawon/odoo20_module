/** @odoo-module **/

// Scoped chatter delta sync. Uses same mail.message records as backend CRM.
// Polling fallback: does not claim to replace native backend Bus/OWL mail.
const timeline = document.getElementById("fpmCrmChatterTimeline");
if (timeline) {
    const oppId = Number(timeline.dataset.opportunityId);
    let lastId = 0;
    for (const node of timeline.querySelectorAll("[data-message-id]")) {
        lastId = Math.max(lastId, Number(node.dataset.messageId) || 0);
    }
    let running = false;
    const refresh = async () => {
        if (running || document.hidden || !timeline.isConnected) return;
        running = true;
        try {
            const response = await fetch(`/my/crm/opportunities/${oppId}/chatter/live?after=${lastId}`, {credentials: "same-origin", cache: "no-store"});
            if (!response.ok) return;
            const data = await response.json();
            for (const msg of data.messages || []) {
                if (timeline.querySelector(`[data-message-id="${msg.id}"]`)) continue;
                const item = document.createElement("div");
                item.className = "fpm-crm-timeline-item fpm-crm-timeline-message fakir-live-message";
                item.dataset.messageId = String(msg.id);
                const card = document.createElement("div");
                card.className = "fpm-crm-timeline-content";
                const author = document.createElement("strong");
                author.textContent = msg.author || "System";
                const time = document.createElement("small");
                time.className = "ms-2";
                time.textContent = msg.date || "";
                const text = document.createElement("div");
                text.className = "fpm-crm-message-body";
                text.textContent = msg.body || "";
                const kind = ["message", "note", "tracking"].includes(msg.kind) ? msg.kind : "message";
                const kindNames = {message: "✉ Message", note: "▤ Log Note", tracking: "↻ Tracking / System"};
                const kindLine = document.createElement("div");
                kindLine.className = "fakir-chatter-kind-line";
                const kindBadge = document.createElement("span");
                kindBadge.className = `fakir-chatter-kind fakir-chatter-kind--${kind}`;
                kindBadge.textContent = kindNames[kind];
                kindLine.appendChild(kindBadge);
                card.append(author, time, kindLine, text);
                item.appendChild(card);
                timeline.prepend(item);
                lastId = Math.max(lastId, Number(msg.id) || 0);
            }
        } catch (error) {
            // Network outages should not block form editing. Retry at next interval.
        } finally { running = false; }
    };
    const timer = setInterval(refresh, 5000);
    window.addEventListener("pagehide", () => clearInterval(timer), {once: true});
}

const detail = document.querySelector(".fpm-crm-detail-page");
if (detail) {
    const select = detail.querySelector("#fakir_detail_stage_id");
    const stages = detail.querySelectorAll(".fakir-stage-choice");
    for (const stage of stages) {
        stage.addEventListener("click", () => {
            if (!select) return;
            select.value = stage.dataset.stageId;
            for (const button of stages) {
                const selected = button === stage;
                button.classList.toggle("active", selected);
                button.setAttribute("aria-pressed", String(selected));
            }
        });
    }
}
