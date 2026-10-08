/** @odoo-module **/
// Portal-only refresh: actual DB counts for the displayed opportunity.
// Five-second polling, not an instantaneous Bus subscription.
const smart = document.querySelector('.fpm-crm-detail-page .fakir-odoo20-smart-buttons[data-opportunity-id]');
if (smart) {
    const id = Number(smart.dataset.opportunityId);
    let pending = false;
    const updateCounts = async () => {
        if (pending || document.hidden || !smart.isConnected || !id) return;
        pending = true;
        try {
            const response = await fetch(`/my/crm/opportunities/${id}/smart-counts`, {
                credentials: 'same-origin', cache: 'no-store', headers: {'Accept': 'application/json'},
            });
            if (!response.ok) return;
            const result = await response.json();
            const meetings = smart.querySelector('.fakir-live-meetings');
            const quotations = smart.querySelector('.fakir-live-quotations');
            if (meetings && Number.isFinite(Number(result.meetings))) {
                const count = Number(result.meetings);
                meetings.textContent = count ? `${count} Meeting(s)` : 'No Meeting';
            }
            if (quotations && Number.isFinite(Number(result.quotations))) {
                quotations.textContent = String(Number(result.quotations));
            }
        } catch (_) {
            // Retry on the next refresh; never interfere with editing or saving.
        } finally { pending = false; }
    };
    const interval = setInterval(updateCounts, 5000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) updateCounts(); });
    window.addEventListener('pagehide', () => clearInterval(interval), {once: true});
}
