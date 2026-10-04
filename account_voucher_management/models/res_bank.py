from odoo import fields, models


class ResBank(models.Model):
    _name = "res.bank"
    _description = "Bank"
    _order = "name"

    name = fields.Char(string="Name", required=True, index=True)
    bic = fields.Char(string="BIC/SWIFT", index=True)
    active = fields.Boolean(default=True)
