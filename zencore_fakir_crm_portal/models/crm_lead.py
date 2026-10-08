from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    lead_creator_id = fields.Many2one(
        "res.users",
        string="Lead Creator",
        default=lambda self: self.env.user,
        readonly=True,
    )

    assign_team = fields.Char(
        string="Assign Team",
    )

    expected_budget = fields.Integer(
        string="Expected Budget",
    )

    product_line_ids = fields.One2many(
        "crm.lead.product",
        "lead_id",
        string="Products",
    )

    product_total = fields.Monetary(
        string="Total",
        currency_field="company_currency",
        compute="_compute_product_total",
    )

    @api.depends("product_line_ids.amount_total")
    def _compute_product_total(self):
        for lead in self:
            lead.product_total = sum(lead.product_line_ids.mapped("amount_total"))

    def action_open_fakir_send_mail(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Send Mail",
            "res_model": "fakir.crm.send.mail.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lead_id": self.id,
            },
        }

    def portal_tracking_display_value(self, tracking, side):
        """Return the same tracked old/new value in a portal-friendly form.

        Odoo stores chatter tracking values in different columns depending on
        the tracked field type.  The old portal template only rendered the
        char columns, so monetary/numeric/date values appeared blank.
        """
        self.ensure_one()
        if side not in ("old", "new"):
            return ""

        field = tracking.field_id
        field_type = field.ttype if field else False

        # Relational, selection and textual tracking values are represented
        # by their human-readable labels in the char tracking columns.
        char_value = getattr(tracking, f"{side}_value_char", False)
        if field_type in ("char", "text", "selection", "many2one", "one2many", "many2many", "reference"):
            return char_value or ""

        if field_type in ("integer", "boolean"):
            value = getattr(tracking, f"{side}_value_integer", False)
            if field_type == "boolean":
                return "True" if bool(value) else "False"
            return str(value or 0)

        if field_type in ("float", "monetary"):
            attr = f"{side}_value_{field_type}"
            value = getattr(tracking, attr, False)
            # Some Odoo versions store monetary values in the float column.
            if value is False and field_type == "monetary":
                value = getattr(tracking, f"{side}_value_float", False)
            value = 0.0 if value is False else value
            digits = 2
            if field_type == "monetary":
                currency = getattr(tracking, "currency_id", False) or self.company_currency
                if currency:
                    digits = currency.decimal_places
                    amount = f"{value:,.{digits}f}"
                    return f"{currency.symbol} {amount}" if currency.position == "before" else f"{amount} {currency.symbol}"
            return f"{value:,.{digits}f}"

        if field_type in ("date", "datetime"):
            value = getattr(tracking, f"{side}_value_datetime", False)
            if value:
                if field_type == "date":
                    return fields.Date.to_string(value.date() if hasattr(value, "date") else value)
                return fields.Datetime.to_string(value)
            return ""

        # Forward-compatible fallback: prefer a human-readable char value,
        # then inspect the standard tracking storage columns that exist.
        if char_value:
            return char_value
        for suffix in ("monetary", "float", "integer", "datetime"):
            name = f"{side}_value_{suffix}"
            if name in tracking._fields:
                value = getattr(tracking, name, False)
                if value not in (False, None, ""):
                    return str(value)
        return ""

