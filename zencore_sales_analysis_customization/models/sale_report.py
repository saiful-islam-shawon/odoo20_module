# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.models import TableSQL
from odoo.tools import SQL


class SaleReport(models.Model):
    _inherit = "sale.report"

    is_free_product = fields.Boolean(string="Is Free Product", readonly=True)

    def _select_dict(self, table: TableSQL):
        res = super()._select_dict(table)
        res["is_free_product"] = SQL(
            "CASE WHEN %s IS NOT NULL AND %s = 'product' THEN TRUE ELSE FALSE END",
            table.reward_id.id,
            table.reward_id.reward_type,
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
            if first_group_field in ("partner_id", "product_id"):
                clean_aggregates = [agg for agg in aggregates if agg != "__count"]
                if clean_aggregates:
                    sold_domain = Domain(domain) & Domain([("is_free_product", "=", False)])
                    sold_stats = {}
                    for row in self._read_group(sold_domain, [groupby[0]], clean_aggregates):
                        key_val = row[0]
                        key_id = key_val.id if hasattr(key_val, "id") else key_val
                        sold_stats[key_id] = dict(zip(clean_aggregates, row[1:]))

                    for grp in result.get("groups", []):
                        val = grp.get(first_group_field)
                        item_id = val[0] if isinstance(val, (list, tuple)) else val
                        if item_id in sold_stats:
                            for agg, agg_val in sold_stats[item_id].items():
                                grp[agg] = agg_val
                        else:
                            for agg in clean_aggregates:
                                grp[agg] = 0.0
        return result
