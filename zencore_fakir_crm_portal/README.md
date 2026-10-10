# Zencore Fakir CRM Portal (Odoo 20)

Portal views for CRM opportunities, including opportunity creation, editing, product lines, activities, and chatter.

## Project layout

| Directory | Responsibility |
| --- | --- |
| `models/` | CRM opportunity and product model extensions |
| `controllers/portal.py` | Portal listing, detail, updates, and activity endpoints |
| `controllers/fakir_reference_crm.py` | Website CRM creation flow and supporting routes |
| `views/` | Backend form extensions, website navigation, and portal QWeb pages |
| `static/src/interactions/` | Website create-opportunity interactions |
| `static/src/js/` | Portal detail, product-line, chatter, search, and other interactions |
| `static/src/scss/` | Page-level styles and component refinements |
| `security/` | Security groups and model permissions |
| `wizard/` | CRM email wizard |

## Editing guidelines

- Preserve existing XML IDs, controller routes, and technical field names. Installed Odoo databases can depend on them.
- Keep UI behavior scoped to the relevant page; avoid global JavaScript event listeners or unscoped SCSS.
- When adding an asset, register it in `__manifest__.py` under the correct bundle.
- Portal endpoints must check record access before reading or updating CRM data.
- Verify changes on an Odoo 20 test database, especially chatter/activity permissions and asset compilation.

## Developer smoke test

1. Install or upgrade the module on a **test** database.
2. Open My Account → Opportunities and test search, column visibility, and record links.
3. Open an opportunity and test Save, stage changes, Products, Extra Info, and Assigned Partner.
4. Post a message, log a note, create/complete an activity, and check backend/portal consistency.
5. Check JavaScript console and frontend asset compilation for errors.

This cleanup intentionally leaves existing feature logic and technical identifiers unchanged.
