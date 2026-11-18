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
        if groupby and groupby[0].startswith("partner_id") and aggregates:
            clean_aggregates = [agg for agg in aggregates if agg != "__count"]
            if clean_aggregates:
                sold_domain = Domain(domain) & Domain([("is_free_product", "=", False)])
                sold_stats = {}
                for row in self._read_group(sold_domain, [groupby[0]], clean_aggregates):
                    partner_val = row[0]
                    pid = partner_val.id if hasattr(partner_val, "id") else partner_val
                    sold_stats[pid] = dict(zip(clean_aggregates, row[1:]))

                for grp in result.get("groups", []):
                    pval = grp.get("partner_id")
                    pid = pval[0] if isinstance(pval, (list, tuple)) else pval
                    if pid in sold_stats:
                        for agg, val in sold_stats[pid].items():
                            grp[agg] = val
                    else:
                        for agg in clean_aggregates:
                            grp[agg] = 0.0
        return result

