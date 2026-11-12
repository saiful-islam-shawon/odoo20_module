import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError
from datetime import timedelta

_logger = logging.getLogger(__name__)

class ImportLC(models.Model):
    _name = 'import.lc'
    _description = 'Import Letter of Credit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'lc_number'
    _order = 'id desc'  
    
    # import_lc_id = fields.Many2one(
    #     'import.lc',
    #     string='LC Number',
    #     required=True,
    #     tracking=True,
    #     ondelete='cascade'
    # )
    # lc_order_id = fields.Many2one(
    #     'lc.order',
    #     string='LC Order',
    #     required=True,
    #     tracking=True,
    #     ondelete='cascade',
    #     help='Link to LC Order'
    # )
    lc_order_id = fields.Many2one(
        'lc.order',
        string='LC Order',
        required=True,
        tracking=True,
        ondelete='restrict',
        check_company=True,
        domain="[('state', 'not in', ['cancel', 'reject']), ('company_id', '=', company_id)]",
        help='Link to the active LC Order that owns this PI'
    )
    
    lc_number = fields.Char(
        string='LC Number', required=True, default=False, copy=False, tracking=True, index=True,
        help='Enter the exact LC number issued by the bank. Import LC numbers are never auto-generated.'
    )

    _lc_number_company_unique = models.Constraint(
        'UNIQUE (company_id, lc_number)',
        'LC Number must be unique within a company.',
    )
    lc_type = fields.Selection(selection=[('local', 'Local'), ('foreign', 'Foreign'), ('epz', 'EPZ'), ('other', 'Other')], string='LC Type', required=True)
    pi_number = fields.Char(string='PI Number', required=True, tracking=True, index=True, help='PI number copied from the selected LC Order')
    lc_order_ids = fields.Many2many(
        'lc.order',
        'lc_order_import_lc_rel',
        'import_lc_id',
        'lc_order_id',
        string='LC Orders',
        help='LC Orders linked to this Import LC'
    )
    departure_port_date = fields.Char(string='Departure Port & Date')
    arrival_port_date = fields.Char(string='Arrival Port & Date')
    shipping_line = fields.Char(string='Shipping Line')
    ci_number = fields.Char(string='CI Number')
    ci_date = fields.Date(string='CI Date')
    ci_invoice_id = fields.Many2one('account.move', string='Commercial Invoice', domain=[('move_type', '=', 'in_invoice')])
    ci_ref = fields.Char(related='ci_invoice_id.ref', string='Bill Reference', store=True)
    ci_invoice_date = fields.Date(related='ci_invoice_id.invoice_date', string='Bill Date', store=True)
    sc_number = fields.Char(string='S/C Number')
    supplier_id = fields.Many2one('res.partner', string='Supplier', required=True, domain=[('supplier_rank', '>', 0)])
    buyer_id = fields.Many2one('res.partner', string='Buyer', domain=[('customer_rank', '>', 0)])
    indent_agent_id = fields.Many2one('res.partner', string='Indent Agent')
    applicant_bank_id = fields.Many2one('res.bank', string='Applicant Bank', required=True)
    advising_bank_id = fields.Many2one('res.bank', string='Advising Bank')
    lc_product_type = fields.Char(string='LC Product Type')
    lc_tolerance_percent = fields.Float(string='LC Tolerance (%)', digits=(5, 2))
    margin_rate = fields.Float(string='Margin Rate (%)', digits=(5, 2))
    margin_value = fields.Monetary(string='Margin Value', currency_field='company_currency_id', compute='_compute_margin_value')
    # branch_id = fields.Many2one('res.company.branch', string='Branch', required=True)
    lc_opening_date = fields.Date(string='LC Opening Date', default=fields.Date.today, required=True)
    lc_expiry_date = fields.Date(string='LC Expiry Date', default=lambda self: fields.Date.today() + timedelta(days=90), required=True)
    shipment_expiry_date = fields.Date(string='Shipment Expiry Date', default=lambda self: fields.Date.today() + timedelta(days=60), required=True)
    payment_terms = fields.Selection(selection=[('sight_draft', 'Sight Draft'), ('deferred_payment', 'Deferred Payment'), ('at_sight', 'At Sight'), ('mixed', 'Mixed')], string='Payment Terms')
    tenor_days = fields.Integer(string='Tenor (Days)', default=0)
    partial_shipment = fields.Selection(selection=[('allowed', 'Allowed'), ('not_allowed', 'Not Allowed')], string='Partial Shipment', default='allowed')
    transshipment = fields.Selection(selection=[('allowed', 'Allowed'), ('not_allowed', 'Not Allowed')], string='Transshipment', default='allowed')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    cnf_agent_id = fields.Many2one('res.partner', string='CNF Agent')
    proforma_invoice_ids = fields.Many2many('account.move', string='Linked Proforma Invoices', domain=[('move_type', '=', 'in_invoice')])
    product_line_ids = fields.One2many('import.lc.product.line', 'import_lc_id', string='Product Information')
    total_lc_cost = fields.Monetary(string='Total LC Cost', currency_field='company_currency_id', compute='_compute_total_lc_cost', store=True)
    document_ids = fields.One2many('import.lc.document', 'import_lc_id', string='Documents')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    landed_cost_ids = fields.One2many('stock.landed.cost', 'import_lc_id', string='Landed Costs')
    all_landed_cost_ids = fields.Many2many(
         'stock.landed.cost',
         string='All Landed Costs',
         compute='_compute_all_landed_costs',
     )
    lc_conversion_rate = fields.Float(
        string='Conversion Rate',
        digits=(16, 6),
        default=1.0,
        tracking=True,
        help='Company-currency value of one LC currency unit; for example, 1 USD = 122 BDT means enter 122.'
    )
    po_state = fields.Selection([
    ('draft', 'RFQ'),
    ('sent', 'RFQ Sent'),
    ('proforma', 'Proforma Invoice'),
    ('to approve', 'To Approve'),
    ('purchase', 'Purchase Order'),
    ('done', 'Locked'),
    ('cancel', 'Cancelled')
], string='PO State', compute='_compute_po_state', store=True) 
    
