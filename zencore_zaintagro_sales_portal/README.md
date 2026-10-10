# Zencore Zaintagro Sales Portal

Odoo 20 website quotation creation module.

## Calculation policy

The portal does not implement its own pricing, tax, margin, or total formulas. Preview requests build one unsaved `sale.order` with all current `sale.order.line` values and read Odoo 20's native computed fields. `document_tax_mode` is order-level, each line keeps its own taxes, and totals come from the same transient order.

Editable line-only overrides (taxes, lead time, unit cost, margin/margin %, unit price) affect the quotation line only and do not mutate product master data.
