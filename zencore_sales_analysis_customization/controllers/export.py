# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import operator
from werkzeug.exceptions import InternalServerError

from odoo.http import request, route
from odoo.tools import osutil
from odoo.addons.web.controllers.export import (
    ExcelExport,
    GroupExportXlsxWriter,
    GroupsTreeNode,
    content_disposition,
    serialize_exception,
)

_logger = logging.getLogger(__name__)

TARGET_GROUP_FIELDS = ('partner_id', 'product_tmpl_id', 'product_id')


def _get_all_group_records(group_node):
    """Recursively collect all data tuples (is_free, row) from group leaves."""
    if group_node.data:
        return list(group_node.data)
    records = []
    for child in group_node.children.values():
        records.extend(_get_all_group_records(child))
    return records


class SalesAnalysisGroupExportXlsxWriter(GroupExportXlsxWriter):

    def __init__(self, fields, columns_headers, row_count):
        super().__init__(fields, columns_headers, row_count)
        subtotal_props = {'text_wrap': True, 'bold': True, 'bg_color': '#e9ecef'}
        self.subtotal_style = self.workbook.add_format(subtotal_props)
        self.subtotal_style_float = self.workbook.add_format(dict(**subtotal_props, num_format='#,##0.00'))
        decimal_places = request.env['res.currency']._read_group([], aggregates=['decimal_places:max'])[0][0] or 2
        self.subtotal_style_monetary = self.workbook.add_format(
            dict(**subtotal_props, num_format=f'#,##0.{decimal_places * "0"}')
        )

    def write_group(self, row, column, group_name, group, group_depth=0):
        # Collect all items for this subtree
        all_items = _get_all_group_records(group)
        if not all_items and not group.children:
            return row, column

        group_name = group_name[1] if isinstance(group_name, tuple) and len(group_name) > 1 else group_name
        if group._groupby_type[group_depth] != 'boolean':
            group_name = group_name or request.env._("Undefined")

        sold_data = [item[1] for item in all_items if not item[0]]
        free_data = [item[1] for item in all_items if item[0]]

        # Write group header with sold-only aggregates and free qty
        count_display = len(all_items) if all_items else group.count
        label = '%s%s (%s)' % ('    ' * group_depth, group_name, count_display)
        self.write(row, column, label, self.header_bold_style)

        free_qty_idx = next((i for i, f in enumerate(self.fields) if f['name'] == 'free_qty'), None)
        qty_idx = next((i for i, f in enumerate(self.fields) if f['name'] == 'product_uom_qty'), None)
        price_unit_idx = next((i for i, f in enumerate(self.fields) if f['name'] == 'price_unit'), None)
        total_indices = [i for i, f in enumerate(self.fields) if f['name'] in ('price_total', 'price_subtotal')]

        sold_qty = (
            sum(r[qty_idx] for r in sold_data if isinstance(r[qty_idx], (int, float)))
            if qty_idx is not None
            else 0.0
        )
        total_free_qty = (
            sum(
                (
                    r[free_qty_idx]
                    if free_qty_idx is not None and isinstance(r[free_qty_idx], (int, float)) and r[free_qty_idx]
                    else (r[qty_idx] if qty_idx is not None and isinstance(r[qty_idx], (int, float)) else 0.0)
                )
                for r in free_data
            )
            if free_data
            else 0.0
        )
        first_total_idx = total_indices[0] if total_indices else None
        sold_total = (
            sum(r[first_total_idx] for r in sold_data if isinstance(r[first_total_idx], (int, float)))
            if first_total_idx is not None
            else 0.0
        )
        sold_avg_price = (sold_total / sold_qty) if sold_qty else 0.0

        for col_idx, field in enumerate(self.fields[1:], start=1):
            val = ''
            header_style = self.header_bold_style
            if col_idx == qty_idx:
                val = sold_qty
                header_style = self.header_bold_style_float
            elif col_idx == free_qty_idx:
                val = total_free_qty
                header_style = self.header_bold_style_float
            elif col_idx in total_indices:
                val = sum(r[col_idx] for r in sold_data if isinstance(r[col_idx], (int, float)))
                header_style = self.header_bold_style_monetary
            elif col_idx == price_unit_idx:
                val = sold_avg_price
                header_style = self.header_bold_style_monetary
            self.write(row, col_idx, val, header_style)
        row += 1

        # Recursively write sub-groups if any
        if group.children:
            for child_group_name, child_group in group.children.items():
                row, column = self.write_group(row, column, child_group_name, child_group, group_depth + 1)
        else:
            # Write sold records first
            for record in sold_data:
                row, column = self._write_row(row, 0, record)

            # Write "Total Free Product" row if free records exist (without any quantity value)
            if free_data:
                free_label = '%sTotal Free Product' % ('    ' * (group_depth + 1))
                self.write(row, 0, free_label, self.subtotal_style)
                free_amount = 0.0
                if price_unit_idx is not None:
                    for r in free_data:
                        q = (
                            r[free_qty_idx]
                            if free_qty_idx is not None and isinstance(r[free_qty_idx], (int, float)) and r[free_qty_idx]
                            else (r[qty_idx] if qty_idx is not None and isinstance(r[qty_idx], (int, float)) else 0.0)
                        )
                        p = r[price_unit_idx] if isinstance(r[price_unit_idx], (int, float)) else 0.0
                        free_amount += q * p

                for col_idx, field in enumerate(self.fields[1:], start=1):
                    val = ''
                    style = self.subtotal_style
                    if col_idx in total_indices:
                        val = free_amount
                        style = self.subtotal_style_monetary
                    self.write(row, col_idx, val, style)
                row += 1

                # Write free records below the separator
                for record in free_data:
                    row, column = self._write_row(row, 0, record)

        return row, 0


