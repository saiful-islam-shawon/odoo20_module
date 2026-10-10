from unittest import SkipTest

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseOrderDelivery(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "picking_type_id" not in cls.env["purchase.order"]._fields:
            raise SkipTest("Requires the optional purchase_stock module")
        cls.other_company = cls.env["res.company"].create({"name": "Sourcing Delivery Company"})
        cls.receipt_type = cls.env["stock.picking.type"].search([
            ("company_id", "=", cls.other_company.id),
            ("code", "=", "incoming"),
        ], limit=1)
        cls.products = cls.env["product.product"].create([
            {"name": "Delivery Product A", "purchase_ok": True},
            {"name": "Delivery Product B", "purchase_ok": True},
        ])
        cls.vendors = cls.env["res.partner"].create([
            {"name": "Delivery Vendor A", "supplier_rank": 1},
            {"name": "Delivery Vendor B", "supplier_rank": 1},
        ])

    def setUp(self):
        super().setUp()
        self.requisition = self.env["zc.purchase.requisition"].with_company(
            self.other_company
        ).create({
            "line_ids": [Command.create({
                "product_id": product.id,
                "quantity": 3,
                "product_uom_id": product.uom_id.id,
            }) for product in self.products],
        })
        self.requisition.action_confirm()
        for vendor, req_line in zip(self.vendors, self.requisition.line_ids):
            rfq = self.env["zc.vendor.rfq"].create({
                "requisition_id": self.requisition.id,
                "partner_id": vendor.id,
                "line_ids": [Command.create({
                    "requisition_line_id": req_line.id,
                    "price_unit": 15,
                    "quality": "good",
                    "delivery_date": fields.Date.today(),
                })],
            })
            rfq.action_mark_received()
            rfq.line_ids.action_recommend()

    def test_receipts_follow_requisition_company_despite_ui_defaults(self):
        self.assertTrue(self.receipt_type)
        # A stale/empty UI default must not leave the required PO field empty.
        self.requisition.with_company(self.env.company).with_context(
            company_id=self.env.company.id, default_picking_type_id=False,
        ).action_create_purchase_orders()
        orders = self.requisition.purchase_order_ids
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders.company_id, self.other_company)
        self.assertEqual(orders.picking_type_id, self.receipt_type)
        self.assertEqual(len(orders.order_line), 2)
        self.assertEqual(self.requisition.state, "done")

    def test_wrong_company_default_is_not_used(self):
        foreign_type = self.env["stock.picking.type"].search([
            ("company_id", "=", self.env.company.id), ("code", "=", "incoming"),
        ], limit=1)
        self.assertTrue(foreign_type)
        self.requisition.with_context(
            default_picking_type_id=foreign_type.id,
        ).action_create_purchase_orders()
        self.assertEqual(self.requisition.purchase_order_ids.picking_type_id, self.receipt_type)

    def test_missing_receipts_gives_configuration_error_before_creating_orders(self):
        self.env["stock.picking.type"].search([
            ("company_id", "=", self.other_company.id), ("code", "=", "incoming"),
        ]).active = False
        # Even an active receipt without a warehouse in another company is invalid.
        foreign_type = self.env["stock.picking.type"].search([
            ("company_id", "=", self.env.company.id), ("code", "=", "incoming"),
        ], limit=1)
        self.env["stock.picking.type"].create({
            "name": "Other Company's Standalone Receipts",
            "code": "incoming",
            "sequence_code": "TESTIN",
            "company_id": self.env.company.id,
            "warehouse_id": False,
            "default_location_src_id": foreign_type.default_location_src_id.id,
            "default_location_dest_id": foreign_type.default_location_dest_id.id,
        })
        with self.assertRaisesRegex(UserError, "No active Receipts operation type"):
            self.requisition.with_context(active_test=False).action_create_purchase_orders()
        self.assertFalse(self.requisition.purchase_order_ids)
        self.assertFalse(self.requisition.rfq_ids.line_ids.purchase_order_line_id)
        self.assertEqual(self.requisition.state, "sourcing")
