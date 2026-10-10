from odoo import _, fields, models
from odoo.exceptions import UserError


class ZCRFQCreateWizard(models.TransientModel):
    _name = "zc.rfq.create.wizard"
    _description = "Create Vendor RFQ"

    requisition_id = fields.Many2one(
        "zc.purchase.requisition", string="Requisition", required=True, readonly=True
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        required=True,
        domain="[('supplier_rank', '>', 0)]",
    )
    quotation_reference = fields.Char(string="Vendor Quotation Ref.")
    quotation_date = fields.Date(string="Quotation Date", default=fields.Date.context_today)

    def action_create_rfq(self):
        self.ensure_one()
        requisition = self.requisition_id
        if requisition.state not in ("confirmed", "sourcing"):
            raise UserError(_("The requisition must be confirmed before creating an RFQ."))
        if not requisition.line_ids:
            raise UserError(_("The requisition has no product lines."))

        rfq = self.env["zc.vendor.rfq"].create(
            {
                "requisition_id": requisition.id,
                "partner_id": self.partner_id.id,
                "quotation_reference": self.quotation_reference,
                "quotation_date": self.quotation_date,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "requisition_line_id": line.id,
                            "price_unit": 0.0,
                        },
                    )
                    for line in requisition.line_ids
                ],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor RFQ"),
            "res_model": "zc.vendor.rfq",
            "view_mode": "form",
            "res_id": rfq.id,
            "target": "current",
        }
