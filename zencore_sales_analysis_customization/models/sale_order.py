# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _write_vals_from_reward_vals(self, reward_vals, old_lines, delete=True):
        """Preserve manually adjusted product_uom_qty on promotional free product reward lines."""
        for vals, line in zip(reward_vals, old_lines):
            if (
                line.is_reward_line
                and line.reward_id
                and line.reward_id.reward_type == "product"
                and line.product_uom_qty
            ):
                vals["product_uom_qty"] = line.product_uom_qty
        return super()._write_vals_from_reward_vals(reward_vals, old_lines, delete=delete)

