# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger(__name__)


class ImportCI(models.Model):
    _name = 'import.ci'
    _description = 'Import Commercial Invoice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'ci_number'
    
    # ============================================
    # BASIC FIELDS
    # ============================================
    
    import_lc_id = fields.Many2one(
        'import.lc',
        string='LC Number',
        required=True,
        tracking=True,
        ondelete='cascade',
        domain="[('state', '!=', 'reject')]",
        help='Link to Import LC (only non-rejected LCs shown)'
    )
    
    pi_number = fields.Char(
        string='PI Number',
        tracking=True,
        help='PI Number from the selected LC'
    )
    
    ci_number = fields.Char(
        string='CI Number',
        required=True,
        tracking=True
    )

    _ci_number_company_unique = models.Constraint(
        'UNIQUE (company_id, ci_number)',
        'CI Number must be unique within a company.',
    )
    
    cancelled_by = fields.Many2one(
        'res.users',
        string='Cancelled By',
        readonly=True,
        tracking=True,
        copy=False
    )
    
    cancelled_date = fields.Datetime(
        string='Cancelled Date',
        readonly=True,
        tracking=True,
        copy=False
    )
    
    ci_date = fields.Date(
        string='CI Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        tracking=True,
        domain=[('supplier_rank', '>', 0)]
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    
    cnf_agent_id = fields.Many2one(
        'res.partner',
        string='C&F Agent',
        tracking=True
    )
    
    # ============================================
    # B/L INFORMATION
    # ============================================
    
    bl_number = fields.Char(
        string='B/L Number',
        tracking=True
    )
    
    bl_date = fields.Date(
        string='B/L Date',
        tracking=True
    )
    
    # ============================================
    # BILL OF ENTRY
    # ============================================
    
    bill_of_entry_number = fields.Char(
        string='Bill of Entry No',
        tracking=True
    )
    
    bill_of_entry_date = fields.Date(
        string='Bill of Entry Date',
        tracking=True
    )
    
    # ============================================
    # PORT INFORMATION
    # ============================================
    
    departure_port = fields.Char(
        string='Departure Port',
        tracking=True
    )
    
    departure_date = fields.Date(
        string='Departure Date',
        tracking=True
    )
    
    arrival_port = fields.Char(
        string='Arrival Port',
        tracking=True
    )
    
    arrival_date = fields.Date(
        string='Arrival Date',
        tracking=True
    )
    
    # ============================================
    # SHIPPING INFORMATION
    # ============================================
    
    shipping_line = fields.Char(
        string='Shipping Line',
        tracking=True
    )
    
    # ============================================
    # PO & WORK ORDER
    # ============================================
    
    po_number = fields.Char(
        string='PO Number',
        tracking=True,
        help='Purchase Order Number from LC'
    )
    
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        tracking=True,
        help='Direct link to Purchase Order'
    )
    
    work_order = fields.Char(
        string='Work Order',
        tracking=True,
        help='Manufacturing Work Order linked to LC'
    )
    
    # ============================================
    # PRODUCT LINES
    # ============================================
    
    product_line_ids = fields.One2many(
        'import.ci.product.line',
        'import_ci_id',
        string='Product Information'
    )
    
    # ============================================
    # VENDOR BILLS
    # ============================================
    
    bill_ids = fields.One2many(
        'account.move',
        'import_ci_id',
        string='Vendor Bills',
        domain=[('move_type', '=', 'in_invoice')]
    )
    
    bill_count = fields.Integer(
        string='Bill Count',
        compute='_compute_bill_count'
    )
    
    # ============================================
    # AMENDMENT
    # ============================================
    
    amendment_id = fields.Many2one(
        'import.lc.amendment',
        string='LC Amendment',
        tracking=True,
        help='Amendment for the selected LC (auto-populated when LC is selected)'
    )
    
    # ============================================
    # OTHER FIELDS
    # ============================================
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='import_lc_id.company_id',
        store=True,
        readonly=True,
        index=True,
    )
    
    is_current_user_approver = fields.Boolean(
        string='Is Current User Approver',
        compute='_compute_is_current_user_approver',
        store=False,
    )

    # ============================================
    # STATE FIELD (Draft and Cancel only)
    # ============================================

    state = fields.Selection([
        ('draft', 'Draft'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    notes = fields.Text(string='Notes')
    
    # ============================================
    # INTERNAL TRACKING FIELDS
    # ============================================
    
    _last_populated_lc_id = fields.Integer(
        string='Last Populated LC',
        default=0,
        copy=False,
        help='Technical field: ID of LC that last populated product lines'
    )
    
    # ============================================
    # COMPUTE METHODS
    # ============================================
    
    def _user_is_lc_approver(self):
        user = self.env.user
        return bool(
            user.is_approver
            or user.has_group('zencore_import_lc.group_lc_approver')
            or user.has_group('base.group_system')
        )

    @api.depends_context('uid')
    def _compute_is_current_user_approver(self):
        allowed = self._user_is_lc_approver()
        for record in self:
            record.is_current_user_approver = allowed

    @api.depends('bill_ids')
    def _compute_bill_count(self):
        """Count vendor bills linked to this CI"""
        for record in self:
            valid_bills = record.bill_ids.filtered(
                lambda b: b.move_type == 'in_invoice' and b.state != 'cancel'
            )
            record.bill_count = len(valid_bills)
    
    def action_cancel(self):
        """Cancel the CI"""
        self.ensure_one()
        
        if self.state == 'cancel':
            raise ValidationError(_('This CI is already cancelled.'))
        if not self._user_is_lc_approver():
            raise AccessError(_('Only LC Approvers can cancel Commercial Invoices.'))

        active_bills = self.bill_ids.filtered(lambda bill: bill.state != 'cancel')
        receipts = getattr(self, 'receipt_ids', self.env['stock.picking'])
        active_receipts = receipts.filtered(lambda receipt: receipt.state != 'cancel')
        if active_bills or active_receipts:
            raise ValidationError(_(
                'Cancel the linked Vendor Bill and Receipt before cancelling this Commercial Invoice.'
            ))

        self.with_context(allow_ci_state_transition=True).write({'state': 'cancel'})
        self.cancelled_by = self.env.user
        self.cancelled_date = fields.Datetime.now()
        _logger.info(f"CI {self.ci_number} cancelled by {self.env.user.name}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cancelled'),
                'message': _('Commercial Invoice %s has been cancelled.') % self.ci_number,
                'type': 'warning',
                'sticky': False,
            }
        }
    
    def write(self, vals):
        if 'state' in vals and not self.env.context.get('allow_ci_state_transition'):
            target_state = vals.get('state')
            state_changes = any(record.state != target_state for record in self)
            if state_changes and not self._user_is_lc_approver():
                raise AccessError(_('Only LC Approvers can change Commercial Invoice status.'))
        if vals.get('state') == 'cancel':
            vals = dict(vals, cancelled_by=self.env.user.id, cancelled_date=fields.Datetime.now())
        return super().write(vals)

    @api.depends('import_lc_id')
    def _compute_amendment_id(self):
        """Auto-populate with the latest approved amendment from LC"""
        for record in self:
            if record.import_lc_id:
                latest_amendment = self.env['import.lc.amendment'].search([
                    ('import_lc_id', '=', record.import_lc_id.id),
                    ('state', '=', 'approved')
                ], order='create_date desc', limit=1)
                
                if latest_amendment:
                    record.amendment_id = latest_amendment
                    _logger.info(f"Auto-populated amendment ID: {latest_amendment.id}")
                else:
                    record.amendment_id = False
            else:
                record.amendment_id = False
    
    @api.depends('import_lc_id', 'import_lc_id.supplier_id')
    def _compute_supplier_id(self):
        """Auto-populate supplier from LC"""
        for record in self:
            if record.import_lc_id and record.import_lc_id.supplier_id:
                record.supplier_id = record.import_lc_id.supplier_id
    
    # ============================================
    # ONCHANGE METHODS
    # ============================================
    
    @api.onchange('amendment_id')
    def _onchange_amendment_id(self):
        """
        Update product lines based on amendment.
        
        CRITICAL: This should NOT overwrite existing product lines if user has already
        modified them. Only populate if lines are empty.
        """
        if not self.amendment_id or self.amendment_id.state != 'approved':
            return
        
        # Check if there are existing product lines
        existing_lines_count = len(self.product_line_ids) if self.product_line_ids else 0
        
        # If lines already exist, DON'T overwrite them
        if existing_lines_count > 0:
            _logger.info(f"Amendment changed but {existing_lines_count} product lines exist - NOT overwriting")
            return
        
        # Only populate if no lines exist
        _logger.info(f"Amendment selected and no product lines - populating from amendment")
        
        if self.amendment_id.amendment_type == 'quantity':
            line_commands = []
            for amendment_line in self.amendment_id.product_line_ids:
                line_vals = {
                    'product_id': amendment_line.product_id.id,
                    'product_name': amendment_line.product_name,
                    'lc_quantity': amendment_line.new_quantity,
                    'unit_price': amendment_line.unit_price,
                    'ci_quantity': 0.0,  # Initialize CI quantity as 0
                }
                line_commands.append((0, 0, line_vals))
            
            if line_commands:
                self.product_line_ids = [(5, 0, 0)] + line_commands
    
    @api.onchange('import_lc_id')
    def _onchange_import_lc_id(self):
        """Compatibility hook; enterprise_flow loads the LC's single PI automatically."""
        return

    def action_create_vendor_bill(self):
        """Create vendor bill from CI using CI quantities"""
        self.ensure_one()
        
        _logger.info(f"=== Creating Vendor Bill from CI {self.ci_number} ===")
        
        if not self.supplier_id:
            raise ValidationError(_('Please select a Supplier before creating a bill.'))
        
        if not self.product_line_ids:
            raise ValidationError(_('Cannot create bill without product lines.'))
        
        # Check if any CI quantity is entered
        lines_with_ci_qty = self.product_line_ids.filtered(lambda l: l.ci_quantity > 0)
        if not lines_with_ci_qty:
            raise ValidationError(_(
                'Cannot create Vendor Bill!\n\n'
                'Please enter CI Quantity for at least one product.\n'
                'CI Quantity represents the actual quantity received in this shipment.'
            ))
        
        zero_price_products = lines_with_ci_qty.filtered(lambda l: l.unit_price <= 0)
        if zero_price_products:
            product_names = ', '.join(zero_price_products.mapped('product_name'))
            raise ValidationError(
                _('The following products have zero or negative prices:\n%s') % product_names
            )
        
        invoice_line_vals = []
        
        for ci_line in lines_with_ci_qty:
            product = ci_line.product_id
            product_uom = product.uom_id
            
            line_vals = {
                'product_id': product.id,
                'name': ci_line.product_name or product.name,
                'quantity': ci_line.ci_quantity,  # Use CI quantity for bill
                'price_unit': ci_line.unit_price,
                'product_uom_id': product_uom.id,
            }
            
            if product.supplier_taxes_id:
                line_vals['tax_ids'] = [(6, 0, product.supplier_taxes_id.ids)]
            
            invoice_line_vals.append((0, 0, line_vals))
            
            _logger.info(f"✓ Bill line: {ci_line.product_name} x {ci_line.ci_quantity}")
        
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.supplier_id.id,
            'invoice_date': self.ci_date or fields.Date.today(),
            'currency_id': self.currency_id.id if self.currency_id else self.env.company.currency_id.id,
            'ref': f"CI: {self.ci_number}",
            'invoice_origin': f"{self.ci_number} - {self.pi_number}" if self.pi_number else self.ci_number,
            'invoice_line_ids': invoice_line_vals,
            'import_ci_id': self.id,
            'narration': f"Vendor Bill from CI {self.ci_number}\n"
                        f"PI: {self.pi_number or 'N/A'}\n"
                        f"LC: {self.import_lc_id.lc_number if self.import_lc_id else 'N/A'}",
        }
        
        try:
            bill = self.env['account.move'].create(bill_vals)
            _logger.info(f"✓ Created Bill {bill.name}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Vendor Bill %s created successfully!') % bill.name,
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'account.move',
                        'res_id': bill.id,
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                    }
                }
            }
        
        except Exception as e:
            _logger.error(f"Failed to create bill: {e}")
            import traceback
            _logger.error(traceback.format_exc())
            raise ValidationError(_('Failed to create bill.\n\nError: %s') % str(e))
    
    def action_view_vendor_bills(self):
        """View all vendor bills linked to this CI"""
        self.ensure_one()
        
        return {
            'name': _('Vendor Bills'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.bill_ids.ids)],
            'context': {
                'default_move_type': 'in_invoice',
                'default_partner_id': self.supplier_id.id if self.supplier_id else False,
                'default_import_ci_id': self.id,
            }
        }
    
    # ============================================
    # CONSTRAINTS
    # ============================================
    
    @api.constrains('ci_date', 'arrival_date', 'departure_date')
    def _check_dates(self):
        """Validate dates"""
        for record in self:
            if record.departure_date and record.arrival_date:
                if record.departure_date > record.arrival_date:
                    raise ValidationError(_('Departure date cannot be after arrival date.'))


