# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    stock_in_qty = fields.Float(
        string="Stock In",
        compute="_compute_stock_movement_quantities",
        digits="Product Unit",
    )
    stock_out_qty = fields.Float(
        string="Stock Out",
        compute="_compute_stock_movement_quantities",
        digits="Product Unit",
    )
    closing_stock_qty = fields.Float(
        string="Closing Stock",
        compute="_compute_stock_movement_quantities",
        digits="Product Unit",
    )

    def _compute_stock_movement_quantities(self):
        # 1. Stock In: Completed incoming receipts from vendor/supplier locations
        in_moves = self.env["stock.move"]._read_group(
            [
                ("product_id", "in", self.ids),
                ("state", "=", "done"),
                ("location_id.usage", "=", "supplier"),
                ("location_dest_id.usage", "=", "internal"),
            ],
            ["product_id"],
            ["quantity:sum"],
        )
        in_qty_map = {product.id: qty for product, qty in in_moves}

        # 2. Stock Out: Confirmed sold quantities from sales orders
        so_lines = self.env["sale.order.line"]._read_group(
            [
                ("product_id", "in", self.ids),
                ("order_id.state", "in", ["sale", "done"]),
            ],
            ["product_id"],
            ["product_uom_qty:sum"],
        )
        out_qty_map = {product.id: qty for product, qty in so_lines}

        # 3. Populate product values
        for product in self:
            product.stock_in_qty = product.uom_id.round(in_qty_map.get(product.id, 0.0))
            product.stock_out_qty = product.uom_id.round(out_qty_map.get(product.id, 0.0))
            product.closing_stock_qty = product.qty_available

