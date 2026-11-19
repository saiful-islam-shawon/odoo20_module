# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.models import TableSQL
from odoo.tools import SQL


class SaleReport(models.Model):
    _inherit = "sale.report"

    free_qty = fields.Float(string="Free Qty", readonly=True)
    is_free_product = fields.Boolean(string="Is Free Product", readonly=True)

    def _select_dict(self, table: TableSQL):
        res = super()._select_dict(table)
        uom_ratio = SQL(
            "(COALESCE(%s, 1) / NULLIF(COALESCE(%s, 1), 0.0))",
            table.product_uom_id.factor,
            table.product_id.uom_id.factor,
        )
        is_free_cond = SQL(
            "%s IS NOT NULL AND %s = 'product'",
            table.reward_id.id,
            table.reward_id.reward_type,
        )

        res["is_free_product"] = SQL("CASE WHEN %s THEN TRUE ELSE FALSE END", is_free_cond)
        res["free_qty"] = SQL(
            "CASE WHEN %s IS NOT TRUE AND %s THEN SUM(%s * %s) ELSE 0 END",
            table.is_downpayment,
            is_free_cond,
            table.product_uom_qty,
            uom_ratio,
        )
        res["product_uom_qty"] = SQL(
            "CASE WHEN %s IS NOT TRUE AND NOT (%s) THEN SUM(%s * %s) ELSE 0 END",
            table.is_downpayment,
            is_free_cond,
            table.product_uom_qty,
            uom_ratio,
        )
        return res

    def _groupby_list(self, table: TableSQL):
        groupby_list = super()._groupby_list(table)
        groupby_list.extend([table.reward_id.id, table.reward_id.reward_type])
        return groupby_list

    @api.model
    @api.readonly
    def web_read_group(
        self,
        domain,
        groupby,
        aggregates=(),
        limit=None,
        offset=0,
        order=None,
        **kwargs,
    ):
        result = super().web_read_group(
            domain,
            groupby,
            aggregates=aggregates,
            limit=limit,
            offset=offset,
            order=order,
            **kwargs,
        )
        if groupby and aggregates:
            first_group_field = groupby[0].split(":")[0]
            if first_group_field in ("partner_id", "product_tmpl_id", "product_id"):
                clean_aggregates = [agg for agg in aggregates if agg != "__count"]
                if clean_aggregates:
                    sold_aggregates = [agg for agg in clean_aggregates if agg.split(":")[0] != "free_qty"]
                    free_aggregates = [agg for agg in clean_aggregates if agg.split(":")[0] == "free_qty"]

                    sold_stats = {}
                    if sold_aggregates:
                        sold_domain = Domain(domain) & Domain([("is_free_product", "=", False)])
                        for row in self._read_group(sold_domain, [groupby[0]], sold_aggregates):
                            key_val = row[0]
                            key_id = key_val.id if hasattr(key_val, "id") else key_val
                            sold_stats[key_id] = dict(zip(sold_aggregates, row[1:]))

                    free_stats = {}
                    if free_aggregates:
                        free_domain = Domain(domain) & Domain([("is_free_product", "=", True)])
                        for row in self._read_group(free_domain, [groupby[0]], free_aggregates):
                            key_val = row[0]
                            key_id = key_val.id if hasattr(key_val, "id") else key_val
                            free_stats[key_id] = dict(zip(free_aggregates, row[1:]))

                    for grp in result.get("groups", []):
                        val = grp.get(first_group_field)
                        item_id = val[0] if isinstance(val, (list, tuple)) else val
                        if item_id in sold_stats:
                            for agg, agg_val in sold_stats[item_id].items():
                                grp[agg] = agg_val
                        else:
                            for agg in sold_aggregates:
                                grp[agg] = 0.0

                        if item_id in free_stats:
                            for agg, agg_val in free_stats[item_id].items():
                                grp[agg] = agg_val
                        else:
                            for agg in free_aggregates:
                                grp[agg] = 0.0
        return result
