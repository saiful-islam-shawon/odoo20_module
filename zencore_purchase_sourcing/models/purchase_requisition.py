from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ZCPurchaseRequisition(models.Model):
    _name = "zc.purchase.requisition"
    _description = "Purchase Requisition"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Requisition No.",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )
    approval_request_id = fields.Many2one(
        "approval.request",
        string="Approval Request",
        copy=False,
        ondelete="set null",
        tracking=True,
    )
    requested_by = fields.Many2one(
        "res.users",
        string="Requested By",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    request_date = fields.Date(
        string="Request Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Comparison Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        help="All vendor RFQ prices under this requisition are compared in this currency.",
    )
    purpose = fields.Text(string="Purpose / Notes")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("sourcing", "Sourcing"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )

    line_ids = fields.One2many(
        "zc.purchase.requisition.line",
        "requisition_id",
        string="Products",
        copy=True,
    )
    rfq_ids = fields.One2many(
        "zc.vendor.rfq",
        "requisition_id",
        string="Vendor RFQs",
        copy=False,
    )
    purchase_order_ids = fields.One2many(
        "purchase.order",
        "zc_requisition_id",
        string="Purchase Orders",
        copy=False,
    )
    comparison_ids = fields.One2many(
        "zc.rfq.comparison",
        "requisition_id",
        string="RFQ Comparisons",
        copy=False,
    )

    rfq_count = fields.Integer(compute="_compute_counts")
    received_rfq_count = fields.Integer(compute="_compute_counts")
    purchase_order_count = fields.Integer(compute="_compute_counts")
    comparison_count = fields.Integer(compute="_compute_counts")
    recommended_line_count = fields.Integer(compute="_compute_counts")
    unprocessed_recommended_line_count = fields.Integer(compute="_compute_counts")
    comparison_sheet_ready = fields.Boolean(
        string="Comparison Sheet Ready",
        compute="_compute_comparison_sheet_ready",
        help="True when every requisition product has one recommended vendor in the RFQ comparison.",
    )

    _sql_constraints = [
        (
            "approval_request_unique",
            "unique(approval_request_id)",
            "An approval request can be linked to only one purchase requisition.",
        ),
    ]

    @api.depends(
        "rfq_ids",
        "rfq_ids.state",
        "purchase_order_ids",
        "comparison_ids",
        "rfq_ids.line_ids.decision",
        "rfq_ids.line_ids.purchase_order_line_id",
    )
    def _compute_counts(self):
        for requisition in self:
            requisition.rfq_count = len(requisition.rfq_ids)
            requisition.received_rfq_count = len(
                requisition.rfq_ids.filtered(lambda r: r.state == "received")
            )
            requisition.purchase_order_count = len(requisition.purchase_order_ids)
            requisition.comparison_count = len(requisition.comparison_ids)
            recommended_lines = requisition.rfq_ids.line_ids.filtered(
                lambda l: l.decision == "recommended"
            )
            requisition.recommended_line_count = len(recommended_lines)
            requisition.unprocessed_recommended_line_count = len(
                recommended_lines.filtered(lambda l: not l.purchase_order_line_id)
            )


    @api.depends(
        "comparison_ids",
        "line_ids",
        "rfq_ids.state",
        "rfq_ids.line_ids.decision",
        "rfq_ids.line_ids.requisition_line_id",
    )
    def _compute_comparison_sheet_ready(self):
        for requisition in self:
            received_lines = requisition.rfq_ids.filtered(
                lambda rfq: rfq.state == "received"
            ).line_ids
            recommended_req_line_ids = set(
                received_lines.filtered(
                    lambda line: line.decision == "recommended"
                ).mapped("requisition_line_id").ids
            )
            requisition.comparison_sheet_ready = bool(
                requisition.comparison_ids
                and requisition.line_ids
                and all(
                    line.id in recommended_req_line_ids
                    for line in requisition.line_ids
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "zc.purchase.requisition"
                ) or _("New")
        return super().create(vals_list)

    def action_confirm(self):
        for requisition in self:
            if not requisition.line_ids:
                raise UserError(_("Add at least one product before confirming the requisition."))
            requisition.state = "confirmed"
        return True

    def action_set_draft(self):
        raise UserError(
            _(
                "Purchase requisitions are controlled by the Approvals workflow and "
                "cannot be reset to draft from CS."
            )
        )

    def action_cancel(self):
        for requisition in self:
            if requisition.purchase_order_ids.filtered(lambda po: po.state not in ("cancel",)):
                raise UserError(_("Cancel linked purchase orders before cancelling this requisition."))
            requisition.state = "cancelled"
        return True

    def action_create_rfq(self):
        self.ensure_one()
        if self.state not in ("confirmed", "sourcing"):
            raise UserError(_("Confirm the requisition before creating vendor RFQs."))
        if not self.line_ids:
            raise UserError(_("This requisition has no product lines."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Vendor RFQ"),
            "res_model": "zc.rfq.create.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_requisition_id": self.id},
        }

    def action_view_rfqs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "zencore_purchase_sourcing.action_zc_vendor_rfq"
        )
        action["domain"] = [("requisition_id", "=", self.id)]
        action["context"] = {"default_requisition_id": self.id}
        return action

    def action_compare_rfqs(self):
        self.ensure_one()
        received = self.rfq_ids.filtered(lambda r: r.state == "received")
        if len(received) < 2:
            raise UserError(_("At least two received RFQs are required for comparison."))

        comparison = self.comparison_ids[:1]
        if not comparison:
            comparison = self.env["zc.rfq.comparison"].create(
                {"requisition_id": self.id}
            )
        comparison._sync_received_lines()
        return comparison.action_open_lines()

    def action_view_comparisons(self):
        self.ensure_one()
        comparisons = self.comparison_ids
        if not comparisons:
            raise UserError(_("No RFQ comparison record exists for this requisition yet."))

        action = self.env["ir.actions.actions"]._for_xml_id(
            "zencore_purchase_sourcing.action_zc_rfq_comparison"
        )
        action["domain"] = [("requisition_id", "=", self.id)]
        action["context"] = {"create": False}
        if len(comparisons) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "views": [
                        (
                            self.env.ref(
                                "zencore_purchase_sourcing.view_zc_rfq_comparison_form"
                            ).id,
                            "form",
                        )
                    ],
                    "res_id": comparisons.id,
                }
            )
        return action


    def action_print_comparison_sheet(self):
        self.ensure_one()
        if not self.comparison_ids:
            raise UserError(_("Create the RFQ comparison before printing the Comparison Sheet."))
        comparison = self.comparison_ids[:1]
        comparison._sync_received_lines()
        if not self.comparison_sheet_ready:
            raise UserError(
                _(
                    "Complete the comparison first. Each requisition product must have one recommended vendor before the Comparison Sheet can be printed."
                )
            )
        return self.env.ref(
            "zencore_purchase_sourcing.action_report_zc_comparison_sheet"
        ).report_action(self)

    def action_view_purchase_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("purchase.purchase_rfq")
        action["domain"] = [("zc_requisition_id", "=", self.id)]
        action["context"] = {"create": False}
        return action

    def action_create_purchase_orders(self):
        self.ensure_one()
        if self.state == "cancelled":
            raise UserError(_("Purchase orders cannot be created from a cancelled requisition."))

        selected_lines = self.rfq_ids.line_ids.filtered(
            lambda l: l.decision == "recommended" and not l.purchase_order_line_id
        )
        if not selected_lines:
            raise UserError(_("There are no new recommended RFQ lines to purchase."))

        # Safety: a requisition line can have only one recommended vendor.
        duplicates = defaultdict(int)
        for line in selected_lines:
            duplicates[line.requisition_line_id.id] += 1
        if any(count > 1 for count in duplicates.values()):
            raise ValidationError(_("A requisition line cannot have more than one recommended vendor."))

        grouped = defaultdict(lambda: self.env["zc.vendor.rfq.line"])
        for line in selected_lines:
            grouped[line.partner_id.id] |= line

        created_orders = self.env["purchase.order"]
        for partner_id, lines in grouped.items():
            po_vals = {
                "partner_id": partner_id,
                "company_id": self.company_id.id,
                "currency_id": self.currency_id.id,
                "origin": self.name,
                "zc_requisition_id": self.id,
            }

            # Keep the selected vendor quotation terms as PO reference when
            # the installed Odoo Purchase model exposes the standard notes field.
            rfq_terms = [
                terms
                for terms in lines.mapped("rfq_id.terms_and_conditions")
                if terms
            ]
            if rfq_terms and "notes" in self.env["purchase.order"]._fields:
                po_vals["notes"] = "<hr/>".join(dict.fromkeys(rfq_terms))

            po = self.env["purchase.order"].create(po_vals)
            for line in lines:
                if not line.delivery_date:
                    raise UserError(
                        _("Set a Delivery Date for %s before creating the purchase order.", line.product_id.display_name)
                    )
                planned_date = fields.Datetime.to_datetime(line.delivery_date)
                po_line = self.env["purchase.order.line"].create(
                    {
                        "order_id": po.id,
                        "product_id": line.product_id.id,
                        "name": line.requisition_line_id.description
                        or line.product_id.display_name,
                        "product_qty": line.quantity,
                        "uom_id": line.product_uom_id.id,
                        "price_unit": line.price_unit,
                        "date_planned": planned_date,
                    }
                )
                line.purchase_order_line_id = po_line.id

            # The requisition has already passed the Approvals workflow, so a PO
            # generated from an approved recommendation should be a confirmed
            # Purchase Order immediately, not remain as an RFQ.
            po.button_confirm()
            if po.state == "to approve":
                # Respect Odoo's standard confirmation logic first, then complete
                # the PO approval because the sourcing requisition is already
                # fully approved upstream in Approvals.
                po.sudo().button_approve()

            if po.state != "purchase":
                raise UserError(
                    _(
                        "Purchase Order %s could not be confirmed automatically. Current state: %s",
                        po.display_name,
                        po.state,
                    )
                )

            created_orders |= po

        all_requisition_lines_ordered = all(
            self.rfq_ids.line_ids.filtered(
                lambda ql, rl=req_line: ql.requisition_line_id == rl
                and ql.decision == "recommended"
                and ql.purchase_order_line_id
            )
            for req_line in self.line_ids
        )
        self.state = "done" if all_requisition_lines_ordered else "sourcing"

        action = self.action_view_purchase_orders()
        if len(created_orders) == 1:
            action.update({"view_mode": "form", "res_id": created_orders.id})
        return action


