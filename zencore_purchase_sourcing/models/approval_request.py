from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    # Odoo 20 no longer provides approval.category.approval_type.
    # Preserve the existing requisition-identification value and behavior.
    approval_type = fields.Selection(
        selection=[("zc_requisition", "Requisition")],
        string="Approval Type",
    )


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    # Expose the category identifier to existing form-view conditions.
    approval_type = fields.Selection(
        related="category_id.approval_type",
        readonly=True,
    )

    zc_requisition_id = fields.Many2one(
        "zc.purchase.requisition",
        string="Purchase Requisition",
        copy=False,
        readonly=True,
    )

    def _zc_is_requisition_approval(self):
        self.ensure_one()
        return bool(
            self.category_id
            and "approval_type" in self.category_id._fields
            and self.category_id.approval_type == "zc_requisition"
        )

    def _zc_prepare_requisition_vals(self, auto_confirm=False):
        self.ensure_one()
        line_commands = []
        product_lines = self.product_line_ids if "product_line_ids" in self._fields else []
        for line in product_lines:
            product = getattr(line, "product_id", False)
            if not product:
                continue
            quantity = getattr(line, "quantity", 0.0) or 1.0
            description = getattr(line, "description", False) or product.display_name
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "description": description,
                        "quantity": quantity,
                        "product_uom_id": product.uom_id.id,
                    },
                )
            )

        if not line_commands:
            raise UserError(
                _(
                    "A Requisition approval must contain at least one product line before it can be fully approved."
                )
            )

        owner = getattr(self, "request_owner_id", False)
        company = getattr(self, "company_id", False) or self.env.company
        vals = {
            "approval_request_id": self.id,
            "requested_by": owner.id if owner else self.env.user.id,
            "request_date": fields.Date.context_today(self),
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "purpose": getattr(self, "reason", False) or self.name,
            "line_ids": line_commands,
        }
        if auto_confirm:
            vals["state"] = "confirmed"
        return vals

    def _zc_create_requisition(self, auto_confirm=False):
        self.ensure_one()
        if self.zc_requisition_id:
            return self.zc_requisition_id

        requisition = self.env["zc.purchase.requisition"].create(
            self._zc_prepare_requisition_vals(auto_confirm=auto_confirm)
        )
        self.zc_requisition_id = requisition.id
        requisition.message_post(
            body=_("Automatically created from approved request %s.", self.display_name)
            if auto_confirm
            else _("Created from approval request %s.", self.display_name)
        )
        return requisition

    def _zc_auto_create_requisition_if_needed(self):
        for request in self:
            if (
                request.request_status == "approved"
                and request._zc_is_requisition_approval()
                and not request.zc_requisition_id
            ):
                request._zc_create_requisition(auto_confirm=True)

    def action_approve(self, *args, **kwargs):
        result = super().action_approve(*args, **kwargs)
        self._zc_auto_create_requisition_if_needed()
        return result

    def action_create_zc_requisition(self):
        self.ensure_one()
        if self.zc_requisition_id:
            return self.action_view_zc_requisition()
        if "request_status" in self._fields and self.request_status != "approved":
            raise UserError(_("The approval request must be approved before creating a requisition."))

        requisition = self._zc_create_requisition(auto_confirm=self._zc_is_requisition_approval())
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Requisition"),
            "res_model": "zc.purchase.requisition",
            "view_mode": "form",
            "res_id": requisition.id,
            "target": "current",
        }

    def action_view_zc_requisition(self):
        self.ensure_one()
        if not self.zc_requisition_id:
            raise UserError(_("No purchase requisition is linked to this approval request."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Requisition"),
            "res_model": "zc.purchase.requisition",
            "view_mode": "form",
            "res_id": self.zc_requisition_id.id,
            "target": "current",
        }


class ApprovalProductLine(models.Model):
    _inherit = "approval.product.line"

    def _zc_is_requisition_line(self):
        self.ensure_one()
        request = self.approval_request_id
        return bool(
            request
            and request.category_id
            and "approval_type" in request.category_id._fields
            and request.category_id.approval_type == "zc_requisition"
        )

    def _zc_is_frozen(self):
        self.ensure_one()
        request = self.approval_request_id
        return bool(
            self._zc_is_requisition_line()
            and (
                request.zc_requisition_id
                or request.request_status in ("approved", "refused", "cancel", "cancelled")
            )
        )

    def write(self, vals):
        tracked_lines = self.filtered(lambda line: line._zc_is_requisition_line())

        if tracked_lines:
            frozen = tracked_lines.filtered(lambda line: line._zc_is_frozen())
            if frozen and set(vals) & {
                "quantity",
                "product_id",
                "product_uom_id",
                "description",
                "approval_request_id",
            }:
                raise UserError(
                    _(
                        "The product lines of a fully processed Requisition approval are locked. "
                        "Change quantities before the final approval."
                    )
                )

            # Once submitted, only quantity may change for Requisition approvals.
            submitted = tracked_lines.filtered(
                lambda line: line.approval_request_id.request_status != "new"
                and not line._zc_is_frozen()
            )
            protected_fields = set(vals) & {
                "product_id",
                "product_uom_id",
                "description",
                "approval_request_id",
            }
            if submitted and protected_fields:
                raise UserError(
                    _(
                        "After a Requisition approval is submitted, only the Quantity may be edited. "
                        "Product, description, and unit are locked."
                    )
                )

        old_quantities = {
            line.id: line.quantity
            for line in tracked_lines
            if "quantity" in vals and line.id
        }

        result = super().write(vals)

        if "quantity" in vals:
            for line in tracked_lines:
                if not line.id or line.id not in old_quantities:
                    continue
                old_qty = old_quantities[line.id]
                new_qty = line.quantity
                rounding = line.product_uom_id.rounding if line.product_uom_id else 0.01
                if float_compare(old_qty, new_qty, precision_rounding=rounding) == 0:
                    continue
                request = line.approval_request_id
                product_name = line.product_id.display_name or line.description or _("Product")
                uom_name = line.product_uom_id.display_name if line.product_uom_id else ""
                request.message_post(
                    body=_(
                        "Quantity changed for %(product)s: %(old_qty)s %(uom)s → %(new_qty)s %(uom)s.",
                        product=product_name,
                        old_qty=old_qty,
                        new_qty=new_qty,
                        uom=uom_name,
                    ),
                    subtype_xmlid="mail.mt_note",
                )
        return result

    @api.model_create_multi
    def create(self, vals_list):
        # Keep the standard draft behavior. Once a Requisition approval has been
        # submitted, lines cannot be added; only existing quantities may change.
        for vals in vals_list:
            request_id = vals.get("approval_request_id")
            request = self.env["approval.request"].browse(request_id).exists() if request_id else self.env["approval.request"]
            if (
                request
                and request.category_id.approval_type == "zc_requisition"
                and request.request_status != "new"
            ):
                raise UserError(
                    _("New product lines cannot be added after a Requisition approval is submitted.")
                )
        return super().create(vals_list)

    def unlink(self):
        blocked = self.filtered(
            lambda line: line._zc_is_requisition_line()
            and line.approval_request_id.request_status != "new"
        )
        if blocked:
            raise UserError(
                _("Product lines cannot be removed after a Requisition approval is submitted.")
            )
        return super().unlink()