class ImportCIProductLine(models.Model):
    _name = 'import.ci.product.line'
    _description = 'Import CI Product Line'
    _order = 'product_name, id'
    
    # ============================================
    # BASIC FIELDS
    # ============================================
    
    import_ci_id = fields.Many2one(
        'import.ci',
        string='Import CI',
        required=True,
        ondelete='cascade',
        index=True
    )
    company_id = fields.Many2one('res.company', related='import_ci_id.company_id', store=True, index=True, readonly=True)

    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        index=True
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        help='Unit copied from the source PI/PO line.',
    )
    
    product_name = fields.Char(
        string='Product Name',
        compute='_compute_product_details',
        store=True,
        readonly=False,
    )
    
    product_category_id = fields.Many2one(
        'product.category',
        string='Category',
        compute='_compute_product_details',
        store=True,
        readonly=False,
    )
    
    # ============================================
    # QUANTITY FIELDS
    # ============================================
    
    lc_quantity = fields.Float(
        string='LC Qty',
        required=True,
        default=0.0,
        help='Total quantity from LC',
        readonly=True,
    )
    
    ci_quantity = fields.Float(
        string='CI Qty',
        required=True,
        default=0.0,
        help='Actual quantity in THIS CI',
    )
    
    # 🔥 CHAINED: CI1→LC, CI2→CI1, CI3→CI2
    available_quantity = fields.Float(
        string='Available Qty',
        compute='_compute_available_quantity',
        store=True,
        readonly=True,
        help='Previous Available - Current CI Qty (waterfall calculation)',
    )
    
    # ============================================
    # PRICE FIELDS
    # ============================================
    
    unit_price = fields.Float(
        string='Unit Price',
        required=True,
        default=0.0,
    )
    
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
    )
    
    # ============================================
    # COMPUTE METHODS
    # ============================================
    
    @api.depends('product_id')
    def _compute_product_details(self):
        """Auto-populate product name and category"""
        for line in self:
            if line.product_id:
                product = line.product_id
                line.product_name = str(product.name or product.display_name or f"Product {product.id}").strip()
                line.product_category_id = product.categ_id
            else:
                line.product_name = False
                line.product_category_id = False
    
    @api.depends('lc_quantity', 'ci_quantity', 'import_ci_id', 'import_ci_id.import_lc_id', 'product_id')
    def _compute_available_quantity(self):
        """
        🔥 CORRECT LOGIC:
        
        CREATING NEW CI:
        - Available = Previous CI's saved available - This CI Qty
        
        EDITING EXISTING CI:
        - If FIRST CI (CI1): Available = LC Qty - This CI Qty
        - If NOT FIRST (CI2, CI3...): Available = Previous CI's saved available - This CI Qty
        
        EXAMPLE:
        ─────────────────────────────────────────────────────────────
        CI1: LC=100, CI=30 → Available = 100 - 30 = 70 (SAVED)
        CI2: CI=20 → Available = 70 - 20 = 50 (SAVED)
        CI3: CI=15 → Available = 50 - 15 = 35 (SAVED)
        
        EDIT CI1: Change to 40
        → Available = 100 - 40 = 60 (first CI uses LC)
        
        EDIT CI2: Change to 25
        → Available = 70 - 25 = 45 (uses CI1's SAVED available=70)
        
        EDIT CI3: Change to 10
        → Available = 50 - 10 = 40 (uses CI2's SAVED available=50)
        ─────────────────────────────────────────────────────────────
        """
        for line in self:
            if not line.import_ci_id or not line.import_ci_id.import_lc_id or not line.product_id:
                line.available_quantity = line.lc_quantity - line.ci_quantity
                continue
            
            lc_id = line.import_ci_id.import_lc_id.id
            product_id = line.product_id.id
            current_ci_id = line.import_ci_id.id
            
            # Check if this is a saved record
            is_existing_ci = isinstance(line.id, int)
            
            # ============================================
            # Get all CIs in chronological order
            # ============================================
            all_cis = self.env['import.ci'].search([
                ('import_lc_id', '=', lc_id),
                ('state', '!=', 'cancel')
            ], order='create_date asc, id asc')
            
            ci_ids_ordered = all_cis.ids
            
            # ============================================
            # CASE 1: NEW CI (not yet saved)
            # ============================================
            if not is_existing_ci:
                if all_cis:
                    last_ci = all_cis[-1]
                    last_ci.invalidate_recordset(['product_line_ids'])
                    
                    last_line = last_ci.product_line_ids.filtered(
                        lambda l: l.product_id.id == product_id and isinstance(l.id, int)
                    )
                    
                    if last_line:
                        starting_available = last_line[0].available_quantity
                    else:
                        starting_available = line.lc_quantity
                else:
                    starting_available = line.lc_quantity
                
                line.available_quantity = starting_available - line.ci_quantity
                
                _logger.debug(
                    f"✨ NEW CI - {line.product_name}: "
                    f"Start={starting_available}, "
                    f"CI={line.ci_quantity}, "
                    f"Available={line.available_quantity}"
                )
                continue
            
            # ============================================
            # CASE 2: EDITING EXISTING CI
            # ============================================
            if current_ci_id not in ci_ids_ordered:
                line.available_quantity = line.lc_quantity - line.ci_quantity
                continue
            
            current_ci_index = ci_ids_ordered.index(current_ci_id)
            
            # Sub-case 2a: FIRST CI - use LC Qty
            if current_ci_index == 0:
                line.available_quantity = line.lc_quantity - line.ci_quantity
                
                _logger.debug(
                    f"📝 EDIT FIRST CI {line.import_ci_id.ci_number} - {line.product_name}: "
                    f"LC={line.lc_quantity}, "
                    f"CI={line.ci_quantity}, "
                    f"Available={line.available_quantity}"
                )
            
            # Sub-case 2b: NOT FIRST CI - use previous CI's SAVED available
            else:
                previous_ci_id = ci_ids_ordered[current_ci_index - 1]
                previous_ci = self.env['import.ci'].browse(previous_ci_id)
                previous_ci.invalidate_recordset(['product_line_ids'])
                
                # Find previous CI's line for same product
                previous_line = previous_ci.product_line_ids.filtered(
                    lambda l: l.product_id.id == product_id and isinstance(l.id, int)
                )
                
                if previous_line:
                    # 🔥 Use previous CI's SAVED available quantity
                    starting_available = previous_line[0].available_quantity
                else:
                    # Product not in previous CI, use LC quantity
                    starting_available = line.lc_quantity
                
                line.available_quantity = starting_available - line.ci_quantity
                
                _logger.debug(
                    f"📝 EDIT CI{current_ci_index + 1} {line.import_ci_id.ci_number} - {line.product_name}: "
                    f"Previous Available={starting_available}, "
                    f"CI={line.ci_quantity}, "
                    f"Available={line.available_quantity}"
                )
    
    @api.depends('ci_quantity', 'unit_price')
    def _compute_total_cost(self):
        """Calculate total cost"""
        for line in self:
            line.total_cost = line.ci_quantity * line.unit_price
    
    # ============================================
    # ONCHANGE METHODS
    # ============================================
    
    @api.onchange('ci_quantity')
    def _onchange_ci_quantity(self):
        """Real-time validation when CI quantity changes"""
        # First recalculate available quantity
        self._compute_available_quantity()
        
        # Validation 1: Negative quantity
        if self.ci_quantity < 0:
            return {
                'warning': {
                    'title': '⚠️ Invalid Quantity',
                    'message': 'CI Quantity cannot be negative!'
                }
            }
        
        # Validation 2: Exceeds LC Quantity
        if self.ci_quantity > self.lc_quantity:
            return {
                'warning': {
                    'title': '⚠️ Exceeded LC Quantity',
                    'message': (
                        f'CI Quantity ({self.ci_quantity}) cannot exceed '
                        f'LC Quantity ({self.lc_quantity})!'
                    )
                }
            }
        
        # Validation 3: Exceeds Available Quantity (based on previous CIs)
        if self.available_quantity < 0:
            max_allowed = self.available_quantity + self.ci_quantity
            
            return {
                'warning': {
                    'title': '⚠️ Exceeded Available Quantity',
                    'message': (
                        f'CI Quantity exceeds available!\n\n'
                        f'Maximum: {max_allowed}\n'
                        f'You entered: {self.ci_quantity}\n'
                        f'Excess: {abs(self.available_quantity)}'
                    )
                }
            }
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """When product changes"""
        if self.product_id:
            product = self.product_id
            self.product_name = str(product.name or product.display_name).strip()
            self.product_category_id = product.categ_id
            
            if product.standard_price > 0:
                self.unit_price = product.standard_price
            
            self._compute_available_quantity()
    
    # ============================================
    # CRUD METHODS - CASCADE UPDATES
    # ============================================
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Create records and trigger cascade update on future CIs
        
        FLOW:
        ─────────────────────────────────────────────────────────────
        1. Create CI2 with CI Qty=4
        2. CI2 calculates: Available = CI1(7) - CI2(4) = 3
        3. Save CI2
        4. Trigger cascade (updates any future CIs if they exist)
        ─────────────────────────────────────────────────────────────
        """
        records = super().create(vals_list)
        
        # Trigger cascade update on all future CIs
        for record in records:
            if record.import_ci_id and record.import_ci_id.import_lc_id:
                record._trigger_cascade_update()
                
                _logger.info(
                    f"✅ CREATED: {record.product_name} | "
                    f"CI: {record.import_ci_id.ci_number} | "
                    f"LC={record.lc_quantity}, "
                    f"CI={record.ci_quantity}, "
                    f"Available={record.available_quantity}"
                )
        
        return records
    
    def write(self, vals):
        """
        Update records and trigger cascade update on future CIs
        
        FLOW:
        ─────────────────────────────────────────────────────────────
        1. User edits CI1: Changes CI Qty from 3 → 5
        2. CI1 recalculates: Available = LC(10) - CI1(5) = 5
        3. Save CI1
        4. CASCADE TRIGGERED:
           - CI2 recalculates: Available = CI1(5) - CI2(4) = 1
           - CI3 recalculates: Available = CI2(1) - CI3(2) = -1 ❌
        5. Save BLOCKED with error message
        ─────────────────────────────────────────────────────────────
        """
        result = super().write(vals)
        
        # If ci_quantity changed, trigger cascade update
        if 'ci_quantity' in vals:
            for line in self:
                _logger.info(
                    f"🔄 UPDATED: {line.product_name} | "
                    f"CI: {line.import_ci_id.ci_number} | "
                    f"New CI Qty={line.ci_quantity}, "
                    f"Available={line.available_quantity}"
                )
                
                # Trigger cascade update on future CIs
                line._trigger_cascade_update()
        
        return result
    
    def _trigger_cascade_update(self):
        """
        🔥 CASCADE UPDATE: Recalculate all FUTURE CIs for same product in same LC
        
        HOW IT WORKS:
        ─────────────────────────────────────────────────────────────
        Timeline: CI1 → CI2 → CI3 → CI4
        
        When CI1 changes:
        1. Find CI2, CI3, CI4 (all created AFTER CI1)
        2. Force recompute their available_quantity
        3. CI2 recalculates (sees new CI1 value)
        4. CI3 recalculates (sees new CI1 + CI2 values)
        5. CI4 recalculates (sees new CI1 + CI2 + CI3 values)
        
        When CI2 changes:
        1. Find CI3, CI4 (created AFTER CI2)
        2. CI1 unchanged (created BEFORE CI2)
        3. CI3, CI4 recalculate with new CI2 value
        ─────────────────────────────────────────────────────────────
        """
        self.ensure_one()
        
        if not self.import_ci_id or not self.import_ci_id.import_lc_id or not self.product_id:
            return
        
        lc_id = self.import_ci_id.import_lc_id.id
        product_id = self.product_id.id
        current_ci_id = self.import_ci_id.id
        
        # Get ALL CIs for this LC (chronological order)
        all_cis = self.env['import.ci'].search([
            ('import_lc_id', '=', lc_id),
            ('state', '!=', 'cancel')
        ], order='create_date asc, id asc')
        
        # Find position of current CI
        ci_ids_ordered = all_cis.ids
        if current_ci_id not in ci_ids_ordered:
            return
        
        current_ci_index = ci_ids_ordered.index(current_ci_id)
        
        # Get all FUTURE CIs (created after current)
        future_ci_ids = ci_ids_ordered[current_ci_index + 1:]
        
        if not future_ci_ids:
            _logger.debug(f"No future CIs to update for {self.import_ci_id.ci_number}")
            return
        
        _logger.info(
            f"🔄 CASCADE: {self.import_ci_id.ci_number} changed, "
            f"updating {len(future_ci_ids)} future CIs..."
        )
        
        # Find all lines in future CIs for same product
        future_lines = self.env['import.ci.product.line'].search([
            ('import_ci_id', 'in', future_ci_ids),
            ('product_id', '=', product_id)
        ])
        
        # Force recomputation of available_quantity
        if future_lines:
            # Invalidate cache to force fresh calculation
            future_lines.invalidate_recordset(['available_quantity'])
            future_lines._compute_available_quantity()
            
            for future_line in future_lines:
                _logger.info(
                    f"  ↳ Updated {future_line.import_ci_id.ci_number}: "
                    f"Available={future_line.available_quantity}"
                )
    
    # ============================================
    # CONSTRAINTS
    # ============================================
    
    @api.constrains('ci_quantity', 'lc_quantity', 'available_quantity')
    def _check_ci_quantity_limits(self):
        """
        Final validation before save
        
        This constraint will PREVENT saving if:
        - CI quantity is negative
        - CI quantity exceeds LC quantity
        - Editing previous CI causes this CI to have negative available
        - Creating new CI exceeds available quantity
        """
        for line in self:
            product_name = line.product_name or 'Product'
            
            # Check 1: Negative quantity
            if line.ci_quantity < 0:
                raise ValidationError(
                    f"❌ {product_name}: Quantity cannot be negative!\n"
                    f"You entered: {line.ci_quantity}"
                )
            
            # Check 2: Exceeds LC Quantity
            if line.ci_quantity > line.lc_quantity:
                raise ValidationError(
                    f"❌ {product_name}: CI Quantity exceeds LC Quantity!\n\n"
                    f"LC Quantity: {line.lc_quantity}\n"
                    f"You entered: {line.ci_quantity}\n"
                    f"Excess: {line.ci_quantity - line.lc_quantity}"
                )
            
            # Check 3: Negative available (exceeded available from previous CIs)
            if line.available_quantity < 0:
                max_allowed = line.available_quantity + line.ci_quantity
                
                raise ValidationError(
                    f"❌ {product_name}: EXCEEDED AVAILABLE QUANTITY!\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"CI: {line.import_ci_id.ci_number if line.import_ci_id else 'New'}\n"
                    f"LC Quantity: {line.lc_quantity}\n"
                    f"Maximum allowed: {max_allowed}\n"
                    f"You entered: {line.ci_quantity}\n"
                    f"Excess: {abs(line.available_quantity)}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💡 Based on previous CI usage\n"
                    f"📝 Please enter {max_allowed} or less"
                )
    
    # ============================================
    # UTILITY METHODS
    # ============================================
    
    @api.depends('product_name', 'ci_quantity')
    def _compute_display_name(self):
        """Preserve the commercial-invoice line label in Odoo 20."""
        for line in self:
            line.display_name = f"{line.product_name or 'Product'} - CI Qty: {line.ci_quantity}"


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    import_ci_id = fields.Many2one(
        'import.ci',
        string='Commercial Invoice',
        tracking=True,
        ondelete='restrict',
        help='Link to the Import Commercial Invoice'
    )
    

    @api.model_create_multi
    def create(self, vals_list):
        """Link bills to PO and update PO invoice count"""
        records = super(AccountMove, self).create(vals_list)
        
        for record in records:
            if record.purchase_id and record.move_type == 'in_invoice':
                try:
                    record.purchase_id._compute_invoice()
                    _logger.info(f"✓ Bill {record.name} linked to PO {record.purchase_id.name}")
                except Exception as e:
                    _logger.warning(f"Could not update PO invoice count: {e}")
        
        return records
