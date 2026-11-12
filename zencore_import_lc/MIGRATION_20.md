# Import LC — Odoo 20.0 compatibility update

## Scope

Technical conversion from **Odoo 19.0.3.0.5** to **Odoo 20.0.3.0.7**. Existing technical models, fields, XML IDs, user groups, data, approval steps, bank/PI/LC/CI flows, posting logic and landed-cost selection are preserved.

### Odoo 20 bank-model compatibility (installation fix)

Odoo 20 **removed `res.bank`** and keeps native bank and account details on `res.partner.bank`. The Import LC workflow, however, uses *bank institutions*, not individual bank-account numbers. Therefore we restore a small, self-contained `res.bank` master **inside this module**, compatible with the original five LC field declarations. The fields and values passed RFQ → PI → LC remain unchanged.

A **Banks** configuration page is available under **Import LC → Configuration → Banks**. Users can read these banks; Purchase Managers and Settings Administrators can maintain them. Create LC bank records there before selecting a required issuing/applicant bank. This register is **separate from Odoo 20 native bank accounts**; it does not populate or link to `res.partner.bank` automatically. On an upgraded database, verify that existing bank records were retained as part of the migration.

### Technical changes

1. Updated the module's Odoo version and descriptive text.
2. Converted `security/ir.model.access.csv` to `security/ir.access.csv` (Odoo 20 unified `ir.access` model). All **33** previous ACL permissions retain their XML IDs and CRUD settings. All **11** former global record rules retain their XML IDs and become global, group-less restrictions with `operation=crud` and the exact same company domain, `[('company_id', 'in', company_ids)]`.
3. Removed old `ir.rule` records from `lc_security.xml`; group/category definitions remain unchanged.
4. Updated the commercial-invoice product-line display-name hook from `name_get` to `_compute_display_name`, keeping the exact label text.
5. Replaced legacy Font Awesome classes/button icon strings with Odoo 20 Material Symbols equivalents.
6. Removed an unused `pytz` import (Odoo 20 uses `zoneinfo`).

The business flow and existing bank field comodels remain unchanged; only the local standalone bank registry/configuration page needed to be restored after Odoo 20 removed the native one.

## Installation and upgrading

- Use **Odoo 20 Enterprise** (the dependency `accountant` is retained from the supplied module), with the other modules listed in `__manifest__.py` installed and available.
- Back up the Odoo 19 database and filestore before a real database upgrade. Run the normal Odoo 19→20 database upgrade procedure; installing an Odoo 20 module ZIP does **not** migrate the database.
- Install the ZIP's `zencore_import_lc/` directory in your Odoo 20 `addons_path`, refresh the Apps list, then install/upgrade `zencore_import_lc`.
- For a previously installed 19.0 module, ensure Odoo's database upgrade has also migrated previously stored ACL and record-rule records to `ir.access` before updating this module.
- Execute the included `tests/test_contracts.py` with `--test-enable` on a disposable database. Verify a purchase RFQ → PI → Import LC → CI → vendor bill → receipt/GRN → landed cost end-to-end, as well as approver/nonapprover and multi-company isolation.

## Verification limits

The package was validated with Python source compilation, XML well-formedness, Odoo 20 access-format/ID/operation assertions, legacy API scans and ZIP integrity checks. **A live Odoo 20 Enterprise server/database was not available in this environment**, so runtime installation, upstream view-inheritance anchors, Odoo 20 enterprise internals and end-to-end workflows need to be verified in your actual Odoo 20 instance.

### v20.0.3.0.7: PO, GRN and manufacturing UoM migration fixes

The Odoo 20 purchase-line API renamed `purchase.order.line.product_uom_id` to
`purchase.order.line.uom_id`. Two independent paths used the old source field:

- the **Create Proforma Invoice** action on an import RFQ/PO; and
- the **PO Number** onchange in the PI form, including the PI create/write fallbacks.

Both paths now read `po_line.uom_id` (with the same product default fallback),
while continuing to write to **the module's own** `lc.order.line.product_uom_id`.
The old custom PI field is intentionally *not* renamed, preserving data and
subsequent LC/CI mappings. `account.move.line.product_uom_id` also remains valid
in Odoo 20 and is intentionally unchanged.

Related Odoo 20 core-field changes were also applied to both document-traceability
builders: `mrp.production.product_uom_id` → `uom_id`, `stock.move.product_uom`
→ `uom_id`, and the previously removed `stock.picking.move_ids_without_package`
→ `move_ids`. The GRN product counts and quantities otherwise behave as before.

An automated `test_odoo20_purchase_line_uom_to_pi_mapping` regression test now
covers PO-to-PI mapping through both user actions (including `onchange`) and
`test_odoo20_related_stock_and_mrp_uom_fields` checks the exposed upstream
field contracts. Neither test has been executed on a live Odoo server here.

After deploying this release to an existing Odoo 20 database, use **Apps →
Upgrade** for `zencore_import_lc` (not a second copy of the addon). On a test
instance verify RFQ selection → PI line loading, creation from RFQ, LC and CI
line UoMs, vendor-bill line UoMs, and GRN/manufacturing document traceability.
