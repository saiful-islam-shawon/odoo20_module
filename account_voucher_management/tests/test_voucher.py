from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestVoucher(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.bank = cls.env["account.account"].create({"name": "Voucher Bank", "code": "V1000", "account_type": "asset_cash", "company_ids": [Command.set(cls.company.ids)]})
        cls.receivable = cls.env["account.account"].create({"name": "Voucher Receivable", "code": "V1100", "account_type": "asset_receivable", "reconcile": True, "company_ids": [Command.set(cls.company.ids)]})
        cls.payable = cls.env["account.account"].create({"name": "Voucher Payable", "code": "V2000", "account_type": "liability_payable", "reconcile": True, "company_ids": [Command.set(cls.company.ids)]})
        cls.expense = cls.env["account.account"].create({"name": "Voucher Expense", "code": "V5000", "account_type": "expense", "company_ids": [Command.set(cls.company.ids)]})
        cls.income = cls.env["account.account"].create({"name": "Voucher Income", "code": "V4000", "account_type": "income", "company_ids": [Command.set(cls.company.ids)]})
        cls.journal = cls.env["account.journal"].create({"name": "Voucher Bank", "code": "VBK", "type": "bank", "company_id": cls.company.id, "default_account_id": cls.bank.id})
        cls.general = cls.env["account.journal"].create({"name": "Voucher General", "code": "VGJ", "type": "general", "company_id": cls.company.id})
        cls.sales = cls.env["account.journal"].create({"name": "Voucher Sales", "code": "VSA", "type": "sale", "company_id": cls.company.id})
        cls.purchase = cls.env["account.journal"].create({"name": "Voucher Purchase", "code": "VPU", "type": "purchase", "company_id": cls.company.id})
        cls.customer = cls.env["res.partner"].create({
            "name": "Voucher Customer", "is_customer": True, "customer_rank": 1,
            "property_account_receivable_id": cls.receivable.id,
        })
        cls.vendor = cls.env["res.partner"].create({
            "name": "Voucher Vendor", "is_vendor": True, "supplier_rank": 1,
            "property_account_payable_id": cls.payable.id,
        })
        cls.both = cls.env["res.partner"].create({
            "name": "Voucher Both", "is_customer": True, "is_vendor": True,
            "customer_rank": 1, "supplier_rank": 1,
            "property_account_receivable_id": cls.receivable.id,
            "property_account_payable_id": cls.payable.id,
        })
        cls.cheque_bank = cls.env["res.bank"].create({"name": "Voucher Cheque Bank", "bic": "VCHQBDDH"})

    def _make_invoice(self, partner=None, amount=100):
        partner = partner or self.customer
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "journal_id": self.sales.id,
            "invoice_date": fields.Date.context_today(self.env.user),
            "invoice_line_ids": [Command.create({
                "name": "Voucher test invoice",
                "quantity": 1,
                "price_unit": amount,
                "account_id": self.income.id,
            })],
        })
        invoice.action_post()
        return invoice

    def _make_vendor_bill(self, partner=None, amount=100):
        partner = partner or self.vendor
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": partner.id,
            "journal_id": self.purchase.id,
            "invoice_date": fields.Date.context_today(self.env.user),
            "invoice_line_ids": [Command.create({
                "name": "Voucher test vendor bill",
                "quantity": 1,
                "price_unit": amount,
                "account_id": self.expense.id,
            })],
        })
        bill.action_post()
        return bill

    def _simple(self, voucher_type="receipt", **extra):
        vals = {"voucher_type": voucher_type, "partner_id": self.customer.id, "journal_id": self.journal.id,
                "debit_account_id": self.bank.id, "credit_account_id": self.receivable.id, "amount_total": 100}
        vals.update(extra)
        # Existing receipt tests get an invoice automatically, while explicitly
        # passing invoice_id=False creates an unallocated customer receipt.
        if voucher_type == "receipt" and "invoice_id" not in extra:
            partner = self.env["res.partner"].browse(vals.get("partner_id"))
            if partner.customer_rank > 0:
                vals["invoice_id"] = self._make_invoice(partner=partner, amount=vals["amount_total"]).id
        return self.env["account.voucher"].create(vals)

    def test_receipt_workflow_post_and_idempotence(self):
        voucher = self._simple()
        invoice = voucher.invoice_id
        self.assertTrue(voucher.voucher_number.startswith("RV-"))
        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()
        self.assertEqual(voucher.accounting_move_id.state, "posted")
        self.assertEqual(invoice.payment_state, "paid")
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
        self.assertTrue(all(voucher.accounting_move_id.line_ids.mapped("currency_id")))
        self.assertEqual(voucher.accounting_move_id.line_ids.currency_id, self.company.currency_id)
        self.assertEqual(voucher.accounting_move_id.line_ids.mapped("debit"), [100.0, 0.0])
        move = voucher.accounting_move_id
        voucher.action_post()
        self.assertEqual(voucher.accounting_move_id, move)
        with self.assertRaises(UserError):
            voucher.write({"amount_total": 200})
        with self.assertRaises(UserError):
            voucher.unlink()

    def test_receipt_reversal_reopens_invoice(self):
        voucher = self._simple()
        invoice = voucher.invoice_id
        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()
        self.assertEqual(invoice.payment_state, "paid")

        voucher.action_reverse()

        self.assertTrue(voucher.reversal_move_id)
        self.assertEqual(voucher.reversal_move_id.state, "posted")
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(invoice.amount_residual, 100)

    def test_create_uses_voucher_type_from_action_context(self):
        vals = {"partner_id": self.customer.id, "journal_id": self.journal.id,
                "debit_account_id": self.bank.id, "credit_account_id": self.receivable.id,
                "amount_total": 100}
        voucher = self.env["account.voucher"].with_context(
            default_voucher_type="receipt"
        ).create(vals)
        self.assertEqual(voucher.voucher_type, "receipt")
        self.assertTrue(voucher.voucher_number.startswith("RV-"))

    def test_hidden_journal_fields_are_defaulted(self):
        receipt = self.env["account.voucher"].create({
            "voucher_type": "receipt", "partner_id": self.customer.id,
            "debit_account_id": self.bank.id, "credit_account_id": self.receivable.id,
            "amount_total": 100,
        })
        self.assertIn(receipt.journal_id.type, ("bank", "cash"))
        self.assertEqual(receipt.debit_account_id, receipt.journal_id.default_account_id)
        self.assertEqual(receipt.credit_account_id.account_type, "asset_receivable")

        payment_defaults = self.env["account.voucher"].with_context(
            default_voucher_type="payment"
        ).default_get(["voucher_type", "journal_id", "debit_account_id", "credit_account_id"])
        self.assertEqual(
            self.env["account.account"].browse(payment_defaults["debit_account_id"]).account_type,
            "liability_payable",
        )
        self.assertEqual(
            payment_defaults["credit_account_id"],
            self.env["account.journal"].browse(payment_defaults["journal_id"]).default_account_id.id,
        )

        journal_voucher = self.env["account.voucher"].create({
            "voucher_type": "journal",
            "line_ids": [Command.create({"account_id": self.expense.id, "name": "Debit", "debit": 50}),
                         Command.create({"account_id": self.payable.id, "name": "Credit", "credit": 50})],
        })
        self.assertEqual(journal_voucher.entry_journal_id, self.general)

    def test_payment_and_partner_classification(self):
        payment = self._simple("payment", partner_id=self.vendor.id, debit_account_id=self.payable.id, credit_account_id=self.bank.id)
        self.assertTrue(payment.voucher_number.startswith("PV-"))
        self._simple("receipt", partner_id=self.both.id)
        self._simple("payment", partner_id=self.both.id, debit_account_id=self.payable.id, credit_account_id=self.bank.id)
        neither = self.env["res.partner"].create({"name": "Neither"})
        with self.assertRaises(ValidationError):
            self._simple(partner_id=neither.id)

    def test_contra_and_expense_validation(self):
        other = self.env["account.journal"].create({"name": "Voucher Cash", "code": "VCS", "type": "cash", "company_id": self.company.id, "default_account_id": self.bank.id})
        contra = self._simple("contra", partner_id=False, journal_id=False, source_journal_id=self.journal.id, destination_journal_id=other.id)
        self.assertTrue(contra.voucher_number.startswith("CV-"))
        with self.assertRaises(ValidationError):
            self._simple("contra", partner_id=False, journal_id=False, source_journal_id=self.journal.id, destination_journal_id=self.journal.id)
        expense = self._simple("expense", partner_id=False, debit_account_id=self.expense.id, credit_account_id=self.bank.id)
        self.assertTrue(expense.voucher_number.startswith("EV-"))

    def test_journal_balance_post_reverse_and_report(self):
        voucher = self.env["account.voucher"].create({"voucher_type": "journal", "entry_journal_id": self.general.id,
            "line_ids": [Command.create({"account_id": self.expense.id, "name": "Debit", "debit": 50}),
                         Command.create({"account_id": self.payable.id, "name": "Credit", "credit": 50})]})
        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post(); voucher.action_reverse()
        self.assertTrue(all(voucher.accounting_move_id.line_ids.mapped("currency_id")))
        self.assertEqual(voucher.reversal_move_id.state, "posted")
        html, _ = self.env["ir.actions.report"]._render_qweb_html("account_voucher_management.action_report_journal_voucher", voucher.ids)
        self.assertIn(b"JV-", html)

    def test_received_cheque_workflow_and_duplicate_protection(self):
        cheque = self._simple(
            payment_mode="cheque", cheque_number=" CHQ-1001 ", cheque_date="2026-08-18",
            cheque_bank_id=self.cheque_bank.id, cheque_payee="Voucher Customer",
        )
        self.assertEqual(cheque.cheque_number, "CHQ-1001")
        cheque.action_submit(); cheque.action_waiting(); cheque.action_approve(); cheque.action_post()
        self.assertEqual(cheque.cheque_status, "received")
        cheque.action_cheque_deposit()
        self.assertEqual(cheque.cheque_status, "deposited")
        cheque.action_cheque_clear()
        self.assertEqual(cheque.cheque_status, "cleared")
        self.assertTrue(cheque.cheque_cleared_date)
        with self.assertRaises(ValidationError):
            self._simple(
                payment_mode="cheque", cheque_number="CHQ-1001", cheque_date="2026-08-18",
                cheque_bank_id=self.cheque_bank.id,
            )


    def test_receipt_without_reference_posts_open_customer_credit(self):
        invoice = self._make_invoice(amount=200)
        voucher = self._simple(invoice_id=False, amount_total=500)

        # Partner Ledger balance is debit - credit in company currency.
        self.assertEqual(voucher.outstanding_balance, 200)

        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()

        self.assertFalse(voucher.invoice_id)
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(invoice.amount_residual, 200)

        receivable_line = voucher.accounting_move_id.line_ids.filtered(
            lambda line: line.account_id == self.receivable
        )
        self.assertEqual(len(receivable_line), 1)
        self.assertEqual(receivable_line.debit, 0)
        self.assertEqual(receivable_line.credit, 500)
        self.assertEqual(receivable_line.partner_id, self.customer)
        self.assertFalse(receivable_line.reconciled)

        voucher.invalidate_recordset(["outstanding_balance"])
        self.assertEqual(voucher.outstanding_balance, -300)

    def test_receipt_without_reference_requires_receivable_credit_account(self):
        voucher = self._simple(
            invoice_id=False,
            amount_total=100,
            credit_account_id=self.income.id,
        )
        with self.assertRaises(ValidationError):
            voucher.action_submit()
        self.assertEqual(voucher.state, "draft")

    def test_receipt_partial_payment_is_allowed_and_invoice_stays_partial(self):
        invoice = self._make_invoice(amount=100)
        voucher = self._simple(invoice_id=invoice.id, amount_total=60)

        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()

        self.assertEqual(invoice.payment_state, "partial")
        self.assertEqual(invoice.amount_residual, 40)
        receivable_line = voucher.accounting_move_id.line_ids.filtered(
            lambda line: line.account_id == self.receivable
        )
        self.assertTrue(receivable_line.reconciled)

    def test_receipt_overpayment_is_rejected_on_submit(self):
        invoice = self._make_invoice(amount=100)
        voucher = self._simple(invoice_id=invoice.id, amount_total=110)

        with self.assertRaises(ValidationError):
            voucher.action_submit()

        self.assertEqual(voucher.state, "draft")
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(invoice.amount_residual, 100)

    def test_partially_paid_invoice_is_fully_paid_on_voucher_post(self):
        invoice = self._make_invoice(amount=100)
        partial_move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.general.id,
            "date": fields.Date.context_today(self.env.user),
            "line_ids": [
                Command.create({
                    "name": "Partial receipt",
                    "account_id": self.bank.id,
                    "partner_id": self.customer.id,
                    "debit": 40,
                    "credit": 0,
                    "currency_id": self.company.currency_id.id,
                    "amount_currency": 40,
                }),
                Command.create({
                    "name": "Partial receipt",
                    "account_id": self.receivable.id,
                    "partner_id": self.customer.id,
                    "debit": 0,
                    "credit": 40,
                    "currency_id": self.company.currency_id.id,
                    "amount_currency": -40,
                }),
            ],
        })
        partial_move.action_post()
        invoice_line = invoice.line_ids.filtered(
            lambda line: line.account_id == self.receivable and not line.reconciled
        )
        payment_line = partial_move.line_ids.filtered(lambda line: line.account_id == self.receivable)
        (invoice_line | payment_line).reconcile()

        self.assertEqual(invoice.payment_state, "partial")
        self.assertEqual(invoice.amount_residual, 60)

        voucher = self._simple(invoice_id=invoice.id, amount_total=60)
        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()

        self.assertEqual(invoice.payment_state, "paid")
        self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))

    def test_receipt_overpayment_is_rechecked_on_post(self):
        invoice = self._make_invoice(amount=100)
        voucher = self._simple(invoice_id=invoice.id, amount_total=80)
        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve()

        # Another receipt reduces the invoice residual after this voucher was approved.
        other_move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.general.id,
            "date": fields.Date.context_today(self.env.user),
            "line_ids": [
                Command.create({
                    "name": "External receipt",
                    "account_id": self.bank.id,
                    "partner_id": self.customer.id,
                    "debit": 30,
                    "credit": 0,
                    "currency_id": self.company.currency_id.id,
                    "amount_currency": 30,
                }),
                Command.create({
                    "name": "External receipt",
                    "account_id": self.receivable.id,
                    "partner_id": self.customer.id,
                    "debit": 0,
                    "credit": 30,
                    "currency_id": self.company.currency_id.id,
                    "amount_currency": -30,
                }),
            ],
        })
        other_move.action_post()
        invoice_line = invoice.line_ids.filtered(
            lambda line: line.account_id == self.receivable and not line.reconciled
        )
        payment_line = other_move.line_ids.filtered(lambda line: line.account_id == self.receivable)
        (invoice_line | payment_line).reconcile()
        self.assertEqual(invoice.amount_residual, 70)

        with self.assertRaises(ValidationError):
            voucher.action_post()

        self.assertEqual(voucher.state, "approved")
        self.assertFalse(voucher.accounting_move_id)


    def test_payment_full_vendor_bill_is_paid_on_post(self):
        bill = self._make_vendor_bill(amount=100)
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=bill.id,
            debit_account_id=self.payable.id,
            credit_account_id=self.bank.id,
            amount_total=100,
        )

        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()

        self.assertEqual(bill.payment_state, "paid")
        self.assertTrue(bill.currency_id.is_zero(bill.amount_residual))
        payable_line = voucher.accounting_move_id.line_ids.filtered(
            lambda line: line.account_id == self.payable
        )
        self.assertEqual(len(payable_line), 1)
        self.assertEqual(payable_line.debit, 100)
        self.assertEqual(payable_line.credit, 0)
        self.assertEqual(payable_line.partner_id, self.vendor)
        self.assertTrue(payable_line.reconciled)

    def test_payment_partial_vendor_bill_is_partially_paid(self):
        bill = self._make_vendor_bill(amount=100)
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=bill.id,
            debit_account_id=self.payable.id,
            credit_account_id=self.bank.id,
            amount_total=60,
        )

        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()

        self.assertEqual(bill.payment_state, "partial")
        self.assertEqual(bill.amount_residual, 40)

    def test_payment_overpayment_is_rejected_on_submit(self):
        bill = self._make_vendor_bill(amount=100)
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=bill.id,
            debit_account_id=self.payable.id,
            credit_account_id=self.bank.id,
            amount_total=110,
        )

        with self.assertRaises(ValidationError):
            voucher.action_submit()

        self.assertEqual(voucher.state, "draft")
        self.assertEqual(bill.payment_state, "not_paid")
        self.assertEqual(bill.amount_residual, 100)

    def test_payment_outstanding_balance_matches_vendor_partner_ledger(self):
        bill = self._make_vendor_bill(amount=100)
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=False,
            debit_account_id=self.payable.id,
            credit_account_id=self.bank.id,
            amount_total=40,
        )

        # A posted vendor bill credits Accounts Payable, so Partner Ledger
        # balance (debit - credit) is negative.
        self.assertEqual(voucher.outstanding_balance, -100)

        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()

        # The unallocated payment debits Accounts Payable by 40, therefore the
        # vendor's Partner Ledger balance becomes -60.
        voucher.invalidate_recordset(["outstanding_balance"])
        self.assertEqual(voucher.outstanding_balance, -60)
        self.assertEqual(bill.payment_state, "not_paid")

    def test_payment_without_reference_posts_open_vendor_debit(self):
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=False,
            debit_account_id=self.payable.id,
            credit_account_id=self.bank.id,
            amount_total=75,
        )

        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()

        self.assertFalse(voucher.invoice_id)
        payable_line = voucher.accounting_move_id.line_ids.filtered(
            lambda line: line.account_id == self.payable
        )
        self.assertEqual(len(payable_line), 1)
        self.assertEqual(payable_line.debit, 75)
        self.assertEqual(payable_line.credit, 0)
        self.assertEqual(payable_line.partner_id, self.vendor)
        self.assertFalse(payable_line.reconciled)

    def test_payment_without_reference_requires_payable_debit_account(self):
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=False,
            debit_account_id=self.expense.id,
            credit_account_id=self.bank.id,
            amount_total=75,
        )

        with self.assertRaises(ValidationError):
            voucher.action_submit()

        self.assertEqual(voucher.state, "draft")

    def test_payment_overpayment_is_rechecked_on_post(self):
        bill = self._make_vendor_bill(amount=100)
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=bill.id,
            debit_account_id=self.payable.id,
            credit_account_id=self.bank.id,
            amount_total=80,
        )
        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve()

        # Another vendor payment reduces the bill residual after approval.
        other_move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.general.id,
            "date": fields.Date.context_today(self.env.user),
            "line_ids": [
                Command.create({
                    "name": "External vendor payment",
                    "account_id": self.payable.id,
                    "partner_id": self.vendor.id,
                    "debit": 30,
                    "credit": 0,
                    "currency_id": self.company.currency_id.id,
                    "amount_currency": 30,
                }),
                Command.create({
                    "name": "External vendor payment",
                    "account_id": self.bank.id,
                    "partner_id": self.vendor.id,
                    "debit": 0,
                    "credit": 30,
                    "currency_id": self.company.currency_id.id,
                    "amount_currency": -30,
                }),
            ],
        })
        other_move.action_post()
        bill_line = bill.line_ids.filtered(
            lambda line: line.account_id == self.payable and not line.reconciled
        )
        payment_line = other_move.line_ids.filtered(lambda line: line.account_id == self.payable)
        (bill_line | payment_line).reconcile()
        self.assertEqual(bill.amount_residual, 70)

        with self.assertRaises(ValidationError):
            voucher.action_post()

        self.assertEqual(voucher.state, "approved")
        self.assertFalse(voucher.accounting_move_id)

    def test_payment_reversal_reopens_vendor_bill(self):
        bill = self._make_vendor_bill(amount=100)
        voucher = self._simple(
            "payment",
            partner_id=self.vendor.id,
            invoice_id=bill.id,
            debit_account_id=self.payable.id,
            credit_account_id=self.bank.id,
            amount_total=100,
        )
        voucher.action_submit(); voucher.action_waiting(); voucher.action_approve(); voucher.action_post()
        self.assertEqual(bill.payment_state, "paid")

        voucher.action_reverse()

        self.assertEqual(bill.payment_state, "not_paid")
        self.assertEqual(bill.amount_residual, 100)

    def test_actions_and_relations(self):
        for xmlid in ("action_all_vouchers", "action_cheque_register", "action_receipt_voucher", "action_payment_voucher", "action_contra_voucher", "action_expense_voucher", "action_journal_voucher"):
            self.assertEqual(self.env.ref("account_voucher_management.%s" % xmlid).res_model, "account.voucher")
        self.assertEqual(self.env["account.voucher"]._fields["debit_account_id"].comodel_name, "account.account")
        self.assertEqual(self.env["account.voucher.line"]._fields["account_id"].comodel_name, "account.account")
        self.assertIn("analytic_precision", self.env["account.voucher.line"]._fields)
