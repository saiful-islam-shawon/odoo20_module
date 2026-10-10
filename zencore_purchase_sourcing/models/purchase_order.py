from odoo import _, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    zc_requisition_id = fields.Many2one(
        "zc.purchase.requisition",
        string="Source Requisition",
        copy=False,
        readonly=True,
        index=True,
    )

    def action_view_zc_requisition(self):
        self.ensure_one()
        if not self.zc_requisition_id:
            raise UserError(_("No source requisition is linked to this purchase order."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Requisition"),
            "res_model": "zc.purchase.requisition",
            "view_mode": "form",
            "res_id": self.zc_requisition_id.id,
            "target": "current",
        }
