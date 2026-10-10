from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestRFQProductRemoval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.buyer = new_test_user(
            cls.env, login="rfq_product_buyer", groups="purchase.group_purchase_user"
        )
        cls.products = cls.env["product.product"].create([
            {"name": name, "purchase_ok": True}
            for name in ("Sourcing A", "Sourcing B", "Sourcing C")
        ])
        cls.vendors = cls.env["res.partner"].create([
            {"name": name, "supplier_rank": 1}
            for name in ("Sourcing Vendor A", "Sourcing Vendor B")
        ])

    def setUp(self):
        super().setUp()
        self.requisition = self.env["zc.purchase.requisition"].create({
            "line_ids": [
                Command.create({
                    "product_id": product.id,
                    "quantity": 10,
                    "product_uom_id": product.uom_id.id,
                })
                for product in self.products
            ],
        })
        self.requisition.action_confirm()
        self.rfqs = self.env["zc.vendor.rfq"]
        for vendor in self.vendors:
            wizard = self.env["zc.rfq.create.wizard"].create({
                "requisition_id": self.requisition.id,
                "partner_id": vendor.id,
            })
            self.rfqs |= self.env["zc.vendor.rfq"].browse(
                wizard.action_create_rfq()["res_id"]
            )

    def _receive(self, rfqs):
        rfqs.line_ids.write({
            "price_unit": 12,
            "quality": "good",
            "delivery_date": fields.Date.today(),
        })
        rfqs.action_mark_received()

    def _compare(self):
        self.requisition.action_compare_rfqs()
        return self.requisition.comparison_ids

    def test_remove_products_in_form_and_compare_partial_quotes(self):
        first, second = self.rfqs
        first_removed = first.line_ids[1]
        second_removed = second.line_ids[0]
        # Exercise the actual RFQ form and Purchase User access rights.
        with Form(first.with_user(self.buyer)) as form:
            form.line_ids.remove(index=1)
        with Form(second.with_user(self.buyer)) as form:
            form.line_ids.remove(index=0)
        self.assertFalse((first_removed | second_removed).exists())
        self.assertEqual(len(self.requisition.line_ids), 3)

        self._receive(self.rfqs)
        comparison = self._compare()
        self.assertEqual(len(comparison.line_ids), 4)
        self.assertEqual(set(comparison.line_ids.rfq_line_id.ids), set(self.rfqs.line_ids.ids))

        for line in first.line_ids:
            line.action_recommend()
        second.line_ids.filtered(
            lambda line: line.product_id == self.products[1]
        ).action_recommend()
        self.assertEqual(comparison.state, "completed")
        self.assertTrue(self.requisition.comparison_sheet_ready)

        self.requisition.action_create_purchase_orders()
        orders = self.requisition.purchase_order_ids
        self.assertEqual(len(orders), 2)
        self.assertEqual(len(orders.order_line), 3)
        for rfq in self.rfqs:
            order = orders.filtered(lambda order: order.partner_id == rfq.partner_id)
            selected = rfq.line_ids.filtered(lambda line: line.decision == "recommended")
            self.assertEqual(set(order.order_line.product_id.ids), set(selected.product_id.ids))
            self.assertTrue(all(line.product_qty == 10 for line in order.order_line))

    def test_reset_and_delete_removes_existing_comparison_row(self):
        self._receive(self.rfqs)
        comparison = self._compare()
        removed = self.rfqs[0].line_ids[0]
        removed.action_recommend()
        old_comparison_line = comparison.line_ids.filtered(
            lambda line: line.rfq_line_id == removed
        )
        old_comparison_line.remarks = "This offer will be withdrawn."
        self.rfqs[0].action_set_draft()
        removed.with_user(self.buyer).unlink()
        self.assertFalse(old_comparison_line.exists())
        self._receive(self.rfqs[0])
        comparison._sync_received_lines()
        self.assertEqual(len(comparison.line_ids), 5)
        self.assertEqual(set(comparison.line_ids.rfq_line_id.ids), set(self.rfqs.line_ids.ids))
        self.assertEqual(comparison.state, "open")
        self.assertFalse(self.requisition.comparison_sheet_ready)

    def test_unquoted_product_keeps_comparison_open(self):
        for rfq in self.rfqs:
            rfq.line_ids[-1].with_user(self.buyer).unlink()
        self._receive(self.rfqs)
        comparison = self._compare()
        for line in self.rfqs[0].line_ids:
            line.action_recommend()
        self.assertEqual(len(comparison.line_ids), 4)
        self.assertEqual(comparison.state, "open")
        self.assertFalse(self.requisition.comparison_sheet_ready)
        with self.assertRaises(UserError):
            self.requisition.action_print_comparison_sheet()

    def test_empty_rfq_cannot_be_received(self):
        rfq = self.rfqs[0]
        rfq.line_ids.with_user(self.buyer).unlink()
        with self.assertRaises(UserError):
            rfq.action_mark_received()
        self.assertEqual(rfq.state, "draft")

    def test_received_and_cancelled_lines_cannot_be_deleted(self):
        rfq = self.rfqs[0]
        self._receive(rfq)
        with self.assertRaises(UserError):
            rfq.line_ids.with_user(self.buyer).unlink()
        rfq.action_cancel()
        with self.assertRaises(UserError):
            rfq.line_ids.with_user(self.buyer).unlink()
        self.assertEqual(len(rfq.line_ids), 3)

    def test_purchase_order_locks_remaining_draft_rfq_lines(self):
        self._receive(self.rfqs[0])
        self.rfqs[0].line_ids[0].action_recommend()
        self.requisition.action_create_purchase_orders()
        draft_rfq = self.rfqs[1]
        self.assertEqual(draft_rfq.state, "draft")
        with self.assertRaises(UserError):
            draft_rfq.line_ids.with_user(self.buyer).unlink()
        self.assertEqual(len(draft_rfq.line_ids), 3)
