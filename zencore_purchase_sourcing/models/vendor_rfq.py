from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ZCVendorRFQ(models.Model):
    _name = "zc.vendor.rfq"
    _description = "Vendor RFQ"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="RFQ No.",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )
    requisition_id = fields.Many2one(
        "zc.purchase.requisition",
        string="Requisition",
        required=True,
        ondelete="cascade",
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        required=True,
        domain="[('supplier_rank', '>', 0)]",
        tracking=True,
    )
    quotation_reference = fields.Char(string="Vendor Quotation Ref.", tracking=True)
    quotation_date = fields.Date(
        string="Quotation Date", default=fields.Date.context_today, tracking=True
    )
    company_id = fields.Many2one(
        related="requisition_id.company_id", string="Company", store=True, readonly=True
    )
    currency_id = fields.Many2one(
        related="requisition_id.currency_id",
        string="Currency",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("received", "Received"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        "zc.vendor.rfq.line", "rfq_id", string="Quotation Lines", copy=True
    )
    terms_and_conditions = fields.Html(
        string="Terms and Conditions",
        tracking=True,
        help="Vendor quotation terms and conditions kept as a sourcing reference.",
    )
    is_locked = fields.Boolean(
        string="Locked",
        compute="_compute_is_locked",
        help="RFQ is locked once any purchase order has been generated for its requisition.",
    )

    @api.depends("requisition_id.purchase_order_ids")
    def _compute_is_locked(self):
        for rfq in self:
            rfq.is_locked = bool(rfq.requisition_id.purchase_order_ids)

    def write(self, vals):
        target_state = vals.get("state")
        if target_state in ("draft", "cancelled"):
            locked = self.filtered(
                lambda rfq: rfq.requisition_id.purchase_order_ids
                and rfq.state != target_state
            )
            if locked:
                raise UserError(
                    _("Vendor RFQs are locked after a purchase order has been generated for the requisition.")
                )
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "zc.vendor.rfq"
                ) or _("New")
        records = super().create(vals_list)
        records.mapped("requisition_id").filtered(
            lambda r: r.state == "confirmed"
        ).write({"state": "sourcing"})
        return records

    def action_mark_received(self):
        for rfq in self:
            if not rfq.line_ids:
                raise UserError(_("The RFQ has no quotation lines."))
            incomplete = rfq.line_ids.filtered(
                lambda line: not line.quality or line.price_unit <= 0 or not line.delivery_date
            )
            if incomplete:
                raise UserError(
                    _("Complete Price, Quality and Delivery Date for every RFQ line first.")
                )
            rfq.state = "received"
        return True

    def action_set_draft(self):
        for rfq in self:
            if rfq.requisition_id.purchase_order_ids:
                raise UserError(
                    _("Vendor RFQs are locked after a purchase order has been generated for the requisition.")
                )
            if rfq.line_ids.filtered(lambda l: l.purchase_order_line_id):
                raise UserError(_("An RFQ used in a purchase order cannot be reset to draft."))
            selected_req_lines = rfq.line_ids.filtered(
                lambda l: l.decision == "recommended"
            ).mapped("requisition_line_id")
            if selected_req_lines:
                siblings = self.env["zc.vendor.rfq.line"].search([
                    ("requisition_line_id", "in", selected_req_lines.ids),
                    ("rfq_id", "!=", rfq.id),
                    ("rfq_id.state", "=", "received"),
                    ("purchase_order_line_id", "=", False),
                ])
                siblings.with_context(zc_skip_decision_logic=True).write(
                    {"decision": "pending"}
                )
            rfq.line_ids.with_context(zc_skip_decision_logic=True).write(
                {"decision": "pending"}
            )
            rfq.state = "draft"
        return True

    def action_cancel(self):
        for rfq in self:
            if rfq.requisition_id.purchase_order_ids:
                raise UserError(
                    _("Vendor RFQs are locked after a purchase order has been generated for the requisition.")
                )
            if rfq.line_ids.filtered(lambda l: l.purchase_order_line_id):
                raise UserError(_("An RFQ used in a purchase order cannot be cancelled."))
            selected_req_lines = rfq.line_ids.filtered(
                lambda l: l.decision == "recommended"
            ).mapped("requisition_line_id")
            if selected_req_lines:
                siblings = self.env["zc.vendor.rfq.line"].search([
                    ("requisition_line_id", "in", selected_req_lines.ids),
                    ("rfq_id", "!=", rfq.id),
                    ("rfq_id.state", "=", "received"),
                    ("purchase_order_line_id", "=", False),
                ])
                siblings.with_context(zc_skip_decision_logic=True).write(
                    {"decision": "pending"}
                )
            rfq.line_ids.with_context(zc_skip_decision_logic=True).write(
                {"decision": "cancelled"}
            )
            rfq.state = "cancelled"
        return True


