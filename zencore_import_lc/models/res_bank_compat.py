# -*- coding: utf-8 -*-
"""Odoo 20 compatibility for the standalone bank master used by Import LC.

Odoo 20 removed the native ``res.bank`` model, merging native bank details
into bank *accounts* (``res.partner.bank``).  This LC module selects banks,
not a vendor's or company's individual account, so swapping the comodel to
``res.partner.bank`` would silently change the business meaning of all five
existing Many2one fields and their linked IDs.

Keep a small, self-contained bank master under its original technical name.
The field names below match the old Odoo 19 res.bank master.  This model is
used only by the Import LC workflow; Odoo 20 payment bank accounts remain
managed by Odoo's native ``res.partner.bank`` model.
"""
from odoo import api, fields, models


class ImportLCBankCompat(models.Model):
    _name = 'res.bank'
    _description = 'Bank (Import LC Compatibility)'
    _order = 'name'
    _rec_names_search = ('name', 'bic')

    name = fields.Char(required=True)
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char()
    city = fields.Char()
    state = fields.Many2one(
        'res.country.state', string='Fed. State',
        domain="[('country_id', '=?', country)]",
    )
    country = fields.Many2one('res.country')
    country_code = fields.Char(related='country.code', string='Country Code')
    email = fields.Char()
    phone = fields.Char()
    active = fields.Boolean(default=True)
    bic = fields.Char(
        'Bank Identifier Code', index=True,
        help='Sometimes called BIC or SWIFT.',
    )

    @api.depends('name', 'bic')
    def _compute_display_name(self):
        for bank in self:
            bank.display_name = (bank.name or '') + ((' - ' + bank.bic) if bank.bic else '')

    @api.onchange('country')
    def _onchange_country(self):
        if self.country and self.state and self.state.country_id != self.country:
            self.state = False