#     state = fields.Selection([
#     ('draft', 'Draft'),
#     ('confirmed', 'Confirmed'),
#     ('done', 'Done'),
#     ('cancel', 'Cancelled')
# ], string='Status', default='draft', tracking=True)
    # GRN (Goods Receipt Note) field - AUTO-COMPUTED from PI number
    grn_ids = fields.Many2many(
        'stock.picking',
        string='GRN/Receipts',
        compute='_compute_grn_ids',
        store=False,
        help='Goods Receipt Notes automatically linked based on PI number in Purchase Orders'
    )
    ci_ids = fields.One2many(
    'import.ci',
    'import_lc_id',
    string='Commercial Invoices',
    help='Commercial Invoices linked to this Import LC'
)

    ci_count = fields.Integer(
        string='CI Count',
        compute='_compute_ci_count',
        help='Number of Commercial Invoices'
    )

    
    grn_count = fields.Integer(
        string='GRN Count',
        compute='_compute_grn_ids'
    )
    
    # NEW: Document Chain Summary
    document_chain_summary = fields.Text(
        string='Document Chain Summary',
        compute='_compute_document_chain_summary',
        store=False,
        help='Shows the complete traceability: PI → PO → Work Order → GRN'
    )
    invoice_count = fields.Integer(
    string='Bill Count',
    compute='_compute_invoice_count'
)
    
    # Field to store all related invoices from POs
    invoice_ids = fields.Many2many(
        'account.move',
        string='Related Bills',
        compute='_compute_invoice_ids',
        store=False,
        help='All vendor bills from related Purchase Orders'
    )
    
    # # State field to control readonly behavior
    # state = fields.Selection([
    #     ('draft', 'Draft'),
    #     ('reject', 'Rejected'), 
    #     ('confirmed', 'Confirmed'),
    #     ('done', 'Done')
    # ], string='Status', default='draft', tracking=True)
    
    # ✅ UPDATED STATE FIELD - Added 'reject' status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('reject', 'Rejected')  # ← NEW STATUS
    ], string='Status', default='draft', tracking=True)
    
    
    # ============================================
    # OTHER CHARGES TAB - New Fields
    # ============================================
    
    # Journal Entries (Other Charges like MISC entries)
    # One2many - automatically shows all journal entries where import_lc_id = this LC
    journal_entry_ids = fields.One2many(
        'account.move',
        'import_lc_id',
        string='Journal Entries (Other Charges)',
        domain=[('move_type', '=', 'entry')],
        help='Miscellaneous journal entries linked to this Import LC'
    )
    
    journal_entry_count = fields.Integer(
        string='Journal Entry Count',
        compute='_compute_journal_entry_count',
        store=False
    )
    
    journal_entry_total = fields.Monetary(
        string='Total Other Charges',
        compute='_compute_journal_entry_total',
        currency_field='company_currency_id',
        store=False
    )
    
    is_current_user_approver = fields.Boolean(
        string='Is Current User Approver',
        compute='_compute_is_current_user_approver',
        store=False
    )
    
    
     # Amendment relationship
    

    
    # ============================================
    # COMPUTE METHODS
    # ============================================
    amendment_ids = fields.One2many(
        'import.lc.amendment',
        'import_lc_id',
        string='Amendments'
    )
    
    def action_create_amendment(self):
        """Open form to create amendment"""
        self.ensure_one()
        return {
            'name': _('Create Amendment'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.lc.amendment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_import_lc_id': self.id,
            }
        }
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
        
        _logger.info(f"Computing approver status for Import LC")
        _logger.info(f"Current user: {current_user.name} (ID: {current_user.id})")
        _logger.info(f"User is_approver: {is_approver}")
        
        for record in self:
            record.is_current_user_approver = is_approver
            
    # def action_reject(self):
    #     """Reject the Import LC"""
    #     self.ensure_one()
    #     self.write({'state': 'reject'})
    #     _logger.info(f"✓ Import LC {self.lc_number} rejected by {self.env.user.name}")
    def action_reject(self):
        """Reject the Import LC - Only for Approvers"""
        self.ensure_one()

        if self.state != 'draft':
            raise ValidationError(_('Only a draft Import LC can be rejected.'))
        
        # Check if current user is an approver
        if not self._user_is_lc_approver():
            raise AccessError(
                "Access Denied!\n\n"
                "Only users with Approver rights can reject Import LCs.\n"
                "Please contact your administrator if you need this access."
            )
        
        self.write({'state': 'reject'})
        _logger.info(f"✓ Import LC {self.lc_number} rejected by {self.env.user.name}")
        return True
   

    @api.depends('journal_entry_ids')
    def _compute_journal_entry_count(self):
        """Count active journal entries linked to this LC"""
        for record in self:
            # Count only journal entries (not invoices) and exclude cancelled
            valid_entries = record.journal_entry_ids.filtered(
                lambda e: e.move_type == 'entry' and e.state != 'cancel'
            )
            record.journal_entry_count = len(valid_entries)
            
            if record.lc_number:
                _logger.info(f"✓ LC {record.lc_number}: {len(valid_entries)} journal entries linked")
    
    @api.depends(
        'journal_entry_ids', 'journal_entry_ids.import_lc_charge_total',
        'journal_entry_ids.state', 'journal_entry_ids.reversed_entry_id',
    )
    def _compute_journal_entry_total(self):
        """Calculate total amount of all posted journal entries"""
        for record in self:
            # Sum only posted journal entries
            posted_entries = record.journal_entry_ids.filtered(
                lambda e: e.state == 'posted' and e.move_type == 'entry'
            )
            
            # Miscellaneous entries have no invoice amount_total. Use their
            # company-currency debits and subtract posted reversals.
            total = sum(
                -entry.import_lc_charge_total if entry.reversed_entry_id else entry.import_lc_charge_total
                for entry in posted_entries
            )
            record.journal_entry_total = total
            
            if record.lc_number and posted_entries:
                _logger.info(f"✓ LC {record.lc_number}: Total Other Charges = {total} ({len(posted_entries)} posted entries)")
   
    def action_create_invoice(self):
        """Create or upload vendor bill"""
        return {
            'name': 'Create Vendor Bill',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_move_form').id,
            'target': 'new',
            'context': {
                'default_move_type': 'in_invoice',
                'default_partner_id': self.supplier_id.id if hasattr(self, 'supplier_id') else False,
                'default_import_lc_id': self.id,
                'default_currency_id': self.currency_id.id,
                'default_ref': self.lc_number,
            }
        }
    # @api.depends('ci_invoice_id')
    # def _compute_invoice_count(self):
    #     for record in self:
    #         record.invoice_count = 1 if record.ci_invoice_id else 0
    # @api.depends('lc_order_ids', 'lc_order_ids.po_number', 'lc_order_ids.po_number.invoice_ids')
    # def _compute_invoice_count(self):
    #     for record in self:
    #         invoice_count = 0
    #         if record.lc_order_ids:
    #             for lc_order in record.lc_order_ids:
    #                 if lc_order.po_number:
    #                     invoice_count += len(lc_order.po_number.invoice_ids)
    #         record.invoice_count = invoice_count
    
    @api.depends('lc_order_id', 'lc_order_id.po_number', 'lc_order_id.po_number.invoice_ids', 'ci_ids', 'ci_ids.bill_ids')
    def _compute_invoice_count(self):
        """Count bills from BOTH Purchase Orders AND Commercial Invoices"""
        for record in self:
            invoice_count = 0
            
            # Count bills from the single linked Purchase Order
            if record.lc_order_id and record.lc_order_id.po_number:
                invoice_count += len(record.lc_order_id.po_number.invoice_ids)
            
            # Count bills from Commercial Invoices
            if record.ci_ids:
                for ci in record.ci_ids:
                    if ci.bill_ids:
                        # Count only non-cancelled bills
                        valid_bills = ci.bill_ids.filtered(lambda b: b.state != 'cancel')
                        invoice_count += len(valid_bills)
            
            record.invoice_count = invoice_count
        
    @api.depends('ci_ids')
    def _compute_ci_count(self):
        """Count Commercial Invoices linked to this Import LC"""
        for record in self:
            record.ci_count = len(record.ci_ids)
    # def action_confirm(self):
    #     """Confirm the Import LC and related Purchase Order"""
    #     self.ensure_one()
        
    #     # Find related Purchase Order through PI number
    #     po = False
    #     if self.pi_number:
    #         lc_orders = self.env['lc.order'].search([
    #             ('pi_number', '=', self.pi_number)
    #         ], limit=1)
            
    #         if lc_orders and lc_orders.po_number:
    #             po = lc_orders.po_number
        
    #     if not po:
    #         # Show error notification
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': _('Error'),
    #                 'message': _('No Purchase Order found for this PI number.'),
    #                 'type': 'danger',
    #                 'sticky': False,
    #             }
    #         }
        
    #     # Check if PO is already confirmed - Show popup and make button disappear
    #     if po.state in ['purchase', 'done']:
    #         # Update state to trigger button visibility change
    #         self.write({'state': 'confirmed'})
            
    #         # Show warning notification
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': _('Already Confirmed'),
    #                 'message': _('Purchase Order %s is already confirmed! (Status: %s)') % (
    #                     po.name, 
    #                     dict(po._fields['state'].selection).get(po.state, po.state)
    #                 ),
    #                 'type': 'warning',
    #                 'sticky': False,
    #                 'next': {
    #                     'type': 'ir.actions.client',
    #                     'tag': 'reload',
    #                 }
    #             }
    #         }
        
    #     # Check if PO is cancelled
    #     if po.state == 'cancel':
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': _('Cancelled Order'),
    #                 'message': _('Purchase Order %s is cancelled! Cannot confirm.') % po.name,
    #                 'type': 'danger',
    #                 'sticky': False,
    #             }
    #         }
        
    #     # Confirm the Purchase Order (only if draft/sent/to approve)
    #     if po.state in ['draft', 'sent', 'to approve']:
    #         try:
    #             # Confirm the PO
    #             po.button_confirm()
    #             _logger.info(f"✓ Purchase Order {po.name} confirmed via Import LC {self.lc_number}")
                
    #             # Update Import LC state to confirmed
    #             self.write({'state': 'confirmed'})
                
    #             # Show success notification and reload to hide the button
    #             return {
    #                 'type': 'ir.actions.client',
    #                 'tag': 'display_notification',
    #                 'params': {
    #                     'title': _('Success'),
    #                     'message': _('Purchase Order %s has been confirmed successfully!') % po.name,
    #                     'type': 'success',
    #                     'sticky': False,
    #                     'next': {
    #                         'type': 'ir.actions.client',
    #                         'tag': 'reload',
    #                     }
    #                 }
    #             }
    #         except Exception as e:
    #             _logger.error(f"Failed to confirm PO {po.name}: {str(e)}")
    #             return {
    #                 'type': 'ir.actions.client',
    #                 'tag': 'display_notification',
    #                 'params': {
    #                     'title': _('Confirmation Failed'),
    #                     'message': _('Failed to confirm Purchase Order %s.\n\nError: %s') % (po.name, str(e)),
    #                     'type': 'danger',
    #                     'sticky': True,
    #                 }
    #             }
        
    #     _logger.info(f"✓ Import LC {self.lc_number} confirmed")
        
    #     # Default: Reload the form
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'reload',
    #     }
    def action_confirm(self):
        """Confirm the Import LC and related Purchase Order - Only for Approvers"""
        self.ensure_one()
        
        # Check if current user is an approver
        if not self._user_is_lc_approver():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Access Denied'),
                    'message': _('Only users with Approver rights can confirm Import LCs.\n\nPlease contact your administrator if you need this access.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        # Resolve the Purchase Order from the selected LC Order; no ambiguous PI lookup.
        po = self.lc_order_id.po_number if self.lc_order_id else False
        
        if not po:
            # Show error notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('No Purchase Order found for this PI number.'),
                    'type': 'danger',
                    'sticky': False,
                }
            }
        
        # Check if PO is already confirmed - Show popup and make button disappear
        if po.state in ['purchase', 'done']:
            # Update state to trigger button visibility change
            self.write({'state': 'confirmed'})
            
            # Show warning notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Already Confirmed'),
                    'message': _('Purchase Order %s is already confirmed! (Status: %s)') % (
                        po.name, 
                        dict(po._fields['state'].selection).get(po.state, po.state)
                    ),
                    'type': 'warning',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }
        
        # Check if PO is cancelled
        if po.state == 'cancel':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cancelled Order'),
                    'message': _('Purchase Order %s is cancelled! Cannot confirm.') % po.name,
                    'type': 'danger',
                    'sticky': False,
                }
            }
        
        # Confirm the Purchase Order (the PI stage is an RFQ milestone too).
        if po.state in ['draft', 'sent', 'proforma', 'to approve']:
            try:
                # Confirm the PO
                po.button_confirm()
                _logger.info(f"✓ Purchase Order {po.name} confirmed via Import LC {self.lc_number} by {self.env.user.name}")
                
                # Update Import LC state to confirmed
                self.write({'state': 'confirmed'})
                
                # Show success notification and reload to hide the button
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Purchase Order %s has been confirmed successfully!') % po.name,
                        'type': 'success',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.client',
                            'tag': 'reload',
                        }
                    }
                }
            except Exception as e:
                _logger.error(f"Failed to confirm PO {po.name}: {str(e)}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Confirmation Failed'),
                        'message': _('Failed to confirm Purchase Order %s.\n\nError: %s') % (po.name, str(e)),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        
        _logger.info(f"✓ Import LC {self.lc_number} confirmed by {self.env.user.name}")
        
        # Default: Reload the form
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    @api.depends('pi_number', 'supplier_id', 'lc_order_id')
    def _compute_grn_ids(self):
        """
        Automatically compute GRNs based on PI number
        Chain: LC Order (PI) → Purchase Order → GRN
        """
        for record in self:
            grn_ids = []
            
            if record.pi_number and record.supplier_id:
                _logger.info(f"=== Computing GRNs for LC {record.lc_number} ===")
                _logger.info(f"PI Number: {record.pi_number}, Supplier: {record.supplier_id.name}")
                
                # Use the single authoritative PI link; fallback remains company-scoped for migrated records.
                lc_order = record.lc_order_id
                if not lc_order:
                    lc_order = self.env['lc.order'].search([
                        ('company_id', '=', record.company_id.id),
                        ('pi_number', '=', record.pi_number),
                    ], order='id desc', limit=1)
                    _logger.info(f"Fallback PI lookup: {lc_order.display_name if lc_order else 'not found'}")

                po_ids = []
                if lc_order and lc_order.po_number:
                    po_ids.append(lc_order.po_number.id)
                    _logger.info(f"  - LC Order {lc_order.name}: PO {lc_order.po_number.name}")
                
                # Also search for POs that might reference this PI in origin
                pos_by_origin = self.env['purchase.order'].search([
                    ('company_id', '=', record.company_id.id),
                    ('partner_id', '=', record.supplier_id.id),
                    ('origin', 'ilike', record.pi_number),
                ])
                
                if pos_by_origin:
                    po_ids.extend(pos_by_origin.ids)
                    _logger.info(f"Found {len(pos_by_origin)} additional PO(s) with PI in origin")
                
                # Remove duplicates
                po_ids = list(set(po_ids))
                
                if po_ids:
                    _logger.info(f"Total {len(po_ids)} Purchase Order(s) found")
                    
                    # Get all GRNs from these Purchase Orders
                    for po_id in po_ids:
                        po = self.env['purchase.order'].browse(po_id)
                        
                        # Find GRNs linked to this PO
                        pickings = self.env['stock.picking'].search([
                            ('purchase_id', '=', po.id),
                            ('picking_type_code', '=', 'incoming'),
                        ])
                        
                        if pickings:
                            grn_ids.extend(pickings.ids)
                            _logger.info(f"  - PO {po.name}: Found {len(pickings)} GRN(s)")
                            for p in pickings:
                                _logger.info(f"    * GRN {p.name}, State: {p.state}")
                        else:
                            _logger.info(f"  - PO {po.name}: No GRNs yet")
                
                # Remove duplicates
                grn_ids = list(set(grn_ids))
                
                record.grn_ids = [(6, 0, grn_ids)]
                record.grn_count = len(grn_ids)
                
                if grn_ids:
                    _logger.info(f"✓ LC {record.lc_number}: Total {len(grn_ids)} GRN(s) linked")
                else:
                    _logger.warning(f"⚠ LC {record.lc_number}: No GRNs found")
                    _logger.info(f"  Checked:")
                    _logger.info(f"  - Linked PI: {lc_order.display_name if lc_order else 'N/A'}")
                    _logger.info(f"  - {len(po_ids)} Purchase Order(s)")
                    _logger.info(f"  Make sure goods are received from these POs")
            else:
                record.grn_ids = [(6, 0, [])]
                record.grn_count = 0
    @api.depends('lc_order_id.po_number.state')
    def _compute_po_state(self):
        """Compute PO state from the authoritative LC Order link."""
        for record in self:
            record.po_state = record.lc_order_id.po_number.state if record.lc_order_id.po_number else False
    # def action_create_vendor_bill_from_ci(self):
    #     """
    #     Create vendor bill from Commercial Invoice (CI) product lines
    #     Simplified version - only CI information, no extra details
    #     """
    #     self.ensure_one()
        
    #     _logger.info(f"=== Creating Vendor Bill from Import LC {self.lc_number} using CI lines ===")
        
    #     # Validation: Check if supplier exists
    #     if not self.supplier_id:
    #         raise ValidationError(_('Please select a Supplier before creating a bill.'))
        
    #     # Find Commercial Invoices linked to this LC
    #     commercial_invoices = self.ci_ids.filtered(lambda ci: ci.state != 'cancel')
        
    #     if not commercial_invoices:
    #         raise ValidationError(
    #             _('No Commercial Invoices found for this Import LC.\n\n'
    #             'Please create a Commercial Invoice first before creating a vendor bill.')
    #         )
        
    #     # Use the first confirmed CI (or any CI if none confirmed)
    #     ci = commercial_invoices.filtered(lambda c: c.state == 'confirmed')
    #     if not ci:
    #         ci = commercial_invoices[0]
    #     else:
    #         ci = ci[0]
        
    #     _logger.info(f"Using CI {ci.ci_number} for bill creation")
        
    #     # Check if CI has product lines
    #     if not ci.product_line_ids:
    #         raise ValidationError(
    #             _('Commercial Invoice %s has no product lines.\n\n'
    #             'Please add products to the CI before creating a vendor bill.') % ci.ci_number
    #         )
        
    #     # Check for zero prices
    #     zero_price_products = ci.product_line_ids.filtered(lambda l: l.unit_price <= 0)
    #     if zero_price_products:
    #         product_names = ', '.join(zero_price_products.mapped('product_name'))
    #         raise ValidationError(
    #             _('The following products in CI %s have zero or negative prices:\n%s\n\n'
    #             'Please set valid prices before creating a bill.') % (ci.ci_number, product_names)
    #         )
        
    #     # Prepare bill line values from CI product lines
    #     invoice_line_vals = []
        
    #     for ci_line in ci.product_line_ids:
    #         if not ci_line.product_id:
    #             _logger.warning(f"Skipping CI line without product_id")
    #             continue
            
    #         # Get product accounts
    #         product = ci_line.product_id
    #         accounts = product.product_tmpl_id.get_product_accounts()
            
    #         # Get the correct UOM - Odoo 19 compatible
    #         product_uom = product.uom_id
            
    #         line_vals = {
    #             'product_id': product.id,
    #             'name': ci_line.product_name or product.name,
    #             'price_unit': ci_line.unit_price,
    #             'product_uom_id': product_uom.id,
    #             'account_id': accounts['expense'].id if accounts.get('expense') else False,
    #         }
            
    #         # Add tax if product has supplier taxes
    #         if product.supplier_taxes_id:
    #             line_vals['tax_ids'] = [(6, 0, product.supplier_taxes_id.ids)]
            
    #         invoice_line_vals.append((0, 0, line_vals))
        
    #     if not invoice_line_vals:
    #         raise ValidationError(_('No valid product lines found in CI to create bill.'))
        
    #     # Prepare vendor bill values - SIMPLIFIED VERSION
    #     bill_vals = {
    #         'move_type': 'in_invoice',
    #         'partner_id': self.supplier_id.id,
    #         'invoice_date': ci.ci_date or fields.Date.today(),
    #         'currency_id': self.currency_id.id if self.currency_id else self.env.company.currency_id.id,
    #         'ref': ci.ci_number,  # Only CI number in Bill Reference
    #         'invoice_line_ids': invoice_line_vals,
    #         'import_ci_id': ci.id,  # Link to CI
    #         # Removed: narration field (no extra text)
    #         # Removed: invoice_origin field (no extra LC/PI details)
    #     }
        
    #     # Create the vendor bill
    #     try:
    #         bill = self.env['account.move'].create(bill_vals)
    #         _logger.info(f"✓ Created Vendor Bill {bill.name} from CI {ci.ci_number}")
            
    #         # Update CI state to billed
    #         ci.write({'state': 'billed'})
            
    #         # Show success notification and open the bill
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': _('Success'),
    #                 'message': _('Vendor Bill %s created successfully from CI %s!') % (bill.name, ci.ci_number),
    #                 'type': 'success',
    #                 'sticky': False,
    #                 'next': {
    #                     'type': 'ir.actions.act_window',
    #                     'res_model': 'account.move',
    #                     'res_id': bill.id,
    #                     'view_mode': 'form',
    #                     'views': [(False, 'form')],
    #                 }
    #             }
    #         }
        
    #     except Exception as e:
    #         _logger.error(f"Failed to create vendor bill from CI {ci.ci_number}: {str(e)}")
    #         raise ValidationError(
    #             _('Failed to create vendor bill.\n\nError: %s') % str(e)
    #         )
    def action_create_vendor_bill_from_ci(self):
        """
        Create vendor bill from the LATEST Commercial Invoice (CI) product lines
        WITH PROPER PURCHASE ORDER LINKING
        """
        self.ensure_one()
        
        _logger.info(f"=== Creating Vendor Bill from Import LC {self.lc_number} using LATEST CI ===")
        
        # Validation: Check if supplier exists
        if not self.supplier_id:
            raise ValidationError(_('Please select a Supplier before creating a bill.'))
        
        # Find Commercial Invoices linked to this LC (exclude cancelled)
        commercial_invoices = self.ci_ids.filtered(lambda ci: ci.state != 'cancel')
        
        if not commercial_invoices:
            raise ValidationError(
                _('No Commercial Invoices found for this Import LC.\n\n'
                'Please create a Commercial Invoice first before creating a vendor bill.')
            )
        
        # Get the LATEST CI by creation date
        latest_ci = commercial_invoices.sorted(key=lambda ci: ci.create_date, reverse=True)[0]
        
        _logger.info(f"✓ Found {len(commercial_invoices)} CI(s), using LATEST: {latest_ci.ci_number} (Created: {latest_ci.create_date})")
        _logger.info(f"✓ Latest CI state: {latest_ci.state}")
        
        # Check if CI has product lines
        if not latest_ci.product_line_ids:
            raise ValidationError(
                _('Commercial Invoice %s has no product lines.\n\n'
                'Please add products to the CI before creating a vendor bill.') % latest_ci.ci_number
            )
        
        # Check for zero prices
        zero_price_products = latest_ci.product_line_ids.filtered(lambda l: l.unit_price <= 0)
        if zero_price_products:
            product_names = ', '.join(zero_price_products.mapped('product_name'))
            raise ValidationError(
                _('The following products in CI %s have zero or negative prices:\n%s\n\n'
                'Please set valid prices before creating a bill.') % (latest_ci.ci_number, product_names)
            )
        
        # Check if any CI quantity is entered
        lines_with_ci_qty = latest_ci.product_line_ids.filtered(lambda l: l.ci_quantity > 0)
        if not lines_with_ci_qty:
            raise ValidationError(_(
                'Cannot create Vendor Bill from CI %s!\n\n'
                'No products have CI Quantity entered.\n'
                'Please enter CI Quantity for at least one product in the Commercial Invoice.'
            ) % latest_ci.ci_number)
        
        # The selected LC Order is authoritative; never guess a PO by PI text.
        purchase_order = self.lc_order_id.po_number if self.lc_order_id else False
        if purchase_order:
            _logger.info(f"✓ Found related PO: {purchase_order.name}")
        else:
            _logger.warning(f"⚠ No PO is linked to LC Order {self.lc_order_id.display_name}")
        
        # Prepare bill line values from CI product lines (only lines with CI quantity > 0)
        invoice_line_vals = []
        
        for ci_line in lines_with_ci_qty:
            if not ci_line.product_id:
                _logger.warning(f"Skipping CI line without product_id")
                continue
            
            # Keep account selection in Odoo's standard stock accounting flow.
            product = ci_line.product_id
            
            # Get the correct UOM
            product_uom = product.uom_id
            
            # Use ci_quantity for the bill
            line_vals = {
                'product_id': product.id,
                'name': ci_line.product_name or product.name,
                'quantity': ci_line.ci_quantity,
                'price_unit': ci_line.unit_price,
                'product_uom_id': product_uom.id,
            }
            
            # Link to Purchase Order Line if PO exists
            if purchase_order:
                po_line = purchase_order.order_line.filtered(
                    lambda l: l.product_id.id == product.id
                )
                if po_line:
                    line_vals['purchase_line_id'] = po_line[0].id
                    _logger.info(f"  ✓ Linked to PO line: {po_line[0].id}")
            
            # Add tax if product has supplier taxes
            if product.supplier_taxes_id:
                line_vals['tax_ids'] = [(6, 0, product.supplier_taxes_id.ids)]
            
            invoice_line_vals.append((0, 0, line_vals))
            _logger.info(f"Prepared bill line: {ci_line.product_name}, Qty: {ci_line.ci_quantity}, Price: {ci_line.unit_price}")
        
        if not invoice_line_vals:
            raise ValidationError(_('No valid product lines found in CI to create bill.'))
        
        # Prepare vendor bill values
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.supplier_id.id,
            'invoice_date': latest_ci.ci_date or fields.Date.today(),
            'currency_id': self.currency_id.id if self.currency_id else self.env.company.currency_id.id,
            'ref': latest_ci.ci_number,
            'invoice_line_ids': invoice_line_vals,
            'import_ci_id': latest_ci.id,
        }
        
        # Link to Purchase Order if found
        if purchase_order:
            bill_vals.update({
                'purchase_id': purchase_order.id,
                'invoice_origin': purchase_order.name,
            })
            _logger.info(f"✓ Bill will be linked to PO {purchase_order.name}")
        else:
            # If no PO, set origin to PI/CI reference
            bill_vals['invoice_origin'] = f"CI: {latest_ci.ci_number} | PI: {self.pi_number}" if self.pi_number else f"CI: {latest_ci.ci_number}"
            _logger.warning(f"⚠ Bill created WITHOUT PO link (no PO found)")
        
        # Create the vendor bill
        try:
            bill = self.env['account.move'].create(bill_vals)
            _logger.info(f"✓ Created Vendor Bill {bill.name} from LATEST CI {latest_ci.ci_number}")
            
            # Update PO invoice status if linked
            if purchase_order:
                purchase_order._compute_invoice()
                _logger.info(f"✓ Updated PO {purchase_order.name} invoice status")
            
            # Note: CI state remains 'draft' - the model only supports 'draft' and 'cancel' states
            _logger.info(f"✓ Vendor bill created successfully for CI {latest_ci.ci_number}")
            
            # Prepare success message
            other_cis_count = len(commercial_invoices) - 1
            existing_bills_count = len(latest_ci.bill_ids) if hasattr(latest_ci, 'bill_ids') else 0
            
            message_parts = [f'Vendor Bill {bill.name} created from LATEST CI {latest_ci.ci_number}']
            
            if purchase_order:
                message_parts.append(f' and linked to PO {purchase_order.name}')
            
            if existing_bills_count > 1:
                message_parts.append(f'\n\n✓ This is bill #{existing_bills_count} for CI {latest_ci.ci_number}')
            
            if other_cis_count > 0:
                message_parts.append(f'\n\nℹ Note: {other_cis_count} other CI(s) exist for this Import LC.')
            
            # Show success notification and open the bill
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _(''.join(message_parts)),
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
            _logger.error(f"Failed to create vendor bill from CI {latest_ci.ci_number}: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
            raise ValidationError(
                _('Failed to create vendor bill.\n\nError: %s') % str(e)
            )
    # def action_view_commercial_invoices(self):
    
    #     self.ensure_one()
    #     return {
    #         'name': _('Commercial Invoices'),
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'import.ci',
    #         'view_mode': 'list,form',
    #         'domain': [('import_lc_id', '=', self.id)],
    #         'context': {
    #             'default_import_lc_id': self.id,
    #             'default_pi_number': self.pi_number,
    #         }
    #     }
    def action_view_commercial_invoices(self):
        """View Commercial Invoices linked to this Import LC"""
        self.ensure_one()
        
        # Use the existing action from XML
        action = self.env.ref('zencore_import_lc.action_import_ci').read()[0]
        
        # Override domain to show only CIs for this LC
        action['domain'] = [('import_lc_id', '=', self.id)]
        
        # Set default values for new CI creation
        action['context'] = {
            'default_import_lc_id': self.id,
            'default_pi_number': self.pi_number,
            'default_supplier_id': self.supplier_id.id if self.supplier_id else False,
        }
        
        return action
    # def action_view_vendor_bills(self):
    #     """Create vendor bill from related Purchase Order"""
    #     self.ensure_one()
        
    #     # Find PO through PI number
    #     po = False
    #     if self.pi_number:
    #         lc_orders = self.env['lc.order'].search([
    #             ('pi_number', '=', self.pi_number)
    #         ], limit=1)
            
    #         if lc_orders and lc_orders.po_number:
    #             po = lc_orders.po_number
        
    #     if not po:
    #         raise ValidationError(_('No Purchase Order found for this PI number.'))
        
    #     # Use the standard PO action to create bill
    #     return po.action_create_invoice()
    
    def action_view_vendor_bills(self):
        """View all vendor bills - from both PO and CI"""
        self.ensure_one()
        
        # Get bills from Purchase Orders
        po_bill_ids = []
        if self.invoice_ids:
            po_bill_ids = self.invoice_ids.ids
        
        # Get bills from Commercial Invoices
        ci_bill_ids = []
        for ci in self.ci_ids:
            if ci.bill_ids:
                ci_bill_ids.extend(ci.bill_ids.ids)
        
        # Combine all bill IDs and remove duplicates
        all_bill_ids = list(set(po_bill_ids + ci_bill_ids))
        
        if not all_bill_ids:
            # If no bills, show empty list with helpful message
            return {
                'type': 'ir.actions.act_window',
                'name': _('Vendor Bills'),
                'res_model': 'account.move',
                'view_mode': 'list,form',
                'domain': [('id', 'in', [])],
                'context': {
                    'default_move_type': 'in_invoice',
                    'default_partner_id': self.supplier_id.id if self.supplier_id else False,
                },
                'help': _('''<p class="o_view_nocontent_smiling_face">
                    No vendor bills found
                </p><p>
                    Create bills from Commercial Invoices or Purchase Orders.
                </p>''')
            }
        
        # Use Odoo's standard vendor bill action
        try:
            action = self.env.ref('account.action_move_in_invoice_type').read()[0]
        except:
            # Fallback if reference doesn't exist
            action = {
                'type': 'ir.actions.act_window',
                'name': _('Vendor Bills'),
                'res_model': 'account.move',
                'view_mode': 'list,form',
            }
        
        # Override domain to show only our bills
        action['domain'] = [('id', 'in', all_bill_ids)]
        
        # Set default values
        action['context'] = {
            'default_move_type': 'in_invoice',
            'default_partner_id': self.supplier_id.id if self.supplier_id else False,
        }
        
        return action
    
    # @api.depends('pi_number', 'lc_order_ids', 'lc_order_ids.po_number', 'lc_order_ids.po_number.invoice_ids')
    # def _compute_invoice_ids(self):
    #     """Compute all bills related to this Import LC via PI number"""
    #     for record in self:
    #         invoice_ids = []
            
    #         if record.pi_number:
    #             # Search all LC Orders with this PI number
    #             lc_orders = self.env['lc.order'].search([
    #                 ('pi_number', '=', record.pi_number)
    #             ])
                
    #             # Get bills from all POs linked to these LC Orders
    #             for lc_order in lc_orders:
    #                 if lc_order.po_number and lc_order.po_number.invoice_ids:
    #                     # Filter only vendor bills (not credit notes)
    #                     bills = lc_order.po_number.invoice_ids.filtered(
    #                         lambda inv: inv.move_type == 'in_invoice'
    #                     )
                        
    #                     if bills:
    #                         invoice_ids.extend(bills.ids)
                
    #             # Remove duplicates
    #             invoice_ids = list(set(invoice_ids))
            
    #         # Set the computed field
    #         record.invoice_ids = [(6, 0, invoice_ids)]
    
    @api.depends('pi_number', 'lc_order_id', 'lc_order_id.po_number', 'lc_order_id.po_number.invoice_ids', 'ci_ids', 'ci_ids.bill_ids')
    def _compute_invoice_ids(self):
        """Compute all bills related to this Import LC - from BOTH POs AND CIs"""
        for record in self:
            invoice_ids = []
            
            # Get bills from the single linked Purchase Order
            if record.pi_number and record.lc_order_id and record.lc_order_id.po_number:
                bills = record.lc_order_id.po_number.invoice_ids.filtered(
                    lambda inv: inv.move_type == 'in_invoice'
                )
                if bills:
                    invoice_ids.extend(bills.ids)
            
            # Get bills from Commercial Invoices
            if record.ci_ids:
                for ci in record.ci_ids:
                    if ci.bill_ids:
                        # Filter only non-cancelled bills
                        valid_bills = ci.bill_ids.filtered(
                            lambda b: b.move_type == 'in_invoice' and b.state != 'cancel'
                        )
                        if valid_bills:
                            invoice_ids.extend(valid_bills.ids)
            
            # Remove duplicates
            invoice_ids = list(set(invoice_ids))
            
            # Set the computed field
            record.invoice_ids = [(6, 0, invoice_ids)]
    def action_create_commercial_invoice(self):
        """Action to create a new Commercial Invoice from Import LC"""
        self.ensure_one()
        return {
            'name': _('Create Commercial Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.ci',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_import_lc_id': self.id,
                'default_pi_number': self.pi_number,
            }
        }
    
    
    @api.depends('pi_number', 'lc_number', 'supplier_id', 'grn_ids')
    def _compute_document_chain_summary(self):
        """Compute document chain showing PI → PO → Work Order → GRN"""
        for record in self:
            lines = []
            
            # Header
            lines.append("=" * 70)
            lines.append("IMPORT LC - COMPLETE DOCUMENT CHAIN")
            lines.append("=" * 70)
            lines.append("")
            
            # Import LC Info
            lines.append(f"IMPORT LC NUMBER  : {record.lc_number or 'N/A'}")
            lines.append(f"PI NUMBER         : {record.pi_number or 'N/A'}")
            lines.append(f"SUPPLIER          : {record.supplier_id.name if record.supplier_id else 'N/A'}")
            lines.append(f"TOTAL LC COST     : {record.total_lc_cost:,.2f} {record.currency_id.name if record.currency_id else ''}")
            lines.append(f"LC STATUS         : {record.state.upper()}")
            lines.append(f"OPENING DATE      : {record.lc_opening_date.strftime('%Y-%m-%d') if record.lc_opening_date else 'N/A'}")
            lines.append(f"EXPIRY DATE       : {record.lc_expiry_date.strftime('%Y-%m-%d') if record.lc_expiry_date else 'N/A'}")
            lines.append("")
            lines.append("-" * 70)
            
            # GRNs and their chains
            if record.grn_ids:
                lines.append(f"LINKED GOODS RECEIPT NOTES (GRNs): {len(record.grn_ids)}")
                lines.append("-" * 70)
                
                for idx, grn in enumerate(record.grn_ids, 1):
                    lines.append(f"\n[GRN #{idx}] {grn.name}")
                    lines.append(f"  Status      : {dict(grn._fields['state'].selection).get(grn.state, grn.state).upper()}")
                    lines.append(f"  Date        : {grn.scheduled_date.strftime('%Y-%m-%d') if grn.scheduled_date else 'N/A'}")
                    lines.append(f"  Location    : {grn.location_dest_id.name if grn.location_dest_id else 'N/A'}")
                    
                    # Purchase Order
                    if grn.purchase_id:
                        po = grn.purchase_id
                        lines.append(f"  ├─ PO       : {po.name}")
                        lines.append(f"  │  Amount   : {po.amount_total:,.2f} {po.currency_id.name if po.currency_id else ''}")
                        lines.append(f"  │  Date     : {po.date_order.strftime('%Y-%m-%d') if po.date_order else 'N/A'}")
                        lines.append(f"  │  Status   : {dict(po._fields['state'].selection).get(po.state, po.state).upper()}")
                    elif grn.origin:
                        lines.append(f"  ├─ Source   : {grn.origin}")
                    else:
                        lines.append(f"  ├─ PO       : Not Linked")
                    
                    # Work Orders
                    wo_domain = [('company_id', '=', grn.company_id.id)]
                    if grn.origin:
                        wo_domain += ['|', ('origin', 'ilike', grn.origin), ('origin', 'ilike', grn.name)]
                    else:
                        wo_domain += [('origin', 'ilike', grn.name)]
                    work_orders = self.env['mrp.production'].search(wo_domain, limit=5)
                    
                    if work_orders:
                        lines.append(f"  │")
                        for wo_idx, wo in enumerate(work_orders, 1):
                            prefix = "  └─" if wo_idx == len(work_orders) and not grn.move_ids_without_package else "  ├─"
                            lines.append(f"{prefix} WO       : {wo.name}")
                            lines.append(f"  │  Product : {wo.product_id.name if wo.product_id else 'N/A'}")
                            lines.append(f"  │  Qty     : {wo.product_qty} {wo.product_uom_id.name if wo.product_uom_id else ''}")
                            lines.append(f"  │  Status  : {dict(wo._fields['state'].selection).get(wo.state, wo.state).upper()}")
                            if wo_idx < len(work_orders):
                                lines.append(f"  │")
                    
                    # Products summary
                    if grn.move_ids:
                        product_count = len(grn.move_ids)
                        lines.append(f"  │")
                        lines.append(f"  └─ Products : {product_count} item(s)")
                        
                        for move_idx, move in enumerate(grn.move_ids[:5], 1):
                            qty_info = f"{move.quantity}/{move.product_uom_qty}" if move.state == 'done' else f"{move.product_uom_qty}"
                            status_icon = "✓" if move.state == 'done' else "○"
                            lines.append(f"     {status_icon} {move.product_id.name}: {qty_info} {move.product_uom.name}")
                        
                        if product_count > 5:
                            lines.append(f"     ... and {product_count - 5} more items")
            else:
                lines.append("\n⚠️  NO GRNs LINKED TO THIS IMPORT LC YET")
                lines.append("")
                lines.append("   GRNs will automatically appear here once:")
                lines.append("   1. Purchase Orders are created with PI number in 'Source Document' field")
                lines.append("   2. Goods are received against those Purchase Orders")
                lines.append("")
                lines.append(f"   Required: PO must have '{record.pi_number}' in Source Document (origin)")
                lines.append(f"   Supplier: {record.supplier_id.name if record.supplier_id else 'N/A'}")
            
            lines.append("\n" + "=" * 70)
            lines.append("END OF DOCUMENT CHAIN")
            lines.append("=" * 70)
            
            record.document_chain_summary = '\n'.join(lines)
    
    @api.depends('landed_cost_ids')
    def _compute_all_landed_costs(self):
        """Expose only landed costs linked to this LC; never leak unrelated company data."""
        for record in self:
            record.all_landed_cost_ids = record.landed_cost_ids
    @api.onchange('lc_order_id')
    def _onchange_lc_order_id(self):
        """Keep the hidden legacy relation synchronized with the single PI."""
        if self.lc_order_id:
            self.lc_order_ids = [(6, 0, [self.lc_order_id.id])]
        else:
            self.lc_order_ids = [(5, 0, 0)]

    def _get_pi_number_selection(self):
        """Deprecated compatibility helper; PI selection now comes from lc_order_id."""
        return []

    # @api.model
    # def _get_pi_number_selection(self):
    #     """Dynamically get PI numbers from lc.order"""
    #     lc_orders = self.env['lc.order'].search([('pi_number', '!=', False)])
    #     pi_numbers = lc_orders.mapped('pi_number')
    #     pi_numbers = sorted(set(pi_numbers))
    #     return [(pi, pi) for pi in pi_numbers if pi]

    # @api.depends('product_line_ids.total_cost')
    # def _compute_total_lc_cost(self):
    #     for lc in self:
    #         lc.total_lc_cost = sum(line.total_cost for line in lc.product_line_ids)
    
    @api.depends('lc_amount', 'lc_conversion_rate')
    def _compute_total_lc_cost(self):
        for lc in self:
            lc.total_lc_cost = (lc.lc_amount or 0.0) * (lc.lc_conversion_rate or 0.0)
    
    @api.depends('total_lc_cost', 'margin_rate')
    def _compute_margin_value(self):
        for lc in self:
            if lc.margin_rate:
                lc.margin_value = lc.total_lc_cost * (lc.margin_rate / 100)
                
            else:
                lc.margin_value = 0.0
    
    @api.constrains('lc_order_id', 'pi_number', 'company_id')
    def _check_lc_order_consistency(self):
        for lc in self:
            if not lc.lc_order_id:
                continue
            if lc.company_id != lc.lc_order_id.company_id:
                raise ValidationError(_('Import LC company must match the selected LC Order company.'))
            if lc.pi_number != lc.lc_order_id.pi_number:
                raise ValidationError(_('Import LC PI Number must match the selected LC Order PI Number.'))

    @api.constrains('lc_expiry_date', 'shipment_expiry_date')
    def _check_dates(self):
        for lc in self:
            if lc.shipment_expiry_date > lc.lc_expiry_date:
                raise ValidationError(_('Shipment expiry cannot exceed LC expiry.'))
    
    @api.constrains('tenor_days')
    def _check_tenor_days(self):
        for lc in self:
            if lc.tenor_days < 0:
                raise ValidationError(_('Tenor days must be positive.'))
    
    def action_view_grn(self):
        """Smart button action to view all GRNs"""
        self.ensure_one()
        return {
            'name': _('Goods Receipt Notes'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.grn_ids.ids)],
            'context': {
                'default_picking_type_code': 'incoming',
            }
        }
    
    @api.model_create_multi
    def create(self, vals_list):
        """Base create layer for Import LC.

        The enterprise workflow enforces one approved PI per Import LC.
        The hidden legacy many-to-many relation is maintained only for upgrade compatibility.
        """
        prepared = []
        for raw_vals in vals_list:
            vals = dict(raw_vals)
            lc_number = (vals.get('lc_number') or '').strip()
            if not lc_number or lc_number.lower() == 'new':
                raise ValidationError(_('LC Number is mandatory. Enter the exact bank-issued LC Number.'))
            vals['lc_number'] = lc_number
            prepared.append(vals)
        return super(ImportLC, self).create(prepared)

    def write(self, vals):
        """Base write layer; single-PI synchronization is handled by enterprise_flow."""
        vals = dict(vals)
        if 'lc_number' in vals:
            lc_number = (vals.get('lc_number') or '').strip()
            if not lc_number or lc_number.lower() == 'new':
                raise ValidationError(_('LC Number is mandatory and cannot be "New".'))
            vals['lc_number'] = lc_number

        if 'state' in vals:
            target_state = vals.get('state')
            protected_target = target_state in ('confirmed', 'done', 'reject')
            reopening_protected = target_state == 'draft' and any(
                record.state in ('confirmed', 'done', 'reject') for record in self
            )
            if (protected_target or reopening_protected) and not self._user_is_lc_approver():
                raise AccessError(_('Only LC Approvers can confirm, reject, complete, or reopen Import LCs.'))

        return super(ImportLC, self).write(vals)

    @api.model
    def _prepare_product_lines_from_pi(self, pi_number, lc_order_id=False):
        """
        Prepare product line commands from PI number
        Returns a list of (0, 0, {vals}) commands
        """
        _logger.info(f"=== _prepare_product_lines_from_pi called with PI: {pi_number} ===")
        
        if not pi_number:
            _logger.warning("No PI number provided")
            return []
        
        lc_order = self.env['lc.order'].browse(lc_order_id).exists() if lc_order_id else self.env['lc.order']
        if not lc_order:
            lc_order = self.env['lc.order'].search([
                ('company_id', '=', self.env.company.id),
                ('pi_number', '=', pi_number),
            ], order='id desc', limit=1)
        
        if not lc_order:
            _logger.warning(f"No LC Order found for PI: {pi_number}")
            return []
        
        _logger.info(f"Found LC Order {lc_order.id} with {len(lc_order.lc_line_ids)} lines")
        
        if not lc_order.lc_line_ids:
            _logger.warning(f"LC Order {lc_order.id} has no product lines!")
            return []
        
        line_commands = []
        for idx, line in enumerate(lc_order.lc_line_ids):
            if not line.product_id:
                _logger.warning(f"Line {idx}: Skipping - no product_id")
                continue
            
            product = line.product_id
            _logger.info(f"Line {idx}: Processing product ID {product.id} - {product.name}")
            
            product_name = product.name or product.display_name or product.default_code or f"Product {product.id}"
            product_name = str(product_name).strip()
            
            if not product_name:
                _logger.error(f"Line {idx}: Product {product.id} has no valid name - SKIPPING")
                continue
            
            line_vals = {
                'product_id': product.id,
                'product_name': product_name,
                'product_category_id': line.product_category_id.id if line.product_category_id else False,
                'quantity': float(line.quantity) if line.quantity else 0.0,
                'unit_price': float(line.unit_price) if line.unit_price else 0.0,
            }
            
            _logger.info(f"Line {idx}: Prepared command with vals: {line_vals}")
            line_commands.append((0, 0, line_vals))
        
        _logger.info(f"=== Prepared {len(line_commands)} product line commands ===")
        return line_commands
    
    @api.onchange('pi_number')
    def _onchange_pi_number(self):
        """Deprecated compatibility hook.

        ``pi_number`` is derived from the selected PI in the single-PI workflow.
        Direct edits are ignored; change ``lc_order_id`` instead.
        """
        return


