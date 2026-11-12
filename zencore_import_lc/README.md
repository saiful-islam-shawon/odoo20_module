# Import LC

Odoo 19 Import LC with company-safe document linking and approval controls.

- Technical name: `zencore_import_lc`
- Author: Mehedi Hasan
- Website: https://www.zencoreltd.com

## Highlights

- LC Order → Import LC → Commercial Invoice traceability
- deterministic PI/PO/GRN/MRP document linking
- company-scoped access rules
- dedicated LC Approver group with server-side transition checks
- LC/CI number uniqueness per company
- amendment support for quantity, conversion rate and shipment dates
- Odoo 19 list-view/action compatibility
- polished backend forms and branded application icon

See the package-level `README.md` for upgrade instructions.

### 19.0.3.0.2 single-PI LC update

- Import LC now supports exactly one approved Proforma Invoice (PI).
- Removed multi-PI selection, bundle validation, combined PI product loading and multi-PI CI selection behavior.
- Commercial Invoices inherit the LC's PI automatically; users no longer choose a PI separately.
- LC logistics, RFQ/PO linkage, GRN lookup and traceability are based on the single selected PI.
- The old `lc_order_ids` relation remains hidden only for upgrade compatibility and is synchronized to the single `lc_order_id`.

### 19.0.3.0.3 LC other-charge → landed-cost update

- Restores creation of miscellaneous Other Charge journal entries directly from an Import LC.
- Adds an LC Journal Entry selector to Landed Costs, limited to journal entries linked to the same LC/company.
- Adds debit Journal Item selection on landed-cost cost lines. Only selected debit items are capitalized; unselected LC charges remain normal expenses.
- Journal Item debit automatically supplies the landed-cost amount for UI, import and RPC creation/write paths.
- Preserves manually selected `account.move.import_lc_id` values while keeping existing CI/ref auto-link behavior.

### 19.0.3.0.4 LC workflow dependency update

- Tracks bill payment/state changes through the real CI-to-bill relation and receipt changes through the stored PO-to-picking relation, removing the non-searchable computed-relation dependency warnings.
- Refreshes related bill/receipt collections when their membership filters change, including cancellations and receipt operation types. LC closure still requires completed receipts and fully paid vendor bills.

### 19.0.3.0.5 LC invoice-rate dependency update

- Explicitly defers invoice currency-rate computation because the computed Import LC link is not precomputed. This matches the ORM's existing fallback and removes the invoice-rate precomputation warning without changing the LC exchange-rate calculation.
- Includes the receipt/bill dependency fixes from 19.0.3.0.4. After deployment, check the current build's fresh log; an earlier build's log retains the warnings emitted by its older code.
