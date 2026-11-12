# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('-at_install', 'post_install')
class TestLCModuleContracts(TransactionCase):
    """Low-cost regression checks for Odoo 19 integration contracts."""

    def test_import_lc_contracts(self):
        lc_model = self.env['import.lc']
        self.assertEqual(lc_model._fields['pi_number'].type, 'char')
        self.assertFalse(lc_model._fields['lc_order_id'].required)  # migration-safe; create/view enforce one PI
        self.assertEqual(lc_model._fields['lc_order_ids'].type, 'many2many')  # hidden upgrade compatibility only
        self.assertTrue(lc_model._fields['lc_order_ids'].readonly)
        self.assertTrue(lc_model._fields['lc_number'].required)
        self.assertIn('lc_order_id', self.env['import.lc.product.line']._fields)
        self.assertIn('port_of_shipment_id', lc_model._fields)
        self.assertIn('destination_port_id', lc_model._fields)
        self.assertNotIn('port_of_shipment_ids', lc_model._fields)
        self.assertIn('po_line_id', self.env['import.lc.product.line']._fields)

    def test_logistics_configuration_contracts(self):
        self.assertIn('import.lc.port', self.env.registry.models)
        self.assertIn('import.lc.container.type', self.env.registry.models)
        self.assertIn('import.lc.container', self.env.registry.models)
        po_fields = self.env['purchase.order']._fields
        self.assertIn('lc_port_of_shipment_id', po_fields)
        self.assertIn('lc_destination_port_id', po_fields)
        self.assertIn('lc_container_type_id', po_fields)
        self.assertIn('lc_container_id', po_fields)
        self.assertIn('lc_transshipment', po_fields)
        self.assertNotIn('lc_pi_number', po_fields)
        self.assertNotIn('lc_pi_date', po_fields)
        self.assertNotIn('lc_conversion_rate', po_fields)
        self.assertIn('lc_expected_shipment_date', po_fields)

    def test_import_requires_lc_before_confirmation(self):
        supplier = self.env['res.partner'].create({'name': 'Import workflow test supplier'})
        order = self.env['purchase.order'].create({
            'partner_id': supplier.id, 'purchase_type': 'import',
        })
        self.assertTrue(order.lc_required)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.button_confirm()
        self.assertEqual(order.state, 'draft')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.button_approve()
        order.purchase_type = 'local'
        self.assertFalse(order.lc_required)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.action_create_proforma_invoice()

    def test_rfq_defaults_preserve_manual_pi_metadata(self):
        supplier = self.env['res.partner'].create({'name': 'PI defaults test supplier'})
        order = self.env['purchase.order'].create({
            'partner_id': supplier.id, 'purchase_type': 'import',
            'lc_expected_shipment_date': '2026-10-15',
            'lc_partial_shipment': 'not_allowed',
        })
        defaults = self.env['lc.order']._po_header_defaults(order)
        self.assertNotIn('pi_number', defaults)
        self.assertNotIn('pi_date', defaults)
        self.assertNotIn('conversion_rate', defaults)
        self.assertEqual(defaults['expected_shipment_date'], order.lc_expected_shipment_date)
        self.assertEqual(defaults['partial_shipment'], 'not_allowed')
        context = order.action_create_proforma_invoice()['context']
        self.assertNotIn('default_pi_number', context)
        self.assertNotIn('default_pi_date', context)
        self.assertEqual(context['default_currency_id'], order.currency_id.id)

    def test_ci_is_pi_scoped(self):
        ci_fields = self.env['import.ci']._fields
        self.assertFalse(ci_fields['lc_order_id'].required)  # migration-safe; LC auto-populates it
        self.assertNotIn('allowed_pi_ids', ci_fields)
        self.assertIn('receipt_ids', ci_fields)
        self.assertIn('po_line_id', self.env['import.ci.product.line']._fields)
        self.assertIn('import_ci_id', self.env['stock.picking']._fields)

    def test_amendment_contracts(self):
        field = self.env['import.lc.amendment']._fields['amendment_type']
        selection = field.selection(self.env['import.lc.amendment']) if callable(field.selection) else field.selection
        keys = {key for key, _label in selection}
        self.assertIn('shipment_date', keys)
        self.assertTrue(self.env['import.lc.amendment']._fields['import_lc_id'].required)
        self.assertIn('lc_order_id', self.env['import.lc.amendment.line']._fields)
        self.assertIn('po_line_id', self.env['import.lc.amendment.line']._fields)

    def test_standard_account_move_fields_are_preserved(self):
        move_fields = self.env['account.move']._fields
        self.assertEqual(move_fields['narration'].type, 'html')
        self.assertEqual(move_fields['purchase_id'].comodel_name, 'purchase.order')

    def test_lc_other_charge_landed_cost_contracts(self):
        landed_cost_fields = self.env['stock.landed.cost']._fields
        cost_line_fields = self.env['stock.landed.cost.lines']._fields

        self.assertIn('import_lc_id', landed_cost_fields)
        self.assertIn('lc_journal_entry_id', landed_cost_fields)
        self.assertEqual(landed_cost_fields['lc_journal_entry_id'].comodel_name, 'account.move')
        self.assertIn('journal_item_id', cost_line_fields)
        self.assertEqual(cost_line_fields['journal_item_id'].comodel_name, 'account.move.line')
        self.assertIn('journal_item_debit', cost_line_fields)
        self.assertIn('journal_item_credit', cost_line_fields)

    def test_approver_group_exists(self):
        group = self.env.ref('zencore_import_lc.group_lc_approver')
        self.assertTrue(group)
        self.assertTrue(group.privilege_id)

    def test_mrp_dependency_contract(self):
        self.assertIn('mrp.production', self.env.registry.models)

    def test_purchase_stock_contract(self):
        self.assertIn('purchase_id', self.env['stock.picking']._fields)
        self.assertIn('purchase_line_id', self.env['stock.move']._fields)
