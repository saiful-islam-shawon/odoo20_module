# Account Voucher Management (Odoo 20 Enterprise)

Traditional receipt, payment, contra, expense, and journal voucher registers backed by posted Odoo `account.move` records.

## Installation and configuration

Add this repository and Odoo Enterprise to `addons_path`, update the Apps list, and install **Account Voucher Management**. Assign users one of Voucher User, Voucher Approver, or Voucher Accountant/Manager. Receipt vouchers use Odoo customers (`customer_rank > 0`) and payment vouchers use Odoo vendors (`supplier_rank > 0`). Configure bank/cash and miscellaneous journals plus the chart of accounts normally in Accounting.

## Workflow

Draft → Submitted → Waiting for Approval → Approved → Posted. Approvers can reject a submitted voucher to Draft when a rejection reason is entered. Managers can cancel an unposted voucher. Posted vouchers are immutable and undeletable; Reverse creates and posts a standard linked reversing journal entry.

## Voucher registers

- Receipt: customer, live outstanding receivable balance, optional posted unpaid/partial invoice reference, bank/cash receipt journal, debit and credit accounts, amount.
- Payment: vendor, optional posted unpaid/partial vendor bill reference, bank/cash payment journal, payable debit account, liquidity credit account, amount.
- Contra: distinct bank/cash source and destination journals with debit and credit accounts.
- Expense: optional partner, bank/cash journal, validated expense debit account, credit account.
- Journal: miscellaneous journal and multiple balanced debit/credit lines with partner, currency amount, and analytic distribution.

Each type has its own menu, action, list and primary form. Search filters cover workflow states and date periods. Five print actions render a traditional voucher PDF with company letterhead, accounting lines, amount in words, narration, audit users, and signatures.

## Accounting behavior

Accounts are `Many2one` links to `account.account`; Odoo 20's shared-account `company_ids` and `check_company` enforce company boundaries. Journals are restricted to `bank` and `cash` where required. Posting uses currency `_convert`, creates a balanced `account.move`, then calls `action_post()`. Duplicate posting is blocked. Odoo ledgers, reports, reconciliation, and audit rules remain authoritative.

## Tests

Run with an Odoo 20 server containing Community and Enterprise paths, for example:

`odoo-bin -d voucher_test --addons-path=odoo/addons,enterprise,odoo-custom-modules -i account_voucher_management --test-enable --stop-after-init --test-tags=/account_voucher_management`

Tests cover register actions, account relations, partner classifications including dual-role/neither, receipt/payment/contra/expense/journal creation, validations, workflow, posting, immutability, idempotence, reversal, and QWeb rendering.

## Known limitations

- Receipt and payment vouchers intentionally create direct standard journal entries because manually selectable counterpart accounts do not map safely to every `account.payment` method/reconciliation configuration. `payment_id` is reserved for a future opt-in payment workflow.
- Receipt vouchers with an invoice reference accept any positive amount up to the invoice remaining due. Posting performs partial or full reconciliation automatically; overpayments are rejected. Receipt vouchers without a reference post an unreconciled customer receivable credit (advance/unallocated receipt).
- Payment vouchers with a vendor bill reference accept any positive amount up to the bill remaining due. Posting performs partial or full payable reconciliation automatically; overpayments are rejected and are rechecked at posting time. Payment vouchers without a reference post an unreconciled Accounts Payable debit for the selected vendor (advance/unallocated payment).
- Sequences ship as global fallbacks. Administrators needing independent numbering per company should create company-specific sequences with the same codes; `with_company().next_by_code()` selects them.
- Exchange rates must exist in standard Odoo currency configuration.
