# -*- coding: utf-8 -*-
"""Enterprise workflow refinements for Import LC.

This file intentionally extends the original models instead of replacing them so
existing databases keep their technical model/field names while the business
workflow enforces one approved PI per Import LC.
"""
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.tools.float_utils import float_compare


class ImportLCPort(models.Model):
    _name = 'import.lc.port'
    _description = 'Import LC Port'
    _order = 'country_id, name'

    name = fields.Char(required=True, index=True)
    code = fields.Char(index=True, help='Port/UNLOCODE or internal code, e.g. BDCTG.')
    country_id = fields.Many2one('res.country', required=True)
    port_type = fields.Selection([
        ('sea', 'Sea Port'),
        ('air', 'Airport'),
        ('land', 'Land Port'),
        ('rail', 'Rail Terminal'),
        ('other', 'Other'),
    ], default='sea', required=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _name_country_unique = models.Constraint(
        'UNIQUE(name, country_id)',
        'The port name must be unique within a country.',
    )

    @api.depends('name', 'code', 'country_id')
    def _compute_display_name(self):
        for record in self:
            bits = [record.name]
            if record.code:
                bits.append(record.code)
            if record.country_id:
                bits.append(record.country_id.code or record.country_id.name)
            record.display_name = ' - '.join(filter(None, bits))


class ImportLCContainerType(models.Model):
    _name = 'import.lc.container.type'
    _description = 'Import LC Container Type'
    _order = 'sequence, name'

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    length_ft = fields.Float(string='Length (ft)')
    refrigerated = fields.Boolean()
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _container_code_unique = models.Constraint(
        'UNIQUE(code)',
        'Container code must be unique.',
    )


class ImportLCContainer(models.Model):
    _name = 'import.lc.container'
    _description = 'Import LC Container'
    _order = 'name'

    name = fields.Char(string='Container Number / Reference', required=True, index=True)
    container_type_id = fields.Many2one('import.lc.container.type', string='Container Type', required=True)
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _container_name_unique = models.Constraint(
        'UNIQUE(name)',
        'Container number/reference must be unique.',
    )


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Keep the PI milestone in Odoo's native RFQ/PO status bar.  The record
    # remains an RFQ at this point; it moves to Purchase Order only after the
    # linked Import LC is confirmed.
    state = fields.Selection(
        # The one-item tuple is an insertion anchor: keep the PI milestone
        # between the RFQ states and Odoo's Purchase Order milestone instead
        # of appending it after Cancelled.
        selection_add=[('proforma', 'Proforma Invoice'), ('purchase',)],
        ondelete={'proforma': 'set default'},
    )

    # RFQ is the source of the commercial/logistics defaults that later flow to PI.
    purchase_type = fields.Selection([
        ('local', 'Local Purchase'),
        ('import', 'Import Purchase'),
    ], string='Purchase Type', required=True, default='local', tracking=True)
    lc_required = fields.Boolean(
        string='LC Required',
        compute='_compute_lc_required',
        readonly=True,
        help='When enabled, this purchase must be linked to a confirmed Import LC before approval/confirmation.',
    )

    @api.depends('purchase_type')
    def _compute_lc_required(self):
        for order in self:
            order.lc_required = order.purchase_type == 'import'

    lc_advising_bank_id = fields.Many2one('res.bank', string='Advising Bank', tracking=True)
    lc_payment_terms = fields.Selection([
        ('sight_draft', 'Sight Draft'),
        ('deferred_payment', 'Deferred Payment'),
        ('at_sight', 'At Sight'),
        ('mixed', 'Mixed'),
    ], string='LC Payment Terms', default='sight_draft', tracking=True)
    lc_pi_term_id = fields.Many2one('lc.pi.term', string='PI Terms', tracking=True)
    lc_partial_shipment = fields.Selection([
        ('allowed', 'Allowed'),
        ('not_allowed', 'Not Allowed'),
    ], string='Partial Shipment Allowed', default='allowed', tracking=True)
    lc_transshipment = fields.Selection([
        ('allowed', 'Allowed'),
        ('not_allowed', 'Not Allowed'),
    ], string='Transshipment Allowed', default='allowed', tracking=True)
    lc_expected_opening_date = fields.Date(string='Expected LC Opening Date', tracking=True)
    lc_expected_shipment_date = fields.Date(
        string='Expected Shipment Date',
        tracking=True,
        help='Expected/preferred shipment timing from the RFQ; actual shipment dates are recorded in the shipment flow.',
    )
    lc_port_of_shipment_id = fields.Many2one(
        'import.lc.port',
        string='Preferred Port of Shipment',
        tracking=True,
        help='Preferred port captured on the RFQ; it is not the actual departure port.',
    )
    lc_destination_port_id = fields.Many2one(
        'import.lc.port',
        string='Destination Port',
        tracking=True,
        help='Expected destination port captured on the RFQ.',
    )
    lc_container_type_id = fields.Many2one('import.lc.container.type', string='Container Type', tracking=True)
    lc_container_id = fields.Many2one('import.lc.container', string='Configured Container', tracking=True)
    lc_container_reference = fields.Char(string='Container / Shipment Reference', tracking=True)
    lc_sc_number = fields.Char(string='S/C Number', tracking=True)
    lc_indent_agent_id = fields.Many2one('res.partner', string='Indent Agent', tracking=True)
    lc_indent_commission_percent = fields.Float(string='Indent Commission (%)', digits=(5, 2), tracking=True)
    lc_indent_commission_amount = fields.Monetary(string='Indent Commission Amount', currency_field='currency_id', tracking=True)
    lc_cnf_agent_id = fields.Many2one('res.partner', string='C&F Agent', tracking=True)

    @api.constrains('lc_indent_commission_percent', 'lc_indent_commission_amount')
    def _check_indent_commission(self):
        for order in self:
            if not 0 <= order.lc_indent_commission_percent <= 100 or order.lc_indent_commission_amount < 0:
                raise ValidationError(_('Indent commission percentage must be between 0 and 100; amount cannot be negative.'))

    def button_confirm(self):
        for order in self:
            if order.lc_required and not order.import_lc_ids.filtered(
                lambda lc: lc.state in ('confirmed', 'done') and lc.company_id == order.company_id
            ):
                raise ValidationError(_(
                    'Import Purchase RFQ/PO %s requires an approved Import LC before confirmation.'
                ) % order.name)
        # Odoo's standard confirmation only accepts its normal RFQ states.
        # A PI-stage RFQ is otherwise still a draft RFQ, so restore that
        # technical state immediately before delegating to the standard flow.
        self.filtered(lambda order: order.state == 'proforma').write({'state': 'draft'})
        return super().button_confirm()

    def button_approve(self, force=False):
        for order in self.filtered('lc_required'):
            if not order.import_lc_ids.filtered(lambda lc: lc.state in ('confirmed', 'done')):
                raise ValidationError(_('Confirm the Import LC before approving this purchase order.'))
        return super().button_approve(force=force)

    @api.constrains('purchase_type', 'state')
    def _check_purchase_type(self):
        for order in self:
            if not order.lc_required and order.state == 'proforma':
                raise ValidationError(_('The Proforma Invoice stage is available only for Import Purchase RFQs.'))
            if not order.lc_required and order.lc_order_ids.filtered(
                lambda pi: pi.state != 'cancel'
            ):
                raise ValidationError(_('Cancel or reject the active PI before switching to Local Purchase.'))
            if order.lc_required and order.state in ('purchase', 'done'):
                if not order.import_lc_ids.filtered(lambda lc: lc.state in ('confirmed', 'done')):
                    raise ValidationError(_('An Import Purchase requires a confirmed Import LC.'))

    @api.onchange('lc_container_id')
    def _onchange_lc_container_id(self):
        if self.lc_container_id:
            self.lc_container_type_id = self.lc_container_id.container_type_id
            self.lc_container_reference = self.lc_container_id.name

    lc_order_ids = fields.One2many('lc.order', 'po_number', string='Proforma Invoices')
    pi_count = fields.Integer(compute='_compute_import_lc_links')
    import_lc_ids = fields.Many2many('import.lc', compute='_compute_import_lc_links', string='Import LCs')
    import_lc_count = fields.Integer(compute='_compute_import_lc_links')
    lc_number_display = fields.Char(compute='_compute_import_lc_links', string='LC Number')

    @api.depends('lc_order_ids', 'lc_order_ids.import_lc_ids', 'lc_order_ids.import_lc_id',
                 'lc_order_ids.import_lc_ids.lc_number', 'lc_order_ids.import_lc_id.lc_number')
    def _compute_import_lc_links(self):
        for po in self:
            pis = po.lc_order_ids
            lcs = pis.mapped('import_lc_ids') | pis.mapped('import_lc_id')
            po.pi_count = len(pis)
            po.import_lc_ids = lcs
            po.import_lc_count = len(lcs)
            if len(lcs) == 1:
                po.lc_number_display = lcs.lc_number
            elif len(lcs) > 1:
                po.lc_number_display = _('%s LCs') % len(lcs)
            else:
                po.lc_number_display = _('No LC')

    def action_create_proforma_invoice(self):
        self.ensure_one()
        if self.state == 'cancel':
            raise ValidationError(_('A Proforma Invoice cannot be created from a cancelled RFQ/PO.'))
        if not self.lc_required:
            raise ValidationError(_('Proforma Invoice and LC workflow are available only for Import Purchase RFQs/POs.'))
        if self.lc_order_ids:
            raise ValidationError(_('This RFQ/PO already has a Proforma Invoice. Use the existing PI instead of creating another one.'))
        line_commands = []
        for po_line in self.order_line.filtered(lambda l: l.product_id and l.product_qty > 0):
            line_commands.append((0, 0, {
                'product_id': po_line.product_id.id,
                'product_category_id': po_line.product_id.categ_id.id,
                'quantity': po_line.product_qty,
                'unit_price': po_line.price_unit,
                # Odoo 19 exposes the purchase-line UOM as ``product_uom_id``.
                # ``product_uom`` was used by older versions and raises an
                # AttributeError on current purchase.order.line records.
                'product_uom_id': (po_line.product_uom_id or po_line.product_id.uom_id).id,
                'po_line_id': po_line.id,
            }))
        return {
            'name': _('Create Proforma Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'lc.order',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_po_number': self.id,
                'default_company_id': self.company_id.id,
                'default_currency_id': self.currency_id.id,
                'default_bank_id': self.lc_advising_bank_id.id or False,
                'default_payment_term_id': self.payment_term_id.id or False,
                'default_lc_payment_terms': self.lc_payment_terms,
                'default_pi_terms': self.lc_pi_term_id.id or False,
                'default_partial_shipment': self.lc_partial_shipment,
                'default_transshipment': self.lc_transshipment,
                'default_expected_lc_opening_date': self.lc_expected_opening_date or fields.Date.context_today(self),
                'default_expected_shipment_date': self.lc_expected_shipment_date or False,
                'default_port_of_shipment_id': self.lc_port_of_shipment_id.id or False,
                'default_destination_port_id': self.lc_destination_port_id.id or False,
                'default_container_type_id': self.lc_container_type_id.id or False,
                'default_sc_number': self.lc_sc_number or False,
                'default_indent_agent_id': self.lc_indent_agent_id.id or False,
                'default_indent_commission_percent': self.lc_indent_commission_percent or 0.0,
                'default_indent_commission_amount': self.lc_indent_commission_amount or 0.0,
                'default_cnf_agent_id': self.lc_cnf_agent_id.id or False,
                'default_lc_line_ids': line_commands,
            },
        }

    def action_view_proforma_invoices(self):
        self.ensure_one()
        action = self.env.ref('zencore_import_lc.action_lc_order').read()[0]
        action['domain'] = [('po_number', '=', self.id)]
        action['context'] = {'default_po_number': self.id, 'default_company_id': self.company_id.id}
        return action

    def action_view_import_lcs(self):
        self.ensure_one()
        action = self.env.ref('zencore_import_lc.action_import_lc').read()[0]
        action['domain'] = [('id', 'in', self.import_lc_ids.ids)]
        return action


class LCOrder(models.Model):
    _inherit = 'lc.order'

    po_number = fields.Many2one(
        'purchase.order', string='RFQ / Purchase Order', tracking=True, check_company=True
    )

    # PI number is supplied by the vendor; it is never a generated internal LC number.
    pi_number = fields.Char(string='PI Number', required=False, tracking=True, index=True)
    transshipment = fields.Selection([
        ('allowed', 'Allowed'),
        ('not_allowed', 'Not Allowed'),
    ], string='Transshipment', default='allowed', required=True, tracking=True)
    expected_shipment_date = fields.Date(string='Expected Shipment Date', tracking=True)
    port_of_shipment_id = fields.Many2one('import.lc.port', string='Preferred Port of Shipment', tracking=True)
    destination_port_id = fields.Many2one('import.lc.port', string='Destination Port', tracking=True)
    container_type_id = fields.Many2one('import.lc.container.type', string='Container Type', tracking=True)
    container_id = fields.Many2one('import.lc.container', string='Configured Container', tracking=True)
    container_reference = fields.Char(string='Container / Shipment Reference', tracking=True)
    sc_number = fields.Char(string='S/C Number', tracking=True)
    indent_agent_id = fields.Many2one('res.partner', string='Indent Agent', tracking=True)
    indent_commission_percent = fields.Float(string='Indent Commission (%)', digits=(5, 2), tracking=True)
    indent_commission_amount = fields.Monetary(string='Indent Commission Amount', currency_field='currency_id', tracking=True)
    cnf_agent_id = fields.Many2one('res.partner', string='C&F Agent', tracking=True)
    is_registered_in_lc = fields.Boolean(
        string='Registered in Import LC',
        compute='_compute_is_registered_in_lc',
        help='A PI linked to an Import LC is part of the LC audit trail and cannot be cancelled.',
    )

    @api.depends('import_lc_id', 'import_lc_ids')
    def _compute_is_registered_in_lc(self):
        for record in self:
            record.is_registered_in_lc = bool(record.import_lc_id or record.import_lc_ids)

    def action_cancel(self):
        """Preserve the audit trail once a PI has been registered in an LC."""
        linked_records = self.filtered(lambda record: record.import_lc_id or record.import_lc_ids)
        if linked_records:
            raise ValidationError(_(
                'Proforma Invoice %s is already registered in an Import LC and cannot be cancelled.'
            ) % ', '.join(linked_records.mapped('pi_number')))
        return super().action_cancel()

    @api.constrains('conversion_rate')
    def _check_conversion_rate(self):
        for record in self:
            if record.conversion_rate <= 0:
                raise ValidationError(_('PI Conversion Rate must be greater than zero.'))

    def _check_single_active_pi_per_po(self, po, exclude_ids=None):
        if not po:
            return
        if po.purchase_type != 'import':
            raise ValidationError(_('A Proforma Invoice can only be created from an Import Purchase RFQ/PO.'))
        domain = [
            ('po_number', '=', po.id),
            ('state', '!=', 'cancel'),
        ]
        if exclude_ids:
            domain.append(('id', 'not in', list(exclude_ids)))
        existing = self.search(domain, limit=1)
        if existing:
            raise ValidationError(_(
                'RFQ/PO %s already has active Proforma Invoice %s. '
                'Cancel or reject the old PI before creating a replacement.'
            ) % (po.name, existing.pi_number or existing.display_name))

    def _po_header_defaults(self, po):
        if po.purchase_type != 'import':
            raise ValidationError(_('Select an Import Purchase RFQ/PO.'))
        values = {
            'bank_id': po.lc_advising_bank_id.id or False,
            'currency_id': po.currency_id.id or False,
            'payment_term_id': po.payment_term_id.id or False,
            'lc_payment_terms': po.lc_payment_terms,
            'pi_terms': po.lc_pi_term_id.id or False,
            'partial_shipment': po.lc_partial_shipment,
            'transshipment': po.lc_transshipment,
            'expected_lc_opening_date': po.lc_expected_opening_date or fields.Date.context_today(self),
            'expected_shipment_date': po.lc_expected_shipment_date or False,
            'port_of_shipment_id': po.lc_port_of_shipment_id.id or False,
            'destination_port_id': po.lc_destination_port_id.id or False,
            'container_type_id': po.lc_container_type_id.id or False,
            'sc_number': po.lc_sc_number or False,
            'indent_agent_id': po.lc_indent_agent_id.id or False,
            'indent_commission_percent': po.lc_indent_commission_percent or 0.0,
            'indent_commission_amount': po.lc_indent_commission_amount or 0.0,
            'cnf_agent_id': po.lc_cnf_agent_id.id or False,
            # Legacy fields are kept synchronized for old reports/integrations.
            'port_of_shipment': po.lc_port_of_shipment_id.display_name if po.lc_port_of_shipment_id else False,
            'destination_port': po.lc_destination_port_id.display_name if po.lc_destination_port_id else False,
            'shipment_container_name': po.lc_container_type_id.display_name if po.lc_container_type_id else False,
        }
        return values

    @api.onchange('container_id')
    def _onchange_container_id(self):
        if self.container_id:
            self.container_type_id = self.container_id.container_type_id
            self.container_reference = self.container_id.name

    @api.onchange('port_of_shipment_id', 'destination_port_id', 'container_type_id', 'container_reference')
    def _onchange_configured_logistics(self):
        """Keep legacy text fields synchronized for old reports/integrations."""
        self.port_of_shipment = self.port_of_shipment_id.display_name if self.port_of_shipment_id else False
        self.destination_port = self.destination_port_id.display_name if self.destination_port_id else False
        self.shipment_container_name = self.container_reference or (
            self.container_type_id.display_name if self.container_type_id else False
        )

    def _po_line_commands(self, po):
        commands = [(5, 0, 0)]
        for po_line in po.order_line.filtered(lambda l: l.product_id and l.product_qty > 0):
            commands.append((0, 0, {
                'product_id': po_line.product_id.id,
                'product_category_id': po_line.product_id.categ_id.id,
                'quantity': po_line.product_qty,
                'unit_price': po_line.price_unit,
                'product_uom_id': (po_line.product_uom_id or po_line.product_id.uom_id).id,
                'po_line_id': po_line.id,
            }))
        return commands

    def _pi_term_commands(self, term_id, clear=True):
        commands = [(5, 0, 0)] if clear else []
        term = self.env['lc.pi.term'].browse(term_id).exists() if term_id else False
        if term:
            for line in term.description_line_ids:
                commands.append((0, 0, {'title': line.title, 'description': line.description}))
        return commands

    @api.onchange('po_number')
    def _onchange_po_number(self):
        """RFQ/PO is the only source for a new PI's products and defaults.

        The legacy implementation tried to reuse quantities from a previous CI
        on the same PO. That makes a new PI depend on historical shipments and
        breaks the requested RFQ -> PI -> LC flow. A PI now always snapshots the
        selected RFQ/PO, while CI utilization is handled later in ``import.ci``.
        """
        self.lc_line_ids = [(5, 0, 0)]
        if not self.po_number:
            return
        defaults = self._po_header_defaults(self.po_number)
        for key, value in defaults.items():
            setattr(self, key, value)
        self.lc_line_ids = self._po_line_commands(self.po_number)

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for raw in vals_list:
            vals = dict(raw)
            if not (vals.get('pi_number') or '').strip():
                raise ValidationError(_('PI Number is mandatory and must match the supplier Proforma Invoice.'))
            vals['pi_number'] = vals['pi_number'].strip()
            po = self.env['purchase.order'].browse(vals.get('po_number')).exists() if vals.get('po_number') else False
            if po:
                self._check_single_active_pi_per_po(po)
                for key, value in self._po_header_defaults(po).items():
                    vals.setdefault(key, value)
                vals.setdefault('company_id', po.company_id.id)
                if not vals.get('lc_line_ids'):
                    vals['lc_line_ids'] = self._po_line_commands(po)[1:]
                if vals.get('pi_terms') and not vals.get('pi_term_line_ids'):
                    vals['pi_term_line_ids'] = self._pi_term_commands(vals['pi_terms'], clear=False)
            elif vals.get('pi_terms') and not vals.get('pi_term_line_ids'):
                vals['pi_term_line_ids'] = self._pi_term_commands(vals['pi_terms'], clear=False)

            # Direct/manual PI creation still uses configured masters. Mirror
            # them into the legacy Char fields which are required by the old
            # schema and are still consumed by some historical reports.
            shipment_port = self.env['import.lc.port'].browse(vals.get('port_of_shipment_id')).exists() if vals.get('port_of_shipment_id') else False
            destination_port = self.env['import.lc.port'].browse(vals.get('destination_port_id')).exists() if vals.get('destination_port_id') else False
            container_type = self.env['import.lc.container.type'].browse(vals.get('container_type_id')).exists() if vals.get('container_type_id') else False
            container = self.env['import.lc.container'].browse(vals.get('container_id')).exists() if vals.get('container_id') else False
            if container:
                vals.setdefault('container_type_id', container.container_type_id.id)
                vals.setdefault('container_reference', container.name)
                container_type = container.container_type_id
            if shipment_port:
                vals['port_of_shipment'] = shipment_port.display_name
            if destination_port:
                vals['destination_port'] = destination_port.display_name
            if vals.get('container_reference') or container_type:
                vals['shipment_container_name'] = vals.get('container_reference') or container_type.display_name
            prepared.append(vals)
        records = super().create(prepared)
        # The RFQ enters the PI stage only after the user actually saves the
        # PI, rather than when they merely open the creation form.
        records._move_linked_rfqs_to_proforma()
        return records

    def _move_linked_rfqs_to_proforma(self):
        """Put linked Import Purchase RFQs in the PI milestone.

        This is deliberately limited to RFQ states.  A PI may be entered
        manually after an RFQ was selected, but creating/editing that PI must
        never move an already-confirmed PO backwards in Odoo's standard flow.
        """
        self.mapped('po_number').filtered(
            lambda po: po.purchase_type == 'import' and po.state in ('draft', 'sent')
        ).write({'state': 'proforma'})

    def write(self, vals):
        vals = dict(vals)
        immutable = set(vals) - {'state'}
        if immutable and any(record.state == 'done' for record in self):
            raise ValidationError(_('A confirmed Proforma Invoice is locked and cannot be edited.'))
        if vals.get('state') == 'cancel':
            protected = self.filtered(lambda record: record.import_lc_id or record.import_lc_ids)
            if protected:
                raise ValidationError(_(
                    'A Proforma Invoice registered in an Import LC cannot be cancelled.'
                ))
        if 'pi_number' in vals:
            vals['pi_number'] = (vals['pi_number'] or '').strip()
            if not vals['pi_number']:
                raise ValidationError(_('Enter the supplier PI number manually.'))
        if 'po_number' in vals and vals['po_number']:
            po = self.env['purchase.order'].browse(vals['po_number']).exists()
            if po:
                self._check_single_active_pi_per_po(po, exclude_ids=self.ids)
                defaults = self._po_header_defaults(po)
                for key, value in defaults.items():
                    vals.setdefault(key, value)
                vals.setdefault('company_id', po.company_id.id)
                if 'lc_line_ids' not in vals:
                    vals['lc_line_ids'] = self._po_line_commands(po)
        if 'pi_terms' in vals and 'pi_term_line_ids' not in vals:
            vals['pi_term_line_ids'] = self._pi_term_commands(vals.get('pi_terms'), clear=True)
        # Users may override configured ports/container on the PI. Always keep
        # the old Char fields synchronized so existing reports remain correct.
        if any(key in vals for key in ('port_of_shipment_id', 'destination_port_id', 'container_id', 'container_type_id', 'container_reference')):
            for record in self:
                local = dict(vals)
                shipment_port = self.env['import.lc.port'].browse(
                    local.get('port_of_shipment_id', record.port_of_shipment_id.id)
                ).exists()
                destination_port = self.env['import.lc.port'].browse(
                    local.get('destination_port_id', record.destination_port_id.id)
                ).exists()
                container_type = self.env['import.lc.container.type'].browse(
                    local.get('container_type_id', record.container_type_id.id)
                ).exists()
                container = self.env['import.lc.container'].browse(
                    local.get('container_id', record.container_id.id)
                ).exists()
                if container:
                    local.setdefault('container_type_id', container.container_type_id.id)
                    local.setdefault('container_reference', container.name)
                    container_type = container.container_type_id
                container_reference = local.get('container_reference', record.container_reference)
                local['port_of_shipment'] = shipment_port.display_name if shipment_port else False
                local['destination_port'] = destination_port.display_name if destination_port else False
                local['shipment_container_name'] = container_reference or (container_type.display_name if container_type else False)
                super(LCOrder, record).write(local)
            if 'po_number' in vals:
                self._move_linked_rfqs_to_proforma()
            return True
        result = super().write(vals)
        if 'po_number' in vals:
            self._move_linked_rfqs_to_proforma()
        return result


class ImportLC(models.Model):
    _inherit = 'import.lc'

    # One Import LC is linked to exactly one approved Proforma Invoice (PI).
    lc_number = fields.Char(string='LC Number', required=True, default=False, copy=False, tracking=True, index=True)
    lc_order_id = fields.Many2one(
        'lc.order', string='Proforma Invoice', required=False, tracking=True,
        ondelete='restrict', check_company=True,
        domain="[('state', '=', 'done'), ('company_id', '=', company_id)]",
        help='The single approved Proforma Invoice covered by this Import LC.'
    )
    # Kept only to preserve old database links during upgrade. The active
    # workflow always mirrors exactly one PI here from ``lc_order_id``.
    lc_order_ids = fields.Many2many(
        'lc.order', 'lc_order_import_lc_rel', 'import_lc_id', 'lc_order_id',
        string='Legacy PI Link', readonly=True,
        help='Technical compatibility field. New workflow supports one PI per Import LC.'
    )
    pi_number = fields.Char(
        string='PI Number', related='lc_order_id.pi_number', store=True,
        readonly=True, required=False,
    )
    buyer_id = fields.Many2one('res.partner', string='Buyer / Applicant', default=lambda self: self.env.company.partner_id, tracking=True)
    applicant_bank_id = fields.Many2one('res.bank', string='Issuing Bank', required=True, tracking=True)

    rfq_no = fields.Char(
        string='RFQ No', compute='_compute_basic_purchase_information', readonly=True,
        help='RFQ/PO number from the selected Proforma Invoice.',
    )
    rfq_date = fields.Date(
        string='RFQ Date', compute='_compute_basic_purchase_information', readonly=True,
        help='RFQ/PO date from the selected Proforma Invoice.',
    )
    supplier_address = fields.Char(string='Supplier Address', related='supplier_id.contact_address', readonly=True)
    purchase_reference = fields.Char(
        string='Buyer / Purchase Reference', copy=False,
        help='Optional internal purchase reference; initially copied from the RFQ vendor reference.',
    )
    responsible_buyer_id = fields.Many2one(
        'res.users', string='Responsible Buyer', copy=False,
        help='Purchase officer; initially copied from the RFQ/PO and editable when needed.',
    )

    # Logistics are now singular because an LC has one PI only.
    port_of_shipment_id = fields.Many2one(
        'import.lc.port', related='lc_order_id.port_of_shipment_id',
        string='Preferred Port of Shipment', readonly=True,
    )
    destination_port_id = fields.Many2one(
        'import.lc.port', related='lc_order_id.destination_port_id',
        string='Destination Port', readonly=True,
    )
    container_type_id = fields.Many2one(
        'import.lc.container.type', related='lc_order_id.container_type_id',
        string='Container Type', readonly=True,
    )
    container_id = fields.Many2one(
        'import.lc.container', related='lc_order_id.container_id',
        string='Configured Container', readonly=True,
    )
    expected_shipment_date = fields.Date(
        related='lc_order_id.expected_shipment_date', string='Expected Shipment Date', readonly=True,
    )

    company_currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True, readonly=True,
    )
    lc_amount = fields.Monetary(
        string='LC Amount', currency_field='currency_id', tracking=True,
        help='Bank-issued documentary credit amount in the LC currency.',
    )
    lc_tolerance_amount = fields.Monetary(
        string='Tolerance Amount', currency_field='currency_id',
        compute='_compute_lc_amounts', store=True,
    )
    lc_utilized_amount = fields.Monetary(
        string='Utilized Amount', currency_field='currency_id',
        compute='_compute_lc_amounts', store=True,
    )
    lc_available_amount = fields.Monetary(
        string='Available Amount', currency_field='currency_id',
        compute='_compute_lc_amounts', store=True,
    )
    lc_amount_bdt = fields.Monetary(
        string='LC Amount (Company Currency)', currency_field='company_currency_id',
        compute='_compute_lc_amounts', store=True,
    )
    incoterm_id = fields.Many2one('account.incoterms', string='Incoterm', tracking=True)
    hs_code_required = fields.Boolean(string='HS Codes Complete', compute='_compute_hs_code_required', store=False)
    lca_number = fields.Char(string='LCAF Number', tracking=True)
    lca_date = fields.Date(string='LCAF Date', tracking=True)
    imp_number = fields.Char(string='Form IMP Number', tracking=True)
    imp_date = fields.Date(string='Form IMP Date', tracking=True)
    importer_registration_no = fields.Char(string='Importer Registration No.', tracking=True)
    latest_shipment_date = fields.Date(string='Latest Shipment Date', tracking=True)
    presentation_period_days = fields.Integer(string='Document Presentation Period (Days)', default=21, tracking=True)
    expiry_place = fields.Char(string='LC Expiry Place', tracking=True)
    landed_cost_count = fields.Integer(string='Landed Cost Count', compute='_compute_landed_cost_count')
    can_create_commercial_invoice = fields.Boolean(
        string='Can Create Commercial Invoice',
        compute='_compute_workflow_actions',
    )
    can_close_lc = fields.Boolean(
        string='Can Close LC',
        compute='_compute_workflow_actions',
    )

    @api.depends('lc_amount', 'lc_tolerance_percent', 'lc_conversion_rate',
                 'ci_ids.product_line_ids.total_cost', 'ci_ids.state')
    def _compute_lc_amounts(self):
        for record in self:
            record.lc_tolerance_amount = record.lc_amount * (record.lc_tolerance_percent or 0.0) / 100.0
            active_cis = record.ci_ids.filtered(lambda ci: ci.state != 'cancel')
            record.lc_utilized_amount = sum(active_cis.mapped('product_line_ids.total_cost'))
            record.lc_available_amount = record.lc_amount + record.lc_tolerance_amount - record.lc_utilized_amount
            record.lc_amount_bdt = record.lc_amount * (record.lc_conversion_rate or 0.0)

    @api.depends('product_line_ids.hs_code')
    def _compute_hs_code_required(self):
        for record in self:
            lines = record.product_line_ids.filtered('product_id')
            record.hs_code_required = bool(lines) and all(line.hs_code for line in lines)

    @api.depends('landed_cost_ids')
    def _compute_landed_cost_count(self):
        for record in self:
            record.landed_cost_count = len(record.landed_cost_ids)

    def _has_available_ci_quantity(self):
        self.ensure_one()
        active_ci_lines = self.ci_ids.filtered(
            lambda ci: ci.state != 'cancel'
        ).mapped('product_line_ids')
        used_by_po_line = defaultdict(float)
        used_by_product = defaultdict(float)
        for line in active_ci_lines:
            if line.po_line_id:
                used_by_po_line[line.po_line_id.id] += line.ci_quantity
            else:
                used_by_product[line.product_id.id] += line.ci_quantity

        for line in self.product_line_ids.filtered('product_id'):
            used_quantity = (
                used_by_po_line.get(line.po_line_id.id, 0.0)
                if line.po_line_id
                else used_by_product.get(line.product_id.id, 0.0)
            )
            rounding = line.uom_id.rounding if line.uom_id else 0.01
            if float_compare(line.quantity - used_quantity, 0.0, precision_rounding=rounding) > 0:
                return True
        return False

    @api.depends(
        'state',
        'product_line_ids.quantity', 'product_line_ids.product_id',
        'product_line_ids.po_line_id', 'product_line_ids.uom_id',
        'ci_ids.state', 'ci_ids.product_line_ids.ci_quantity',
        'ci_ids.product_line_ids.product_id', 'ci_ids.product_line_ids.po_line_id',
        # Traverse searchable source relations so Odoo can find the affected
        # LCs when a receipt or bill changes. The display collections below
        # are non-stored computed fields and cannot be traversed in depends.
        'grn_ids', 'lc_order_id.po_number.picking_ids',
        'lc_order_id.po_number.picking_ids.state',
        'lc_order_id.po_number.picking_ids.picking_type_id.code',
        'invoice_ids', 'ci_ids.bill_ids', 'ci_ids.bill_ids.state',
        'ci_ids.bill_ids.payment_state', 'ci_ids.bill_ids.move_type',
    )
    def _compute_workflow_actions(self):
        for record in self:
            record.can_create_commercial_invoice = (
                record.state == 'confirmed' and record._has_available_ci_quantity()
            )
            active_grns = record.grn_ids.filtered(lambda picking: picking.state != 'cancel')
            active_bills = record.invoice_ids.filtered(
                lambda bill: bill.move_type == 'in_invoice' and bill.state != 'cancel'
            )
            record.can_close_lc = bool(
                record.state == 'confirmed'
                and active_grns
                and all(picking.state == 'done' for picking in active_grns)
                and active_bills
                and all(bill.payment_state == 'paid' for bill in active_bills)
            )

    @api.depends('lc_order_id.po_number', 'lc_order_id.po_number.name', 'lc_order_id.po_number.date_order')
    def _compute_basic_purchase_information(self):
        for record in self:
            po = record.lc_order_id.po_number if record.lc_order_id else False
            record.rfq_no = po.name if po else False
            record.rfq_date = fields.Date.to_date(po.date_order) if po and po.date_order else False

    def _validate_single_pi(self, pi):
        pi = pi.exists()
        if not pi:
            raise ValidationError(_('Select one approved Proforma Invoice.'))
        if len(pi) != 1:
            raise ValidationError(_('Only one Proforma Invoice can be linked to an Import LC.'))
        if pi.state != 'done':
            raise ValidationError(_('Only a confirmed/approved Proforma Invoice can be linked to an Import LC.'))
        if self and any(record.company_id and record.company_id != pi.company_id for record in self):
            raise ValidationError(_('Import LC company must match the selected Proforma Invoice company.'))
        domain = [
            ('state', '!=', 'reject'),
            ('id', 'not in', self.ids),
            '|',
            ('lc_order_id', '=', pi.id),
            ('lc_order_ids', 'in', [pi.id]),
        ]
        other_lc = self.search(domain, limit=1)
        if other_lc:
            raise ValidationError(_(
                'PI %s is already linked to Import LC %s. One PI can belong to only one active Import LC.'
            ) % (pi.pi_number, other_lc.lc_number))
        return pi

    def _single_pi_defaults(self, pi):
        pi = self._validate_single_pi(pi)
        company = pi.company_id
        values = {
            'company_id': company.id,
            'buyer_id': company.partner_id.id,
            'supplier_id': pi.vendor_id.id,
            'currency_id': pi.currency_id.id,
            'purchase_reference': pi.po_number.partner_ref if pi.po_number else False,
            'responsible_buyer_id': (
                pi.po_number.user_id.id if pi.po_number and pi.po_number.user_id else self.env.user.id
            ),
            'advising_bank_id': pi.bank_id.id or False,
            'payment_terms': pi.lc_payment_terms,
            'partial_shipment': pi.partial_shipment,
            'transshipment': pi.transshipment,
            'lc_conversion_rate': pi.conversion_rate or 1.0,
            'sc_number': pi.sc_number or False,
            'indent_agent_id': pi.indent_agent_id.id or False,
            'cnf_agent_id': pi.cnf_agent_id.id or False,
            'incoterm_id': pi.po_number.incoterm_id.id if pi.po_number and pi.po_number.incoterm_id else False,
        }
        if pi.expected_lc_opening_date:
            values['lc_opening_date'] = pi.expected_lc_opening_date
        return values

    def _product_commands_from_pi(self, pi, clear=True):
        pi = self._validate_single_pi(pi)
        commands = [(5, 0, 0)] if clear else []
        for line in pi.lc_line_ids.filtered('product_id'):
            product = line.product_id
            commands.append((0, 0, {
                'lc_order_id': pi.id,
                'po_line_id': line.po_line_id.id or False,
                'product_id': product.id,
                'product_name': product.display_name,
                'product_category_id': line.product_category_id.id or product.categ_id.id,
                'quantity': line.quantity,
                'unit_price': line.unit_price,
                'uom_id': line.product_uom_id.id or line.product_id.uom_id.id,
                'hs_code': getattr(line, 'hs_code', False) or False,
            }))
        return commands

    @staticmethod
    def _resolve_legacy_pi_commands(commands, current_ids=None):
        ids = set(current_ids or [])
        if not commands:
            return list(ids)
        for command in commands:
            if isinstance(command, int):
                ids.add(command)
                continue
            if not isinstance(command, (list, tuple)) or not command:
                continue
            op = command[0]
            if op == 6:
                ids = set(command[2] or [])
            elif op == 4:
                ids.add(command[1])
            elif op == 3:
                ids.discard(command[1])
            elif op == 5:
                ids.clear()
        return list(ids)

    @api.onchange('lc_order_id')
    def _onchange_lc_order_id_enterprise(self):
        if not self.lc_order_id:
            self.lc_order_ids = [(5, 0, 0)]
            self.product_line_ids = [(5, 0, 0)]
            return
        try:
            pi = self._validate_single_pi(self.lc_order_id)
        except ValidationError as exc:
            self.lc_order_id = False
            return {'warning': {'title': _('Invalid PI Selection'), 'message': str(exc)}}
        defaults = self._single_pi_defaults(pi)
        for key, value in defaults.items():
            setattr(self, key, value)
        self.lc_order_ids = [(6, 0, [pi.id])]
        self.product_line_ids = self._product_commands_from_pi(pi, clear=True)

    @api.constrains('lc_order_id', 'company_id')
    def _check_lc_order_consistency(self):
        for record in self:
            if record.lc_order_id:
                record._validate_single_pi(record.lc_order_id)
                if record.company_id != record.lc_order_id.company_id:
                    raise ValidationError(_('Import LC company must match the selected Proforma Invoice company.'))

    @api.constrains('lc_number')
    def _check_manual_lc_number(self):
        for record in self:
            if not record.lc_number or not record.lc_number.strip() or record.lc_number.strip().lower() == 'new':
                raise ValidationError(_('LC Number is mandatory and must be entered exactly as issued by the bank.'))

    @api.constrains(
        'lc_amount', 'lc_tolerance_percent', 'lc_conversion_rate',
        'lc_opening_date', 'lc_expiry_date', 'latest_shipment_date',
        'presentation_period_days',
    )
    def _check_lc_terms(self):
        for record in self:
            if record.lc_amount < 0:
                raise ValidationError(_('LC Amount cannot be negative.'))
            if not 0 <= record.lc_tolerance_percent <= 100:
                raise ValidationError(_('LC Tolerance must be between 0 and 100 percent.'))
            if record.lc_conversion_rate <= 0:
                raise ValidationError(_('LC Conversion Rate must be greater than zero.'))
            if record.lc_opening_date and record.lc_expiry_date and record.lc_opening_date > record.lc_expiry_date:
                raise ValidationError(_('LC Opening Date cannot be later than the Expiry Date.'))
            if record.latest_shipment_date and record.lc_expiry_date and record.latest_shipment_date > record.lc_expiry_date:
                raise ValidationError(_('Latest Shipment Date cannot be later than the LC Expiry Date.'))
            if record.presentation_period_days < 0:
                raise ValidationError(_('Document Presentation Period cannot be negative.'))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for raw in vals_list:
            vals = dict(raw)
            lc_number = (vals.get('lc_number') or '').strip()
            if not lc_number or lc_number.lower() == 'new':
                raise ValidationError(_('LC Number is mandatory. Enter the bank-issued LC Number; it is not auto-generated.'))
            vals['lc_number'] = lc_number

            pi_id = vals.get('lc_order_id')
            if not pi_id and vals.get('lc_order_ids'):
                pi_ids = self._resolve_legacy_pi_commands(vals.get('lc_order_ids'))
                if len(pi_ids) > 1:
                    raise ValidationError(_('Only one Proforma Invoice can be linked to an Import LC.'))
                pi_id = pi_ids[0] if pi_ids else False
            pi = self._validate_single_pi(self.env['lc.order'].browse(pi_id))
            vals['lc_order_id'] = pi.id
            vals['lc_order_ids'] = [(6, 0, [pi.id])]
            for key, value in self._single_pi_defaults(pi).items():
                vals.setdefault(key, value)
            vals['product_line_ids'] = self._product_commands_from_pi(pi, clear=True)
            vals.setdefault('lc_amount', sum(pi.lc_line_ids.mapped('subtotal')))
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        if 'state' in vals:
            target_state = vals['state']
            for record in self:
                allowed = (
                    record.state == target_state
                    or (record.state == 'draft' and target_state in {'confirmed', 'reject'})
                    or (record.state == 'confirmed' and target_state == 'done')
                )
                if not allowed:
                    raise ValidationError(_('Invalid Import LC status transition: %s to %s.') % (record.state, target_state))
        closed_immutable = set(vals) - {'state'}
        if closed_immutable and any(record.state == 'done' for record in self):
            raise ValidationError(_('A closed Import LC is locked and cannot be edited.'))
        immutable = closed_immutable - {'journal_entry_ids'}
        if immutable and any(record.state in ('confirmed', 'done', 'reject') for record in self) \
                and not (self.env.context.get('allow_approved_amendment') and self._user_is_lc_approver()):
            raise ValidationError(_('A confirmed Import LC is locked. Use an approved amendment for controlled changes.'))
        if 'lc_number' in vals:
            number = (vals.get('lc_number') or '').strip()
            if not number or number.lower() == 'new':
                raise ValidationError(_('LC Number is mandatory and cannot be "New".'))
            vals['lc_number'] = number

        legacy_pi_ids = None
        if 'lc_order_ids' in vals:
            legacy_pi_ids = self._resolve_legacy_pi_commands(vals['lc_order_ids'])
            if len(legacy_pi_ids) > 1:
                raise ValidationError(_('Only one Proforma Invoice can be linked to an Import LC.'))
            vals.pop('lc_order_ids')
            if 'lc_order_id' not in vals:
                vals['lc_order_id'] = legacy_pi_ids[0] if legacy_pi_ids else False

        if 'lc_order_id' in vals:
            if not vals['lc_order_id']:
                raise ValidationError(_('An Import LC must have one Proforma Invoice.'))
            for record in self:
                pi = record._validate_single_pi(self.env['lc.order'].browse(vals['lc_order_id']))
                local_vals = dict(vals)
                local_vals['lc_order_id'] = pi.id
                local_vals['lc_order_ids'] = [(6, 0, [pi.id])]
                for key, value in record._single_pi_defaults(pi).items():
                    local_vals.setdefault(key, value)
                local_vals['product_line_ids'] = record._product_commands_from_pi(pi, clear=True)
                super(ImportLC, record).write(local_vals)
            return True
        return super().write(vals)

    def action_confirm(self):
        if not self._user_is_lc_approver():
            raise AccessError(_('Only LC Approvers can confirm Import LCs.'))
        for record in self:
            if record.state != 'draft':
                raise ValidationError(_('Only a draft Import LC can be confirmed.'))
            pi = record._validate_single_pi(record.lc_order_id)
            if record.lc_amount <= 0:
                raise ValidationError(_('Enter a positive LC Amount before confirmation.'))
            po = pi.po_number
            if not po:
                raise ValidationError(_('The selected PI does not have an RFQ/PO.'))
            if po.state == 'cancel':
                raise ValidationError(_('Cancelled RFQ/PO cannot be confirmed through LC: %s') % po.name)
            record.write({'state': 'confirmed'})
            if po.state in ('draft', 'sent', 'proforma', 'to approve'):
                po.button_confirm()
        return True

    def action_close(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise ValidationError(_('Only a confirmed Import LC can be closed.'))

        # Closing is the terminal point of the import cycle.  Every incoming
        # GRN linked to the LC's PO must be completed first; a missing GRN is
        # also treated as incomplete rather than allowing a premature close.
        grns = self.grn_ids.filtered(lambda picking: picking.state != 'cancel')
        if not grns:
            raise ValidationError(_('This LC cannot be closed until at least one GRN is created and completed.'))
        pending_grns = grns.filtered(lambda picking: picking.state != 'done')
        if pending_grns:
            raise ValidationError(_(
                'Complete all GRNs before closing this LC. Pending GRN(s): %s'
            ) % ', '.join(pending_grns.mapped('name')))

        # Only non-cancelled vendor bills count.  Every such bill must be
        # fully paid; draft, posted-unpaid and partially paid bills block LC
        # closure.
        bills = self.invoice_ids.filtered(
            lambda bill: bill.move_type == 'in_invoice' and bill.state != 'cancel'
        )
        if not bills:
            raise ValidationError(_('This LC cannot be closed until a Vendor Bill is created and paid.'))
        unpaid_bills = bills.filtered(lambda bill: bill.payment_state != 'paid')
        if unpaid_bills:
            raise ValidationError(_(
                'Pay all Vendor Bills before closing this LC. Unpaid bill(s): %s'
            ) % ', '.join(unpaid_bills.mapped('name')))

        self.write({'state': 'done'})
        return True

    @api.depends('ci_ids.bill_ids', 'ci_ids.bill_ids.state', 'ci_ids.bill_ids.move_type')
    def _compute_invoice_ids(self):
        for record in self:
            bills = record.ci_ids.mapped('bill_ids').filtered(
                lambda bill: bill.move_type == 'in_invoice' and bill.state != 'cancel'
            )
            record.invoice_ids = bills

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    def action_view_vendor_bills(self):
        self.ensure_one()
        bills = self.invoice_ids
        action = self.env.ref('account.action_move_in_invoice_type').read()[0]
        action['domain'] = [('id', 'in', bills.ids)]
        action['context'] = {'default_move_type': 'in_invoice', 'default_partner_id': self.supplier_id.id or False}
        return action

    def action_create_vendor_bill_from_ci(self):
        self.ensure_one()
        active_cis = self.ci_ids.filtered(lambda ci: ci.state != 'cancel')
        if len(active_cis) == 1:
            return active_cis.action_create_vendor_bill()
        action = self.env.ref('zencore_import_lc.action_import_ci').read()[0]
        action['domain'] = [('import_lc_id', '=', self.id), ('state', '!=', 'cancel')]
        action['context'] = {'default_import_lc_id': self.id, 'default_lc_order_id': self.lc_order_id.id}
        return action

    def action_create_commercial_invoice(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise ValidationError(_('Commercial Invoices can only be created for a confirmed Import LC.'))
        if not self._has_available_ci_quantity():
            raise ValidationError(_('No product quantity remains available for another Commercial Invoice.'))
        return {
            'name': _('Create Commercial Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.ci',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_import_lc_id': self.id,
                'default_lc_order_id': self.lc_order_id.id,
            },
        }

    def action_view_commercial_invoices(self):
        self.ensure_one()
        action = self.env.ref('zencore_import_lc.action_import_ci').read()[0]
        action['domain'] = [('import_lc_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    def action_view_landed_costs(self):
        self.ensure_one()
        return {
            'name': _('Landed Costs'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.landed.cost',
            'view_mode': 'list,form',
            'domain': [('import_lc_id', '=', self.id)],
            'context': {
                'default_import_lc_id': self.id,
                'default_company_id': self.company_id.id,
                'create': self.state != 'done',
                'edit': self.state != 'done',
            },
        }

    @api.depends(
        'lc_order_id', 'lc_order_id.po_number',
        'lc_order_id.po_number.picking_ids',
        'lc_order_id.po_number.picking_ids.state',
        'lc_order_id.po_number.picking_ids.picking_type_id.code',
    )
    def _compute_grn_ids(self):
        Picking = self.env['stock.picking']
        for record in self:
            po = record.lc_order_id.po_number if record.lc_order_id else False
            pickings = Picking
            if po:
                pickings = Picking.search([
                    ('purchase_id', '=', po.id),
                    ('picking_type_code', '=', 'incoming'),
                    ('state', '!=', 'cancel'),
                ])
            record.grn_ids = pickings
            record.grn_count = len(pickings)

    @api.depends('lc_order_id.po_number.state')
    def _compute_po_state(self):
        for record in self:
            record.po_state = record.lc_order_id.po_number.state if record.lc_order_id and record.lc_order_id.po_number else False

    @api.depends(
        'lc_number', 'supplier_id', 'state', 'lc_order_id.pi_number',
        'lc_order_id.po_number', 'ci_ids.ci_number', 'ci_ids.receipt_ids',
        'ci_ids.bill_ids', 'grn_ids'
    )
    def _compute_document_chain_summary(self):
        for record in self:
            pi = record.lc_order_id
            po = pi.po_number if pi else False
            cis = record.ci_ids.filtered(lambda c: c.state != 'cancel')
            lines = [
                '=' * 72,
                'IMPORT LC - PI / PO / CI / BILL / RECEIPT TRACEABILITY',
                '=' * 72,
                f"LC NUMBER : {record.lc_number or 'N/A'}",
                f"SUPPLIER  : {record.supplier_id.display_name if record.supplier_id else 'N/A'}",
                f"STATUS    : {(record.state or '').upper() or 'N/A'}",
                f"PI        : {pi.pi_number if pi else 'N/A'}",
                f"PO        : {po.name if po else 'N/A'}",
                '',
            ]
            if pi:
                lines.append(f"PI Amount : {sum(pi.lc_line_ids.mapped('subtotal')):,.2f} {pi.currency_id.name if pi.currency_id else ''}")
                lines.append(f"CIs       : {len(cis)}")
                for ci in cis.sorted(lambda c: (c.ci_date or fields.Date.today(), c.id)):
                    active_bills = ci.bill_ids.filtered(lambda b: b.state != 'cancel')
                    receipts = ci.receipt_ids.filtered(lambda p: p.state != 'cancel')
                    lines.append(f"  - CI {ci.ci_number or 'N/A'} | Bills: {len(active_bills)} | Receipts: {len(receipts)}")
                lines.append(f"PO GRNs   : {len(record.grn_ids)}")
            else:
                lines.append('No approved PI is linked to this LC.')
            lines.extend(['', '=' * 72, 'END OF TRACEABILITY', '=' * 72])
            record.document_chain_summary = '\n'.join(lines)


class ImportLCProductLine(models.Model):
    _inherit = 'import.lc.product.line'

    lc_order_id = fields.Many2one('lc.order', string='Source PI', ondelete='restrict', index=True)
    po_line_id = fields.Many2one('purchase.order.line', string='Source PO Line', ondelete='restrict', index=True)
    currency_id = fields.Many2one(
        'res.currency', related='import_lc_id.currency_id', store=True, readonly=True,
    )
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', help='Unit copied from the source PI/PO line.')
    hs_code = fields.Char(string='HS Code', help='Customs HS code required for the import declaration.')


class ImportCI(models.Model):
    _inherit = 'import.ci'

    state = fields.Selection(
        selection_add=[('confirmed', 'Confirmed'), ('paid', 'Paid'), ('cancel',)],
        ondelete={'confirmed': 'set default', 'paid': 'set default'},
    )

    lc_order_id = fields.Many2one(
        'lc.order', string='PI Number', required=False, tracking=True, ondelete='restrict', check_company=True,
        help='PI inherited automatically from the selected Import LC.'
    )
    pi_number = fields.Char(related='lc_order_id.pi_number', string='PI Number (Text)', store=True, readonly=True)
    departure_port_id = fields.Many2one('import.lc.port', string='Departure Port', tracking=True)
    arrival_port_id = fields.Many2one('import.lc.port', string='Arrival Port', tracking=True)
    container_type_id = fields.Many2one('import.lc.container.type', string='Container Type', tracking=True)
    container_id = fields.Many2one('import.lc.container', string='Configured Container', tracking=True)
    container_reference = fields.Char(string='Container / Shipment Reference', tracking=True)
    receipt_ids = fields.One2many('stock.picking', 'import_ci_id', string='Receipts')
    receipt_count = fields.Integer(compute='_compute_receipt_count')

    @api.depends('receipt_ids', 'receipt_ids.state')
    def _compute_receipt_count(self):
        for record in self:
            record.receipt_count = len(record.receipt_ids.filtered(lambda p: p.state != 'cancel'))

    def _pi_header_values(self, pi):
        lc = self.import_lc_id if len(self) == 1 else False
        return {
            'supplier_id': pi.vendor_id.id or False,
            'currency_id': pi.currency_id.id or False,
            'purchase_order_id': pi.po_number.id or False,
            'po_number': pi.po_number.name if pi.po_number else False,
            'cnf_agent_id': (lc.cnf_agent_id.id if lc and lc.cnf_agent_id else pi.cnf_agent_id.id) or False,
            'departure_port_id': pi.port_of_shipment_id.id or False,
            'arrival_port_id': pi.destination_port_id.id or False,
            'departure_port': pi.port_of_shipment_id.display_name if pi.port_of_shipment_id else (pi.port_of_shipment or False),
            'arrival_port': pi.destination_port_id.display_name if pi.destination_port_id else (pi.destination_port or False),
            'container_type_id': pi.container_type_id.id or False,
            'container_id': pi.container_id.id or False,
            'container_reference': pi.container_reference or False,
        }

    def _effective_quantity_amendment(self, lc):
        if not lc:
            return self.env['import.lc.amendment']
        return self.env['import.lc.amendment'].search([
            ('import_lc_id', '=', lc.id),
            ('state', '=', 'approved'),
            ('amendment_type', '=', 'quantity'),
        ], order='approved_date desc, id desc', limit=1)

    def _ci_line_commands(self, pi, clear=True, lc=None):
        commands = [(5, 0, 0)] if clear else []
        lc = lc or (self.import_lc_id if len(self) == 1 else False)
        amendment = self._effective_quantity_amendment(lc)
        amended_by_po_line = {}
        amended_by_product = {}
        if amendment:
            for amd_line in amendment.product_line_ids.filtered(lambda l: not l.lc_order_id or l.lc_order_id == pi):
                if amd_line.po_line_id:
                    amended_by_po_line[amd_line.po_line_id.id] = amd_line.new_quantity
                elif amd_line.product_id and lc and lc.lc_order_id == pi:
                    amended_by_product[amd_line.product_id.id] = amd_line.new_quantity
        for line in pi.lc_line_ids.filtered('product_id'):
            effective_qty = amended_by_po_line.get(
                line.po_line_id.id if line.po_line_id else 0,
                amended_by_product.get(line.product_id.id, line.quantity),
            )
            commands.append((0, 0, {
                'lc_order_line_id': line.id,
                'po_line_id': line.po_line_id.id or False,
                'product_id': line.product_id.id,
                'product_name': line.product_id.display_name,
                'product_category_id': line.product_category_id.id or line.product_id.categ_id.id,
                'lc_quantity': effective_qty,
                'ci_quantity': 0.0,
                'unit_price': line.unit_price,
                'uom_id': line.product_uom_id.id or line.product_id.uom_id.id,
            }))
        return commands

    def _check_lc_amount_limit(self):
        for ci in self:
            lc = ci.import_lc_id
            if lc and lc.lc_amount > 0 and lc.lc_available_amount < -0.00001:
                raise ValidationError(_(
                    'CI amount exceeds the available Import LC value for %s. '
                    'Available amount: %.2f %s.'
                ) % (lc.lc_number, lc.lc_available_amount, lc.currency_id.name or ''))

    @api.onchange('import_lc_id')
    def _onchange_import_lc_id(self):
        self.lc_order_id = False
        self.product_line_ids = [(5, 0, 0)]
        self.amendment_id = False
        self.purchase_order_id = False
        self.po_number = False
        if not self.import_lc_id:
            return
        self.cnf_agent_id = self.import_lc_id.cnf_agent_id
        self.lc_order_id = self.import_lc_id.lc_order_id
        if self.lc_order_id:
            return self._onchange_lc_order_id_enterprise()

    @api.onchange('lc_order_id')
    def _onchange_lc_order_id_enterprise(self):
        self.product_line_ids = [(5, 0, 0)]
        if not self.lc_order_id:
            return
        if self.import_lc_id and self.lc_order_id != self.import_lc_id.lc_order_id:
            self.lc_order_id = self.import_lc_id.lc_order_id
            return {'warning': {'title': _('Invalid PI'), 'message': _('The PI must match the selected Import LC.')}}
        values = self._pi_header_values(self.lc_order_id)
        for key, value in values.items():
            setattr(self, key, value)
        if self.import_lc_id:
            latest = self.env['import.lc.amendment'].search([
                ('import_lc_id', '=', self.import_lc_id.id),
                ('state', '=', 'approved'),
            ], order='approved_date desc, id desc', limit=1)
            self.amendment_id = latest or False
        self.product_line_ids = self._ci_line_commands(self.lc_order_id, clear=True, lc=self.import_lc_id)

    @api.constrains('import_lc_id', 'lc_order_id')
    def _check_ci_pi_link(self):
        for record in self:
            if record.import_lc_id and record.lc_order_id != record.import_lc_id.lc_order_id:
                raise ValidationError(_('CI PI must match the single PI linked to the selected Import LC.'))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for raw in vals_list:
            vals = dict(raw)
            lc = self.env['import.lc'].browse(vals.get('import_lc_id')).exists() if vals.get('import_lc_id') else False
            if not lc or not lc.lc_order_id:
                raise ValidationError(_('Select an Import LC with a linked Proforma Invoice before saving a Commercial Invoice.'))
            pi = lc.lc_order_id
            requested_pi = self.env['lc.order'].browse(vals.get('lc_order_id')).exists() if vals.get('lc_order_id') else False
            if requested_pi and requested_pi != pi:
                raise ValidationError(_('The Commercial Invoice PI must match the single PI linked to the Import LC.'))
            vals['lc_order_id'] = pi.id
            # Build deterministic downstream references from the selected PI.
            vals.update({
                'supplier_id': pi.vendor_id.id or False,
                'currency_id': pi.currency_id.id or False,
                'purchase_order_id': pi.po_number.id or False,
                'po_number': pi.po_number.name if pi.po_number else False,
                'cnf_agent_id': vals.get('cnf_agent_id') or lc.cnf_agent_id.id or pi.cnf_agent_id.id or False,
                'departure_port_id': vals.get('departure_port_id') or pi.port_of_shipment_id.id or False,
                'arrival_port_id': vals.get('arrival_port_id') or pi.destination_port_id.id or False,
                'departure_port': vals.get('departure_port') or (pi.port_of_shipment_id.display_name if pi.port_of_shipment_id else pi.port_of_shipment),
                'arrival_port': vals.get('arrival_port') or (pi.destination_port_id.display_name if pi.destination_port_id else pi.destination_port),
                'container_type_id': vals.get('container_type_id') or pi.container_type_id.id or False,
                'container_id': vals.get('container_id') or pi.container_id.id or False,
                'container_reference': vals.get('container_reference') or pi.container_reference or False,
            })
            if not vals.get('amendment_id'):
                latest = self.env['import.lc.amendment'].search([
                    ('import_lc_id', '=', lc.id),
                    ('state', '=', 'approved'),
                ], order='approved_date desc, id desc', limit=1)
                vals['amendment_id'] = latest.id or False
            if not vals.get('product_line_ids'):
                vals['product_line_ids'] = self._ci_line_commands(pi, clear=False, lc=lc)
            prepared.append(vals)
        records = super().create(prepared)
        records._check_lc_amount_limit()
        return records

    def write(self, vals):
        vals = dict(vals)
        immutable = set(vals) - {'state', 'cancelled_by', 'cancelled_date'}
        if immutable and any(record.state != 'draft' for record in self):
            raise ValidationError(_('A confirmed Commercial Invoice is locked and cannot be edited.'))
        if 'import_lc_id' in vals or 'lc_order_id' in vals:
            for record in self:
                lc = self.env['import.lc'].browse(vals.get('import_lc_id', record.import_lc_id.id)).exists()
                if not lc or not lc.lc_order_id:
                    raise ValidationError(_('Select an Import LC with a linked Proforma Invoice.'))
                pi = lc.lc_order_id
                requested_pi = self.env['lc.order'].browse(vals.get('lc_order_id')).exists() if vals.get('lc_order_id') else False
                if requested_pi and requested_pi != pi:
                    raise ValidationError(_('The Commercial Invoice PI must match the single PI linked to the Import LC.'))
                local = dict(vals)
                local.update({
                    'lc_order_id': pi.id,
                    'supplier_id': pi.vendor_id.id or False,
                    'currency_id': pi.currency_id.id or False,
                    'purchase_order_id': pi.po_number.id or False,
                    'po_number': pi.po_number.name if pi.po_number else False,
                    'departure_port_id': pi.port_of_shipment_id.id or False,
                    'arrival_port_id': pi.destination_port_id.id or False,
                    'departure_port': pi.port_of_shipment_id.display_name if pi.port_of_shipment_id else pi.port_of_shipment,
                    'arrival_port': pi.destination_port_id.display_name if pi.destination_port_id else pi.destination_port,
                    'container_type_id': pi.container_type_id.id or False,
                    'container_id': pi.container_id.id or False,
                    'container_reference': pi.container_reference or False,
                    'product_line_ids': record._ci_line_commands(pi, clear=True, lc=lc),
                })
                super(ImportCI, record).write(local)
            self._check_lc_amount_limit()
            return True
        result = super().write(vals)
        self._check_lc_amount_limit()
        return result

    def _sync_payment_stage(self):
        """Keep the CI stage aligned with its active Vendor Bill payment."""
        for record in self:
            active_bills = record.bill_ids.filtered(
                lambda bill: bill.move_type == 'in_invoice' and bill.state != 'cancel'
            )
            all_paid = bool(active_bills) and all(
                bill.payment_state == 'paid' for bill in active_bills
            )
            if all_paid and record.state == 'confirmed':
                record.with_context(allow_ci_state_transition=True).write({'state': 'paid'})
            elif not all_paid and record.state == 'paid':
                record.with_context(allow_ci_state_transition=True).write({'state': 'confirmed'})

    def action_view_vendor_bills(self):
        self.ensure_one()
        bills = self.bill_ids.filtered(lambda b: b.move_type == 'in_invoice' and b.state != 'cancel')
        if len(bills) == 1:
            return {
                'name': _('Vendor Bill'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': bills.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'name': _('Vendor Bills'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bills.ids)],
            'context': {
                'default_move_type': 'in_invoice',
                'default_partner_id': self.supplier_id.id or False,
                'default_import_ci_id': self.id,
            },
        }

    def action_confirm(self):
        """Confirm the Commercial Invoice before downstream processing."""
        self.ensure_one()
        if not self._user_is_lc_approver():
            raise AccessError(_('Only LC Approvers can confirm Commercial Invoices.'))
        if self.state != 'draft':
            raise ValidationError(_('Only a draft Commercial Invoice can be confirmed.'))
        if not self.import_lc_id or not self.lc_order_id:
            raise ValidationError(_('Link the Commercial Invoice to an Import LC and Proforma Invoice before confirming.'))
        if not self.product_line_ids:
            raise ValidationError(_('Add at least one product line before confirming the Commercial Invoice.'))
        self.with_context(allow_ci_state_transition=True).write({'state': 'confirmed'})
        return True

    def action_create_vendor_bill(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise ValidationError(_('Confirm the Commercial Invoice before creating the Vendor Bill.'))
        existing = self.bill_ids.filtered(lambda b: b.state != 'cancel')
        if existing:
            raise ValidationError(_(
                'A Vendor Bill already exists for this Commercial Invoice. '
                'Delete or cancel that bill before creating a new one.'
            ))
        if not self.purchase_order_id:
            raise ValidationError(_('The selected PI has no RFQ/PO, so a Vendor Bill cannot be linked correctly.'))

        billed_by_key = defaultdict(float)
        for bill in existing:
            for invoice_line in bill.invoice_line_ids:
                key = invoice_line.purchase_line_id.id if invoice_line.purchase_line_id else invoice_line.product_id.id
                billed_by_key[key] += invoice_line.quantity

        billable_lines = []
        for line in self.product_line_ids.filtered(lambda l: l.ci_quantity > 0):
            key = line.po_line_id.id if line.po_line_id else line.product_id.id
            billable_qty = line.ci_quantity - billed_by_key.get(key, 0.0)
            if billable_qty > 0.00001:
                billable_lines.append((line, billable_qty))
        if not billable_lines:
            raise ValidationError(_('No unbilled quantity is available for a Vendor Bill.'))
        invoice_lines = []
        for line, billable_qty in billable_lines:
            if line.unit_price <= 0:
                raise ValidationError(_('Unit price must be greater than zero for %s.') % line.product_id.display_name)
            # Let stock_account choose the bill account from the linked PO line
            # and product valuation settings; forcing the expense account here
            # bypasses Stock Valuation for perpetual stockable products.
            values = {
                'product_id': line.product_id.id,
                'name': line.product_name or line.product_id.display_name,
                'quantity': billable_qty,
                'price_unit': line.unit_price,
                'product_uom_id': line.uom_id.id or line.product_id.uom_id.id,
                'purchase_line_id': line.po_line_id.id or False,
            }
            if line.product_id.supplier_taxes_id:
                values['tax_ids'] = [(6, 0, line.product_id.supplier_taxes_id.ids)]
            invoice_lines.append((0, 0, values))
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.supplier_id.id,
            'invoice_date': self.ci_date or fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'ref': self.ci_number,
            'invoice_origin': self.purchase_order_id.name,
            'purchase_id': self.purchase_order_id.id,
            'import_ci_id': self.id,
            'invoice_line_ids': invoice_lines,
        })
        return {
            'name': _('Vendor Bill'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_receipts(self):
        self.ensure_one()
        return {
            'name': _('CI Receipts'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('import_ci_id', '=', self.id)],
        }


class ImportCIProductLine(models.Model):
    _inherit = 'import.ci.product.line'

    lc_order_line_id = fields.Many2one('lc.order.line', string='Source PI Line', ondelete='restrict', index=True)
    po_line_id = fields.Many2one('purchase.order.line', string='Source PO Line', ondelete='restrict', index=True)
    currency_id = fields.Many2one(
        'res.currency', related='import_ci_id.currency_id', store=True, readonly=True,
    )

    @api.constrains('ci_quantity', 'unit_price', 'import_ci_id')
    def _check_ci_lc_amount(self):
        self.mapped('import_ci_id')._check_lc_amount_limit()

    @api.depends('lc_quantity', 'ci_quantity', 'import_ci_id', 'import_ci_id.import_lc_id',
                 'import_ci_id.lc_order_id', 'product_id')
    def _compute_available_quantity(self):
        """PI-scoped utilization: each PI consumes only its own LC allocation."""
        for line in self:
            ci = line.import_ci_id
            if not ci or not ci.import_lc_id or not ci.lc_order_id or not line.product_id:
                line.available_quantity = line.lc_quantity - line.ci_quantity
                continue
            domain = [
                ('import_ci_id.import_lc_id', '=', ci.import_lc_id.id),
                ('import_ci_id.lc_order_id', '=', ci.lc_order_id.id),
                ('import_ci_id.state', '!=', 'cancel'),
                ('product_id', '=', line.product_id.id),
            ]
            if line.po_line_id:
                domain.append(('po_line_id', '=', line.po_line_id.id))
            previous_lines = self.search(domain)
            if line.id:
                previous_lines -= line
            used_elsewhere = sum(previous_lines.mapped('ci_quantity'))
            line.available_quantity = line.lc_quantity - used_elsewhere - line.ci_quantity

    def _trigger_cascade_update(self):
        for line in self:
            ci = line.import_ci_id
            if not ci or not ci.import_lc_id or not ci.lc_order_id or not line.product_id:
                continue
            domain = [
                ('import_ci_id.import_lc_id', '=', ci.import_lc_id.id),
                ('import_ci_id.lc_order_id', '=', ci.lc_order_id.id),
                ('import_ci_id.state', '!=', 'cancel'),
                ('product_id', '=', line.product_id.id),
            ]
            if line.po_line_id:
                domain.append(('po_line_id', '=', line.po_line_id.id))
            siblings = self.search(domain)
            siblings.invalidate_recordset(['available_quantity'])
            siblings._compute_available_quantity()


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    import_ci_id = fields.Many2one('import.ci', string='Commercial Invoice', tracking=True, ondelete='restrict', index=True)

    def copy_data(self, default=None):
        default = dict(default or {})
        if len(self) == 1 and self.import_ci_id and 'import_ci_id' not in default:
            default['import_ci_id'] = False
        return super().copy_data(default)

    def copy(self, default=None):
        default = dict(default or {})
        # A backorder represents the quantity still waiting for a later CI.
        if self.import_ci_id and 'import_ci_id' not in default:
            default['import_ci_id'] = False
        return super().copy(default)

    def button_validate(self):
        for picking in self.filtered(lambda p: p.import_ci_id and p.picking_type_code == 'incoming'):
            ci = picking.import_ci_id
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure') or 2
            active_moves = picking.move_ids.filtered(lambda m: m.state != 'cancel')
            move_po_line_ids = set(active_moves.mapped('purchase_line_id').ids)
            move_product_ids = set(active_moves.mapped('product_id').ids)
            expected_by_po_line = defaultdict(float)
            expected_by_product = defaultdict(float)
            for line in ci.product_line_ids.filtered(lambda l: l.ci_quantity > 0):
                # Service/non-stock lines do not belong to the receipt and are ignored here.
                if line.po_line_id and line.po_line_id.id in move_po_line_ids:
                    expected_by_po_line[line.po_line_id.id] += line.ci_quantity
                    expected_by_product[line.product_id.id] += line.ci_quantity
                elif not line.po_line_id and line.product_id.id in move_product_ids:
                    expected_by_product[line.product_id.id] += line.ci_quantity

            actual_by_po_line = defaultdict(float)
            actual_by_product = defaultdict(float)
            for move in active_moves:
                actual_qty = move.quantity
                if move.purchase_line_id:
                    actual_by_po_line[move.purchase_line_id.id] += actual_qty
                actual_by_product[move.product_id.id] += actual_qty

            if expected_by_po_line:
                for po_line_id, expected in expected_by_po_line.items():
                    actual = actual_by_po_line.get(po_line_id, 0.0)
                    if float_compare(actual, expected, precision_digits=precision) != 0:
                        product = self.env['purchase.order.line'].browse(po_line_id).product_id.display_name
                        raise ValidationError(_(
                            'Receipt quantity must match CI %s.\n%s: CI Qty = %s, Receipt Qty = %s'
                        ) % (ci.ci_number, product, expected, actual))
            else:
                for product_id, expected in expected_by_product.items():
                    actual = actual_by_product.get(product_id, 0.0)
                    if float_compare(actual, expected, precision_digits=precision) != 0:
                        product = self.env['product.product'].browse(product_id).display_name
                        raise ValidationError(_(
                            'Receipt quantity must match CI %s.\n%s: CI Qty = %s, Receipt Qty = %s'
                        ) % (ci.ci_number, product, expected, actual))

            for product_id, actual in actual_by_product.items():
                expected = expected_by_product.get(product_id, 0.0)
                if actual > 0 and float_compare(actual, expected, precision_digits=precision) != 0:
                    product = self.env['product.product'].browse(product_id).display_name
                    raise ValidationError(_(
                        'Receipt has quantity not covered by CI %s.\n%s: CI Qty = %s, Receipt Qty = %s'
                    ) % (ci.ci_number, product, expected, actual))
        return super().button_validate()


class AccountMoveEnterprise(models.Model):
    _inherit = 'account.move'

    def _check_closed_import_lc(self):
        if any(move.import_lc_id.state == 'done' for move in self.filtered('import_lc_id')):
            raise ValidationError(_('Journal entries and Vendor Bills linked to a closed Import LC are read-only.'))

    @api.model_create_multi
    def create(self, vals_list):
        lc_ids = [vals.get('import_lc_id') for vals in vals_list if vals.get('import_lc_id')]
        closed_lcs = self.env['import.lc'].browse(lc_ids).filtered(lambda lc: lc.state == 'done')
        if closed_lcs:
            raise ValidationError(_('A closed Import LC is read-only; no new accounting entry can be linked to it.'))
        records = super().create(vals_list)
        records._check_closed_import_lc()
        return records

    def write(self, vals):
        self._check_closed_import_lc()
        return super().write(vals)

    def unlink(self):
        self._check_closed_import_lc()
        return super().unlink()

    @api.depends(
        'ref', 'narration', 'move_type', 'company_id', 'import_ci_id',
        'purchase_id',
    )
    def _compute_import_lc_id(self):
        for record in self:
            # Preserve the LC explicitly selected on a manual journal entry.
            # Bills generated from a CI take precedence, followed by the
            # single LC linked to a purchase order.
            manual_lc = (
                record.import_lc_id
                if record.import_lc_id and record.import_lc_id.company_id == record.company_id
                else False
            )
            lc = record.import_ci_id.import_lc_id if record.import_ci_id else manual_lc
            if not lc and record.purchase_id:
                purchase_lcs = record.purchase_id.import_lc_ids.filtered(
                    lambda candidate: candidate.company_id == record.company_id
                    and candidate.state != 'reject'
                )
                if len(purchase_lcs) == 1:
                    lc = purchase_lcs
            if not lc and record.move_type == 'entry' and record.ref:
                lc = self.env['import.lc'].search([
                    ('company_id', '=', record.company_id.id),
                    '|',
                    ('lc_number', '=', record.ref),
                    ('lc_order_id.pi_number', '=', record.ref),
                ], order='id desc', limit=1)
            record.import_lc_id = lc

    @api.depends(
        'currency_id', 'company_currency_id', 'company_id', 'invoice_date', 'date', 'move_type',
        'import_lc_id', 'import_lc_id.currency_id', 'import_lc_id.lc_conversion_rate',
    )
    def _compute_invoice_currency_rate(self):
        """Use the LC-negotiated rate on draft vendor bills.

        LC/PI stores ``company currency per one document currency`` (for
        example 122 BDT for 1 USD).  Odoo's ``invoice_currency_rate`` stores
        the inverse, company currency -> document currency, hence ``1 / rate``.
        """
        super()._compute_invoice_currency_rate()
        for move in self:
            lc = move.import_lc_id
            if (
                move.state == 'draft'
                and move.is_invoice(include_receipts=True)
                and lc
                and move.currency_id == lc.currency_id
                and move.currency_id != move.company_currency_id
                and lc.lc_conversion_rate > 0
            ):
                move.invoice_currency_rate = 1.0 / lc.lc_conversion_rate

    def _compute_payment_state(self):
        super()._compute_payment_state()
        commercial_invoices = self.filtered(
            lambda move: move.move_type == 'in_invoice' and move.import_ci_id
        ).mapped('import_ci_id')
        if commercial_invoices:
            commercial_invoices._sync_payment_stage()

    def unlink(self):
        commercial_invoices = self.filtered('import_ci_id').mapped('import_ci_id')
        result = super().unlink()
        if commercial_invoices:
            commercial_invoices._sync_payment_stage()
        return result


class AccountMoveLineEnterprise(models.Model):
    _inherit = 'account.move.line'

    @api.depends(
        'move_id.currency_id', 'move_id.import_lc_id',
        'move_id.import_lc_id.currency_id', 'move_id.move_type',
    )
    def _compute_currency_id(self):
        super()._compute_currency_id()
        for line in self:
            move = line.move_id
            lc = move.import_lc_id
            if (
                move.state == 'draft'
                and move.move_type == 'entry'
                and lc
                and lc.currency_id != line.company_currency_id
            ):
                # Other-charge journal entries created from an LC use the PI
                # currency on every line; the LC-specific rate below converts
                # those USD amounts to company-currency balances.
                line.currency_id = lc.currency_id

    @api.depends(
        'currency_id', 'company_id', 'move_id.date', 'move_id.invoice_date',
        'move_id.invoice_currency_rate', 'move_id.import_lc_id',
        'move_id.import_lc_id.currency_id', 'move_id.import_lc_id.lc_conversion_rate',
    )
    def _compute_currency_rate(self):
        """Apply the same LC rate to invoice and manual journal-entry lines."""
        super()._compute_currency_rate()
        for line in self:
            move = line.move_id
            lc = move.import_lc_id
            if (
                move.state == 'draft'
                and lc
                and line.currency_id == lc.currency_id
                and line.currency_id != line.company_currency_id
                and lc.lc_conversion_rate > 0
            ):
                line.currency_rate = 1.0 / lc.lc_conversion_rate


class ImportLCAmendment(models.Model):
    _inherit = 'import.lc.amendment'

    # Make the LC selector explicit and searchable from the standalone Amendment menu.
    import_lc_id = fields.Many2one(
        'import.lc', string='LC Number', required=True, tracking=True, ondelete='cascade', check_company=True,
        domain="[('state', '!=', 'reject')]",
        help='Select the exact Import LC to amend.'
    )

    def _load_lc_products(self):
        """Load the current LC quantity snapshot for the LC's single PI.

        Quantity amendments change the LC allocation, not the latest shipment.
        Therefore the baseline is the latest approved quantity amendment, then
        the original LC product lines. Each line retains its Source PI/PO line.
        """
        self.ensure_one()
        if not self.import_lc_id:
            return False
        previous = self.env['import.lc.amendment'].search([
            ('import_lc_id', '=', self.import_lc_id.id),
            ('state', '=', 'approved'),
            ('amendment_type', '=', 'quantity'),
            ('id', '!=', self.id),
        ], order='approved_date desc, id desc', limit=1)
        commands = [(5, 0, 0)]
        if previous and previous.product_line_ids:
            for line in previous.product_line_ids:
                commands.append((0, 0, {
                    'lc_order_id': line.lc_order_id.id or False,
                    'po_line_id': line.po_line_id.id or False,
                    'product_id': line.product_id.id or False,
                    'product_name': line.product_name or line.product_id.display_name,
                    'original_quantity': line.new_quantity,
                    'new_quantity': line.new_quantity,
                    'unit_price': line.unit_price,
                }))
        else:
            for line in self.import_lc_id.product_line_ids.filtered('product_id'):
                commands.append((0, 0, {
                    'lc_order_id': line.lc_order_id.id or False,
                    'po_line_id': line.po_line_id.id or False,
                    'product_id': line.product_id.id,
                    'product_name': line.product_name or line.product_id.display_name,
                    'original_quantity': line.quantity,
                    'new_quantity': line.quantity,
                    'unit_price': line.unit_price,
                }))
        if len(commands) == 1:
            raise ValidationError(_('The selected LC has no product lines available for a quantity amendment.'))
        self.product_line_ids = commands
        return True


class ImportLCAmendmentLineEnterprise(models.Model):
    _inherit = 'import.lc.amendment.line'

    lc_order_id = fields.Many2one('lc.order', string='Source PI', readonly=True, ondelete='restrict', index=True)
    po_line_id = fields.Many2one('purchase.order.line', string='Source PO Line', readonly=True, ondelete='restrict', index=True)
