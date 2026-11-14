# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    import_lc_state = fields.Selection(
        related='import_lc_id.state',
        string='Import LC Status',
        readonly=True,
    )

    lc_journal_entry_id = fields.Many2one(
        'account.move',
        string='LC Journal Entry',
        ondelete='restrict',
        help=(
            'Other-charge journal entry linked to the same Import LC. '
            'Choose the individual debit Journal Items to capitalize in Additional Costs.'
        ),
    )

    def _find_import_lc_from_pickings(self, pickings):
        for picking in pickings:
            if hasattr(picking, 'import_ci_id') and picking.import_ci_id and picking.import_ci_id.import_lc_id:
                return picking.import_ci_id.import_lc_id
            if picking.purchase_id:
                lc = self.env['import.lc'].search([
                    ('lc_order_id.po_number', '=', picking.purchase_id.id),
                    ('state', '!=', 'cancel'),
                ], limit=1)
                if lc:
                    return lc
        return False

    @api.onchange('picking_ids')
    def _onchange_picking_ids_auto_link_import_lc(self):
        if not self.import_lc_id and self.picking_ids:
            lc = self._find_import_lc_from_pickings(self.picking_ids)
            if lc:
                self.import_lc_id = lc.id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('import_lc_id') and vals.get('picking_ids'):
                picking_ids = []
                for cmd in vals['picking_ids']:
                    if isinstance(cmd, (list, tuple)) and len(cmd) == 3 and cmd[0] == 6:
                        picking_ids.extend(cmd[2])
                    elif isinstance(cmd, (list, tuple)) and len(cmd) == 3 and cmd[0] == 4:
                        picking_ids.append(cmd[1])
                if picking_ids:
                    pickings = self.env['stock.picking'].browse(picking_ids)
                    lc = self._find_import_lc_from_pickings(pickings)
                    if lc:
                        vals['import_lc_id'] = lc.id
        return super().create(vals_list)

    def _check_import_lc_editable(self):
        if any(cost.import_lc_id.state == 'done' for cost in self.filtered('import_lc_id')):
            raise ValidationError(_('A closed Import LC and its landed costs are read-only.'))

    def write(self, vals):
        self._check_import_lc_editable()
        res = super().write(vals)
        if 'picking_ids' in vals or ('import_lc_id' in vals and not vals.get('import_lc_id')):
            for cost in self:
                if not cost.import_lc_id and cost.picking_ids:
                    lc = cost._find_import_lc_from_pickings(cost.picking_ids)
                    if lc:
                        super(StockLandedCost, cost.with_context(tracking_disable=True)).write({'import_lc_id': lc.id})
        return res

    def unlink(self):
        self._check_import_lc_editable()
        return super().unlink()

    @api.constrains('lc_journal_entry_id', 'import_lc_id', 'company_id')
    def _check_lc_journal_entry(self):
        for cost in self.filtered('lc_journal_entry_id'):
            journal_entry = cost.lc_journal_entry_id

            if journal_entry.move_type != 'entry':
                raise ValidationError(_('Only journal entries can be selected.'))

            if journal_entry.state == 'cancel':
                raise ValidationError(_('A cancelled journal entry cannot be selected.'))

            if not cost.import_lc_id:
                raise ValidationError(
                    _('Link the landed cost to an Import LC before selecting an LC journal entry.')
                )

            if journal_entry.import_lc_id != cost.import_lc_id:
                raise ValidationError(
                    _('The journal entry must belong to the same Import LC as the landed cost.')
                )

            if journal_entry.company_id != cost.company_id:
                raise ValidationError(
                    _('The journal entry and landed cost must belong to the same company.')
                )

            invalid_lines = cost.cost_lines.filtered(
                lambda line: line.journal_item_id
                and line.journal_item_id.move_id != journal_entry
            )
            if invalid_lines:
                raise ValidationError(
                    _(
                        'One or more selected Journal Items belong to a different journal entry. '
                        'Remove those items before changing the LC Journal Entry.'
                    )
                )

    def _validate_lc_charge_sources(self):
        """Re-check charge sources at validation time in case the JE changed later."""
        for cost in self.filtered(lambda record: record.lc_journal_entry_id or record.cost_lines.filtered('journal_item_id')):
            journal_entry = cost.lc_journal_entry_id
            if not journal_entry:
                raise ValidationError(
                    _('Select an LC Journal Entry before validating journal-item based landed costs.')
                )
            if journal_entry.move_type != 'entry' or journal_entry.state == 'cancel':
                raise ValidationError(
                    _('The selected LC Journal Entry must be an active journal entry.')
                )
            if journal_entry.import_lc_id != cost.import_lc_id:
                raise ValidationError(
                    _('The selected LC Journal Entry is no longer linked to this Import LC.')
                )
            if journal_entry.company_id != cost.company_id:
                raise ValidationError(
                    _('The selected LC Journal Entry is not in the landed cost company.')
                )
            invalid_items = cost.cost_lines.filtered(
                lambda line: line.journal_item_id
                and (
                    line.journal_item_id.move_id != journal_entry
                    or line.journal_item_id.debit <= 0
                    or line.journal_item_id.company_id != cost.company_id
                )
            )
            if invalid_items:
                raise ValidationError(
                    _('One or more landed-cost Journal Items are no longer valid debit items of the selected LC Journal Entry.')
                )

    def button_validate(self):
        self._check_import_lc_editable()
        self._validate_lc_charge_sources()
        return super().button_validate()


