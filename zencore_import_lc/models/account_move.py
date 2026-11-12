from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    # The LC link is computed after creation. Match the ORM's deferred rate
    # computation explicitly so its non-precomputed dependency is supported.
    invoice_currency_rate = fields.Float(precompute=False)
    
    import_lc_id = fields.Many2one(
        'import.lc',
        string='Import LC',
        compute='_compute_import_lc_id',
        store=True,
        readonly=False,
        tracking=True,
        copy=False,
        ondelete='restrict',
        help='Link to Import Letter of Credit'
    )
    import_lc_ids = fields.Many2many(
        'import.lc',
        'import_lc_journal_entry_rel',
        'move_id',
        'import_lc_id',
        string='Related Import LCs',
        help='Import LCs this journal entry is related to'
    )
    
    lc_number = fields.Char(
        related='import_lc_id.lc_number',
        string='LC Number',
        store=True,
        readonly=True
    )
    
    lc_type = fields.Selection(
        related='import_lc_id.lc_type',
        string='LC Type',
        store=True,
        readonly=True
    )
    
    # Journal type to show Miscellaneous, Bank, Cash, etc.
    journal_type_display = fields.Char(
        string='Journal Type',
        compute='_compute_journal_type_display',
        store=True
    )
    
    # Add a field to check if journal is miscellaneous
    is_miscellaneous_journal = fields.Boolean(
        string='Is Miscellaneous Journal',
        compute='_compute_is_miscellaneous_journal',
        store=True
    )

    import_lc_charge_total = fields.Monetary(
        string='Total (Company Currency)',
        currency_field='company_currency_id',
        compute='_compute_import_lc_charge_total',
        help='Total debit amount for this Import LC journal entry in company currency.',
    )

    @api.depends('move_type', 'line_ids.debit')
    def _compute_import_lc_charge_total(self):
        for move in self:
            move.import_lc_charge_total = (
                sum(move.line_ids.mapped('debit')) if move.move_type == 'entry' else 0.0
            )
    
    @api.depends('journal_id', 'journal_id.type')
    def _compute_journal_type_display(self):
        """Display friendly journal type names"""
        type_mapping = {
            'general': 'Miscellaneous Operations',
            'sale': 'Sales',
            'purchase': 'Purchase',
            'cash': 'Cash',
            'bank': 'Bank'
        }
        for record in self:
            if record.journal_id and record.journal_id.type:
                record.journal_type_display = type_mapping.get(
                    record.journal_id.type, 
                    record.journal_id.type.title()
                )
            else:
                record.journal_type_display = 'N/A'
    
    @api.depends('journal_id', 'journal_id.type')
    def _compute_is_miscellaneous_journal(self):
        """Check if the journal is of type 'general' (Miscellaneous)"""
        for record in self:
            record.is_miscellaneous_journal = (
                record.journal_id and record.journal_id.type == 'general'
            )
    @api.depends('ref', 'narration', 'move_type', 'company_id', 'import_ci_id')
    def _compute_import_lc_id(self):
        """Link bills/journal entries to an LC without ambiguous cross-company matches."""
        for record in self:
            # CI linkage has highest priority. Otherwise preserve a manually selected LC
            # (e.g. an Other Charge created directly from the LC) before falling back
            # to deterministic reference-based auto-linking.
            manual_lc = record.import_lc_id if record.import_lc_id and record.import_lc_id.company_id == record.company_id else False
            lc = record.import_ci_id.import_lc_id if record.import_ci_id else manual_lc
            if not lc and record.move_type == 'entry' and record.ref:
                domain = [
                    ('company_id', '=', record.company_id.id),
                    '|',
                    ('lc_number', '=', record.ref),
                    ('pi_number', '=', record.ref),
                ]
                lc = self.env['import.lc'].search(domain, order='id desc', limit=1)
            record.import_lc_id = lc
