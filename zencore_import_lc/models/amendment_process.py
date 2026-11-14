import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger(__name__)


class ImportLCAmendment(models.Model):
    _name = 'import.lc.amendment'
    _description = 'Import LC Amendment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'amendment_number'
    _order = 'amendment_date desc, id desc'
    
    # Amendment Identification
    amendment_number = fields.Char(
        string='Amendment No',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('New')
    )
    is_current_user_approver = fields.Boolean(
        string='Is Current User Approver',
        compute='_compute_is_current_user_approver',
        store=False
    )
    
    import_lc_id = fields.Many2one(
        'import.lc',
        string='LC Number',
        required=True,
        tracking=True,
        ondelete='cascade',
        check_company=True,
        help='Parent Import LC for this amendment'
    )
    
    amendment_date = fields.Date(
        string='Amendment Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    
    # Amendment Type
    amendment_type = fields.Selection([
        ('quantity', 'Quantity Increase / Decrease'),
        ('value', 'LC Amount Change'),
        ('shipment_date', 'Shipment Date Change'),
    ], string='Amendment Type', required=True, tracking=True)
    
    # Changes Details
    reason = fields.Text(
        string='Reason for Amendment',
        required=True,
        tracking=True
    )
    
    # ============================================
    # AUTO-FILLED FIELDS FROM LC
    # ============================================
    
    # Basic LC Info (Auto-filled, Read-only)
    lc_number = fields.Char(
        string='LC Number',
        related='import_lc_id.lc_number',
        store=True,
        readonly=True
    )
    
    pi_number = fields.Char(
        string='PI Number',
        compute='_compute_pi_number',
        store=True,
        readonly=True
    )
    
    supplier_id = fields.Many2one(
        related='import_lc_id.supplier_id',
        string='Supplier',
        store=True,
        readonly=True
    )
    
    lc_type = fields.Selection(
        related='import_lc_id.lc_type',
        string='LC Type',
        store=True,
        readonly=True
    )
    
    lc_opening_date = fields.Date(
        related='import_lc_id.lc_opening_date',
        string='LC Opening Date',
        store=True,
        readonly=True
    )
    
    lc_expiry_date = fields.Date(
        related='import_lc_id.lc_expiry_date',
        string='LC Expiry Date',
        store=True,
        readonly=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='import_lc_id.currency_id',
        string='Currency',
        store=True,
        readonly=True
    )

    company_currency_id = fields.Many2one(
        'res.currency',
        related='import_lc_id.company_currency_id',
        string='Company Currency',
        store=True,
        readonly=True,
    )
    
    current_lc_status = fields.Selection(
        related='import_lc_id.state',
        string='Current LC Status',
        store=True,
        readonly=True
    )
    
    # Shipment Date Amendment
    old_shipment_date = fields.Date(
        string='Current Shipment Date',
        tracking=True,
        readonly=True,
        help='Auto-filled from LC'
    )
    
    new_shipment_date = fields.Date(
        string='New Shipment Date',
        tracking=True
    )
    
    # LC Value Amendment
    old_lc_value = fields.Float(
        string='Current LC Amount',
        tracking=True,
        readonly=True,
        help='Auto-filled from LC'
    )
    
    new_lc_value = fields.Float(
        string='New LC Amount',
        tracking=True
    )
    
    # Total LC Cost (for reference)
    total_lc_cost = fields.Monetary(
        string='Total LC Cost',
        currency_field='company_currency_id',
        related='import_lc_id.total_lc_cost',
        store=True,
        readonly=True,
        help='Total cost of the LC (for reference)'
    )
    
    # Product Line Amendments
    product_line_ids = fields.One2many(
        'import.lc.amendment.line',
        'amendment_id',
        string='Product Changes'
    )
    
    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True, required=True)
    
    # Approval
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True
    )
    
    approved_date = fields.Date(
        string='Approved Date',
        readonly=True,
        tracking=True
    )
    
    rejection_reason = fields.Text(
        string='Rejection Reason',
        tracking=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='import_lc_id.company_id',
        store=True,
        readonly=True,
        index=True,
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
        """Check if the current user has approver rights"""
        current_user = self.env.user
        is_approver = self._user_is_lc_approver()
        
        _logger.info(f"Computing approver status for LC Amendment")
        _logger.info(f"Current user: {current_user.name} (ID: {current_user.id})")
        _logger.info(f"User is_approver: {is_approver}")
        
        for record in self:
            record.is_current_user_approver = is_approver
    
    @api.depends('import_lc_id', 'import_lc_id.pi_number')
    def _compute_pi_number(self):
        """Get PI number from Import LC"""
        for record in self:
            record.pi_number = record.import_lc_id.pi_number if record.import_lc_id else False
    
    # ============================================
    # ONCHANGE - AUTO-FILL ALL DATA
    # ============================================
    
    @api.onchange('import_lc_id')
    def _onchange_import_lc_id(self):
        """
        MASTER ONCHANGE: Auto-fill ALL fields when LC is selected
        This is the main function that populates everything
        """
        if not self.import_lc_id:
            # Clear fields if LC is removed
            self._clear_amendment_fields()
            return
        
        lc = self.import_lc_id
        
        _logger.info(f"=" * 80)
        _logger.info(f"AUTO-FILLING Amendment from LC: {lc.lc_number}")
        _logger.info(f"=" * 80)
        
        # 1. Populate amendment-specific fields
        self.old_shipment_date = lc.shipment_expiry_date
        self.new_shipment_date = lc.shipment_expiry_date
        
        self.old_lc_value = lc.lc_amount
        self.new_lc_value = lc.lc_amount
        
        _logger.info(f"✓ Auto-filled basic info:")
        _logger.info(f"  - LC Number: {lc.lc_number}")
        _logger.info(f"  - PI Number: {lc.pi_number}")
        _logger.info(f"  - Supplier: {lc.supplier_id.name if lc.supplier_id else 'N/A'}")
        _logger.info(f"  - Shipment Date: {self.old_shipment_date}")
        _logger.info(f"  - LC Amount: {self.old_lc_value}")
        _logger.info(f"  - Total LC Cost: {lc.total_lc_cost}")
        
        # 2. If amendment type is 'quantity', auto-load product lines
        if self.amendment_type == 'quantity':
            _logger.info("Amendment type is 'quantity' - loading products...")
            self._load_lc_products()
        
        _logger.info(f"=" * 80)
        _logger.info(f"✓ AUTO-FILL COMPLETE")
        _logger.info(f"=" * 80)
    
    @api.onchange('amendment_type')
    def _onchange_amendment_type(self):
        """
        Auto-load products when quantity amendment type is selected
        """
        if self.amendment_type == 'quantity':
            if self.import_lc_id:
                if not self.import_lc_id.product_line_ids:
                    return {
                        'warning': {
                            'title': _('No Products Found'),
                            'message': _('The selected LC does not have any product lines. '
                                       'Please select a different LC or choose another amendment type.')
                        }
                    }
                
                # Auto-load products
                _logger.info("Amendment type changed to 'quantity' - auto-loading products")
                self._load_lc_products()
            else:
                return {
                    'warning': {
                        'title': _('Select LC First'),
                        'message': _('Please select an LC Number first before choosing Quantity amendment type.')
                    }
                }
    
    # ============================================
    # HELPER METHODS
    # ============================================
    
    def _clear_amendment_fields(self):
        """Clear all amendment fields"""
        self.old_shipment_date = False
        self.new_shipment_date = False
        self.old_lc_value = 0.0
        self.new_lc_value = 0.0
        self.product_line_ids = [(5, 0, 0)]
    
    def _get_field_value(self, record, field_names_list, default=0.0):
        """
        Helper to safely get field value from record
        Tries multiple field names in order
        """
        for field_name in field_names_list:
            try:
                if hasattr(record, field_name):
                    value = getattr(record, field_name, None)
                    if value is not None and value > 0:
                        _logger.info(f"  ✓ Found '{field_name}' = {value}")
                        return value
            except Exception as e:
                _logger.debug(f"  Could not access field '{field_name}': {e}")
                continue
        
        _logger.warning(f"  ✗ No valid value found in fields: {field_names_list}")
        return default
    def _load_lc_products(self):
        """
        Load products with SMART PRIORITY:
        1. Latest NON-CANCELLED CI (if exists) → Most recent data
        2. Latest Approved Amendment (if exists) → Previously adjusted quantities
        3. Original LC product lines → Fallback
        
        CANCELLED CIs are COMPLETELY IGNORED
        """
        if not self.import_lc_id:
            _logger.warning("No LC selected")
            return False
        
        _logger.info(f"=" * 80)
        _logger.info(f"SMART PRODUCT LOADING for LC {self.import_lc_id.lc_number}")
        _logger.info(f"CANCELLED CIs WILL BE IGNORED")
        _logger.info(f"=" * 80)
        
        # ============================================
        # STEP 1: Check for LATEST NON-CANCELLED COMMERCIAL INVOICE
        # ============================================
        latest_ci = None
        if hasattr(self.import_lc_id, 'ci_ids') and self.import_lc_id.ci_ids:
            # FILTER OUT CANCELLED CIs - only get active ones
            active_cis = self.import_lc_id.ci_ids.filtered(
                lambda ci: ci.state != 'cancel'  # IGNORE cancelled CIs
            )
            if active_cis:
                latest_ci = active_cis.sorted(key=lambda ci: ci.create_date, reverse=True)[0]
                _logger.info(f"✓ Found LATEST NON-CANCELLED CI: {latest_ci.ci_number} (Created: {latest_ci.create_date})")
                _logger.info(f"  State: {latest_ci.state}")
            else:
                _logger.info("No non-cancelled CIs found (all CIs are cancelled or no CIs exist)")
                
                # Log cancelled CIs for debugging
                cancelled_cis = self.import_lc_id.ci_ids.filtered(lambda ci: ci.state == 'cancel')
                if cancelled_cis:
                    _logger.info(f"  Found {len(cancelled_cis)} cancelled CIs (IGNORED):")
                    for ci in cancelled_cis:
                        _logger.info(f"    - {ci.ci_number} (Cancelled: {ci.cancelled_date})")
        else:
            _logger.info("LC has no CIs attached")
        
        if latest_ci and latest_ci.product_line_ids:
            _logger.info(f">>> PRIORITY 1: Loading from LATEST NON-CANCELLED CI <<<")
            return self._load_from_ci(latest_ci)
        else:
            if latest_ci:
                _logger.info("CI found but has no product lines")
            else:
                _logger.info("No valid non-cancelled CI found")
        
        # ============================================
        # STEP 2: Check for LATEST APPROVED AMENDMENT
        # ============================================
        latest_amendment = None
        approved_amendments = self.env['import.lc.amendment'].search([
            ('import_lc_id', '=', self.import_lc_id.id),
            ('state', '=', 'approved'),
            ('amendment_type', '=', 'quantity'),
            ('id', '!=', self.id)  # Exclude current amendment
        ], order='approved_date desc, id desc', limit=1)
        
        if approved_amendments:
            latest_amendment = approved_amendments[0]
            _logger.info(f"✓ Found LATEST APPROVED AMENDMENT: {latest_amendment.amendment_number} (Approved: {latest_amendment.approved_date})")
        
        if latest_amendment and latest_amendment.product_line_ids:
            _logger.info(f">>> PRIORITY 2: Loading from LATEST AMENDMENT <<<")
            return self._load_from_amendment(latest_amendment)
        else:
            _logger.info("No approved amendment found or amendment has no product lines")
        
        # ============================================
        # STEP 3: Fallback to ORIGINAL LC PRODUCT LINES
        # ============================================
        _logger.info(f">>> PRIORITY 3: Loading from ORIGINAL LC <<<")
        _logger.info(f"  (No non-cancelled CIs and no approved amendments found)")
        return self._load_from_lc_original()
    def _load_from_lc_original(self):
        """Load products from original LC (fallback method)"""
        _logger.info(f"Loading products from ORIGINAL LC product lines")
        
        lc_product_lines = self.import_lc_id.product_line_ids
        
        if not lc_product_lines:
            _logger.warning(f"LC {self.import_lc_id.lc_number} has no product lines")
            return False
        
        _logger.info(f"Found {len(lc_product_lines)} product lines in original LC")
        
        # DIAGNOSTIC: Log first line's fields (only once for debugging)
        if lc_product_lines:
            first_line = lc_product_lines[0]
            _logger.info(f"\nDIAGNOSTIC: Fields in LC product line model:")
            numeric_fields = {}
            for field_name in first_line._fields:
                try:
                    value = getattr(first_line, field_name, None)
                    if isinstance(value, (int, float)) and value > 0:
                        numeric_fields[field_name] = value
                except:
                    pass
            _logger.info(f"Numeric fields with values > 0:")
            for fname, fval in numeric_fields.items():
                _logger.info(f"  {fname}: {fval}")
        
        # Create amendment product lines
        line_commands = []
        successful_loads = []
        failed_loads = []
        
        for idx, lc_line in enumerate(lc_product_lines):
            _logger.info(f"\n--- Processing LC Line {idx + 1} (ID: {lc_line.id}) ---")
            
            # Get product
            if not hasattr(lc_line, 'product_id') or not lc_line.product_id:
                _logger.warning(f"✗ Line {idx + 1}: No product_id found")
                failed_loads.append(f"Line {idx + 1}: No product")
                continue
            
            product = lc_line.product_id
            product_name = product.name
            _logger.info(f"Product: {product_name} (ID: {product.id})")
            
            # Get quantity - try ALL possible field names
            qty_fields = [
                'quantity', 'product_qty', 'qty', 'product_quantity',
                'ordered_qty', 'lc_quantity', 'lc_qty', 'order_qty',
                'product_uom_qty', 'quantity_done', 'qty_received',
                'qty_ordered', 'amount', 'qty_to_receive'
            ]
            
            qty = self._get_field_value(lc_line, qty_fields, 0.0)
            
            if qty <= 0:
                _logger.warning(f"  ✗ No valid quantity found for {product_name}")
                failed_loads.append(f"{product_name}: No quantity")
                continue
            
            # Get unit price - try ALL possible field names
            price_fields = [
                'unit_price', 'price_unit', 'price', 'price_subtotal',
                'price_total', 'lc_price', 'lc_unit_price', 'rate',
                'unit_rate', 'product_price', 'sale_price'
            ]
            
            price = self._get_field_value(lc_line, price_fields, 0.0)
            
            # If price is still 0, try calculating from totals
            if price == 0 and qty > 0:
                _logger.info("  Attempting to calculate price from totals...")
                total_fields = ['price_total', 'price_subtotal', 'amount_total', 'subtotal']
                total_price = self._get_field_value(lc_line, total_fields, 0.0)
                if total_price > 0:
                    price = total_price / qty
                    _logger.info(f"  ✓ Calculated price from total: {price}")
            
            _logger.info(f"  Final values: Qty={qty}, Price={price}")
            
            # Build line values with EXPLICIT values (not defaults)
            line_vals = {
                'product_id': product.id,
                'product_name': product_name,
                'original_quantity': float(qty),  # Explicit conversion
                'new_quantity': float(qty),       # Explicit conversion
                'unit_price': float(price),       # Explicit conversion
            }
            
            line_commands.append((0, 0, line_vals))
            successful_loads.append(f"{product_name}: Qty={qty}, Price={price}")
            _logger.info(f"  ✓ Added line with values: {line_vals}")
        
        _logger.info(f"\n" + "=" * 80)
        _logger.info(f"LOAD SUMMARY:")
        _logger.info(f"  Total lines in LC: {len(lc_product_lines)}")
        _logger.info(f"  Successfully loaded: {len(line_commands)}")
        _logger.info(f"  Failed: {len(failed_loads)}")
        
        if successful_loads:
            _logger.info(f"\nSuccessful loads:")
            for item in successful_loads:
                _logger.info(f"  ✓ {item}")
        
        if failed_loads:
            _logger.warning(f"\nFailed loads:")
            for item in failed_loads:
                _logger.warning(f"  ✗ {item}")
        
        _logger.info(f"=" * 80)
        
        if line_commands:
            # Clear existing lines and add new ones
            self.product_line_ids = [(5, 0, 0)] + line_commands
            _logger.info(f"✓ Successfully loaded {len(line_commands)} product lines from original LC")
            return True
        else:
            _logger.error("✗ No valid product lines could be loaded!")
            raise ValidationError(_(
                'Could not load any valid product lines from LC %s.\n\n'
                'This might be because:\n'
                '• LC has no product lines with products\n'
                '• Product lines have zero or negative quantities\n'
                '• Field names in LC don\'t match expected names\n\n'
                'Please check the server logs for detailed field information.\n'
                'Contact your system administrator to configure the correct field mappings.'
            ) % self.import_lc_id.lc_number)

    # ============================================
    # CRUD METHODS - CRITICAL FIX
    # ============================================
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Generate amendment number on create
        AUTOMATIC FIX: Always ensure complete product data is saved
        """
        for vals in vals_list:
            # Generate amendment number
            if vals.get('amendment_number', _('New')) == _('New'):
                if vals.get('import_lc_id'):
                    lc = self.env['import.lc'].browse(vals['import_lc_id'])
                    amendment_count = self.search_count([
                        ('import_lc_id', '=', lc.id)
                    ])
                    vals['amendment_number'] = f"{lc.lc_number}/AMD-{amendment_count + 1:03d}"
                else:
                    vals['amendment_number'] = self.env['ir.sequence'].next_by_code('import.lc.amendment') or _('New')
        
        # Create the records first
        records = super(ImportLCAmendment, self).create(vals_list)
        
        # AUTOMATIC FIX: For quantity amendments, ensure all product data is complete
        for record in records:
            if record.amendment_type == 'quantity' and record.import_lc_id:
                _logger.info(f"Processing quantity amendment {record.amendment_number}...")
                
                # Store user's new_quantity changes (if any were set)
                user_new_quantities = {}
                if record.product_line_ids:
                    for line in record.product_line_ids:
                        # Store by index position since product_id might be missing
                        idx = list(record.product_line_ids).index(line)
                        user_new_quantities[idx] = line.new_quantity
                
                # Always reload products from LC to ensure complete data
                _logger.info(f"Reloading products from LC to ensure complete data...")
                record._load_lc_products()
                
                # Restore user's new_quantity changes
                if user_new_quantities:
                    _logger.info(f"Restoring {len(user_new_quantities)} user quantity changes...")
                    for idx, line in enumerate(record.product_line_ids):
                        if idx in user_new_quantities:
                            line.new_quantity = user_new_quantities[idx]
                            _logger.info(f"  Restored qty {user_new_quantities[idx]} for line {idx}")
                
                _logger.info(f"✓ Amendment {record.amendment_number} saved with complete data")
        
        return records
    def _load_from_ci(self, ci):
        """Load product lines from Commercial Invoice"""
        _logger.info(f"Loading products from CI: {ci.ci_number}")
        
        if not ci.product_line_ids:
            _logger.warning(f"CI {ci.ci_number} has no product lines")
            return False
        
        line_commands = []
        successful_loads = []
        
        for idx, ci_line in enumerate(ci.product_line_ids):
            if not ci_line.product_id:
                _logger.warning(f"CI line {idx+1}: No product_id")
                continue
            
            product = ci_line.product_id
            product_name = product.name
            
            # Get quantity from CI
            qty = ci_line.ci_quantity
            price = ci_line.unit_price if hasattr(ci_line, 'unit_price') else 0.0
            
            if qty <= 0:
                _logger.warning(f"CI line {idx+1}: Zero or negative quantity")
                continue
            
            line_vals = {
                'product_id': product.id,
                'product_name': product_name,
                'original_quantity': float(qty),
                'new_quantity': float(qty),
                'unit_price': float(price),
            }
            
            line_commands.append((0, 0, line_vals))
            successful_loads.append(f"{product_name}: Qty={qty}, Price={price}")
            _logger.info(f"  ✓ CI Line: {product_name}, Qty={qty}, Price={price}")
        
        if line_commands:
            self.product_line_ids = [(5, 0, 0)] + line_commands
            _logger.info(f"✓ Successfully loaded {len(line_commands)} products from CI {ci.ci_number}")
            _logger.info(f"=" * 80)
            return True
        
        _logger.warning(f"✗ No valid products loaded from CI {ci.ci_number}")
        return False
    def _load_from_amendment(self, amendment):
        """Load product lines from previous approved amendment"""
        _logger.info(f"Loading products from Amendment: {amendment.amendment_number}")
        
        if not amendment.product_line_ids:
            _logger.warning(f"Amendment {amendment.amendment_number} has no product lines")
            return False
        
        line_commands = []
        successful_loads = []
        
        for idx, amd_line in enumerate(amendment.product_line_ids):
            if not amd_line.product_id:
                _logger.warning(f"Amendment line {idx+1}: No product_id")
                continue
            
            product = amd_line.product_id
            product_name = product.name
            
            # Use the AMENDED quantity (new_quantity) as the starting point
            # This becomes the "current quantity" for the new amendment
            qty = amd_line.new_quantity if amd_line.new_quantity > 0 else amd_line.original_quantity
            price = amd_line.unit_price
            
            if qty <= 0:
                _logger.warning(f"Amendment line {idx+1}: Zero or negative quantity")
                continue
            
            line_vals = {
                'product_id': product.id,
                'product_name': product_name,
                'original_quantity': float(qty),  # Use amended qty as new baseline
                'new_quantity': float(qty),
                'unit_price': float(price),
            }
            
            line_commands.append((0, 0, line_vals))
            successful_loads.append(f"{product_name}: Qty={qty} (from previous amendment)")
            _logger.info(f"  ✓ Amendment Line: {product_name}, Qty={qty}, Price={price}")
        
        if line_commands:
            self.product_line_ids = [(5, 0, 0)] + line_commands
            _logger.info(f"✓ Successfully loaded {len(line_commands)} products from Amendment {amendment.amendment_number}")
            _logger.info(f"=" * 80)
            return True
        
        _logger.warning(f"✗ No valid products loaded from Amendment {amendment.amendment_number}")
        return False
        
    def write(self, vals):
        """Write amendment data and enforce approval-only approve/reject transitions."""
        if 'state' in vals:
            target_state = vals.get('state')
            if target_state in ('approved', 'rejected') and not self._user_is_lc_approver():
                raise AccessError(_('Only LC Approvers can approve or reject amendments.'))

        _logger.info(f"Amendment.write called for {self.ids}")
        
        # Store user's new_quantity changes BEFORE write
        stored_new_quantities = {}
        for record in self:
            if record.amendment_type == 'quantity' and record.product_line_ids:
                stored_new_quantities[record.id] = {}
                for idx, line in enumerate(record.product_line_ids):
                    stored_new_quantities[record.id][idx] = line.new_quantity
        
        # Perform the write operation
        result = super(ImportLCAmendment, self).write(vals)
        
        # AUTOMATIC FIX: After write, check and fix any incomplete product lines
        for record in self:
            if record.amendment_type == 'quantity' and record.import_lc_id:
                
                # Check if product lines exist and are complete
                needs_reload = False
                
                if not record.product_line_ids:
                    _logger.warning(f"No product lines in {record.amendment_number} - will reload")
                    needs_reload = True
                else:
                    # Check for incomplete lines (missing product_id or zero original_quantity/unit_price)
                    incomplete_lines = record.product_line_ids.filtered(
                        lambda l: not l.product_id or l.original_quantity == 0
                    )
                    
                    if incomplete_lines:
                        _logger.warning(f"{len(incomplete_lines)} incomplete lines in {record.amendment_number} - will reload")
                        needs_reload = True
                
                if needs_reload:
                    _logger.info(f"Auto-reloading products for {record.amendment_number}...")
                    
                    # Reload all product data from LC
                    record._load_lc_products()
                    
                    # Restore user's new_quantity changes
                    if record.id in stored_new_quantities:
                        _logger.info(f"Restoring user's quantity changes...")
                        for idx, line in enumerate(record.product_line_ids):
                            if idx in stored_new_quantities[record.id]:
                                line.new_quantity = stored_new_quantities[record.id][idx]
                    
                    _logger.info(f"✓ Products auto-reloaded for {record.amendment_number}")
        
        return result
    
    # ============================================
    # ACTION METHODS
    # ============================================
    
    def action_reload_products(self):
        """
        Manual action to reload products from LC
        (Kept for compatibility - auto-reload now happens on save)
        """
        self.ensure_one()
        if not self.import_lc_id:
            raise ValidationError(_('Please select an LC first.'))
        
        # Store user's new quantity changes before reload
        user_quantities = {}
        for idx, line in enumerate(self.product_line_ids):
            user_quantities[idx] = line.new_quantity
        
        # Reload products
        if self._load_lc_products():
            # Restore user's quantity changes
            for idx, line in enumerate(self.product_line_ids):
                if idx in user_quantities:
                    line.new_quantity = user_quantities[idx]
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('%d products reloaded from LC %s') % (
                        len(self.product_line_ids), 
                        self.import_lc_id.lc_number
                    ),
                    'type': 'success',
                    'sticky': False,
                }
            }
    
    def action_submit(self):
        """Submit amendment for approval"""
        self.ensure_one()
        
        if not self.id:
            raise ValidationError(_('Please save the amendment first before submitting.'))
        
        if self.state != 'draft':
            raise ValidationError(_('Only draft amendments can be submitted.'))
        
        # Validation based on amendment type
        if self.amendment_type == 'shipment_date':
            if not self.new_shipment_date:
                raise ValidationError(_('Please specify the new shipment date.'))
            if self.new_shipment_date == self.old_shipment_date:
                raise ValidationError(_('New shipment date must be different from current date.'))
        
        elif self.amendment_type == 'quantity':
            if not self.product_line_ids:
                raise ValidationError(_(
                    'No product lines available.\n\n'
                    'Please save the amendment first to load products from the LC.'
                ))
            
            # Validate that all lines have complete data
            invalid_lines = []
            for line in self.product_line_ids:
                if line.original_quantity <= 0:
                    product_name = line.product_name or (line.product_id.name if line.product_id else 'Unknown Product')
                    invalid_lines.append(f"• {product_name}: Current Qty = {line.original_quantity}")
            
            if invalid_lines:
                raise ValidationError(_(
                    '⚠️ Some product lines have invalid data:\n\n%s\n\n'
                    'Please save the amendment again to reload complete data.'
                ) % '\n'.join(invalid_lines))
            
            # Check quantity changes
            changed_products = []
            unchanged_products = []

            for line in self.product_line_ids:
                product_name = line.product_name or (line.product_id.name if line.product_id else 'Unknown Product')
                if line.new_quantity <= 0:
                    raise ValidationError(_('New quantity must be greater than zero for %s.') % product_name)

                if line.new_quantity != line.original_quantity:
                    changed_products.append({
                        'name': product_name,
                        'old': line.original_quantity,
                        'new': line.new_quantity,
                        'change': line.new_quantity - line.original_quantity
                    })
                else:
                    unchanged_products.append({
                        'name': product_name,
                        'qty': line.original_quantity
                    })

            if not changed_products:
                raise ValidationError(_(
                    '⚠️ NO QUANTITY CHANGES DETECTED!\n\n'
                    'For a Quantity Increase / Decrease amendment, at least ONE product quantity must be changed.'
                ))

            _logger.info(f"Quantity validation passed for {self.amendment_number}: {len(changed_products)} products changed ✓")

        elif self.amendment_type == 'value':
            if not self.new_lc_value:
                raise ValidationError(_('Please specify the new LC amount.'))
            if self.new_lc_value == self.old_lc_value:
                raise ValidationError(_('New LC amount must be different from the current amount.'))

        # Submit
        self.write({'state': 'submitted'})

        # Success notification with summary
        if self.amendment_type == 'quantity' and changed_products:
            summary = _('Amendment submitted successfully!\n\nQuantity changes:\n')
            for prod in changed_products[:3]:  # Show first 3
                sign = '+' if prod['change'] > 0 else ''
                summary += _('• %s: %s → %s (%s%s)\n') % (
                    prod['name'], prod['old'], prod['new'], sign, prod['change']
                )
            if len(changed_products) > 3:
                summary += _('• ... and %d more products\n') % (len(changed_products) - 3)

            message = summary
        else:
            message = _('Amendment %s submitted for approval.') % self.amendment_number
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✓ Submitted for Approval'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }
    
    
    def action_approve(self):
        """
        Approve amendment WITHOUT updating LC product lines.
        
        CRITICAL CHANGE: Amendment is now INDEPENDENT of LC.
        - CI will read from amendment if approved
        - LC product lines remain UNCHANGED
        - Amendment serves as a "snapshot" of quantity changes only
        """
        self.ensure_one()
        
        # Check if current user is an approver
        if not self._user_is_lc_approver():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Access Denied'),
                    'message': _('Only users with Approver rights can approve amendments.\n\nPlease contact your administrator if you need this access.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        if self.state != 'submitted':
            raise ValidationError(_('Only submitted amendments can be approved.'))
        
        # ============================================
        # APPLY CHANGES TO LC (NON-QUANTITY AMENDMENTS ONLY)
        # ============================================
        lc_vals = {}
        
        # Shipment date amendment - OK to update LC
        if self.amendment_type == 'shipment_date' and self.new_shipment_date:
            lc_vals['shipment_expiry_date'] = self.new_shipment_date
            _logger.info(f"Updating LC shipment date: {self.old_shipment_date} → {self.new_shipment_date}")
        
        # LC amount amendment - apply only through the approved amendment flow.
        if self.amendment_type == 'value' and self.new_lc_value:
            lc_vals['lc_amount'] = self.new_lc_value
            _logger.info(f"Updating LC amount: {self.old_lc_value} → {self.new_lc_value}")
        
        # ============================================
        # CRITICAL: DO NOT UPDATE LC PRODUCT LINES
        # ============================================
        if self.amendment_type == 'quantity':
            # Log for tracking purposes only
            _logger.info(f"✓ Quantity amendment approved: {self.amendment_number}")
            _logger.info(f"  LC product lines will remain UNCHANGED")
            _logger.info(f"  Future CIs will reference this amendment for quantities")
            
            for amendment_line in self.product_line_ids:
                if amendment_line.product_id:
                    _logger.info(f"  - {amendment_line.product_name}: "
                               f"{amendment_line.original_quantity} → {amendment_line.new_quantity}")
        
        # Update LC (shipment date and conversion rate only)
        if lc_vals:
            self.import_lc_id.with_context(allow_approved_amendment=True).write(lc_vals)
            _logger.info(f"✓ LC {self.import_lc_id.lc_number} updated (non-quantity fields only)")
        
        # Mark amendment as approved
        self.write({
            'state': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': fields.Date.today()
        })

        if self.amendment_type == 'quantity' and self.import_lc_id:
            lc = self.import_lc_id
            lc.invalidate_recordset(['has_quantity_amendment'])
            lc.product_line_ids.invalidate_recordset(['amended_quantity', 'total_cost'])
            new_amount = sum(line.total_cost for line in lc.product_line_ids)
            lc.with_context(allow_approved_amendment=True).write({'lc_amount': new_amount})
            lc.flush_recordset()
            lc.product_line_ids.flush_recordset()
            _logger.info(f"✓ LC {lc.lc_number} amount updated from quantity amendment to {new_amount}")

            # Synchronize amended quantities to linked GRNs (Demand and Quantity)
            for amd_line in self.product_line_ids.filtered('product_id'):
                for grn in lc.grn_ids.filtered(lambda p: p.state != 'cancel'):
                    matching_moves = grn.move_ids.filtered(
                        lambda m: m.state != 'cancel' and (
                            (amd_line.po_line_id and m.purchase_line_id == amd_line.po_line_id) or
                            (m.product_id == amd_line.product_id)
                        )
                    )
                    for move in matching_moves:
                        move.write({
                            'product_uom_qty': amd_line.new_quantity,
                            'quantity': amd_line.new_quantity,
                        })
                        move.flush_recordset()
                    grn.flush_recordset()
            _logger.info(f"✓ Synchronized amended quantities to linked GRNs for LC {lc.lc_number}")

        self.flush_recordset()
        _logger.info(f"✓ Amendment {self.amendment_number} approved by {self.env.user.name}")
        _logger.info(f"✓ LC product lines preserved - no changes made")
        
        # Prepare success message
        if self.amendment_type == 'quantity':
            message = _(
                'Amendment %s approved!\n\n'
                '✓ LC product lines remain unchanged\n'
                '✓ Future Commercial Invoices will reference this amendment\n'
                '✓ Amendment serves as a record of quantity changes'
            ) % self.amendment_number
        else:
            message = _('Amendment %s approved and applied to LC %s') % (
                self.amendment_number,
                self.import_lc_id.lc_number
            )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('✓ Approved'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }

    def action_reject(self):
        """Reject amendment - Only for Approvers"""
        self.ensure_one()
        
        # Check if current user is an approver
        if not self._user_is_lc_approver():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Access Denied'),
                    'message': _('Only users with Approver rights can reject amendments.\n\nPlease contact your administrator if you need this access.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        if self.state != 'submitted':
            raise ValidationError(_('Only submitted amendments can be rejected.'))
        
        return {
            'name': _('Reject Amendment'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.lc.amendment.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_amendment_id': self.id}
        }
    
    # def action_reject(self):
    #     """Reject amendment"""
    #     self.ensure_one()
    #     if self.state != 'submitted':
    #         raise ValidationError(_('Only submitted amendments can be rejected.'))
        
    #     return {
    #         'name': _('Reject Amendment'),
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'import.lc.amendment.reject.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': {'default_amendment_id': self.id}
    #     }
    
    def action_cancel(self):
        """Cancel amendment"""
        self.ensure_one()
        if self.state == 'approved':
            raise ValidationError(_('Cannot cancel approved amendments.'))
        
        self.write({'state': 'cancelled'})
        self.flush_recordset()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cancelled'),
                'message': _('Amendment cancelled.'),
                'type': 'warning',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }
    
    def action_draft(self):
        """Reset to draft"""
        self.ensure_one()
        if self.state not in ('submitted', 'rejected'):
            raise ValidationError(_('Only submitted or rejected amendments can be reset to draft.'))
        
        self.write({'state': 'draft'})
        self.flush_recordset()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reset'),
                'message': _('Amendment reset to draft.'),
                'type': 'info',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }


# ============================================
# AMENDMENT LINE MODEL
# ============================================

class ImportLCAmendmentLine(models.Model):
    _name = 'import.lc.amendment.line'
    _description = 'Import LC Amendment Line'
    _order = 'id'
    
    amendment_id = fields.Many2one(
        'import.lc.amendment',
        string='Amendment',
        required=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one('res.company', related='amendment_id.company_id', store=True, index=True, readonly=True)
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=False
    )
    
    product_name = fields.Char(
        string='Product Name',
        required=False
    )
    
    original_quantity = fields.Float(
        string='Current Qty',
        required=True,
        digits=(16, 2),
        default=0.0,
        readonly=True
    )
    
    new_quantity = fields.Float(
        string='New Qty',
        required=True,
        digits=(16, 2),
        default=0.0
    )
    
    unit_price = fields.Float(
        string='Unit Price',
        digits=(16, 2),
        default=0.0,
        readonly=True
    )
    
    quantity_change = fields.Float(
        string='Change',
        compute='_compute_quantity_change',
        store=True
    )
    
    change_percentage = fields.Float(
        string='Change %',
        compute='_compute_change_percentage',
        store=True
    )
    
    @api.depends('original_quantity', 'new_quantity')
    def _compute_quantity_change(self):
        for line in self:
            line.quantity_change = line.new_quantity - line.original_quantity
    
    @api.depends('original_quantity', 'new_quantity')
    def _compute_change_percentage(self):
        for line in self:
            if line.original_quantity > 0:
                line.change_percentage = ((line.new_quantity - line.original_quantity) / line.original_quantity) * 100
            else:
                line.change_percentage = 0.0
    
    @api.constrains('new_quantity', 'original_quantity')
    def _check_quantity_value(self):
        """Ensure quantity is strictly positive for quantity amendments"""
        for line in self:
            if line.amendment_id and line.amendment_id.amendment_type == 'quantity':
                product_display = line.product_name or (line.product_id.name if line.product_id else 'Unknown Product')
                if line.new_quantity <= 0:
                    raise ValidationError(_(
                        '❌ INVALID QUANTITY!\n\n'
                        'Product: %s\n'
                        'New Qty: %s\n\n'
                        '✏️ Please enter a value greater than 0.'
                    ) % (product_display, line.new_quantity))

    @api.onchange('new_quantity')
    def _onchange_new_quantity(self):
        """Real-time validation when user changes New Qty"""
        if self.amendment_id and self.amendment_id.amendment_type == 'quantity':
            if self.new_quantity <= 0:
                product_display = self.product_name or (self.product_id.name if self.product_id else 'Product')
                return {
                    'warning': {
                        'title': _('❌ Invalid Quantity'),
                        'message': _(
                            'Product: %s\n\n'
                            'Quantity must be greater than zero.'
                        ) % product_display
                    }
                }


# ============================================
# REJECTION WIZARD
# ============================================

class ImportLCAmendmentRejectWizard(models.TransientModel):
    _name = 'import.lc.amendment.reject.wizard'
    _description = 'Amendment Rejection Wizard'
    
    amendment_id = fields.Many2one(
        'import.lc.amendment',
        string='Amendment',
        required=True
    )
    
    rejection_reason = fields.Text(
        string='Rejection Reason',
        required=True
    )
    
    def action_confirm_reject(self):
        """Confirm rejection with reason and enforce approver access server-side."""
        self.ensure_one()
        if not self.amendment_id._user_is_lc_approver():
            raise AccessError(_('Only LC Approvers can reject amendments.'))
        self.amendment_id.write({
            'state': 'rejected',
            'rejection_reason': self.rejection_reason
        })
        self.amendment_id.flush_recordset()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rejected'),
                'message': _('Amendment has been rejected.'),
                'type': 'warning',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }
