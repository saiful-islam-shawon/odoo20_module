# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('-at_install', 'post_install')
class TestZencoreImportLCOdoo20Conversion(TransactionCase):
    """Verify Odoo 20 API compatibility for converted code paths in zencore_import_lc."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.uom_unit = cls.env.ref('uom.product_uom_unit')
        cls.supplier = cls.env['res.partner'].create({'name': 'Odoo20 LC Test Supplier'})
        cls.bank = cls.env['import.lc.bank'].create({'name': 'Odoo20 Test Bank', 'bic': 'TESTBDDH'})
        cls.product = cls.env['product.product'].create({
            'name': 'Odoo20 Test Raw Material',
            'type': 'consu',
            'uom_id': cls.uom_unit.id,
        })
        cls.approver_group = cls.env.ref('zencore_import_lc.group_lc_approver')
        cls.env.user.write({'group_ids': [(4, cls.approver_group.id)]})

    def test_01_po_to_pi_uses_uom_id(self):
        """Ensure action_create_proforma_invoice and _po_line_commands read po_line.uom_id."""
        order = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'purchase_type': 'import',
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 10.0,
                'uom_id': self.uom_unit.id,
                'price_unit': 50.0,
            })],
        })
        action = order.action_create_proforma_invoice()
        line_commands = action['context']['default_lc_line_ids']
        self.assertEqual(len(line_commands), 1)
        self.assertEqual(line_commands[0][2]['product_uom_id'], self.uom_unit.id)

        po_commands = self.env['lc.order']._po_line_commands(order)
        self.assertEqual(len(po_commands), 2)  # (5, 0, 0) + line command
        self.assertEqual(po_commands[1][2]['product_uom_id'], self.uom_unit.id)

    def test_02_ci_line_display_name_compute(self):
        """Ensure ImportCIProductLine computes display_name via _compute_display_name."""
        po = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'purchase_type': 'import',
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 5.0,
                'uom_id': self.uom_unit.id,
                'price_unit': 20.0,
            })],
        })
        pi = self.env['lc.order'].create({
            'pi_number': 'PI-O20-001',
            'po_number': po.id,
            'conversion_rate': 120.0,
        })
        pi.action_confirm()
        lc = self.env['import.lc'].create({
            'lc_number': 'LC-O20-001',
            'lc_type': 'foreign',
            'lc_order_id': pi.id,
            'supplier_id': self.supplier.id,
            'applicant_bank_id': self.bank.id,
            'lc_conversion_rate': 120.0,
        })
        lc.action_confirm()
        ci = self.env['import.ci'].create({
            'ci_number': 'CI-O20-001',
            'import_lc_id': lc.id,
            'lc_order_id': pi.id,
        })
        ci_line = ci.product_line_ids[:1]
        self.assertTrue(ci_line)
        ci_line.ci_quantity = 3.0
        self.assertEqual(
            ci_line.display_name,
            f"{ci_line.product_name or 'Product'} - CI Qty: {ci_line.ci_quantity}",
        )

    def test_03_document_chain_and_closed_lc_unlink_guard(self):
        """Verify picking/LC document chains use move_ids/uom_id and unlink guards closed LCs."""
        po = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'purchase_type': 'import',
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 4.0,
                'uom_id': self.uom_unit.id,
                'price_unit': 25.0,
            })],
        })
        pi = self.env['lc.order'].create({
            'pi_number': 'PI-O20-002',
            'po_number': po.id,
            'conversion_rate': 120.0,
        })
        pi.action_confirm()
        lc = self.env['import.lc'].create({
            'lc_number': 'LC-O20-002',
            'lc_type': 'foreign',
            'lc_order_id': pi.id,
            'supplier_id': self.supplier.id,
            'applicant_bank_id': self.bank.id,
            'lc_conversion_rate': 120.0,
        })
        lc.action_confirm()
        po.button_confirm()
        picking = po.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming')[:1]
        self.assertTrue(picking)
        self.assertIn(self.product.name, picking.document_chain)
        self.assertIn(self.uom_unit.name, picking.document_chain)
        self.assertIn(self.uom_unit.name, lc.document_chain_summary)

        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id),
            ('type', '=', 'general'),
        ], limit=1)
        account = self.env['account.account'].search([], limit=1)
        if journal and account:
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'import_lc_id': lc.id,
            })
            lc.write({'state': 'done'})
            with self.assertRaises(ValidationError), self.cr.savepoint():
                move.unlink()

