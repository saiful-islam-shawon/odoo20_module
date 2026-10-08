from odoo import api, fields, models


class CrmLeadProduct(models.Model):
    _name = "crm.lead.product"
    _description = "CRM Lead Product"
    _order = "id"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Lead/Opportunity",
        required=True,
        ondelete="cascade",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product Name",
        required=True,
    )

    category_id = fields.Many2one(
        related="product_id.categ_id",
        string="Category",
        readonly=True,
    )

    brand = fields.Char(
        related="product_id.product_tmpl_id.brand",
        string="Brand",
        readonly=False,
    )

    product_group = fields.Char(
        related="product_id.product_tmpl_id.product_group",
        string="Product Group",
        readonly=False,
    )

    part_number = fields.Integer(
        related="product_id.product_tmpl_id.part_number",
        string="Part Number",
        readonly=False,
    )

    quantity = fields.Float(string="Quantity", default=1.0, required=True)

    price_unit = fields.Float(string="Unit Price", digits="Product Price", default=0.0)

    tax_ids = fields.Many2many(
        "account.tax",
        "crm_lead_product_tax_rel",
        "lead_product_id",
        "tax_id",
        string="Taxes",
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', parent.company_id)]",
    )

    currency_id = fields.Many2one(
        related="lead_id.company_id.currency_id",
        string="Currency",
        readonly=True,
    )

    amount_total = fields.Monetary(
        string="Amount",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )

    @api.depends("quantity", "price_unit", "tax_ids")
    def _compute_amount_total(self):
        for line in self:
            base = line.quantity * line.price_unit
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(
                    line.price_unit,
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.lead_id.partner_id,
                )
                line.amount_total = taxes["total_included"]
            else:
                line.amount_total = base

    @api.onchange("product_id")
    def _onchange_product_id_commercial(self):
        for line in self:
            if line.product_id:
                line.price_unit = line.product_id.lst_price
                line.tax_ids = line.product_id.taxes_id.filtered(
                    lambda tax: not line.lead_id.company_id or tax.company_id == line.lead_id.company_id
                )
