/** @odoo-module **/
// Detail-page-scoped implementation; independent of the legacy publicWidget registry.
const rootSelector = '.fpm-crm-detail-page .fpm-product-editor';
function setupProducts(editor) {
    if (editor.dataset.fakirInlineReady) return;
    editor.dataset.fakirInlineReady = '1';
    const rows = editor.querySelector('.fpm-product-rows');
    const template = editor.querySelector('.fpm-product-row-template');
    if (!rows || !template) return;
    function taxList(row) { return row.querySelector('.fpm-product-taxes'); }
    function recompute() {
        let sum = 0;
        for (const row of rows.querySelectorAll('tr.fpm-product-row')) {
            const qty = Number(row.querySelector('.fpm-product-quantity')?.value || 0);
            const price = Number(row.querySelector('.fpm-product-price')?.value || 0);
            let amount = Math.max(0, qty) * Math.max(0, price);
            const tax = taxList(row);
            // UI preview for simple percent/fixed taxes; server remains authoritative.
            for (const option of tax?.selectedOptions || []) {
                const v = Number(option.dataset.amount || 0);
                if (option.dataset.amountType === 'percent') amount += qty * price * v / 100;
                if (option.dataset.amountType === 'fixed') amount += qty * v;
            }
            const cell = row.querySelector('.fpm-product-amount');
            if (cell) cell.textContent = amount.toFixed(2);
            sum += amount;
        }
        const total = editor.querySelector('.fpm-product-total');
        if (total) total.textContent = sum.toFixed(2);
    }
    editor.addEventListener('click', (ev) => {
        const add = ev.target.closest('.fakir-v20-add-line');
        if (add && editor.contains(add)) {
            ev.preventDefault();
            const fragment = template.content.cloneNode(true);
            rows.insertBefore(fragment, add.closest('tr'));
            const added = add.closest('tr').previousElementSibling;
            added?.querySelector('.fpm-product-select')?.focus();
            recompute();
            return;
        }
        const remove = ev.target.closest('.fpm-remove-product-row');
        if (remove && editor.contains(remove)) {
            ev.preventDefault();
            remove.closest('tr.fpm-product-row')?.remove();
            recompute();
        }
    });
    editor.addEventListener('change', (ev) => {
        const row = ev.target.closest('tr.fpm-product-row');
        if (!row) return;
        if (ev.target.matches('.fpm-product-select')) {
            const selected = ev.target.selectedOptions[0];
            const setInput = (name, value) => { const input = row.querySelector(name); if (input) input.value = value || ''; };
            setInput('.fpm-product-price', selected?.dataset.price || '0');
            setInput('.fpm-product-brand', selected?.dataset.brand);
            setInput('.fpm-product-group', selected?.dataset.group);
            setInput('.fpm-product-part-number', selected?.dataset.partNumber);
            const cat = row.querySelector('.fpm-product-category');
            if (cat) cat.textContent = selected?.dataset.category || '-';
            const defaultTaxes = (selected?.dataset.defaultTaxes || '').split(',');
            for (const option of taxList(row)?.options || []) option.selected = defaultTaxes.includes(option.value);
        }
        if (ev.target.matches('.fpm-product-taxes, .fpm-product-select')) {
            const tax = taxList(row);
            const hidden = row.querySelector('.fpm-product-tax-ids');
            if (hidden) hidden.value = [...(tax?.selectedOptions || [])].map(x => x.value).join(',');
        }
        recompute();
    });
    editor.addEventListener('input', (ev) => {
        if (ev.target.closest('tr.fpm-product-row')) recompute();
    });
    recompute();
}
function setupPriority(page) {
    if (page.dataset.fakirPriorityReady) return;
    page.dataset.fakirPriorityReady='1';
    const hidden = page.querySelector('.fakir-v20-priority-value');
    if (!hidden) return;
    const stars = [...page.querySelectorAll('.fakir-v20-star')];
    const refresh = () => stars.forEach((star) => {
        const selected = Number(star.dataset.star) <= Number(hidden.value);
        star.classList.toggle('is-active', selected);
        star.setAttribute('aria-pressed', String(selected));
    });
    for (const star of stars) star.addEventListener('click', () => {
        hidden.value = hidden.value === star.dataset.star ? '0' : star.dataset.star;
        refresh();
    });
    refresh();
}
function boot() {
    document.querySelectorAll(rootSelector).forEach(setupProducts);
    document.querySelectorAll('.fpm-crm-detail-page').forEach(setupPriority);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
