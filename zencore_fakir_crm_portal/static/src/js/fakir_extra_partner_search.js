/** @odoo-module **/
// Progressive enhancement for Extra Info & Assigned Partner select fields.
// Keep original select names/values so existing controller Save remains unchanged.
const rootSelector = '.fpm-crm-detail-page .fakir-extra-standard, .fpm-crm-detail-page .fakir-odoo20-assigned';
function enhance(select) {
    if (select.dataset.fakirExtraSearchReady) return;
    select.dataset.fakirExtraSearchReady = '1';
    const container = document.createElement('div');
    container.className = 'fakir-extra-search-wrap';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'fakir-extra-search-trigger';
    trigger.setAttribute('aria-label', `Choose ${select.name.replaceAll('_', ' ')}`);
    trigger.setAttribute('aria-expanded', 'false');
    const label = document.createElement('span');
    label.className = 'fakir-extra-search-trigger-label';
    const arrow = document.createElement('span');
    arrow.textContent = '▾';
    trigger.append(label, arrow);
    const panel = document.createElement('div');
    panel.className = 'fakir-extra-search-panel';
    panel.hidden = true;
    const query = document.createElement('input');
    query.type = 'search';
    query.placeholder = 'Search...';
    query.className = 'fakir-extra-search-input';
    query.setAttribute('aria-label', 'Search options');
    const options = document.createElement('div');
    options.className = 'fakir-extra-search-options';
    panel.append(query, options);
    container.append(trigger, panel);
    select.before(container);
    container.prepend(select);
    select.classList.add('fakir-extra-native-select');
    function refresh() {
        label.textContent = select.selectedOptions[0]?.textContent.trim() || 'Select...';
        for (const button of options.querySelectorAll('button')) {
            button.setAttribute('aria-selected', String(button.dataset.value === select.value));
        }
    }
    function populate() {
        options.replaceChildren();
        const needle = query.value.trim().toLocaleLowerCase();
        let count = 0;
        for (const opt of select.options) {
            if (opt.disabled || opt.hidden) continue;
            const value = opt.textContent.trim();
            if (needle && !value.toLocaleLowerCase().includes(needle)) continue;
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'fakir-extra-search-option';
            item.textContent = value;
            item.dataset.value = opt.value;
            item.setAttribute('role', 'option');
            item.addEventListener('click', () => {
                select.value = opt.value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
                refresh();
                close();
                trigger.focus();
            });
            options.append(item);
            count++;
        }
        if (!count) {
            const empty = document.createElement('div');
            empty.className = 'fakir-extra-search-empty';
            empty.textContent = 'No matching records';
            options.append(empty);
        }
        refresh();
    }
    function close() { panel.hidden = true; trigger.setAttribute('aria-expanded', 'false'); }
    trigger.addEventListener('click', () => {
        const opening = panel.hidden;
        document.querySelectorAll('.fakir-extra-search-panel').forEach(other => { other.hidden = true; });
        document.querySelectorAll('.fakir-extra-search-trigger').forEach(other => other.setAttribute('aria-expanded', 'false'));
        panel.hidden = !opening;
        trigger.setAttribute('aria-expanded', String(opening));
        if (opening) { query.value = ''; populate(); query.focus(); }
    });
    query.addEventListener('input', populate);
    container.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });
    document.addEventListener('click', (event) => { if (!container.contains(event.target)) close(); });
    select.addEventListener('change', () => { refresh(); if (!panel.hidden) populate(); });
    populate();
}
function start() { document.querySelectorAll(rootSelector).forEach(root => root.querySelectorAll('.fakir-extra-field select.form-select').forEach(enhance)); }
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
else start();