class ImportLCProductLine(models.Model):
    _name = 'import.lc.product.line'
    _description = 'Import LC Product Line'
    
    import_lc_id = fields.Many2one(
        'import.lc',
        string='Import LC',
        required=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one('res.company', related='import_lc_id.company_id', store=True, index=True, readonly=True)
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
    )
    
    product_name = fields.Char(
        string='Product Name',
        required=True,
        store=True,
    )
    
    product_category_id = fields.Many2one(
        'product.category',
        string='Category',
        store=True,
    )
    
    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=0.0,
    )
    
    unit_price = fields.Float(
        string='Unit Price',
        required=True,
        default=0.0,
    )
    
    total_cost = fields.Float(
        string='Total LC Cost',
        compute='_compute_total_cost',
        store=True,
    )
    
    @api.depends('quantity', 'unit_price')
    def _compute_total_cost(self):
        for line in self:
            line.total_cost = line.quantity * line.unit_price
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Auto-fill product name and category when product is selected"""
        if self.product_id:
            product = self.product_id
            product_name = product.name or product.display_name or product.default_code or f"Product {product.id}"
            self.product_name = str(product_name).strip()
            self.product_category_id = product.categ_id
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure product_name is always set"""
        _logger.info(f"=== ImportLCProductLine.create called with {len(vals_list)} records ===")
        
        processed_vals = []
        
        for idx, vals in enumerate(vals_list):
            _logger.info(f"Line Record {idx}: {vals}")
            
            if not vals.get('product_id'):
                _logger.warning(f"Line Record {idx}: Skipping - no product_id")
                continue
            
            if not vals.get('import_lc_id'):
                _logger.warning(f"Line Record {idx}: Skipping - no import_lc_id")
                continue
            
            # Auto-set product_name if missing
            if not vals.get('product_name'):
                product = self.env['product.product'].browse(vals['product_id'])
                product_name = product.name or product.display_name or product.default_code or f"Product {product.id}"
                vals['product_name'] = str(product_name).strip()
                _logger.info(f"Line Record {idx}: Auto-set product_name to '{vals['product_name']}'")
            
            if not vals.get('product_name') or not vals['product_name'].strip():
                _logger.error(f"Line Record {idx}: product_name is invalid after processing - SKIPPING")
                continue
            
            processed_vals.append(vals)
        
        if not processed_vals:
            _logger.warning("No valid line records to create after processing")
            return self.env['import.lc.product.line']
        
        result = super(ImportLCProductLine, self).create(processed_vals)
        _logger.info(f"=== Successfully created {len(result)} product lines ===")
        
        for line in result:
            _logger.info(f"Created line ID {line.id}: {line.product_name}, Qty: {line.quantity}, Price: {line.unit_price}")
        
        return result