class ZCPurchaseRequisitionLine(models.Model):
    _name = "zc.purchase.requisition.line"
    _description = "Purchase Requisition Line"
    _order = "sequence, id"

    @api.depends("product_id")
    def _compute_display_name(self):
        for line in self:
            line.display_name = line.product_id.display_name if line.product_id else _("Requisition Line")

    sequence = fields.Integer(default=10)
    requisition_id = fields.Many2one(
        "zc.purchase.requisition",
        string="Requisition",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="requisition_id.company_id", store=True)
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain="[('purchase_ok', '=', True)]",
    )
    description = fields.Text(string="Description")
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    allowed_uom_ids = fields.Many2many(
        "uom.uom",
        string="Allowed Units",
        compute="_compute_allowed_uom_ids",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit",
        required=True,
        domain="[('id', 'in', allowed_uom_ids)]",
        ondelete="restrict",
    )

    _sql_constraints = [
        ("quantity_positive", "CHECK(quantity > 0)", "Quantity must be greater than zero."),
    ]


    @api.depends("product_id", "product_id.uom_id", "product_id.uom_ids")
    def _compute_allowed_uom_ids(self):
        """Odoo 19 removed UoM categories.

        Requisition lines follow the same product-specific UoM approach used by
        Odoo 19 sale/purchase lines: the product's inventory UoM plus its
        configured additional packagings/UoMs.
        """
        for line in self:
            line.allowed_uom_ids = line.product_id.uom_id | line.product_id.uom_ids

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
                if not line.description:
                    line.description = line.product_id.display_name