class StockLandedCostLine(models.Model):
    _inherit = 'stock.landed.cost.lines'

    import_lc_id = fields.Many2one(
        related='cost_id.import_lc_id',
        string='Import LC',
        store=True,
        readonly=True,
    )

    journal_item_id = fields.Many2one(
        'account.move.line',
        string='Journal Item',
        ondelete='restrict',
        help=(
            'Debit journal item from the LC Journal Entry selected on this landed cost. '
            'Only items selected here are capitalized through landed cost; other LC charges stay as normal expenses.'
        ),
    )
    journal_item_debit = fields.Monetary(
        related='journal_item_id.debit',
        string='Debit',
        currency_field='currency_id',
    )
    journal_item_credit = fields.Monetary(
        related='journal_item_id.credit',
        string='Credit',
        currency_field='currency_id',
    )

    def _check_import_lc_editable(self):
        if any(line.cost_id.import_lc_id.state == 'done' for line in self.filtered('cost_id')):
            raise ValidationError(_('A closed Import LC and its landed costs are read-only.'))

    @api.onchange('journal_item_id')
    def _onchange_journal_item_id(self):
        for line in self.filtered('journal_item_id'):
            line.price_unit = line.journal_item_id.debit
            if not line.name:
                line.name = (
                    line.journal_item_id.name
                    or line.journal_item_id.move_id.ref
                    or line.journal_item_id.move_id.name
                )

    @api.model_create_multi
    def create(self, vals_list):
        costs = self.env['stock.landed.cost'].browse(
            [vals.get('cost_id') for vals in vals_list if vals.get('cost_id')]
        ).exists()
        costs._check_import_lc_editable()
        self._set_journal_item_values(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._check_import_lc_editable()
        self._set_journal_item_values([vals])
        return super().write(vals)

    def unlink(self):
        self._check_import_lc_editable()
        return super().unlink()

    @api.model
    def _set_journal_item_values(self, vals_list):
        """Keep journal-item sourced cost amounts consistent outside the web UI too."""
        journal_item_ids = {
            vals.get('journal_item_id')
            for vals in vals_list
            if vals.get('journal_item_id')
        }
        if not journal_item_ids:
            return

        items = {
            item.id: item
            for item in self.env['account.move.line'].browse(journal_item_ids).exists()
        }
        for vals in vals_list:
            item = items.get(vals.get('journal_item_id'))
            if not item:
                continue
            vals['price_unit'] = item.debit
            if not vals.get('name'):
                vals['name'] = item.name or item.move_id.ref or item.move_id.name

    @api.constrains('journal_item_id', 'cost_id')
    def _check_journal_item(self):
        for line in self.filtered('journal_item_id'):
            item = line.journal_item_id
            cost = line.cost_id
            journal_entry = cost.lc_journal_entry_id

            if not journal_entry:
                raise ValidationError(
                    _('Select an LC Journal Entry on the landed cost before selecting a Journal Item.')
                )

            if item.move_id != journal_entry:
                raise ValidationError(
                    _('The Journal Item must belong to the LC Journal Entry selected on the landed cost.')
                )

            if item.debit <= 0:
                raise ValidationError(
                    _('Only debit Journal Items can be capitalized through landed cost.')
                )

            if item.company_id != cost.company_id:
                raise ValidationError(
                    _('The Journal Item and landed cost must belong to the same company.')
                )
