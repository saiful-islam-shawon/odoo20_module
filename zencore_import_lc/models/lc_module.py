import logging
from odoo import models, fields, api
from datetime import date
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    
    lc_order_id = fields.Many2one('lc.order', string='LC Reference', readonly=True)

class LCOrder(models.Model):
    _name = 'lc.order'
    _description = 'Letter of Credit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'pi_number'
    _order = 'id desc'  
    

    name = fields.Char(string='PC Number', default='New')
    
    po_number = fields.Many2one('purchase.order', string='Work Order', tracking=True, check_company=True)
    vendor_id = fields.Many2one('res.partner', string='Supplier', related='po_number.partner_id', store=True, tracking=True)
    pi_number = fields.Char(string='PI Number', tracking=True)
    attachment_count = fields.Integer(
        string='Documents',
        compute='_compute_attachment_count',
        help='Number of optional supplier documents attached to this Proforma Invoice.',
    )
    pi_document_ids = fields.One2many(
        'lc.order.document',
        'lc_order_id',
        string='Supplier PI Documents',
        help='Optional supplier proforma invoice documents and supporting files.',
    )
    
    
    is_current_user_approver = fields.Boolean(
        string='Is Current User Approver',
        compute='_compute_is_current_user_approver',
        store=False
    )
    
    
    import_lc_id = fields.Many2one(
         'import.lc',
        string='Import LC',
         tracking=True,
        ondelete='restrict'
     )
    import_lc_ids = fields.Many2many(
        'import.lc',
        'lc_order_import_lc_rel',
        'lc_order_id',
        'import_lc_id',
        string='Import LCs',
        tracking=True,
        help='Import LCs linked to this LC Order'
    )
    bank_id = fields.Many2one('res.bank', string='Advising Bank', tracking=True)
    pi_date = fields.Date(string='PI Date', default=fields.Date.today, tracking=True)
    expected_lc_opening_date = fields.Date(string='Expected LC Opening Date', default=fields.Date.today, tracking=True)
    
    # Lines - readonly controlled by view, not here
    lc_line_ids = fields.One2many('lc.order.line', 'lc_order_id', string='Products')
    
    lc_payment_terms = fields.Selection(
        selection=[
            ('sight_draft', 'Sight Draft'),
            ('deferred_payment', 'Deferred Payment'),
            ('at_sight', 'At Sight'),
            ('mixed', 'Mixed')
        ],
        string='LC Payment Mode',
        required=True,
        default='sight_draft',
        tracking=True
    )
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Payment Terms',
        tracking=True,
        help='Payment term copied from the RFQ/PO.',
    )
    pi_terms = fields.Many2one('lc.pi.term', string='PI Terms', tracking=True)
    pi_term_line_ids = fields.One2many('lc.pi.term.line', 'lc_order_id', string='PI Term Lines')
    partial_shipment = fields.Selection(
        selection=[
            ('allowed', 'Allowed'),
            ('not_allowed', 'Not Allowed')
        ],
        string='Partial Shipment',
        default='allowed',
        required=True,
        help="Whether partial shipments are allowed under this LC"
    )
    
    conversion_rate = fields.Float(
        string='Conversion Rate',
        digits=(16, 6),
        default=1.0,
        tracking=True,
        help='Company-currency value of one PI currency unit; for example, 1 USD = 122 BDT means enter 122.'
    )
    shipment_container_name = fields.Char(
        string='Shipment/Container Name',
        size=100,
        help="Name of the shipment or container (e.g., 'CONTAINER-12345', 'SHIPMENT-ABC')"
    )
    
    port_of_shipment = fields.Char(
        string='Port of Shipment',
        size=80,
        required=True,
        help="Port from where goods will be shipped (e.g., 'Port of Shanghai', 'JNPT Mumbai')"
    )
    
    destination_port = fields.Char(
        string='Destination Port',
        size=80,
        required=True,
        help="Port where goods will arrive (e.g., 'Port of Chittagong', 'Port of Colombo')"
    )
    
    company_id = fields.Many2one('res.company', required=True,
                            default=lambda self: self.env.company)

    company_currency_id = fields.Many2one('res.currency',
                                        related='company_id.currency_id',
                                        store=True, readonly=True)

    currency_id = fields.Many2one('res.currency', required=True,
                                tracking=True,
                                compute='_compute_currency_id',
                                store=True, readonly=False)

    amount_total = fields.Monetary(
        string='PI Total',
        currency_field='currency_id',
        compute='_compute_pi_totals',
        store=True,
    )
    amount_total_company = fields.Monetary(
        string='PI Total (Company Currency)',
        currency_field='company_currency_id',
        compute='_compute_pi_totals',
        store=True,
    )

    invoice_currency_rate = fields.Float(
        compute='_compute_invoice_currency_rate',
        store=True, readonly=False, digits=0
    )

    expected_currency_rate = fields.Float(
        compute="_compute_expected_currency_rate", digits=0
    )

    date = fields.Date(default=fields.Date.context_today, required=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Confirmed'),
        ('cancel', 'Cancelled'),
    ], default='draft', tracking=True)
    
    # NEW FIELD: Check if this PO has a CI
    has_ci = fields.Boolean(
        string='Has Commercial Invoice',
        compute='_compute_has_ci',
        store=False,
        help='Whether this Work Order has a Commercial Invoice created'
    )
    
    # NEW FIELD: Related CI record
    related_ci_id = fields.Many2one(
        'import.ci',
        string='Related CI',
        compute='_compute_related_ci',
        store=False,
        help='Commercial Invoice created for this Work Order'
    )
    
    def _user_is_lc_approver(self):
        """Return True for users explicitly allowed to approve LC documents."""
        user = self.env.user
        return bool(
            user.is_approver
            or user.has_group('zencore_import_lc.group_lc_approver')
            or user.has_group('base.group_system')
        )

    @api.depends_context('uid')
    def _compute_is_current_user_approver(self):
        """Check if the current user has approver rights"""
        for record in self:
            current_user = self.env.user
            record.is_current_user_approver = record._user_is_lc_approver()

    @api.depends('pi_document_ids')
    def _compute_attachment_count(self):
        for record in self:
            record.attachment_count = len(record.pi_document_ids)

    def action_view_pi_documents(self):
        """Open the supplier documents linked to this Proforma Invoice."""
        self.ensure_one()
        return {
            'name': 'Proforma Invoice Documents',
            'type': 'ir.actions.act_window',
            'res_model': 'lc.order.document',
            'view_mode': 'list,form',
            'domain': [('lc_order_id', '=', self.id)],
            'context': {
                'default_lc_order_id': self.id,
            },
        }
    
    @api.depends('company_id')
    def _compute_currency_id(self):
        for record in self:
            record.currency_id = record.currency_id or record.company_id.currency_id

    @api.depends('currency_id', 'company_currency_id', 'company_id', 'date')
    def _compute_expected_currency_rate(self):
        for record in self:
            if record.currency_id:
                record.expected_currency_rate = self.env['res.currency']._get_conversion_rate(
                    from_currency=record.company_currency_id,
                    to_currency=record.currency_id,
                    company=record.company_id,
                    date=record.date or fields.Date.today(),
                )
            else:
                record.expected_currency_rate = 1.0

    @api.depends('currency_id', 'company_currency_id', 'company_id', 'date')
    def _compute_invoice_currency_rate(self):
        for record in self:
            record.invoice_currency_rate = record.expected_currency_rate

    def refresh_invoice_currency_rate(self):
        for record in self:
            record.invoice_currency_rate = record.expected_currency_rate
        return True

    @api.depends('lc_line_ids.subtotal', 'conversion_rate', 'currency_id', 'company_currency_id')
    def _compute_pi_totals(self):
        for record in self:
            record.amount_total = sum(record.lc_line_ids.mapped('subtotal'))
            rate = 1.0 if record.currency_id == record.company_currency_id else (record.conversion_rate or 0.0)
            record.amount_total_company = record.amount_total * rate
    
    # ============================================
    # ACTION METHODS - STATE MANAGEMENT
    # ============================================
    
    def action_confirm(self):
        """Confirm the Proforma Invoice; no approval workflow is required."""
        for record in self:
            if record.state == 'draft':
                record.write({'state': 'done'})
                _logger.info(f"✓ LC Order {record.name} confirmed")
        return True
    
    def action_cancel(self):
        """Cancel the Proforma Invoice; no approval workflow is required."""
        for record in self:
            if record.state != 'cancel':
                record.write({'state': 'cancel'})
                _logger.info(f"✓ LC Order {record.name} cancelled by {self.env.user.name}")
        return True
    
    def action_set_to_draft(self):
        """Reset to Draft state"""
        for record in self:
            if record.state == 'cancel':
                record.write({'state': 'draft'})
                _logger.info(f"✓ LC Order {record.name} reset to draft")
        return True
    
    @api.depends('po_number', 'pi_number')
    def _compute_has_ci(self):
        """Check if this Work Order has a Commercial Invoice"""
        for record in self:
            has_ci = False
            if record.po_number:
                # Search for CI that references this PO
                ci_count = self.env['import.ci'].search_count([
                    ('company_id', '=', record.company_id.id),
                    ('po_number', '=', record.po_number.name),
                ])
                has_ci = ci_count > 0
            
            record.has_ci = has_ci
            _logger.info(f"LC Order {record.id}: has_ci = {has_ci}")
    
    @api.depends('po_number', 'pi_number')
    def _compute_related_ci(self):
        """Find the related CI for this Work Order"""
        for record in self:
            related_ci = False
            if record.po_number:
                # Search for CI that references this PO
                ci = self.env['import.ci'].search([
                    ('company_id', '=', record.company_id.id),
                    ('po_number', '=', record.po_number.name),
                ], order='create_date desc, id desc', limit=1)
                
                if ci:
                    related_ci = ci
                    _logger.info(f"Found related CI {ci.ci_number} for PO {record.po_number.name}")
            
            record.related_ci_id = related_ci
    
    @api.onchange('pi_terms')
    def _onchange_pi_terms(self):
        """Auto-populate payment term lines when payment term is selected"""
        if self.pi_terms:
            # Clear existing lines
            self.pi_term_line_ids = [(5, 0, 0)]
            
            # Create new lines from the selected payment term's description lines
            lines = []
            for line in self.pi_terms.description_line_ids:
                lines.append((0, 0, {
                    'title': line.title,
                    'description': line.description,
                }))
            self.pi_term_line_ids = lines
        else:
            # Clear lines if no payment term is selected
            self.pi_term_line_ids = [(5, 0, 0)]
    
    @api.onchange('po_number')
    def _onchange_po_number(self):
        """Populate a PI strictly from the selected RFQ/PO.

        Previous CI history must never change the source quantity of a new PI.
        Commercial Invoice utilization is tracked later, per PI, by ``import.ci``.
        """
        self.lc_line_ids = [(5, 0, 0)]
        if self.po_number:
            self._populate_lines_from_po()

    def _populate_lines_from_ci(self, ci):
        """Populate lines from Commercial Invoice"""
        _logger.info(f"Populating from CI {ci.ci_number}")
        
        new_lines = []
        for idx, ci_line in enumerate(ci.product_line_ids):
            # Include ALL lines with product_id (even if qty=0 or price=0)
            if ci_line.product_id:
                line_vals = {
                    'product_id': ci_line.product_id.id,
                    'quantity': ci_line.ci_quantity,
                    'unit_price': ci_line.unit_price,
                    'product_category_id': ci_line.product_category_id.id if ci_line.product_category_id else False,
                    # Note: po_line_id is NOT set here since we're using CI data
                }
                new_lines.append((0, 0, line_vals))
                _logger.info(f"  ✓ CI Line {idx}: {ci_line.product_name}, Qty: {ci_line.ci_quantity}, Price: {ci_line.unit_price}")
            else:
                _logger.warning(f"  ✗ CI Line {idx}: Skipped - No product_id")
        
        # Set the NEW lines from CI
        if new_lines:
            self.lc_line_ids = new_lines
            _logger.info(f"✓ Set {len(new_lines)} lines from CI")
        else:
            _logger.warning(f"No valid lines found in CI")
    
    def _populate_lines_from_po(self):
        """Populate lines from Purchase Order"""
        _logger.info(f"Populating from PO {self.po_number.name}")
        
        new_lines = []
        for idx, po_line in enumerate(self.po_number.order_line):
            # Only include lines with valid product and quantity
            if po_line.product_id and po_line.product_qty > 0:
                line_vals = {
                    'product_id': po_line.product_id.id,
                    'quantity': po_line.product_qty,
                    'unit_price': po_line.price_unit,
                    'po_line_id': po_line.id,
                    'product_category_id': po_line.product_id.categ_id.id,
                }
                new_lines.append((0, 0, line_vals))
                _logger.info(f"  ✓ PO Line {idx}: {po_line.product_id.name}, Qty: {po_line.product_qty}")
            else:
                _logger.warning(f"  ✗ PO Line {idx}: Skipped (no product or zero qty)")
        
        # Set the NEW lines from PO
        if new_lines:
            self.lc_line_ids = new_lines
            _logger.info(f"✓ Set {len(new_lines)} lines from PO")
        else:
            _logger.warning(f"No valid lines found in PO")
    
    @api.model_create_multi
    def create(self, vals_list):
        """Create LC with proper sequence and allow line creation"""
        _logger.info(f"=== LCOrder.create called ===")
        
        processed_vals = []
        for vals in vals_list:
            _logger.info(f"Creating LC Order with vals keys: {vals.keys()}")
            
            # Generate sequence
            if vals.get('name', 'New') == 'New':
                seq = self.env['ir.sequence'].next_by_code('lc.order') or '/'
                vals['name'] = seq
            
            # Check if lc_line_ids exists and has valid data
            if 'lc_line_ids' in vals:
                line_commands = vals['lc_line_ids']
                _logger.info(f"Original line commands: {len(line_commands)} commands")
                _logger.info(f"Commands: {line_commands}")
                
                # Filter out any invalid commands
                valid_commands = []
                for cmd in line_commands:
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 3:
                        command_type = cmd[0]
                        if command_type == 0:  # Create command (0, 0, {values})
                            line_vals = cmd[2]
                            # Validate the line has required fields
                            if (line_vals.get('product_id') and 
                                line_vals.get('quantity', 0) > 0):
                                valid_commands.append(cmd)
                                _logger.info(f"Valid line: {line_vals.get('product_id')}, Qty: {line_vals.get('quantity')}")
                            else:
                                _logger.warning(f"Skipping invalid line: {cmd}")
                        else:
                            valid_commands.append(cmd)
                
                vals['lc_line_ids'] = valid_commands
                _logger.info(f"Filtered to {len(valid_commands)} valid commands")
            
            processed_vals.append(vals)
        
        # IMPORTANT: Set context to allow line creation from parent
        records = super(LCOrder, self.with_context(allow_lc_line_operations=True)).create(processed_vals)
        
        # Log what was created
        for record in records:
            _logger.info(f"✓ Created LC Order {record.name} with {len(record.lc_line_ids)} lines")
            for line in record.lc_line_ids:
                _logger.info(f"  - {line.product_id.name}: Qty={line.quantity}, Price={line.unit_price}")
        
        return records
    
    def write(self, vals):
        """Handle writes while enforcing approval-only terminal state transitions."""
        if 'state' in vals:
            target_state = vals.get('state')
            allowed_states = {'draft', 'done', 'cancel'}
            if target_state not in allowed_states:
                raise UserError(_('A Proforma Invoice can only be Draft, Confirmed, or Cancelled.'))

        _logger.info(f"=== LCOrder.write called for {self.ids} ===")
        _logger.info(f"Write vals keys: {vals.keys()}")
        
        # Log line commands if present
        if 'lc_line_ids' in vals:
            _logger.info(f"Line commands: {vals['lc_line_ids']}")
        else:
            _logger.info(f"No lc_line_ids in vals - existing {len(self.lc_line_ids)} lines will be preserved")
        
        # IMPORTANT: Set context to allow line operations from parent
        result = super(LCOrder, self.with_context(allow_lc_line_operations=True)).write(vals)
        
        # Log the result
        for record in self:
            _logger.info(f"✓ After write, LC {record.name} has {len(record.lc_line_ids)} lines")
            for line in record.lc_line_ids:
                _logger.info(f"  - {line.product_id.name}: Qty={line.quantity}, Price={line.unit_price}")
        
        return result


