/** @odoo-module **/

function initFakirCRM() {
    const alert = document.querySelector('#fakir-crm-created-alert');
    if (alert) {
        window.setTimeout(() => {
            if (alert.isConnected) {
                const bsAlert = window.bootstrap?.Alert?.getOrCreateInstance(alert);
                if (bsAlert) bsAlert.close();
                else alert.remove();
            }
        }, 5000);
    }
    const contact = document.querySelector('#crm_partner_select');
    const list = document.querySelector('#fakir_crm_partner_options');
    if (contact && list) {
        const sync = () => {
            const option = [...list.options].find((item) => item.value === contact.value);
            document.querySelector('#crm_partner_id').value = option?.dataset.id || '';
            if (!option) return;
            const ids = {name: '#crm_contact_name', email: '#crm_email', phone: '#crm_phone', company: '#crm_partner_name', function: '#crm_function', street: '#crm_street', city: '#crm_city', zip: '#crm_zip'};
            for (const [key, selector] of Object.entries(ids)) {
                const input = document.querySelector(selector);
                if (input) {input.value = option.dataset[key] || ''; input.dispatchEvent(new Event('change', {bubbles:true}));}
            }
        };
        contact.addEventListener('change', sync);
        contact.addEventListener('input', () => { document.querySelector('#crm_partner_id').value = ''; });
    }
    const form = document.querySelector('#crm_opportunity_form');
    if (form) {
        form.addEventListener('submit', (event) => {
            if (!form.checkValidity()) {
                const field = form.querySelector(':invalid');
                const pane = field?.closest('.tab-pane');
                if (pane && !pane.classList.contains('active')) {
                    const trigger = document.querySelector(`[data-bs-target="#${pane.id}"]`);
                    if (trigger) window.bootstrap?.Tab?.getOrCreateInstance(trigger)?.show();
                }
                event.preventDefault(); form.reportValidity(); return;
            }
            const button = form.querySelector('[type="submit"]');
            if (button) {button.disabled = true; button.textContent = 'Submitting...';}
        });
    }
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initFakirCRM);
else initFakirCRM();