class ZCVendorRFQLine(models.Model):
    _name = "zc.vendor.rfq.line"
    _description = "Vendor RFQ Line"
    _order = "requisition_line_id, partner_id, id"

    rfq_id = fields.Many2one(
        "zc.vendor.rfq", string="RFQ", required=True, ondelete="cascade", index=True
    )
    requisition_id = fields.Many2one(
        related="rfq_id.requisition_id", string="Requisition", store=True, index=True
    )
    requisition_line_id = fields.Many2one(
        "zc.purchase.requisition.line",
        string="Requisition Line",
        required=True,
        ondelete="restrict",
        index=True,
    )
    product_id = fields.Many2one(
        related="requisition_line_id.product_id", string="Product", store=True, readonly=True
    )
    quantity = fields.Float(
        related="requisition_line_id.quantity", string="Quantity", store=True, readonly=True
    )
    product_uom_id = fields.Many2one(
        related="requisition_line_id.product_uom_id",
        string="Unit",
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="rfq_id.partner_id", string="Vendor", store=True, readonly=True, index=True
    )
    company_id = fields.Many2one(related="rfq_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(
        related="rfq_id.currency_id", string="Currency", store=True, readonly=True
    )
    price_unit = fields.Monetary(
        string="Unit Price", currency_field="currency_id", required=True, default=0.0
    )
    quality = fields.Selection(
        [("good", "Good"), ("average", "Average"), ("poor", "Poor")],
        string="Quality",
        required=False,
    )
    delivery_date = fields.Date(
        string="Delivery Date",
        help="Vendor committed delivery date for this quoted product.",
    )
    # Kept only for upgrade compatibility with versions <= 19.0.1.0.2.
    # It is no longer displayed or used by the sourcing workflow.
    delivery_time = fields.Integer(
        string="Legacy Delivery Time (Days)",
        default=0,
        help="Legacy field retained so existing databases can migrate Delivery Days to Delivery Date.",
    )
    decision = fields.Selection(
        [
            ("pending", "Pending"),
            ("recommended", "Recommended"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Decision",
        default="pending",
        required=True,
        copy=False,
        index=True,
    )
    purchase_order_line_id = fields.Many2one(
        "purchase.order.line",
        string="Purchase Order Line",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    _sql_constraints = [
        ("price_non_negative", "CHECK(price_unit >= 0)", "Unit price cannot be negative."),
        (
            "rfq_requisition_line_unique",
            "unique(rfq_id, requisition_line_id)",
            "The same requisition line cannot appear twice in one RFQ.",
        ),
    ]

    @api.constrains("requisition_line_id", "rfq_id")
    def _check_same_requisition(self):
        for line in self:
            if (
                line.requisition_line_id
                and line.rfq_id
                and line.requisition_line_id.requisition_id != line.rfq_id.requisition_id
            ):
                raise ValidationError(
                    _("An RFQ can only contain lines from its own requisition.")
                )

    @api.constrains("decision", "requisition_line_id")
    def _check_single_recommendation(self):
        for line in self.filtered(lambda l: l.decision == "recommended"):
            count = self.search_count(
                [
                    ("requisition_line_id", "=", line.requisition_line_id.id),
                    ("decision", "=", "recommended"),
                ]
            )
            if count > 1:
                raise ValidationError(
                    _("Only one vendor can be recommended for the same requisition line.")
                )

    def write(self, vals):
        if self.env.context.get("zc_skip_decision_logic") or "decision" not in vals:
            return super().write(vals)

        new_decision = vals.get("decision")
        if new_decision == "recommended" and len(self) > 1:
            line_ids = self.mapped("requisition_line_id").ids
            if len(line_ids) != len(set(line_ids)):
                raise ValidationError(
                    _("Recommend vendors one requisition line at a time.")
                )

        for line in self:
            if line.purchase_order_line_id and new_decision != line.decision:
                raise UserError(
                    _("The decision cannot be changed after a purchase order has been generated.")
                )
            if new_decision == "recommended":
                if line.rfq_id.state != "received":
                    raise UserError(_("Only received RFQs can be recommended."))
                siblings = self.search(
                    [
                        ("requisition_line_id", "=", line.requisition_line_id.id),
                        ("id", "!=", line.id),
                    ]
                )
                locked = siblings.filtered(lambda l: l.purchase_order_line_id)
                if locked:
                    raise UserError(
                        _("Another vendor for this requisition line is already used in a purchase order.")
                    )
                siblings.with_context(zc_skip_decision_logic=True).write(
                    {"decision": "cancelled"}
                )

        return super().write(vals)

    def action_recommend(self):
        self.ensure_one()
        self.write({"decision": "recommended"})
        return True

    def action_reject(self):
        self.ensure_one()
        self.write({"decision": "rejected"})
        return True

    def action_cancel_decision(self):
        self.ensure_one()
        self.write({"decision": "cancelled"})
        return True

    def action_reset_decision(self):
        self.ensure_one()
        self.write({"decision": "pending"})
        return True