class ImportLCDocument(models.Model):
    _name = 'import.lc.document'
    _description = 'Import LC Document'
    
    import_lc_id = fields.Many2one('import.lc', string='Import LC', required=True, ondelete='cascade')
    name = fields.Char(string='Document Name', required=True)
    file = fields.Binary(string='File', required=True)
    file_name = fields.Char(string='File Name')
    company_id = fields.Many2one(related='import_lc_id.company_id', store=True, string='Company')


class ResCompanyBranch(models.Model):
    _name = 'res.company.branch'
    _description = 'Company Branch'
    _order = 'name'

    name = fields.Char(string='Branch Name', required=True)
    code = fields.Char(string='Branch Code')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    address = fields.Text(string='Address')
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    
    
class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'
    
    # Keep this field for manual linking of landed costs
    import_lc_id = fields.Many2one(
        'import.lc',
        string='Import LC',
        tracking=True,
        ondelete='restrict',
        help='Link this Landed Cost to an Import LC'
    )


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    
    # Removed import_lc_id field - GRNs are now computed automatically based on PI number
class CommercialInvoice(models.Model):
    _name = 'commercial.invoice'
    _description = 'Commercial Invoice'
    _rec_name = 'ci_number'

    ci_number = fields.Char(string='CI Number', required=True)
    ci_date = fields.Date(string='CI Date', required=True)
    

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    # NEW: Document Chain field for GRN traceability
    document_chain = fields.Text(
        string='Document Chain (PI→PO→WO→GRN)',
        compute='_compute_document_chain',
        store=False,
        help='Shows complete traceability: PI → PO → Work Order → GRN'
    )
    
    @api.depends('purchase_id', 'origin', 'partner_id', 'scheduled_date', 'state', 'move_ids')
    def _compute_document_chain(self):
        """Compute the complete document chain for this GRN"""
        for picking in self:
            if picking.picking_type_code != 'incoming':
                picking.document_chain = 'Not applicable (Not a GRN/Receipt)'
                continue
            
            lines = []
            
            # Header
            lines.append("=" * 70)
            lines.append("DOCUMENT TRACEABILITY CHAIN - GRN")
            lines.append("=" * 70)
            lines.append("")
            
            # 1. GRN Information
            lines.append(f"[1] GRN (GOODS RECEIPT NOTE)")
            lines.append(f"    GRN Number      : {picking.name}")
            lines.append(f"    Status          : {dict(picking._fields['state'].selection).get(picking.state, picking.state).upper()}")
            lines.append(f"    Scheduled Date  : {picking.scheduled_date.strftime('%Y-%m-%d %H:%M') if picking.scheduled_date else 'Not Set'}")
            lines.append(f"    Supplier        : {picking.partner_id.name if picking.partner_id else 'N/A'}")
            if picking.location_dest_id:
                lines.append(f"    Destination     : {picking.location_dest_id.display_name}")
            lines.append("")
            
            # 2. Import LC Information (search for matching LC)
            lines.append(f"[2] IMPORT LC (LETTER OF CREDIT)")
            
            # Resolve the LC deterministically from the linked Purchase Order first.
            lc = self.env['import.lc']
            if picking.purchase_id:
                lc = self.env['import.lc'].search([
                    ('company_id', '=', picking.company_id.id),
                    ('supplier_id', '=', picking.partner_id.id),
                    ('lc_order_id.po_number', '=', picking.purchase_id.id),
                ], order='id desc', limit=1)

                # Fallback only to an actual PI match in the PO source; never keep an arbitrary supplier LC.
                if not lc and picking.purchase_id.origin:
                    origin = picking.purchase_id.origin.strip()
                    lc = self.env['import.lc'].search([
                        ('company_id', '=', picking.company_id.id),
                        ('supplier_id', '=', picking.partner_id.id),
                        ('pi_number', '=', origin),
                    ], order='id desc', limit=1)
                    if not lc:
                        candidates = self.env['import.lc'].search([
                            ('company_id', '=', picking.company_id.id),
                            ('supplier_id', '=', picking.partner_id.id),
                            ('pi_number', '!=', False),
                        ], order='id desc')
                        lc = next((candidate for candidate in candidates if candidate.pi_number in origin), self.env['import.lc'])
            
            if lc:
                lines.append(f"    LC Number       : {lc.lc_number}")
                lines.append(f"    PI Number       : {lc.pi_number}")
                lines.append(f"    LC Type         : {dict(lc._fields['lc_type'].selection).get(lc.lc_type, lc.lc_type)}")
                lines.append(f"    Total LC Cost   : {lc.total_lc_cost:,.2f} {lc.currency_id.name if lc.currency_id else ''}")
                lines.append(f"    Opening Date    : {lc.lc_opening_date.strftime('%Y-%m-%d') if lc.lc_opening_date else 'N/A'}")
                lines.append(f"    Expiry Date     : {lc.lc_expiry_date.strftime('%Y-%m-%d') if lc.lc_expiry_date else 'N/A'}")
                lines.append(f"    Status          : {lc.state.upper()}")
            else:
                lines.append(f"    Status          : NOT LINKED")
                lines.append(f"    Note            : This GRN is not linked to any Import LC")
            lines.append("")
            
            # 3. Purchase Order Information
            lines.append(f"[3] PURCHASE ORDER")
            if picking.purchase_id:
                po = picking.purchase_id
                lines.append(f"    PO Number       : {po.name}")
                lines.append(f"    PO Date         : {po.date_order.strftime('%Y-%m-%d') if po.date_order else 'N/A'}")
                lines.append(f"    Vendor          : {po.partner_id.name}")
                lines.append(f"    Total Amount    : {po.amount_total:,.2f} {po.currency_id.name if po.currency_id else ''}")
                lines.append(f"    PO Status       : {dict(po._fields['state'].selection).get(po.state, po.state).upper()}")
                if po.payment_term_id:
                    lines.append(f"    Payment Terms   : {po.payment_term_id.name}")
            elif picking.origin:
                lines.append(f"    Source Doc      : {picking.origin}")
                lines.append(f"    Status          : Purchase Order not directly linked")
            else:
                lines.append(f"    Status          : NOT LINKED")
            lines.append("")
            
            # 4. Work Orders (Manufacturing Orders)
            lines.append(f"[4] WORK ORDERS (MANUFACTURING)")
            wo_domain = [('company_id', '=', picking.company_id.id)]
            if picking.origin:
                wo_domain += ['|', ('origin', 'ilike', picking.origin), ('origin', 'ilike', picking.name)]
            else:
                wo_domain += [('origin', 'ilike', picking.name)]
            work_orders = self.env['mrp.production'].search(wo_domain, limit=10)
            
            if work_orders:
                lines.append(f"    Found {len(work_orders)} Work Order(s):")
                for idx, wo in enumerate(work_orders, 1):
                    lines.append(f"    [{idx}] WO Number    : {wo.name}")
                    lines.append(f"        Product      : {wo.product_id.name if wo.product_id else 'N/A'}")
                    lines.append(f"        Quantity     : {wo.product_qty} {wo.product_uom_id.name if wo.product_uom_id else ''}")
                    lines.append(f"        Status       : {dict(wo._fields['state'].selection).get(wo.state, wo.state).upper()}")
                    if idx < len(work_orders):
                        lines.append("")
            else:
                lines.append(f"    Status          : NO WORK ORDERS FOUND")
                lines.append(f"    Note            : No manufacturing orders linked to this GRN")
            lines.append("")
            
            # 5. Products Summary
            lines.append(f"[5] PRODUCTS IN THIS GRN")
            if picking.move_ids:
                lines.append(f"    Total Products  : {len(picking.move_ids)}")
                lines.append(f"    Product Details :")
                for idx, move in enumerate(picking.move_ids[:10], 1):
                    qty_done = f"{move.quantity}/{move.product_uom_qty}" if move.state == 'done' else f"0/{move.product_uom_qty}"
                    lines.append(f"    [{idx}] {move.product_id.name}")
                    lines.append(f"        Qty (Done/Expected) : {qty_done} {move.product_uom.name}")
                    if move.state == 'done':
                        lines.append(f"        Status              : RECEIVED ✓")
                    else:
                        lines.append(f"        Status              : PENDING")
                    if idx < min(10, len(picking.move_ids)):
                        lines.append("")
                
                if len(picking.move_ids) > 10:
                    lines.append(f"    ... and {len(picking.move_ids) - 10} more products")
            else:
                lines.append(f"    Status          : NO PRODUCTS")
            
            lines.append("")
            lines.append("=" * 70)
            lines.append("END OF DOCUMENT CHAIN")
            lines.append("=" * 70)
            
            picking.document_chain = '\n'.join(lines)
    
    # @api.model_create_multi
    # def create(self, vals_list):
    #     """Override create to log GRN creation"""
    #     records = super(StockPicking, self).create(vals_list)
        
    #     for record in records:
    #         if record.picking_type_code == 'incoming':
    #             _logger.info(f"GRN {record.name} created")
        
    #     return records
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to log GRN creation"""
        records = super(StockPicking, self).create(vals_list)
        
        for record in records:
            if record.picking_type_code == 'incoming':
                _logger.info(f"GRN {record.name} created")
        
        return records
