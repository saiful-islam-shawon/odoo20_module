from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_customer = fields.Boolean(string="Voucher Customer", tracking=True)
    is_vendor = fields.Boolean(string="Voucher Vendor", tracking=True)
