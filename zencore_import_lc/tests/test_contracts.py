# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('-at_install', 'post_install')
class TestLCModuleContracts(TransactionCase):
    """Low-cost regression checks for Odoo 20 integration contracts."""

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

    def test_odoo20_unified_access_rights(self):
        """Odoo 20 company isolation must remain a global restriction."""
        restriction_ids = (
            'lc_order_company_rule',
            'lc_order_line_company_rule',
            'import_lc_company_rule',
            'import_lc_product_line_company_rule',
            'import_lc_document_company_rule',
            'lc_order_document_company_rule',
            'import_ci_company_rule',
            'import_ci_product_line_company_rule',
            'import_lc_amendment_company_rule',
            'import_lc_amendment_line_company_rule',
            'company_branch_company_rule',
        )
        for xml_id in restriction_ids:
            access = self.env.ref('zencore_import_lc.' + xml_id)
            self.assertEqual(access._name, 'ir.access')
            self.assertFalse(access.group_id)
            self.assertEqual(access.operation, 'crud')
            self.assertEqual(access.domain, "[('company_id', 'in', company_ids)]")

        user_access = self.env.ref('zencore_import_lc.access_import_lc_user')
        self.assertEqual(user_access._name, 'ir.access')
        self.assertEqual(user_access.operation, 'cru')
        self.assertEqual(user_access.group_id, self.env.ref('base.group_user'))
        approver_access = self.env.ref('zencore_import_lc.access_import_lc_approver')
        self.assertEqual(approver_access.operation, 'crud')

    def test_odoo20_standalone_bank_compatibility(self):
        """LC bank fields must still select institutions, not bank accounts."""
        bank_model = self.env['res.bank']
        self.assertIn('bic', bank_model._fields)
        self.assertIn('country', bank_model._fields)
        refs = (
            ('purchase.order', 'lc_advising_bank_id'),
            ('lc.order', 'bank_id'),
            ('import.lc', 'applicant_bank_id'),
            ('import.lc', 'advising_bank_id'),
        )
        for model, field in refs:
            self.assertEqual(self.env[model]._fields[field].comodel_name, 'res.bank')
        # The separate Import LC bank register must remain usable without
        # creating a partner's bank account or an account number.
        bank = bank_model.sudo().create({'name': 'LC Test Bank', 'bic': 'LCTBBDDH'})
        self.assertEqual(bank.display_name, 'LC Test Bank - LCTBBDDH')

    def test_odoo20_purchase_line_uom_to_pi_mapping(self):
        """RFQ selection and the Create PI action share Odoo 20's UoM field."""
        po_line_model = self.env['purchase.order.line']
        self.assertIn('uom_id', po_line_model._fields)
        self.assertNotIn('product_uom_id', po_line_model._fields)
        self.assertIn('product_uom_id', self.env['lc.order.line']._fields)

        supplier = self.env['res.partner'].create({'name': 'Odoo 20 PI UoM regression supplier'})
        product = self.env['product.product'].create({'name': 'Odoo 20 PI UoM regression product', 'purchase_ok': True})
        order = self.env['purchase.order'].create({
            'partner_id': supplier.id,
            'purchase_type': 'import',
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': 'Regression product',
                'product_qty': 4.0,
                'price_unit': 12.50,
                'uom_id': product.uom_id.id,
            })],
        })
        po_line = order.order_line.filtered('product_id')
        self.assertEqual(len(po_line), 1)

        pi_model = self.env['lc.order']
        po_commands = pi_model._po_line_commands(order)
        self.assertEqual(po_commands[0], (5, 0, 0))
        self.assertEqual(po_commands[1][2]['product_uom_id'], po_line.uom_id.id)
        self.assertEqual(po_commands[1][2]['po_line_id'], po_line.id)

        action = order.action_create_proforma_invoice()
        action_lines = action['context']['default_lc_line_ids']
        self.assertEqual(action_lines[0][2]['product_uom_id'], po_line.uom_id.id)
        self.assertEqual(action_lines[0][2]['quantity'], po_line.product_qty)
        self.assertEqual(action_lines[0][2]['unit_price'], po_line.price_unit)

        pi = pi_model.new({'po_number': order.id})
        pi._onchange_po_number()
        self.assertEqual(len(pi.lc_line_ids), 1)
        self.assertEqual(pi.lc_line_ids.product_uom_id.id, po_line.uom_id.id)

    def test_odoo20_related_stock_and_mrp_uom_fields(self):
        """Traceability uses current UoM fields, not renamed Odoo 19 ones."""
        self.assertIn('uom_id', self.env['stock.move']._fields)
        self.assertNotIn('product_uom', self.env['stock.move']._fields)
        self.assertIn('product_uom_qty', self.env['stock.move']._fields)
        self.assertIn('uom_id', self.env['mrp.production']._fields)
        self.assertNotIn('product_uom_id', self.env['mrp.production']._fields)
        self.assertIn('move_ids', self.env['stock.picking']._fields)
        self.assertNotIn('move_ids_without_package', self.env['stock.picking']._fields)
        self.assertIn('product_uom_id', self.env['account.move.line']._fields)

    def test_import_lc_confirm_and_ci_quantity_availability_odoo20_uom(self):
        """Confirming an Import LC and computing CI availability must work with Odoo 20 UoMs."""
        supplier = self.env['res.partner'].create({'name': 'LC Confirm UoM Supplier', 'supplier_rank': 1})
        product = self.env['product.product'].create({'name': 'LC Confirm UoM Product', 'purchase_ok': True})
        bank = self.env['res.bank'].sudo().create({'name': 'LC Confirm Test Bank', 'bic': 'LCCNBBDD'})
        order = self.env['purchase.order'].create({
            'partner_id': supplier.id,
            'purchase_type': 'import',
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': 'LC Confirm UoM Line',
                'product_qty': 10.0,
                'price_unit': 25.0,
                'uom_id': product.uom_id.id,
            })],
        })
        po_line = order.order_line.filtered('product_id')
        pi = self.env['lc.order'].create({
            'po_number': order.id,
            'pi_number': 'PI-UOM-20-001',
            'port_of_shipment': 'Shanghai',
            'destination_port': 'Chittagong',
            'lc_line_ids': [(0, 0, {
                'po_line_id': po_line.id,
                'product_id': product.id,
                'quantity': 10.0,
                'unit_price': 25.0,
                'product_uom_id': po_line.uom_id.id,
            })],
        })
        pi.action_confirm()
        self.assertEqual(pi.state, 'done')

        lc = self.env['import.lc'].create({
            'lc_order_id': pi.id,
            'lc_number': 'LC-UOM-20-001',
            'lc_type': 'foreign',
            'applicant_bank_id': bank.id,
            'lc_amount': 250.0,
        })
        self.assertEqual(lc.state, 'draft')
        self.assertFalse(lc.can_create_commercial_invoice)

        # AC-1: Confirm and read computed workflow actions (simulates web_read after Confirm)
        lc.action_confirm()
        self.assertEqual(lc.state, 'confirmed')
        read_data = lc.read(['state', 'can_create_commercial_invoice', 'can_close_lc'])
        self.assertTrue(read_data[0]['can_create_commercial_invoice'])
        self.assertTrue(lc._has_available_ci_quantity())

        # AC-2: Partial CI still leaves available quantity
        ci = self.env['import.ci'].create({
            'import_lc_id': lc.id,
            'ci_number': 'CI-UOM-20-001',
        })
        ci.product_line_ids.write({'ci_quantity': 4.0})
        lc.invalidate_recordset(['can_create_commercial_invoice'])
        self.assertTrue(lc._has_available_ci_quantity())
        self.assertTrue(lc.can_create_commercial_invoice)

        # AC-3: Full CI coverage leaves no available quantity
        ci.product_line_ids.write({'ci_quantity': 10.0})
        lc.invalidate_recordset(['can_create_commercial_invoice'])
        self.assertFalse(lc._has_available_ci_quantity())
        self.assertFalse(lc.can_create_commercial_invoice)

        # AC-4: Empty uom_id fallback uses 0.01 precision cleanly
        lc.product_line_ids.write({'uom_id': False})
        self.assertFalse(lc._has_available_ci_quantity())
        ci.product_line_ids.write({'ci_quantity': 9.0})
        self.assertTrue(lc._has_available_ci_quantity())

    def test_import_lc_amount_auto_calculation_and_option_a(self):
        """LC Amount auto-populates from product lines while keeping draft override and connected formulas."""
        supplier = self.env['res.partner'].create({'name': 'LC Amount Auto Supplier', 'supplier_rank': 1})
        product = self.env['product.product'].create({'name': 'LC Amount Auto Product', 'purchase_ok': True})
        bank = self.env['res.bank'].sudo().create({'name': 'LC Amount Test Bank', 'bic': 'LCAMBDDH'})

        def _make_approved_pi(pi_num, qty, price, conv_rate=120.0):
            po = self.env['purchase.order'].create({
                'partner_id': supplier.id,
                'purchase_type': 'import',
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'name': f'Line {pi_num}',
                    'product_qty': qty,
                    'price_unit': price,
                    'uom_id': product.uom_id.id,
                })],
            })
            po_line = po.order_line.filtered('product_id')
            pi = self.env['lc.order'].create({
                'po_number': po.id,
                'pi_number': pi_num,
                'port_of_shipment': 'Chattogram',
                'destination_port': 'CGP',
                'conversion_rate': conv_rate,
                'lc_line_ids': [(0, 0, {
                    'po_line_id': po_line.id,
                    'product_id': product.id,
                    'quantity': qty,
                    'unit_price': price,
                    'product_uom_id': po_line.uom_id.id,
                })],
            })
            pi.action_confirm()
            return pi

        pi_main = _make_approved_pi('PI-AMT-001', 20.0, 3.0)
        pi_alt = _make_approved_pi('PI-AMT-002', 10.0, 5.0)

        # AC-1a: Onchange on PI selection auto-populates lc_amount and clearing resets it
        lc_form = self.env['import.lc'].new({'lc_order_id': pi_main.id})
        lc_form._onchange_lc_order_id_enterprise()
        self.assertEqual(lc_form.lc_amount, 60.0)
        lc_form.lc_order_id = False
        lc_form._onchange_lc_order_id_enterprise()
        self.assertEqual(lc_form.lc_amount, 0.0)

        # AC-1b & AC-3: Creating with UI default 0.0 auto-populates lc_amount & preserves connected formulas
        lc = self.env['import.lc'].create({
            'lc_order_id': pi_main.id,
            'lc_number': 'LC-AMT-001',
            'lc_type': 'foreign',
            'applicant_bank_id': bank.id,
            'lc_amount': 0.0,
            'lc_tolerance_percent': 10.0,
            'margin_rate': 1.0,
        })
        self.assertEqual(lc.lc_amount, 60.0)
        self.assertEqual(sum(lc.product_line_ids.mapped('total_cost')), 60.0)
        self.assertEqual(lc.lc_tolerance_amount, 6.0)
        self.assertEqual(lc.lc_utilized_amount, 0.0)
        self.assertEqual(lc.lc_available_amount, 66.0)
        self.assertEqual(lc.lc_amount_bdt, 7200.0)
        self.assertEqual(lc.total_lc_cost, 7200.0)
        self.assertEqual(lc.margin_value, 72.0)

        # AC-2: Draft manual override preserved even after editing HS code on product lines
        lc.write({'lc_amount': 65.0})
        lc.product_line_ids.write({'hs_code': '080450'})
        self.assertEqual(lc.lc_amount, 65.0)

        # AC-1c: Changing PI on draft LC without specifying lc_amount updates lc_amount
        lc.write({'lc_order_id': pi_alt.id})
        self.assertEqual(lc.lc_amount, 50.0)

        # AC-4: Confirm LC and verify Value Amendment updates lc_amount without being overwritten
        lc.action_confirm()
        self.assertEqual(lc.lc_amount, 50.0)
        amendment = self.env['import.lc.amendment'].create({
            'import_lc_id': lc.id,
            'amendment_type': 'value',
            'reason': 'Bank value increase',
            'new_lc_value': 80.0,
        })
        amendment.action_submit()
        amendment.action_approve()
        self.assertEqual(lc.lc_amount, 80.0)

    def test_import_lc_amendment_quantity_increase_decrease_and_reflection(self):
        """Quantity Increase/Decrease amendments update LC product lines and LC Amount."""
        supplier = self.env['res.partner'].create({'name': 'AMD Qty Test Supplier', 'supplier_rank': 1})
        product = self.env['product.product'].create({'name': 'AMD Qty Test Product', 'purchase_ok': True})
        bank = self.env['res.bank'].sudo().create({'name': 'AMD Qty Test Bank', 'bic': 'AMDQBDDH'})

        order = self.env['purchase.order'].create({
            'partner_id': supplier.id,
            'purchase_type': 'import',
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': 'AMD Qty Line',
                'product_qty': 20.0,
                'price_unit': 3.0,
                'uom_id': product.uom_id.id,
            })],
        })
        po_line = order.order_line.filtered('product_id')
        pi = self.env['lc.order'].create({
            'po_number': order.id,
            'pi_number': 'PI-AMD-001',
            'port_of_shipment': 'Shanghai',
            'destination_port': 'Chittagong',
            'conversion_rate': 120.0,
            'lc_line_ids': [(0, 0, {
                'po_line_id': po_line.id,
                'product_id': product.id,
                'quantity': 20.0,
                'unit_price': 3.0,
                'product_uom_id': po_line.uom_id.id,
            })],
        })
        pi.action_confirm()

        lc = self.env['import.lc'].create({
            'lc_order_id': pi.id,
            'lc_number': 'LC-AMD-001',
            'lc_type': 'foreign',
            'applicant_bank_id': bank.id,
            'lc_amount': 0.0,
            'lc_tolerance_percent': 10.0,
            'margin_rate': 1.0,
        })
        lc.action_confirm()
        self.assertEqual(lc.state, 'confirmed')
        self.assertEqual(lc.lc_amount, 60.0)
        self.assertFalse(lc.has_quantity_amendment)
        self.assertEqual(lc.product_line_ids[0].amended_quantity, 0.0)
        self.assertEqual(lc.product_line_ids[0].total_cost, 60.0)

        # AC-1: Test Quantity Increase (20 -> 25)
        amd_inc = self.env['import.lc.amendment'].create({
            'import_lc_id': lc.id,
            'amendment_type': 'quantity',
            'reason': 'Increase order volume',
        })
        amd_inc._onchange_import_lc_id()
        self.assertEqual(len(amd_inc.product_line_ids), 1)
        self.assertEqual(amd_inc.product_line_ids[0].original_quantity, 20.0)

        # Set new quantity to 25.0 (increase of +5.0)
        amd_inc.product_line_ids[0].write({'new_quantity': 25.0})
        self.assertEqual(amd_inc.product_line_ids[0].quantity_change, 5.0)

        # Submit and approve amendment
        amd_inc.action_submit()
        self.assertEqual(amd_inc.state, 'submitted')
        amd_inc.action_approve()
        self.assertEqual(amd_inc.state, 'approved')

        # AC-4 & AC-5: Check Import LC reflection after approval
        lc.invalidate_recordset()
        self.assertTrue(lc.has_quantity_amendment)
        line = lc.product_line_ids[0]
        self.assertEqual(line.amended_quantity, 25.0)
        self.assertEqual(line.total_cost, 75.0)  # 25 * 3.0
        self.assertEqual(lc.lc_amount, 75.0)
        self.assertEqual(lc.lc_amount_bdt, 9000.0)  # 75 * 120.0
        self.assertEqual(lc.total_lc_cost, 9000.0)
        self.assertEqual(lc.margin_value, 90.0)  # 1% of 9000.0
        self.assertEqual(lc.lc_available_amount, 82.5)  # 75 + 7.5 - 0

        # Downstream CI uses the amended quantity (25.0)
        ci_action = lc.action_create_commercial_invoice()
        ci_vals = ci_action['context']
        ci = self.env['import.ci'].create({
            'import_lc_id': ci_vals['default_import_lc_id'],
            'ci_number': 'CI-AMD-001',
        })
        self.assertEqual(ci.product_line_ids[0].lc_quantity, 25.0)

        # AC-2: Test subsequent Quantity Decrease (25 -> 22)
        amd_dec = self.env['import.lc.amendment'].create({
            'import_lc_id': lc.id,
            'amendment_type': 'quantity',
            'reason': 'Slight volume adjustment down',
        })
        amd_dec._onchange_import_lc_id()
        self.assertEqual(amd_dec.product_line_ids[0].original_quantity, 25.0)
        amd_dec.product_line_ids[0].write({'new_quantity': 22.0})
        amd_dec.action_submit()
        amd_dec.action_approve()

        lc.invalidate_recordset()
        line.invalidate_recordset()
        self.assertEqual(line.amended_quantity, 22.0)
        self.assertEqual(line.total_cost, 66.0)  # 22 * 3.0
        self.assertEqual(lc.lc_amount, 66.0)
