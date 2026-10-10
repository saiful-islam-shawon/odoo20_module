from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ZCRFQComparison(models.Model):
    _name = "zc.rfq.comparison"
    _description = "RFQ Comparison"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Comparison No.",
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
        readonly=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    comparison_date = fields.Datetime(
        string="Comparison Date",
        default=fields.Datetime.now,
        readonly=True,
        tracking=True,
    )
    created_by = fields.Many2one(
        "res.users",
        string="Compared By",
        default=lambda self: self.env.user,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="requisition_id.company_id",
        string="Company",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="requisition_id.currency_id",
        string="Currency",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [("open", "Open"), ("completed", "Completed")],
        string="Status",
        compute="_compute_state",
    )
    line_ids = fields.One2many(
        "zc.rfq.comparison.line",
        "comparison_id",
        string="Comparison Lines",
        copy=False,
    )
    line_count = fields.Integer(compute="_compute_line_count")

    _sql_constraints = [
        (
            "requisition_unique",
            "unique(requisition_id)",
            "Only one RFQ comparison record is allowed per requisition.",
        ),
    ]

    @api.depends(
        "requisition_id.line_ids",
        "requisition_id.rfq_ids.state",
        "requisition_id.rfq_ids.line_ids.decision",
        "requisition_id.rfq_ids.line_ids.requisition_line_id",
    )
    def _compute_state(self):
        for record in self:
            requisition = record.requisition_id
            received_lines = requisition.rfq_ids.filtered(
                lambda rfq: rfq.state == "received"
            ).line_ids
            recommended_req_line_ids = set(
                received_lines.filtered(
                    lambda line: line.decision == "recommended"
                ).mapped("requisition_line_id").ids
            )
            record.state = (
                "completed"
                if requisition.line_ids
                and all(
                    line.id in recommended_req_line_ids
                    for line in requisition.line_ids
                )
                else "open"
            )

    @api.depends("line_ids")
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "zc.rfq.comparison"
                ) or _("New")
        return super().create(vals_list)

    def _sync_received_lines(self):
        """Add newly received RFQ lines without deleting prior comparison history."""
        ComparisonLine = self.env["zc.rfq.comparison.line"]
        for comparison in self:
            received_lines = comparison.requisition_id.rfq_ids.filtered(
                lambda rfq: rfq.state == "received"
            ).line_ids
            existing_ids = set(comparison.line_ids.mapped("rfq_line_id").ids)
            vals_list = [
                {
                    "comparison_id": comparison.id,
                    "rfq_line_id": line.id,
                }
                for line in received_lines
                if line.id not in existing_ids
            ]
            if vals_list:
                ComparisonLine.create(vals_list)
        return True

    def action_open_lines(self):
        self.ensure_one()
        self._sync_received_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("RFQ Comparison - %s", self.requisition_id.name),
            "res_model": "zc.rfq.comparison.line",
            "view_mode": "list",
            "views": [
                (
                    self.env.ref(
                        "zencore_purchase_sourcing.view_zc_rfq_comparison_line_list"
                    ).id,
                    "list",
                )
            ],
            "domain": [
                ("comparison_id", "=", self.id),
                ("rfq_id.state", "=", "received"),
            ],
            "context": {
                "group_by": "requisition_line_id",
                "create": False,
                "delete": False,
            },
            "target": "current",
        }


class ZCRFQComparisonLine(models.Model):
    _name = "zc.rfq.comparison.line"
    _description = "RFQ Comparison Line"
    _order = "requisition_line_id, price_unit, id"

    comparison_id = fields.Many2one(
        "zc.rfq.comparison",
        string="Comparison",
        required=True,
        ondelete="cascade",
        index=True,
    )
    rfq_line_id = fields.Many2one(
        "zc.vendor.rfq.line",
        string="RFQ Line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    requisition_id = fields.Many2one(
        related="comparison_id.requisition_id",
        string="Requisition",
        store=True,
        readonly=True,
    )
    requisition_line_id = fields.Many2one(
        related="rfq_line_id.requisition_line_id",
        string="Product",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        related="rfq_line_id.product_id",
        string="Product",
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="rfq_line_id.partner_id",
        string="Vendor",
        store=True,
        readonly=True,
    )
    rfq_id = fields.Many2one(
        related="rfq_line_id.rfq_id",
        string="RFQ",
        store=True,
        readonly=True,
    )
    quantity = fields.Float(
        related="rfq_line_id.quantity",
        string="Quantity",
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        related="rfq_line_id.product_uom_id",
        string="Unit",
        readonly=True,
    )
    price_unit = fields.Monetary(
        related="rfq_line_id.price_unit",
        string="Unit Price",
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="rfq_line_id.currency_id",
        string="Currency",
        readonly=True,
    )
    quality = fields.Selection(
        related="rfq_line_id.quality",
        string="Quality",
        readonly=True,
    )
    delivery_date = fields.Date(
        related="rfq_line_id.delivery_date",
        string="Delivery Date",
        readonly=True,
    )
    decision = fields.Selection(
        related="rfq_line_id.decision",
        string="Decision",
        readonly=True,
    )
    purchase_order_line_id = fields.Many2one(
        related="rfq_line_id.purchase_order_line_id",
        string="Purchase Order Line",
        readonly=True,
    )
    remarks = fields.Text(
        string="Remarks",
        help="Line-by-line sourcing remarks entered during RFQ comparison.",
    )

    _sql_constraints = [
        (
            "comparison_rfq_line_unique",
            "unique(comparison_id, rfq_line_id)",
            "The same RFQ line can appear only once in a comparison.",
        ),
    ]

    @api.constrains("comparison_id", "rfq_line_id")
    def _check_same_requisition(self):
        for line in self:
            if (
                line.comparison_id
                and line.rfq_line_id
                and line.comparison_id.requisition_id != line.rfq_line_id.requisition_id
            ):
                raise ValidationError(
                    _("A comparison can only contain RFQ lines from its own requisition.")
                )

    def write(self, vals):
        old_remarks = {line.id: line.remarks for line in self} if "remarks" in vals else {}
        result = super().write(vals)
        if "remarks" in vals:
            for line in self:
                if old_remarks.get(line.id) != line.remarks:
                    line.comparison_id.message_post(
                        body=_(
                            "Remark updated for %(product)s / %(vendor)s: %(remark)s",
                            product=line.product_id.display_name,
                            vendor=line.partner_id.display_name,
                            remark=line.remarks or _("(cleared)"),
                        )
                    )
        return result

    def _post_decision_message(self, label):
        for line in self:
            line.comparison_id.message_post(
                body=_(
                    "%(decision)s: %(product)s / %(vendor)s%(remark)s",
                    decision=label,
                    product=line.product_id.display_name,
                    vendor=line.partner_id.display_name,
                    remark=(" — %s" % line.remarks) if line.remarks else "",
                )
            )

    def action_recommend(self):
        self.ensure_one()
        self.rfq_line_id.action_recommend()
        self._post_decision_message(_("Recommended"))
        return True

    def action_reject(self):
        self.ensure_one()
        self.rfq_line_id.action_reject()
        self._post_decision_message(_("Rejected"))
        return True

    def action_cancel_decision(self):
        self.ensure_one()
        self.rfq_line_id.action_cancel_decision()
        self._post_decision_message(_("Cancelled"))
        return True

    def action_reset_decision(self):
        self.ensure_one()
        self.rfq_line_id.action_reset_decision()
        self._post_decision_message(_("Reset to Pending"))
        return True