class CustomExcelExport(ExcelExport):

    @route('/web/export/xlsx', type='http', auth='user')
    def web_export_xlsx(self, data):
        try:
            params = json.loads(data)
            model = params.get('model')
            groupby = params.get('groupby')
            is_target = (
                model == 'sale.report'
                and groupby
                and any(g.split(':')[0] in TARGET_GROUP_FIELDS for g in groupby)
            )

            if not is_target:
                return super().web_export_xlsx(data)

            # Custom export logic for sale.report with partner_id / product_tmpl_id / product_id grouping
            fields, ids, domain, import_compat = (
                operator.itemgetter('fields', 'ids', 'domain', 'import_compat')(params)
            )
            Model = request.env[model].with_context(import_compat=import_compat, **params.get('context', {}))
            if not Model._is_an_ordinary_table():
                fields = [field for field in fields if field['name'] != 'id']

            field_names = [f['name'] for f in fields]
            columns_headers = field_names if import_compat else [val['label'].strip() for val in fields]

            records = Model.browse(ids) if ids else Model.search(domain)
            export_data = records.export_data(['.id', 'is_free_product'] + field_names).get('datas', [])

            groupby_type = [Model._fields[x.split(':', 1)[0].split('.', 1)[0]].type for x in groupby]
            tree = GroupsTreeNode(Model, field_names, groupby, groupby_type)

            if ids:
                domain = [('id', 'in', ids)]
                SearchModel = Model.with_context(active_test=False)
            else:
                SearchModel = Model
            groups_data = SearchModel.formatted_read_group(domain, groupby, ['__count', 'id:array_agg'])

            record_rows = {}
            for row in export_data:
                if row[0]:
                    record_id = int(row[0])
                    is_free = bool(row[1])
                    record_rows[record_id] = (is_free, row[2:])

            groups = [group['id:array_agg'] for group in groups_data]
            grouped_rows = [[] for _ in groups]
            for group_index, ids_list in enumerate(groups):
                for record_id in ids_list:
                    if record_id in record_rows:
                        grouped_rows[group_index].append(record_rows[record_id])

            for group_info, group_rows in zip(groups_data, grouped_rows):
                tree.insert_leaf(group_info, group_rows)

            # Write output via SalesAnalysisGroupExportXlsxWriter
            with SalesAnalysisGroupExportXlsxWriter(fields, columns_headers, tree.count) as xlsx_writer:
                x, y = 1, 0
                for group_name, group in tree.children.items():
                    x, y = xlsx_writer.write_group(x, y, group_name, group)
            response_data = xlsx_writer.value

            return request.make_response(
                response_data,
                headers=[
                    ('Content-Disposition', content_disposition(osutil.clean_filename(self.filename(model) + self.extension))),
                    ('Content-Type', self.content_type),
                ],
            )
        except Exception as exc:
            _logger.exception("Exception during request handling in CustomExcelExport.")
            payload = json.dumps({
                'code': 0,
                'message': "Odoo Server Error",
                'data': serialize_exception(exc),
            })
            raise InternalServerError(payload) from exc
