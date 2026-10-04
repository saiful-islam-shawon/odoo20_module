from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class AccountVoucher(models.Model):
    _name = "account.voucher"
    _description = "Accounting Voucher"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, voucher_number desc, id desc"
    _check_company_auto = True

    voucher_number = fields.Char(default="New", readonly=True, copy=False, index=True, tracking=True)
    voucher_type = fields.Selection([
        ("receipt", "Receipt Voucher"), ("payment", "Payment Voucher"),
        ("contra", "Contra Voucher"), ("expense", "Expense Voucher"),
        ("journal", "Journal Voucher"),
    ], required=True, index=True, readonly=True, tracking=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company,
                                 index=True, tracking=True)
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    currency_id = fields.Many2one("res.currency", required=True,
                                  default=lambda self: self.env.company.currency_id, tracking=True)
    state = fields.Selection([
        ("draft", "Draft"), ("submitted", "Submitted"),
        ("waiting", "Waiting for Approval"), ("approved", "Approved"),
        ("posted", "Posted"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, readonly=True, copy=False, index=True, tracking=True)
    partner_id = fields.Many2one("res.partner", check_company=True, tracking=True)
    partner_commercial_id = fields.Many2one(
        "res.partner",
        related="partner_id.commercial_partner_id",
        string="Commercial Partner",
        readonly=True,
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Reference",
        check_company=True,
        copy=False,
        tracking=True,
        domain=[
            ("move_type", "in", ("out_invoice", "in_invoice")),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")),
        ],
    )
    outstanding_balance = fields.Monetary(
        string="Outstanding Balance",
        compute="_compute_outstanding_balance",
        currency_field="company_currency_id",
        help=(
            "Posted Partner Ledger balance in company currency as of the voucher date. "
            "Receipt vouchers use Accounts Receivable; payment vouchers use Accounts Payable."
        ),
    )
    payment_mode = fields.Selection([
        ("cash", "Cash"), ("bank", "Bank Transfer"), ("cheque", "Cheque"),
    ], default="bank", required=True, tracking=True)
    cheque_direction = fields.Selection([
        ("received", "Received Cheque"), ("issued", "Issued Cheque"),
    ], compute="_compute_cheque_direction", store=True)
    cheque_number = fields.Char(copy=False, index=True, tracking=True)
    cheque_date = fields.Date(copy=False, tracking=True)
    cheque_bank_id = fields.Many2one("res.bank", string="Cheque Bank", copy=False, tracking=True)
    cheque_branch = fields.Char(copy=False, tracking=True)
    cheque_payee = fields.Char(copy=False, tracking=True)
    cheque_status = fields.Selection([
        ("draft", "Draft"), ("received", "Received"), ("issued", "Issued"),
        ("deposited", "Deposited"), ("cleared", "Cleared"),
        ("bounced", "Bounced"), ("cancelled", "Cancelled"),
    ], default="draft", required=True, readonly=True, copy=False, index=True, tracking=True)
    cheque_deposit_date = fields.Date(readonly=True, copy=False, tracking=True)
    cheque_cleared_date = fields.Date(readonly=True, copy=False, tracking=True)
    cheque_bounce_date = fields.Date(readonly=True, copy=False, tracking=True)
    cheque_bounce_reason = fields.Text(copy=False, tracking=True)
    journal_id = fields.Many2one("account.journal", string="Payment/Receipt Journal", check_company=True,
                                 domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    source_journal_id = fields.Many2one("account.journal", check_company=True,
                                        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    destination_journal_id = fields.Many2one("account.journal", check_company=True,
                                             domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    entry_journal_id = fields.Many2one("account.journal", string="General Journal", check_company=True,
                                       domain="[('type', '=', 'general'), ('company_id', '=', company_id)]")
    debit_account_id = fields.Many2one("account.account", check_company=True,
                                       domain="[('company_ids', 'in', company_id)]", tracking=True)
    credit_account_id = fields.Many2one("account.account", check_company=True,
                                        domain="[('company_ids', 'in', company_id)]", tracking=True)
    amount_total = fields.Monetary(currency_field="currency_id", tracking=True)
    reference = fields.Char(tracking=True)
    narration = fields.Text(tracking=True)
    line_ids = fields.One2many("account.voucher.line", "voucher_id", copy=True)
    total_debit = fields.Monetary(compute="_compute_totals", currency_field="currency_id", store=True)
    total_credit = fields.Monetary(compute="_compute_totals", currency_field="currency_id", store=True)
    accounting_move_id = fields.Many2one("account.move", readonly=True, copy=False, check_company=True)
    payment_id = fields.Many2one("account.payment", readonly=True, copy=False, check_company=True)
    reversal_move_id = fields.Many2one("account.move", readonly=True, copy=False, check_company=True)
    created_by = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    posted_by = fields.Many2one("res.users", readonly=True, copy=False)
    approval_date = fields.Datetime(readonly=True, copy=False)
    posting_date = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(copy=False)
    rejected_by = fields.Many2one("res.users", readonly=True, copy=False)
    rejection_date = fields.Datetime(readonly=True, copy=False)

    @api.depends("line_ids.debit", "line_ids.credit")
    def _compute_totals(self):
        for voucher in self:
            voucher.total_debit = sum(voucher.line_ids.mapped("debit"))
            voucher.total_credit = sum(voucher.line_ids.mapped("credit"))

    @api.depends("partner_id", "company_id", "date", "voucher_type", "state", "reversal_move_id")
    def _compute_outstanding_balance(self):
        """Show the selected partner's Partner Ledger balance as of the voucher date.

        ``account.move.line.balance`` is debit - credit in company currency,
        matching the Balance column used by Odoo's Partner Ledger.

        * Receipt Voucher  -> posted Accounts Receivable lines.
        * Payment Voucher  -> posted Accounts Payable lines.

        The sign is intentionally preserved exactly like the Partner Ledger.
        For example, a vendor with 1,200 debit and 2,100 credit has a balance
        of -900, so this field also shows -900.
        """
        MoveLine = self.env["account.move.line"]
        account_type_by_voucher = {
            "receipt": "asset_receivable",
            "payment": "liability_payable",
        }

        for voucher in self:
            voucher.outstanding_balance = 0.0
            account_type = account_type_by_voucher.get(voucher.voucher_type)
            if not account_type or not voucher.partner_id or not voucher.company_id:
                continue

            commercial_partner = voucher.partner_id.commercial_partner_id
            domain = [
                ("company_id", "=", voucher.company_id.id),
                ("move_id.state", "=", "posted"),
                ("account_id.account_type", "=", account_type),
                ("partner_id", "child_of", commercial_partner.id),
            ]
            if voucher.date:
                domain.append(("date", "<=", voucher.date))

            voucher.outstanding_balance = sum(MoveLine.search(domain).mapped("balance"))

    @api.depends("voucher_type")
    def _compute_cheque_direction(self):
        for voucher in self:
            voucher.cheque_direction = "received" if voucher.voucher_type == "receipt" else "issued"

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        """Keep invoice and counterpart account aligned with the selected partner."""
        for voucher in self:
            if voucher.voucher_type not in ("receipt", "payment"):
                continue

            if (
                voucher.invoice_id
                and voucher.invoice_id.commercial_partner_id != voucher.partner_commercial_id
            ):
                voucher.invoice_id = False

            if not voucher.partner_id or voucher.invoice_id:
                continue

            partner = voucher.partner_id.with_company(voucher.company_id)
            if voucher.voucher_type == "receipt":
                receivable_account = partner.property_account_receivable_id
                if receivable_account:
                    voucher.credit_account_id = receivable_account
            else:
                payable_account = partner.property_account_payable_id
                if payable_account:
                    voucher.debit_account_id = payable_account

    @api.onchange("invoice_id")
    def _onchange_invoice_id(self):
        """Keep voucher currency/counterpart account aligned with its selected bill/invoice."""
        for voucher in self:
            if voucher.voucher_type not in ("receipt", "payment") or not voucher.invoice_id:
                continue

            voucher.currency_id = voucher.invoice_id.currency_id
            if voucher.voucher_type == "receipt":
                accounts = voucher._get_invoice_open_receivable_lines().mapped("account_id")
                if len(accounts) == 1:
                    voucher.credit_account_id = accounts
            else:
                accounts = voucher._get_bill_open_payable_lines().mapped("account_id")
                if len(accounts) == 1:
                    voucher.debit_account_id = accounts

    @api.model
    def _voucher_type_defaults(self, voucher_type, company):
        """Return the journals and counterpart accounts hidden from the voucher form."""
        values = {}
        journals = self.env["account.journal"].search([
            ("company_id", "=", company.id), ("type", "in", ("bank", "cash")),
        ], order="type, sequence, id")
        liquidity_accounts = journals.mapped("default_account_id")
        if voucher_type in ("receipt", "payment", "expense") and journals:
            values["journal_id"] = journals[0].id
        elif voucher_type == "contra" and journals:
            values["source_journal_id"] = journals[0].id
            if len(journals) > 1:
                values["destination_journal_id"] = journals[1].id
        elif voucher_type == "journal":
            values["entry_journal_id"] = self.env["account.journal"].search([
                ("company_id", "=", company.id), ("type", "=", "general"),
            ], order="sequence, id", limit=1).id

        account_domain = [("company_ids", "in", company.ids)]
        if voucher_type == "receipt":
            values["debit_account_id"] = liquidity_accounts[:1].id
            values["credit_account_id"] = self.env["account.account"].search(
                account_domain + [("account_type", "=", "asset_receivable")], limit=1).id
        elif voucher_type == "payment":
            values["debit_account_id"] = self.env["account.account"].search(
                account_domain + [("account_type", "=", "liability_payable")], limit=1).id
            values["credit_account_id"] = liquidity_accounts[:1].id
        elif voucher_type == "contra":
            values["credit_account_id"] = journals[:1].default_account_id.id
            values["debit_account_id"] = journals[1:2].default_account_id.id
        elif voucher_type == "expense":
            values["credit_account_id"] = liquidity_accounts[:1].id
        return values

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        voucher_type = values.get("voucher_type") or self.env.context.get("default_voucher_type")
        company = self.env["res.company"].browse(values.get("company_id")) or self.env.company
        defaults = self._voucher_type_defaults(voucher_type, company)
        values.update({key: value for key, value in defaults.items() if key in fields_list and not values.get(key)})
        return values

    @api.model_create_multi
    def create(self, vals_list):
        codes = {"receipt": "account.voucher.receipt", "payment": "account.voucher.payment",
                 "contra": "account.voucher.contra", "expense": "account.voucher.expense",
                 "journal": "account.voucher.journal"}
        for vals in vals_list:
            if vals.get("cheque_number"):
                vals["cheque_number"] = vals["cheque_number"].strip()
            voucher_type = vals.get("voucher_type") or self.env.context.get("default_voucher_type")
            if voucher_type:
                # Readonly fields are not always included in values sent by the web client.
                vals["voucher_type"] = voucher_type
            if vals.get("voucher_number", "New") == "New":
                company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
                vals["voucher_number"] = self.env["ir.sequence"].with_company(company).next_by_code(
                    codes.get(voucher_type)) or "New"
            company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
            defaults = self._voucher_type_defaults(voucher_type, company)
            for key, value in defaults.items():
                if value and not vals.get(key):
                    vals[key] = value
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("cheque_number"):
            vals["cheque_number"] = vals["cheque_number"].strip()
        protected = {"date", "company_id", "currency_id", "partner_id", "invoice_id", "payment_mode", "cheque_number",
                     "cheque_date", "cheque_bank_id", "cheque_branch", "cheque_payee", "journal_id", "source_journal_id",
                     "destination_journal_id", "entry_journal_id", "debit_account_id", "credit_account_id",
                     "amount_total", "reference", "narration", "line_ids"}
        if protected.intersection(vals) and any(v.state == "posted" for v in self):
            raise UserError(_("Posted vouchers cannot be modified. Reverse the voucher instead."))
        return super().write(vals)

    def unlink(self):
        if any(v.state == "posted" for v in self):
            raise UserError(_("Posted vouchers cannot be deleted."))
        return super().unlink()

    @api.constrains("voucher_type", "partner_id", "journal_id", "source_journal_id", "destination_journal_id",
                    "debit_account_id", "credit_account_id", "amount_total", "line_ids", "company_id",
                    "payment_mode", "cheque_number", "cheque_date", "cheque_bank_id")
    def _check_voucher(self):
        for v in self:
            if v.voucher_type != "journal":
                if v.amount_total <= 0:
                    raise ValidationError(_("Amount must be greater than zero."))
                if not v.debit_account_id or not v.credit_account_id:
                    raise ValidationError(_("Debit and credit accounts are required."))
                if v.debit_account_id == v.credit_account_id:
                    raise ValidationError(_("Debit and credit accounts must differ."))
            if v.voucher_type == "receipt" and (not v.partner_id or v.partner_id.customer_rank <= 0):
                raise ValidationError(_("A customer is required for a receipt voucher."))
            if v.voucher_type == "payment" and (not v.partner_id or v.partner_id.supplier_rank <= 0):
                raise ValidationError(_("A vendor is required for a payment voucher."))
            if v.voucher_type in ("receipt", "payment", "expense") and (
                    not v.journal_id or v.journal_id.type not in ("bank", "cash")):
                raise ValidationError(_("A bank or cash journal is required."))
            if v.voucher_type == "expense" and v.debit_account_id.account_type not in (
                    "expense", "expense_depreciation", "expense_direct_cost"):
                raise ValidationError(_("An expense voucher debit account must be an expense account."))
            if v.voucher_type == "contra":
                if not v.source_journal_id or not v.destination_journal_id:
                    raise ValidationError(_("Source and destination journals are required."))
                if v.source_journal_id == v.destination_journal_id:
                    raise ValidationError(_("Source and destination journals must differ."))
                if v.source_journal_id.type not in ("bank", "cash") or v.destination_journal_id.type not in ("bank", "cash"):
                    raise ValidationError(_("Contra journals must be bank or cash journals."))
            if v.voucher_type == "journal":
                if not v.line_ids:
                    raise ValidationError(_("Journal voucher lines are required."))
                if float_compare(v.total_debit, v.total_credit, precision_rounding=v.currency_id.rounding):
                    raise ValidationError(_("Journal voucher debit and credit totals must balance."))
            if v.payment_mode == "cheque":
                if v.voucher_type not in ("receipt", "payment", "expense"):
                    raise ValidationError(_("Cheque payment mode is available only for receipt, payment and expense vouchers."))
                if not v.cheque_number or not v.cheque_date or not v.cheque_bank_id:
                    raise ValidationError(_("Cheque number, cheque date and cheque bank are required."))
                duplicate = self.search_count([
                    ("id", "!=", v.id), ("company_id", "=", v.company_id.id),
                    ("cheque_number", "=", v.cheque_number.strip()),
                    ("cheque_bank_id", "=", v.cheque_bank_id.id),
                    ("cheque_status", "!=", "cancelled"),
                ])
                if duplicate:
                    raise ValidationError(_("This cheque number already exists for the selected bank."))

    def _get_invoice_open_receivable_lines(self):
        self.ensure_one()
        if not self.invoice_id:
            return self.env["account.move.line"]
        return self.invoice_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
        )

    def _check_receipt_invoice(self):
        """Validate an optional customer invoice and prevent overpayment.

        A receipt may pay all or only part of the invoice's current residual.
        Amounts greater than the current residual are rejected.
        """
        self.ensure_one()
        if self.voucher_type != "receipt":
            return

        invoice = self.invoice_id
        if not invoice:
            # Reference is optional.  Without an invoice the voucher is an
            # unallocated customer receipt / advance and must remain as an
            # open credit on Accounts Receivable.
            if not self.credit_account_id or self.credit_account_id.account_type != "asset_receivable":
                raise ValidationError(_(
                    "A receipt voucher without an invoice must credit an Accounts Receivable account."
                ))
            return
        if invoice.move_type != "out_invoice":
            raise ValidationError(_("Reference must be a customer invoice."))
        if invoice.state != "posted":
            raise ValidationError(_("Only posted customer invoices can be used in a receipt voucher."))
        if invoice.payment_state not in ("not_paid", "partial"):
            raise ValidationError(_("Only unpaid or partially paid customer invoices can be used."))
        if invoice.company_id != self.company_id:
            raise ValidationError(_("The selected invoice must belong to the same company as the voucher."))
        if invoice.commercial_partner_id != self.partner_commercial_id:
            raise ValidationError(_("The selected invoice does not belong to the selected customer."))
        if invoice.currency_id != self.currency_id:
            raise ValidationError(_("Voucher currency must be the same as the selected invoice currency."))

        receivable_lines = self._get_invoice_open_receivable_lines()
        if not receivable_lines:
            raise ValidationError(_("The selected invoice has no open receivable amount."))
        receivable_accounts = receivable_lines.mapped("account_id")
        if len(receivable_accounts) != 1:
            raise ValidationError(_("The selected invoice uses more than one open receivable account."))
        if self.credit_account_id != receivable_accounts:
            raise ValidationError(_("Credit Account must match the receivable account of the selected invoice."))

        if float_compare(
            self.amount_total,
            invoice.amount_residual,
            precision_rounding=invoice.currency_id.rounding,
        ) > 0:
            raise ValidationError(_(
                "Voucher amount (%(voucher_amount)s %(currency)s) cannot be greater than "
                "the invoice remaining due (%(invoice_due)s %(currency)s).",
                voucher_amount=self.amount_total,
                invoice_due=invoice.amount_residual,
                currency=invoice.currency_id.name,
            ))

    def _reconcile_receipt_invoice(self, move):
        """Reconcile the posted receipt move with its selected invoice."""
        self.ensure_one()
        if self.voucher_type != "receipt" or not self.invoice_id:
            return

        invoice_lines = self._get_invoice_open_receivable_lines().filtered(
            lambda line: line.account_id == self.credit_account_id
        )
        voucher_lines = move.line_ids.filtered(
            lambda line: line.account_id == self.credit_account_id and not line.reconciled
        )
        if not invoice_lines or not voucher_lines:
            raise ValidationError(_("Could not find matching receivable lines to reconcile the invoice."))

        (invoice_lines | voucher_lines).reconcile()

        # The receipt line itself must be fully allocated.  The invoice may
        # legitimately keep a residual amount when this voucher is a partial
        # payment; Odoo will then set the invoice payment status to "Partial".
        if any(not line.reconciled for line in voucher_lines):
            raise ValidationError(_("The receipt amount could not be fully reconciled with the selected invoice."))

    def _get_bill_open_payable_lines(self):
        self.ensure_one()
        if not self.invoice_id:
            return self.env["account.move.line"]
        return self.invoice_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "liability_payable" and not line.reconciled
        )

    def _check_payment_bill(self):
        """Validate an optional vendor bill and prevent vendor overpayment."""
        self.ensure_one()
        if self.voucher_type != "payment":
            return

        bill = self.invoice_id
        if not bill:
            # Without a bill this is an unallocated vendor payment/advance.
            # Keep it as an open debit on Accounts Payable.
            if not self.debit_account_id or self.debit_account_id.account_type != "liability_payable":
                raise ValidationError(_(
                    "A payment voucher without a vendor bill must debit an Accounts Payable account."
                ))
            return

        if bill.move_type != "in_invoice":
            raise ValidationError(_("Reference must be a vendor bill."))
        if bill.state != "posted":
            raise ValidationError(_("Only posted vendor bills can be used in a payment voucher."))
        if bill.payment_state not in ("not_paid", "partial"):
            raise ValidationError(_("Only unpaid or partially paid vendor bills can be used."))
        if bill.company_id != self.company_id:
            raise ValidationError(_("The selected vendor bill must belong to the same company as the voucher."))
        if bill.commercial_partner_id != self.partner_commercial_id:
            raise ValidationError(_("The selected vendor bill does not belong to the selected vendor."))
        if bill.currency_id != self.currency_id:
            raise ValidationError(_("Voucher currency must be the same as the selected vendor bill currency."))

        payable_lines = self._get_bill_open_payable_lines()
        if not payable_lines:
            raise ValidationError(_("The selected vendor bill has no open payable amount."))
        payable_accounts = payable_lines.mapped("account_id")
        if len(payable_accounts) != 1:
            raise ValidationError(_("The selected vendor bill uses more than one open payable account."))
        if self.debit_account_id != payable_accounts:
            raise ValidationError(_("Debit Account must match the payable account of the selected vendor bill."))

        if float_compare(
            self.amount_total,
            bill.amount_residual,
            precision_rounding=bill.currency_id.rounding,
        ) > 0:
            raise ValidationError(_(
                "Voucher amount (%(voucher_amount)s %(currency)s) cannot be greater than "
                "the vendor bill remaining due (%(bill_due)s %(currency)s).",
                voucher_amount=self.amount_total,
                bill_due=bill.amount_residual,
                currency=bill.currency_id.name,
            ))

    def _reconcile_payment_bill(self, move):
        """Reconcile the posted payment voucher with its selected vendor bill."""
        self.ensure_one()
        if self.voucher_type != "payment" or not self.invoice_id:
            return

        bill_lines = self._get_bill_open_payable_lines().filtered(
            lambda line: line.account_id == self.debit_account_id
        )
        voucher_lines = move.line_ids.filtered(
            lambda line: line.account_id == self.debit_account_id and not line.reconciled
        )
        if not bill_lines or not voucher_lines:
            raise ValidationError(_("Could not find matching payable lines to reconcile the vendor bill."))

        (bill_lines | voucher_lines).reconcile()

        # The voucher debit must be fully allocated.  The vendor bill may keep
        # a residual amount for partial payments, in which case Odoo sets the
        # payment status to Partial automatically.
        if any(not line.reconciled for line in voucher_lines):
            raise ValidationError(_("The payment amount could not be fully reconciled with the selected vendor bill."))

    def action_submit(self):
        for voucher in self.filtered(lambda v: v.state == "draft"):
            voucher._check_voucher()
            voucher._check_receipt_invoice()
            voucher._check_payment_bill()
            voucher.write({"state": "submitted"})
            voucher.message_post(body=_("Voucher submitted."))
        return True

    def action_waiting(self):
        self.filtered(lambda v: v.state == "submitted").write({"state": "waiting"})

    def action_approve(self):
        if not self.env.user.has_group("account_voucher_management.group_voucher_approver"):
            raise AccessError(_("Only voucher approvers may approve vouchers."))
        if any(v.state != "waiting" for v in self):
            raise UserError(_("Only vouchers waiting for approval can be approved."))
        self.write({
            "state": "approved", "approved_by": self.env.user.id, "approval_date": fields.Datetime.now()})
        self.message_post(body=_("Voucher approved."))

    def action_reject(self):
        for v in self:
            if v.state not in ("submitted", "waiting") or not v.rejection_reason:
                raise UserError(_("Enter a rejection reason before rejecting a submitted voucher."))
            v.write({"state": "draft", "rejected_by": self.env.user.id, "rejection_date": fields.Datetime.now()})
            v.message_post(body=_("Voucher rejected: %s", v.rejection_reason))

    def action_cancel(self):
        for v in self:
            if v.state != "draft":
                raise UserError(_("Only draft vouchers can be cancelled."))
            v.state = "cancelled"
            if v.payment_mode == "cheque" and v.cheque_status != "cleared":
                v.cheque_status = "cancelled"
            v.message_post(body=_("Voucher cancelled."))

    def _move_lines(self):
        self.ensure_one()
        if self.voucher_type == "journal":
            return [Command.create(line._prepare_move_line()) for line in self.line_ids]
        company_amount = self.currency_id._convert(self.amount_total, self.company_currency_id, self.company_id, self.date)
        foreign = self.currency_id != self.company_currency_id
        reference_name = self.invoice_id.name if self.voucher_type in ("receipt", "payment") and self.invoice_id else self.reference
        common = {"name": self.narration or reference_name or self.voucher_number,
                  "partner_id": self.partner_id.id or False, "currency_id": self.currency_id.id}
        return [Command.create({**common, "account_id": self.debit_account_id.id, "debit": company_amount,
                                "credit": 0.0,
                                "amount_currency": self.amount_total if foreign else company_amount}),
                Command.create({**common, "account_id": self.credit_account_id.id, "debit": 0.0,
                                "credit": company_amount,
                                "amount_currency": -self.amount_total if foreign else -company_amount})]

    def action_post(self):
        if not self.env.user.has_group("account_voucher_management.group_voucher_manager"):
            raise AccessError(_("Only voucher accountants/managers may post vouchers."))
        for v in self:
            if v.accounting_move_id:
                if v.state == "posted":
                    continue
                raise UserError(_("An accounting entry already exists for this voucher."))
            if v.state != "approved":
                raise UserError(_("Only approved vouchers can be posted."))
            v._check_voucher()
            v._check_receipt_invoice()
            v._check_payment_bill()
            journal = v.entry_journal_id or v.journal_id or v.destination_journal_id
            if not journal:
                raise UserError(_("Select a journal before posting."))
            reference_name = v.invoice_id.name if v.voucher_type in ("receipt", "payment") and v.invoice_id else v.reference
            move = self.env["account.move"].create({"move_type": "entry", "journal_id": journal.id,
                "date": v.date, "ref": "%s%s" % (v.voucher_number, reference_name and " - " + reference_name or ""),
                "company_id": v.company_id.id, "currency_id": v.currency_id.id, "line_ids": v._move_lines()})
            move.action_post()
            v._reconcile_receipt_invoice(move)
            v._reconcile_payment_bill(move)
            posting_values = {"accounting_move_id": move.id, "state": "posted", "posted_by": self.env.user.id,
                              "posting_date": fields.Datetime.now()}
            if v.payment_mode == "cheque" and v.cheque_status == "draft":
                posting_values["cheque_status"] = v.cheque_direction
            v.write(posting_values)
            v.message_post(body=_("Voucher posted as %s.", move.display_name))
        return True

    def action_reverse(self):
        for v in self:
            if v.state != "posted" or not v.accounting_move_id or v.reversal_move_id:
                raise UserError(_("Only an unreversed posted voucher can be reversed."))
            # cancel=True first removes existing reconciliations (including the
            # selected customer invoice) and then reconciles the original move
            # with its reversal. For receipt vouchers this reopens the invoice.
            reversal = v.accounting_move_id._reverse_moves([{"date": fields.Date.context_today(v),
                                                              "ref": _("Reversal of %s", v.voucher_number)}], cancel=True)
            v.reversal_move_id = reversal[:1]
            v.message_post(body=_("Voucher reversed by %s.", reversal[:1].display_name))
        return True

    def action_view_move(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "account.move", "view_mode": "form",
                "res_id": self.accounting_move_id.id}

    def action_print_voucher(self):
        self.ensure_one()
        report_by_type = {
            "receipt": "account_voucher_management.action_report_receipt_voucher",
            "payment": "account_voucher_management.action_report_payment_voucher",
            "contra": "account_voucher_management.action_report_contra_voucher",
            "expense": "account_voucher_management.action_report_expense_voucher",
            "journal": "account_voucher_management.action_report_journal_voucher",
        }
        report_xmlid = report_by_type.get(
            self.voucher_type,
            "account_voucher_management.action_report_all_vouchers",
        )
        return self.env.ref(report_xmlid).report_action(self)

    def action_cheque_deposit(self):
        for voucher in self:
            if voucher.payment_mode != "cheque" or voucher.cheque_direction != "received" or voucher.cheque_status != "received":
                raise UserError(_("Only a received cheque can be marked as deposited."))
            voucher.write({"cheque_status": "deposited", "cheque_deposit_date": fields.Date.context_today(voucher)})
            voucher.message_post(body=_("Cheque marked as deposited."))
        return True

    def action_cheque_clear(self):
        for voucher in self:
            allowed = ("deposited",) if voucher.cheque_direction == "received" else ("issued",)
            if voucher.payment_mode != "cheque" or voucher.cheque_status not in allowed:
                raise UserError(_("The cheque is not ready to be cleared."))
            voucher.write({"cheque_status": "cleared", "cheque_cleared_date": fields.Date.context_today(voucher)})
            voucher.message_post(body=_("Cheque marked as cleared."))
        return True

    def action_cheque_bounce(self):
        for voucher in self:
            if voucher.payment_mode != "cheque" or voucher.cheque_status not in ("received", "deposited", "issued"):
                raise UserError(_("Only an active cheque can be marked as bounced."))
            if not voucher.cheque_bounce_reason:
                raise UserError(_("Enter a bounce reason first."))
            voucher.write({"cheque_status": "bounced", "cheque_bounce_date": fields.Date.context_today(voucher)})
            voucher.message_post(body=_("Cheque bounced: %s", voucher.cheque_bounce_reason))
        return True

    def action_cheque_cancel(self):
        for voucher in self:
            if voucher.payment_mode != "cheque" or voucher.cheque_status not in (
                    "received", "issued", "deposited", "bounced"):
                raise UserError(_("Only an active or bounced cheque can be cancelled."))
            voucher.cheque_status = "cancelled"
            voucher.message_post(body=_("Cheque cancelled."))
        return True


class AccountVoucherLine(models.Model):
    _name = "account.voucher.line"
    _description = "Voucher Accounting Line"
    _inherit = "analytic.mixin"
    _order = "sequence, id"
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    voucher_id = fields.Many2one("account.voucher", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="voucher_id.company_id", store=True)
    account_id = fields.Many2one("account.account", required=True, check_company=True,
                                 domain="[('company_ids', 'in', company_id)]")
    partner_id = fields.Many2one("res.partner", check_company=True)
    name = fields.Char(string="Label", required=True)
    debit = fields.Monetary(currency_field="currency_id")
    credit = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="voucher_id.currency_id", store=True)
    amount_currency = fields.Monetary(currency_field="currency_id")

    @api.constrains("debit", "credit")
    def _check_amounts(self):
        for line in self:
            if line.debit < 0 or line.credit < 0 or (line.debit and line.credit) or not (line.debit or line.credit):
                raise ValidationError(_("Each voucher line must contain one positive debit or credit."))

    def _prepare_move_line(self):
        self.ensure_one()
        foreign = self.currency_id != self.company_id.currency_id
        balance = self.debit - self.credit
        company_balance = self.currency_id._convert(balance, self.company_id.currency_id, self.company_id,
                                                     self.voucher_id.date) if foreign else balance
        return {"account_id": self.account_id.id, "partner_id": self.partner_id.id or False, "name": self.name,
                "debit": max(company_balance, 0.0), "credit": max(-company_balance, 0.0),
                "currency_id": self.currency_id.id,
                "amount_currency": self.amount_currency if foreign and self.amount_currency else (
                    balance if foreign else company_balance),
                "analytic_distribution": self.analytic_distribution or False}
