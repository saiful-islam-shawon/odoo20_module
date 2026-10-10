from email.utils import formataddr

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class FakirCrmSendMailWizard(models.TransientModel):
    _name = "fakir.crm.send.mail.wizard"
    _description = "Fakir CRM Send Mail"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Opportunity",
        required=True,
        readonly=True,
    )
    email_to = fields.Char(string="To", required=True)
    subject = fields.Char(string="Subject", required=True)
    message_body = fields.Text(string="Message", required=True)

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        lead = self.env["crm.lead"].browse(
            values.get("lead_id") or self.env.context.get("default_lead_id")
        ).exists()
        if not lead:
            return values

        description_plain = html2plaintext(lead.description or "").strip()

        priority_label = "Normal"
        priority_field = lead._fields.get("priority")
        if priority_field and lead.priority:
            selection = priority_field.selection
            if callable(selection):
                selection = selection(self.env["crm.lead"])
            priority_label = dict(selection or []).get(
                lead.priority,
                lead.priority,
            )

        expected_revenue = (
            "%0.2f" % lead.expected_revenue
            if lead.expected_revenue
            else "TBD"
        )

        values.update({
            "email_to": lead.email_from or "",
            "subject": "Regarding: %s" % (lead.name or "Opportunity"),
            "message_body": "\n".join([
                "Hi Team,",
                "",
                "Hope you're having a good week.",
                "",
                "I’ve just created a new lead in our Odoo CRM and wanted to loop you in so your team can review the requirements and take any necessary next steps.",
                "",
                "Here is a quick overview:",
                "",
                "• Lead / Opportunity: %s" % (lead.name or "N/A"),
                "• Company / Client: %s" % (
                    lead.partner_id.name
                    or lead.contact_name
                    or "N/A"
                ),
                "• Contact Person: %s (%s)" % (
                    lead.contact_name or "N/A",
                    lead.email_from or "No email provided",
                ),
                "• Expected Revenue: %s" % expected_revenue,
                "• Priority: %s" % priority_label,
                "",
                "• Key Notes / Scope:",
                description_plain or "Please check Odoo for full notes.",
                "",
                "Direct Link to Lead:",
                "",
                "Please feel free to jump in, update the chatter, or reach out if anything needs clarification.",
                "",
                "Thanks!",
            ]),
        })
        return values

    def _get_recipient_user(self):
        self.ensure_one()
        email_to = (self.email_to or "").strip()
        if not email_to or "@" not in email_to:
            raise UserError(_("Please enter a valid recipient email address."))

        recipient_users = self.env["res.users"].sudo().search([
            ("email", "=ilike", email_to),
            ("active", "=", True),
        ])
        for user in recipient_users:
            if (
                user.has_group(
                    "zencore_fakir_crm_portal.group_crm_website_access"
                )
                or user.has_group("base.group_system")
            ):
                return user

        raise UserError(_("This user does not have CRM access"))

    def _build_opportunity_url(self):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_str(
            "web.base.url"
        )
        return "%s/my/crm/opportunities/%s" % (
            (base_url or "").rstrip("/"),
            self.lead_id.id,
        )

    def _build_email_body(self, opportunity_url):
        self.ensure_one()
        message_body = (self.message_body or "").strip()
        message_lines = (
            message_body.replace("\r\n", "\n")
            .replace("\r", "\n")
            .split("\n")
        )

        html_parts = []
        button_inserted = False

        for raw_line in message_lines:
            line = raw_line.strip()

            if not line:
                html_parts.append(
                    '<div style="height: 10px; line-height: 10px;">&nbsp;</div>'
                )
                continue

            if line.lower() == "direct link to lead:":
                html_parts.append(
                    '<div style="margin-top: 18px; margin-bottom: 10px; '
                    'font-weight: 700; color: #333333;">Direct Link to Lead:</div>'
                )
                html_parts.append(
                    '<div style="margin: 0 0 18px 0;">'
                    '<a href="%s" style="display: inline-block; '
                    'background-color: #714b67; color: #ffffff; '
                    'padding: 11px 20px; text-decoration: none; '
                    'border-radius: 5px; font-weight: 600;">'
                    'View Opportunity</a></div>'
                    % escape(opportunity_url)
                )
                button_inserted = True
                continue

            if line.lower() == "here is a quick overview:":
                html_parts.append(
                    '<div style="margin-top: 14px; margin-bottom: 8px; '
                    'font-weight: 700; color: #333333;">'
                    'Here is a quick overview:</div>'
                )
                continue

            if line.startswith("•"):
                bullet_text = line[1:].strip()
                if ":" in bullet_text:
                    label, value = bullet_text.split(":", 1)
                    html_parts.append(
                        '<div style="margin: 5px 0 5px 14px;">'
                        '<span style="margin-right: 7px;">&#8226;</span>'
                        '<strong>%s:</strong>%s</div>'
                        % (escape(label.strip()), escape(value))
                    )
                else:
                    html_parts.append(
                        '<div style="margin: 5px 0 5px 14px;">'
                        '<span style="margin-right: 7px;">&#8226;</span>%s</div>'
                        % escape(bullet_text)
                    )
                continue

            html_parts.append(
                '<div style="margin: 0 0 8px 0;">%s</div>'
                % escape(line)
            )

        if not button_inserted:
            html_parts.append(
                '<div style="margin-top: 20px; padding-top: 18px; '
                'border-top: 1px solid #e5e5e5;">'
                '<div style="margin-bottom: 10px; font-weight: 700;">'
                'Direct Link to Lead:</div>'
                '<a href="%s" style="display: inline-block; '
                'background-color: #714b67; color: #ffffff; '
                'padding: 11px 20px; text-decoration: none; '
                'border-radius: 5px; font-weight: 600;">'
                'View Opportunity</a></div>'
                % escape(opportunity_url)
            )

        organized_message_html = Markup("".join(html_parts))
        return Markup(
            '<div style="font-family: Arial, Helvetica, sans-serif; '
            'font-size: 14px; line-height: 1.6; color: #333333; '
            'max-width: 680px; margin: 0; padding: 0;">{message}</div>'
        ).format(message=organized_message_html)

    def action_send_mail(self):
        self.ensure_one()
        lead = self.lead_id.exists()
        if not lead:
            raise UserError(_("The opportunity no longer exists."))

        email_to = (self.email_to or "").strip()
        subject = (self.subject or "").strip()
        message_body = (self.message_body or "").strip()

        if not subject:
            raise UserError(_("Please enter an email subject."))
        if not message_body:
            raise UserError(_("Please enter an email message."))

        self._get_recipient_user()
        opportunity_url = self._build_opportunity_url()
        email_body = self._build_email_body(opportunity_url)

        sender_user = self.env.user
        sender_email = (sender_user.email or "").strip()
        if not sender_email:
            raise UserError(
                _("Your Odoo user does not have an email address configured.")
            )

        email_from = formataddr((sender_user.name or "", sender_email))

        mail = self.env["mail.mail"].sudo().create({
            "subject": subject,
            "body_html": email_body,
            "email_to": email_to,
            "email_from": email_from,
            "model": "crm.lead",
            "res_id": lead.id,
        })
        mail.send()

        chatter_message_html = Markup(
            str(escape(message_body)).replace("\n", "<br/>")
        )
        log_body = Markup(
            "<p><strong>Email sent</strong></p>"
            "<p><strong>To:</strong> {email_to}</p>"
            "<p><strong>Subject:</strong> {subject}</p>"
            "<div>{message_body}</div>"
        ).format(
            email_to=escape(email_to),
            subject=escape(subject),
            message_body=chatter_message_html,
        )

        lead.sudo().message_post(
            body=log_body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

        return {"type": "ir.actions.act_window_close"}
