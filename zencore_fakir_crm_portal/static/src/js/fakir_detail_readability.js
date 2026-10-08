/** @odoo-module **/
// Scoped progressive enhancement: preserve the underlying native selects and form payload.
const PAGE = '.fpm-crm-detail-page';

function enhanceSelect(select) {
    if (select.dataset.fakirReadableReady) return;
    select.dataset.fakirReadableReady = '1';
    const wrapper = document.createElement('div');
    wrapper.className = 'fakir-readable-select';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'fakir-readable-trigger';
    button.setAttribute('aria-expanded', 'false');
    const chips = document.createElement('span');
    chips.className = 'fakir-readable-chips';
    const chevron = document.createElement('span');
    chevron.className = 'fakir-readable-chevron';
    chevron.textContent = '▾';
    button.append(chips, chevron);
    const panel = document.createElement('div');
    panel.className = 'fakir-readable-options';
    panel.hidden = true;
    wrapper.append(button, panel);
    select.parentNode.insertBefore(wrapper, select);
    wrapper.append(select);
    select.classList.add('fakir-readable-native');

    const options = [...select.options].filter(option => option.value && !option.disabled);
    const refresh = () => {
        chips.replaceChildren();
        const selected = options.filter(option => option.selected);
        if (!selected.length) {
            const placeholder = document.createElement('span');
            placeholder.className = 'fakir-readable-placeholder';
            placeholder.textContent = select.classList.contains('fpm-product-taxes') ? 'Select taxes' : 'Select tags';
            chips.append(placeholder);
        }
        for (const option of selected) {
            const chip = document.createElement('span');
            chip.className = 'fakir-readable-chip';
            chip.textContent = option.textContent.trim();
            chips.append(chip);
        }
        for (const input of panel.querySelectorAll('input[type="checkbox"]')) {
            const option = options.find(opt => opt.value === input.value);
            input.checked = !!option?.selected;
        }
    };
    for (const option of options) {
        const label = document.createElement('label');
        label.className = 'fakir-readable-option';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = option.value;
        input.checked = option.selected;
        const text = document.createElement('span');
        text.textContent = option.textContent.trim();
        input.addEventListener('change', () => {
            option.selected = input.checked;
            select.dispatchEvent(new Event('change', { bubbles: true }));
            refresh();
        });
        label.append(input, text);
        panel.append(label);
    }
    const close = () => {
        panel.hidden = true;
        button.setAttribute('aria-expanded', 'false');
    };
    button.addEventListener('click', () => {
        const open = panel.hidden;
        document.querySelectorAll(`${PAGE} .fakir-readable-options`).forEach(other => { other.hidden = true; });
        document.querySelectorAll(`${PAGE} .fakir-readable-trigger`).forEach(other => { other.setAttribute('aria-expanded', 'false'); });
        panel.hidden = !open;
        button.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', event => { if (!wrapper.contains(event.target)) close(); });
    select.addEventListener('change', refresh);
    refresh();
}

function setup(page) {
    if (page.dataset.fakirReadabilityReady) return;
    page.dataset.fakirReadabilityReady = '1';
    const init = () => page.querySelectorAll('.fpm-crm-tag-select, .fpm-product-row .fpm-product-taxes').forEach(enhanceSelect);
    init();
    // Product default taxes are set by the existing editor; refresh the chip UI after selection.
    page.addEventListener('change', event => {
        if (event.target.matches('.fpm-product-select')) {
            const tax = event.target.closest('tr.fpm-product-row')?.querySelector('.fpm-product-taxes');
            tax?.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    // Rows added by the existing inline-products script require the same enhancement.
    const rows = page.querySelector('.fpm-product-rows');
    if (rows) {
        const observer = new MutationObserver(records => {
            if (records.some(record => [...record.addedNodes].some(node => node.nodeType === 1 && (node.matches?.('tr.fpm-product-row') || node.querySelector?.('tr.fpm-product-row'))))) init();
        });
        observer.observe(rows, { childList: true });
    }
}
function boot() { document.querySelectorAll(PAGE).forEach(setup); }
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