class LCOrderDocument(models.Model):
    _name = 'lc.order.document'
    _description = 'Proforma Invoice Supporting Document'
    _order = 'create_date desc, id desc'

    lc_order_id = fields.Many2one(
        'lc.order',
        string='Proforma Invoice',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='lc_order_id.company_id',
        store=True,
        readonly=True,
    )
    name = fields.Char(string='Document Name', required=True, default='Supporting Document')
    file = fields.Binary(string='File', required=True, attachment=True)
    file_name = fields.Char(string='File Name')
    mimetype = fields.Char(string='File Type', compute='_compute_mimetype')

    @api.depends('file_name')
    def _compute_mimetype(self):
        for record in self:
            record.mimetype = record.file_name.rsplit('.', 1)[-1].upper() if '.' in (record.file_name or '') else False


class LCOrderLine(models.Model):
    _name = 'lc.order.line'
    _description = 'LC Line'
    
    lc_order_id = fields.Many2one('lc.order', string='LC Order', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='lc_order_id.company_id', store=True, index=True, readonly=True)
    currency_id = fields.Many2one(
        'res.currency', related='lc_order_id.currency_id', store=True, readonly=True,
    )
    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        help='Unit copied from the source purchase order line.',
    )
    quantity = fields.Float(string='Quantity', required=True)
    unit_price = fields.Monetary(
        string='Unit Price', required=True, currency_field='currency_id',
    )
    po_line_id = fields.Many2one('purchase.order.line', string='PO Line')
    product_category_id = fields.Many2one(
        'product.category',
        string='Category',
        store=True
    )
    subtotal = fields.Monetary(
        string='Subtotal',
        currency_field='currency_id',
        compute='_compute_subtotal',
        store=True
    )
    
    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
    
    @api.model
    def default_get(self, fields_list):
        """Override default_get to prevent UI from creating lines"""
        # Check if being called from UI without proper context
        if not self.env.context.get('allow_lc_line_operations'):
            active_model = self.env.context.get('active_model')
            # Allow if coming from LC Order
            if active_model != 'lc.order':
                _logger.warning("Blocking default_get - direct UI access")
                return {}
        
        return super(LCOrderLine, self).default_get(fields_list)
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Allow creation from parent LC Order, block direct UI creation
        """
        # Check if operation is allowed (from LC Order's create/write)
        if not self.env.context.get('allow_lc_line_operations'):
            _logger.error("❌ Attempted to create LC line without proper context")
            _logger.error(f"Context: {self.env.context}")
            raise AccessError(
                "❌ Product lines cannot be created directly!\n\n"
                "These lines are automatically populated from the Work Order (PO).\n"
                "To add products, please select or change the Work Order in the main form."
            )
        
        _logger.info(f"=== LCOrderLine.create called with {len(vals_list)} records ===")
        
        for idx, vals in enumerate(vals_list):
            _logger.info(f"  Line {idx}: Product={vals.get('product_id')}, Qty={vals.get('quantity')}, Price={vals.get('unit_price')}")
        
        # Allow the creation
        result = super(LCOrderLine, self).create(vals_list)
        
        _logger.info(f"✓ Successfully created {len(result)} LC order lines")
        
        return result
    
    def write(self, vals):
        """Allow write from parent LC Order, block direct UI editing"""
        # Check if operation is allowed (from LC Order's write)
        if not self.env.context.get('allow_lc_line_operations'):
            _logger.error(f"❌ Attempted to write to LC line {self.ids} without proper context")
            raise AccessError(
                "❌ Product lines cannot be edited directly!\n\n"
                "These lines are automatically populated from the Work Order (PO).\n"
                "To modify products, please change the Work Order in the main form."
            )
        
        _logger.info(f"LCOrderLine.write for {self.ids}: {vals}")
        return super(LCOrderLine, self).write(vals)
    
    def unlink(self):
        """Allow unlink from parent LC Order, block direct UI deletion"""
        # Check if operation is allowed (from LC Order's write with clear command)
        if not self.env.context.get('allow_lc_line_operations'):
            _logger.error(f"❌ Attempted to unlink LC line {self.ids} without proper context")
            raise AccessError(
                "❌ Product lines cannot be deleted directly!\n\n"
                "These lines are automatically populated from the Work Order (PO).\n"
                "To remove products, please change the Work Order in the main form."
            )
        
        _logger.info(f"LCOrderLine.unlink for {self.ids}")
        return super(LCOrderLine, self).unlink()
    
    @api.constrains('product_id', 'quantity', 'unit_price')
    def _check_line_validity(self):
        """Ensure all lines are valid"""
        for line in self:
            if not line.product_id:
                raise UserError("Every line must have a product!")
            if line.quantity <= 0:
                raise UserError(f"Quantity must be greater than zero for product {line.product_id.name}!")
            if line.unit_price < 0:
                raise UserError(f"Unit price cannot be negative for product {line.product_id.name}!")


class LCPiTerm(models.Model):
    _name = 'lc.pi.term'
    _description = 'LC PI Terms'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Name', required=True)
    description_line_ids = fields.One2many('lc.pi.term.description', 'pi_term_id', string='Description Lines')


class LCPiTermDescription(models.Model):
    _name = 'lc.pi.term.description'
    _description = 'PI Term Description Template'
    
    pi_term_id = fields.Many2one('lc.pi.term', string='PI Term', required=True, ondelete='cascade')
    title = fields.Text(string='Title', required=True)
    description = fields.Text(string='Description', required=True)


class LCPiTermLine(models.Model):
    _name = 'lc.pi.term.line'
    _description = 'PI Term Line in LC Order'
    
    lc_order_id = fields.Many2one('lc.order', string='LC Order', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='lc_order_id.company_id', store=True, index=True, readonly=True)
    title = fields.Text(string='Title', required=True)
    description = fields.Text(string='Description', required=True)
