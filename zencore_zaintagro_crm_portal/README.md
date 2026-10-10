# Zencore Zaintagro CRM Portal (Odoo 20)

## What it does
- Adds a website top menu named **CRM**.
- Menu/page are visible only to users with **Zaint Agro Portal / CRM Portal / Access** (or system administrators).
- Provides a custom Odoo-style opportunity creation form with Notes, Extra Info and Assigned Partner tabs.
- Searchable selectors for Contact, Salesperson, Tags, UTM values, Company, Sales Team and Assigned Partner.
- Creates a standard `crm.lead` with `type='opportunity'`.
- Supports Odoo standard predictive probability by leaving probability automatic, or manual probability when AI is switched off.
- Supports Odoo's standard partner auto-assignment after save.

## Security design
Portal users are not granted broad `crm.lead` ACLs. The controller checks the dedicated group on every page/search/create endpoint. Creation uses a narrowly scoped `sudo()` only after server-side field allowlisting and relational-ID validation. Existing contact email/phone are not modified through this form.

## Dependencies
`website`, `portal`, `crm`, `utm`, `website_crm_partner_assign`

## 20.0.1.6.0
- Uses Odoo's native `base_geolocalize` service when Automatic Assignment is clicked.
- Fills latitude/longitude before save and runs standard CRM partner assignment after opportunity creation.
- Adds Odoo-style scoped section separators for Extra Info and Assigned Partner tabs.
