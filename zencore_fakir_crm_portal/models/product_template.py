from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    brand = fields.Char(
        string="Brand",
    )

    product_group = fields.Char(
        string="Product Group",
    )

    part_number = fields.Integer(
        string="Part Number",
    )