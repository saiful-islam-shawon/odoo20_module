# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_reward_line_readonly = fields.Boolean(
        string="Is Reward Line Readonly",
        compute="_compute_is_reward_line_readonly",
    )

    @api.depends("is_reward_line", "reward_id.reward_type")
    def _compute_is_reward_line_readonly(self):
        for line in self:
            line.is_reward_line_readonly = bool(
                line.is_reward_line and line.reward_id and line.reward_id.reward_type != "product"
            )

    @api.onchange("product_uom_qty")
    def _onchange_product_uom_qty_free_reward(self):
        for line in self:
            if line.is_reward_line and line.reward_id and line.reward_id.reward_type == "product":
                line.discount = 100.0

    def write(self, vals):
        if "product_uom_qty" in vals:
            for line in self:
                if line.is_reward_line and line.reward_id and line.reward_id.reward_type == "product":
                    vals.setdefault("discount", 100.0)
        return super().write(vals)

