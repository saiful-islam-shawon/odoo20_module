import json
from urllib.parse import urlencode

from markupsafe import escape

from odoo import fields, http
from odoo.fields import Command
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError
from werkzeug.exceptions import BadRequest, Forbidden


class ZaintagroSalesPortal(http.Controller):
    GROUP_XMLID = "zencore_zaintagro_sales_portal.group_sales_portal_access"

    def _check_access(self):
        user = request.env.user
        if not user.has_group(self.GROUP_XMLID) and not user.has_group("base.group_system"):
            raise Forbidden("You do not have permission to access this Sales page.")

    @staticmethod
    def _int(value):
        try:
            return int(value) if value not in (None, "", False) else False
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _float(value, default=0.0):
        try:
            return float(value) if value not in (None, "", False) else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _bool(value):
        return str(value).lower() in {"1", "true", "on", "yes"}

    @staticmethod
    def _normalize_datetime(value):
        """Convert an HTML datetime-local value to Odoo's server datetime format."""
        if value in (None, "", False):
            return False
        text = str(value).strip()
        try:
            # Browsers submit datetime-local as YYYY-MM-DDTHH:MM[:SS].
            # Odoo fields.Datetime expects the canonical server format.
            parsed = fields.Datetime.to_datetime(text.replace("T", " "))
        except (TypeError, ValueError):
            raise ValidationError("Invalid date/time value.")
        return fields.Datetime.to_string(parsed)


    @staticmethod
    def _run_onchanges(record, field_names):
        """Run the model's real @api.onchange handlers on an in-memory record.

        This lets the website form reuse Odoo's own Sales onchange business logic
        instead of duplicating it in JavaScript.
        """
        for field_name in field_names:
            if field_name not in record._fields:
                continue
            for method in record._onchange_methods.get(field_name, ()):
                method(record)
        return record

    def _company_ids(self):
        return request.env.user.company_ids.ids or [request.env.company.id]

    def _scoped_search_config(self, kind):
        company_id = request.env.company.id
        company_ids = self._company_ids()
        sale_group = request.env.ref("sales_team.group_sale_salesman", raise_if_not_found=False)
        sale_group_id = sale_group.id if sale_group else False
        configs = {
            "customer": ("res.partner", [("active", "=", True), "|", ("company_id", "=", False), ("company_id", "in", company_ids)]),
            "payment_term": ("account.payment.term", ["|", ("company_id", "=", False), ("company_id", "=", company_id)]),
            "salesperson": ("res.users", [("active", "=", True), ("share", "=", False), ("company_ids", "in", company_ids)] + ([("all_group_ids", "in", sale_group_id)] if sale_group_id else [])),
            "team": ("crm.team", ["|", ("company_id", "=", False), ("company_id", "=", company_id)]),
            "template": ("sale.order.template", [("template_type", "=", "quotation"), "|", ("company_id", "=", False), ("company_id", "=", company_id)]),
            "tag": ("crm.tag", []),
            "fiscal_position": ("account.fiscal.position", ["|", ("company_id", "=", False), ("company_id", "=", company_id)]),
            "payment_method": ("account.payment.method.line", [("payment_type", "=", "inbound"), ("company_id", "=", company_id)]),
            "journal": ("account.journal", [("type", "=", "sale"), ("company_id", "=", company_id)]),
            "incoterm": ("account.incoterms", []),
            "warehouse": ("stock.warehouse", [("company_id", "=", company_id), ("active", "=", True)]),
            "opportunity": ("crm.lead", [("type", "=", "opportunity"), "|", ("company_id", "=", False), ("company_id", "=", company_id)]),
            "campaign": ("utm.campaign", []),
            "medium": ("utm.medium", []),
            "source": ("utm.source", []),
            "product": ("product.product", [("sale_ok", "=", True), ("active", "=", True), "|", ("company_id", "=", False), ("company_id", "=", company_id)]),
            "tax": ("account.tax", [("type_tax_use", "=", "sale"), ("active", "=", True), "|", ("company_id", "=", False), ("company_id", "=", company_id)]),
        }
        if kind not in configs:
            raise BadRequest("Unsupported search type")
        return configs[kind]

    def _validate_id(self, kind, record_id):
        record_id = self._int(record_id)
        if not record_id:
            return False
        model_name, domain = self._scoped_search_config(kind)
        record = request.env[model_name].sudo().search(domain + [("id", "=", record_id)], limit=1)
        return record.id or False

    def _search_records(self, kind, term="", limit=12):
        self._check_access()
        model_name, domain = self._scoped_search_config(kind)
        limit = min(max(self._int(limit) or 12, 1), 60)
        fetch_limit = min(limit + 1, 61)
        model = request.env[model_name].sudo()
        pairs = model.name_search(name=(term or "").strip(), domain=domain, operator="ilike", limit=fetch_limit)
        has_more = len(pairs) > limit
        pairs = pairs[:limit]
        ids = [record_id for record_id, _ in pairs]
        records = {record.id: record for record in model.browse(ids).exists()}
        items = []
        for record_id, display_name in pairs:
            record = records.get(record_id)
            if not record:
                continue
            item = {"id": record_id, "name": display_name}
            if kind == "customer":
                item["secondary"] = record.email or record.phone or record.contact_address or ""
            elif kind == "salesperson":
                item["secondary"] = record.login or ""
            elif kind == "product":
                item.update({
                    "secondary": record.default_code or record.product_tmpl_id.name or "",
                    "default_code": record.default_code or "",
                })
            elif kind == "tax":
                item["secondary"] = record.description or ""
            items.append(item)
        return {"items": items, "has_more": has_more}

    def _m2o_payload(self, record):
        return {"id": record.id, "name": record.display_name} if record else {"id": False, "name": ""}

    def _order_base_vals(self, data):
        vals = {"company_id": request.env.company.id}
        partner_id = self._validate_id("customer", data.get("partner_id"))
        if partner_id:
            vals["partner_id"] = partner_id

        field_map = {
            "payment_term_id": "payment_term",
            "user_id": "salesperson",
            "team_id": "team",
            "sale_order_template_id": "template",
            "fiscal_position_id": "fiscal_position",
            "preferred_payment_method_line_id": "payment_method",
            "journal_id": "journal",
            "incoterm": "incoterm",
            "warehouse_id": "warehouse",
            "opportunity_id": "opportunity",
            "campaign_id": "campaign",
            "medium_id": "medium",
            "source_id": "source",
        }
        SaleOrder = request.env["sale.order"]
        for field_name, kind in field_map.items():
            if field_name in SaleOrder._fields:
                record_id = self._validate_id(kind, data.get(field_name))
                if record_id:
                    vals[field_name] = record_id

        if data.get("date_order"):
            vals["date_order"] = self._normalize_datetime(data["date_order"])
        if data.get("validity_date"):
            vals["validity_date"] = data["validity_date"]
        if data.get("commitment_date") and "commitment_date" in SaleOrder._fields:
            vals["commitment_date"] = self._normalize_datetime(data["commitment_date"])
        if data.get("document_tax_mode") in {"tax_excluded", "tax_included"}:
            vals["document_tax_mode"] = data["document_tax_mode"]
        if data.get("picking_policy") in {"direct", "one"} and "picking_policy" in SaleOrder._fields:
            vals["picking_policy"] = data["picking_policy"]
        return vals

    def _line_vals_from_payload(self, line, validate=True):
        display_type = line.get("display_type") or False
        name = (line.get("name") or "").strip()
        if display_type in {"line_section", "line_subsection", "line_note"}:
            return {"display_type": display_type, "name": name or ("Section" if display_type == "line_section" else "Note")}

        product_id = self._validate_id("product", line.get("product_id")) if validate else self._int(line.get("product_id"))
        if not product_id:
            if validate:
                raise ValidationError("Every normal order line must have a valid product.")
            return False
        vals = {
            "product_id": product_id,
            "product_uom_qty": max(self._float(line.get("qty"), 1.0), 0.0),
        }
        if name:
            vals["name"] = name

        # Rebuild the transient line with the same price state as the Odoo web client.
        # `price_unit` is the value the user sees; `technical_price_unit` is Odoo's
        # reference price used to tell a normal computed price from a manual override.
        # Keeping both is critical when only `document_tax_mode` changes: Odoo 20 keeps
        # Unit Price unchanged and recomputes subtotal/tax/total from the same price.
        if line.get("price_state_ready") and line.get("price_unit") not in (None, ""):
            vals["price_unit"] = self._float(line.get("price_unit"), 0.0)
            if "technical_price_unit" in request.env["sale.order.line"]._fields:
                vals["technical_price_unit"] = self._float(
                    line.get("technical_price_unit"), vals["price_unit"]
                )
        elif line.get("manual_price") and line.get("price_unit") not in (None, ""):
            vals["price_unit"] = self._float(line.get("price_unit"), 0.0)
        tax_ids = []
        for raw in line.get("tax_ids") or []:
            tax_id = self._validate_id("tax", raw) if validate else self._int(raw)
            if tax_id:
                tax_ids.append(tax_id)
        if line.get("manual_taxes"):
            vals["tax_ids"] = [Command.set(tax_ids)]

        SaleOrderLine = request.env["sale.order.line"]
        if line.get("manual_lead_time") and "customer_lead" in SaleOrderLine._fields:
            vals["customer_lead"] = max(self._int(line.get("lead_time")) or 0, 0)
        if line.get("manual_unit_cost") and "purchase_price" in SaleOrderLine._fields:
            vals["purchase_price"] = max(self._float(line.get("unit_cost"), 0.0), 0.0)
        return vals

    def _apply_manual_line_overrides(self, record, payload):
        """Re-apply line values that are editable in the native quotation line.

        Product onchanges are intentionally executed first so Odoo can compute its normal
        defaults (taxes, lead time, cost, price, etc.).  User overrides are then applied
        only to this transient/order line, matching the backend form behaviour without
        mutating the product master record.
        """
        if payload.get("manual_price") and payload.get("price_unit") not in (None, ""):
            record.price_unit = self._float(payload.get("price_unit"), 0.0)

        if payload.get("manual_taxes"):
            tax_ids = []
            for raw in payload.get("tax_ids") or []:
                tax_id = self._validate_id("tax", raw)
                if tax_id:
                    tax_ids.append(tax_id)
            record.tax_ids = [Command.set(tax_ids)]
            self._run_onchanges(record, ["tax_ids"])

        if payload.get("manual_lead_time") and "customer_lead" in record._fields:
            record.customer_lead = max(self._int(payload.get("lead_time")) or 0, 0)

        if payload.get("manual_unit_cost") and "purchase_price" in record._fields:
            record.purchase_price = max(self._float(payload.get("unit_cost"), 0.0), 0.0)

        # sale_margin exposes Margin and Margin (%) as editable computed fields with
        # native onchange methods. Reuse those onchanges so editing either value adjusts
        # Unit Price exactly like the Odoo 20 quotation line, without custom formulas.
        if payload.get("manual_margin") and "margin" in record._fields:
            record.margin = self._float(payload.get("margin"), 0.0)
            self._run_onchanges(record, ["margin"])
        elif payload.get("manual_margin_percent") and "margin_percent" in record._fields:
            record.margin_percent = self._float(payload.get("margin_percent"), 0.0) / 100.0
            self._run_onchanges(record, ["margin_percent"])

        return record

    def _serialize_line(self, line):
        if line.display_type:
            return {
                "display_type": line.display_type,
                "name": line.name or "",
                "product_id": False,
                "product_name": "",
                "product_template_name": "",
                "product_variant_name": "",
                "qty": 0,
                "price_unit": 0,
                "tax_ids": [],
                "taxes": [],
                "lead_time": 0,
                "unit_cost": 0,
                "margin": 0,
                "margin_percent": 0,
                "subtotal": 0,
                "tax_amount": 0,
                "total": 0,
            }

        # Keep this payload sourced from the actual Odoo sale.order.line record.  The
        # website only renders these values; it does not reproduce tax/margin formulas.
        product_template = getattr(line, "product_template_id", False) or line.product_id.product_tmpl_id
        unit_cost = getattr(line, "purchase_price", 0.0) if "purchase_price" in line._fields else 0.0
        margin = getattr(line, "margin", 0.0) if "margin" in line._fields else 0.0
        if "margin_percent" in line._fields:
            # Odoo stores margin_percent as a ratio (0.50 == 50%).  The website
            # displays the same human percentage as the backend percentage widget.
            margin_percent = (line.margin_percent or 0.0) * 100.0
        else:
            # Fallback only for databases where the dedicated margin-percent field is absent.
            # Margin itself still comes from Odoo's sale_margin computation when installed.
            margin_percent = (margin / line.price_subtotal * 100.0) if line.price_subtotal else 0.0

        return {
            "display_type": False,
            "name": line.name or "",
            "product_id": line.product_id.id,
            "product_name": line.product_id.display_name,
            "product_template_name": product_template.display_name if product_template else "",
            "product_variant_name": line.product_id.display_name or "",
            "qty": line.product_uom_qty,
            "price_unit": line.price_unit,
            "technical_price_unit": (
                line.technical_price_unit
                if "technical_price_unit" in line._fields
                else line.price_unit
            ),
            "tax_ids": line.tax_ids.ids,
            "taxes": [{"id": tax.id, "name": tax.display_name} for tax in line.tax_ids],
            "lead_time": line.customer_lead if "customer_lead" in line._fields else 0,
            "unit_cost": unit_cost,
            "margin": margin,
            "margin_percent": margin_percent,
            "subtotal": line.price_subtotal,
            "tax_amount": line.price_tax,
            "total": line.price_total,
        }

    def _order_defaults_payload(self, order):
        fields_to_m2o = {
            "payment_term_id": "payment_term",
            "user_id": "salesperson",
            "team_id": "team",
            "sale_order_template_id": "template",
            "fiscal_position_id": "fiscal_position",
            "preferred_payment_method_line_id": "payment_method",
            "journal_id": "journal",
            "incoterm": "incoterm",
            "warehouse_id": "warehouse",
            "opportunity_id": "opportunity",
            "campaign_id": "campaign",
            "medium_id": "medium",
            "source_id": "source",
        }
        result = {
            "currency_symbol": order.currency_id.symbol or "",
            "currency_position": order.currency_id.position or "after",
            "document_tax_mode": order.document_tax_mode or "tax_excluded",
            "require_signature": bool(order.require_signature),
            "prepayment_percent": (order.prepayment_percent or 0.0) * 100.0,
            "validity_date": fields.Date.to_string(order.validity_date) if order.validity_date else "",
            "note": str(order.note or ""),
        }
        for field_name in fields_to_m2o:
            if field_name in order._fields:
                result[field_name] = self._m2o_payload(order[field_name])
        if "picking_policy" in order._fields:
            result["picking_policy"] = order.picking_policy or "direct"
        if "incoterm_location" in order._fields:
            result["incoterm_location"] = order.incoterm_location or ""
        return result

    def _build_preview_order(self, order_data, line_payloads):
        """Build one unsaved Odoo 20 quotation and let native Sales computes do all math.

        The website never reproduces pricing/tax/margin formulas.  The transient
        ``sale.order`` receives the document-level context first, then every
        ``sale.order.line`` is created under that order.  Product defaults and
        Odoo's native product onchange run before line-only manual overrides.
        Reading the computed fields afterwards triggers the exact model computes
        used by the backend quotation form (price_subtotal/price_tax/price_total,
        amount_untaxed/amount_tax/amount_total and tax_totals).
        """
        order_vals = self._order_base_vals(order_data)
        commands = []
        normalized_payloads = []
        for payload in line_payloads:
            line_vals = self._line_vals_from_payload(payload, validate=True)
            if line_vals:
                commands.append(Command.create(line_vals))
                normalized_payloads.append(payload)
        order_vals["order_line"] = commands

        SaleOrder = request.env["sale.order"].sudo().with_company(request.env.company)
        order = SaleOrder.new(order_vals)

        # The standard backend form runs the product onchange when a product/variant
        # is chosen.  Reuse that method where available; it calls Odoo 20's
        # _reset_price_unit(), which respects pricelist, fiscal position and
        # document_tax_mode.  Computed fields such as tax_ids/customer_lead/name
        # are still model computes, not custom portal formulas.
        records = list(order.order_line)
        for record, payload in zip(records, normalized_payloads):
            if record.display_type:
                continue

            # A newly selected product has no prior price state, so reproduce the native
            # product onchange once to establish Odoo's price/technical price.  For an
            # existing line we must NOT run that onchange on every preview: in Odoo 20,
            # changing document_tax_mode does not depend-trigger _compute_price_unit and
            # therefore the displayed Unit Price stays unchanged.
            if not payload.get("price_state_ready"):
                if record.product_id and hasattr(record, "_onchange_product_id"):
                    record._onchange_product_id()
            elif payload.get("recompute_price") and not payload.get("manual_price"):
                # Quantity/pricelist-style changes do legitimately recompute the native
                # product price.  Force only Odoo's own price compute, preserving its
                # technical/manual-price semantics.
                record.with_context(force_price_recomputation=True)._compute_price_unit()

            self._apply_manual_line_overrides(record, payload)

        # Accessing these model fields deliberately forces native computes on NewId
        # records.  No database row is created by this preview.
        for line in order.order_line:
            if not line.display_type:
                _ = (line.price_subtotal, line.price_tax, line.price_total)
                if "margin" in line._fields:
                    _ = line.margin
                if "margin_percent" in line._fields:
                    _ = line.margin_percent
        _ = (order.amount_untaxed, order.amount_tax, order.amount_total)
        if "tax_totals" in order._fields:
            _ = order.tax_totals
        return order

    @http.route("/zaintagro/sales", type="http", auth="user", website=True, sitemap=False)
    def sales_page(self, **kwargs):
        self._check_access()
        SaleOrder = request.env["sale.order"].sudo().with_company(request.env.company)
        order = SaleOrder.new({"company_id": request.env.company.id})
        values = {
            "today": fields.Date.context_today(order),
            "now": fields.Datetime.now(),
            "now_input": fields.Datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "defaults": self._order_defaults_payload(order),
            "success": kwargs.get("success"),
            "error": kwargs.get("error"),
            "created_name": kwargs.get("created_name"),
        }
        return request.render("zencore_zaintagro_sales_portal.sales_quotation_page", values)

    @http.route("/zaintagro/sales/search", type="http", auth="user", website=True, methods=["GET"], csrf=False, readonly=True, sitemap=False)
    def sales_search(self, kind="", term="", limit=12, **kwargs):
        return request.make_json_response(self._search_records(kind, term, limit))

    @http.route("/zaintagro/sales/customer-defaults", type="http", auth="user", website=True, methods=["POST"], csrf=True, sitemap=False)
    def customer_defaults(self, **post):
        self._check_access()
        partner_id = self._validate_id("customer", post.get("partner_id"))
        if not partner_id:
            return request.make_json_response({"ok": False, "message": "Please select a valid customer."})
        SaleOrder = request.env["sale.order"].sudo().with_company(request.env.company)
        order = SaleOrder.new({"company_id": request.env.company.id, "partner_id": partner_id})
        self._run_onchanges(order, ["company_id", "partner_id"])
        payload = self._order_defaults_payload(order)
        payload.update({
            "ok": True,
            "partner_invoice_id": self._m2o_payload(order.partner_invoice_id),
            "partner_shipping_id": self._m2o_payload(order.partner_shipping_id),
        })
        return request.make_json_response(payload)

    @http.route("/zaintagro/sales/order-onchange", type="http", auth="user", website=True, methods=["POST"], csrf=True, sitemap=False)
    def order_onchange(self, **post):
        self._check_access()
        try:
            order_data = json.loads(post.get("order") or "{}")
        except json.JSONDecodeError:
            raise BadRequest("Invalid order payload")
        changed_field = (post.get("field") or "").strip()
        allowed_changed = {
            "partner_id", "payment_term_id", "user_id", "team_id",
            "sale_order_template_id", "fiscal_position_id",
            "preferred_payment_method_line_id", "journal_id", "incoterm",
            "warehouse_id", "opportunity_id", "campaign_id", "medium_id",
            "source_id", "document_tax_mode", "picking_policy",
        }
        if changed_field not in allowed_changed:
            raise BadRequest("Unsupported onchange field")
        SaleOrder = request.env["sale.order"].sudo().with_company(request.env.company)
        vals = self._order_base_vals(order_data)
        order = SaleOrder.new(vals)
        self._run_onchanges(order, [changed_field])
        payload = self._order_defaults_payload(order)
        payload["ok"] = True
        return request.make_json_response(payload)

    @http.route("/zaintagro/sales/template-defaults", type="http", auth="user", website=True, methods=["POST"], csrf=True, sitemap=False)
    def template_defaults(self, **post):
        self._check_access()
        partner_id = self._validate_id("customer", post.get("partner_id"))
        template_id = self._validate_id("template", post.get("template_id"))
        if not template_id:
            return request.make_json_response({"ok": False, "message": "Please select a valid quotation template."})
        vals = {"company_id": request.env.company.id, "sale_order_template_id": template_id}
        if partner_id:
            vals["partner_id"] = partner_id
        SaleOrder = request.env["sale.order"].sudo().with_company(request.env.company)
        order = SaleOrder.new(vals)
        self._run_onchanges(order, ["company_id", "partner_id", "sale_order_template_id"])
        if hasattr(order, "_onchange_sale_order_template_id"):
            order._onchange_sale_order_template_id()
        payload = self._order_defaults_payload(order)
        payload.update({
            "ok": True,
            "lines": [self._serialize_line(line) for line in order.order_line],
            "amount_untaxed": order.amount_untaxed,
            "amount_tax": order.amount_tax,
            "amount_total": order.amount_total,
        })
        return request.make_json_response(payload)

    @http.route("/zaintagro/sales/line-preview", type="http", auth="user", website=True, methods=["POST"], csrf=True, sitemap=False)
    def line_preview(self, **post):
        self._check_access()
        try:
            order_data = json.loads(post.get("order") or "{}")
            line_data = json.loads(post.get("line") or "{}")
        except json.JSONDecodeError:
            raise BadRequest("Invalid preview payload")
        order = self._build_preview_order(order_data, [line_data])
        line = order.order_line[:1]
        if not line:
            return request.make_json_response({"ok": False, "message": "Unable to compute order line."})
        result = self._serialize_line(line)
        result.update({
            "ok": True,
            "currency_symbol": order.currency_id.symbol or "",
            "currency_position": order.currency_id.position or "after",
        })
        return request.make_json_response(result)

    @http.route("/zaintagro/sales/totals-preview", type="http", auth="user", website=True, methods=["POST"], csrf=True, sitemap=False)
    def totals_preview(self, **post):
        self._check_access()
        try:
            order_data = json.loads(post.get("order") or "{}")
            lines = json.loads(post.get("lines") or "[]")
        except json.JSONDecodeError:
            raise BadRequest("Invalid totals payload")

        order = self._build_preview_order(order_data, lines)
        tax_totals = order.tax_totals if "tax_totals" in order._fields else {}
        if not isinstance(tax_totals, dict):
            tax_totals = {}
        return request.make_json_response({
            "ok": True,
            # Every row and every total comes from the *same* transient sale.order.
            # This is essential for Odoo 20 document-level Tax Excl./Tax Incl. mode:
            # each line keeps its own taxes while the order aggregates native results.
            "lines": [self._serialize_line(line) for line in order.order_line],
            "document_tax_mode": order.document_tax_mode or "tax_excluded",
            "amount_untaxed": order.amount_untaxed,
            "amount_tax": order.amount_tax,
            "amount_total": order.amount_total,
            "tax_totals": tax_totals,
            "currency_symbol": order.currency_id.symbol or "",
            "currency_position": order.currency_id.position or "after",
        })

    @http.route("/zaintagro/sales/quotation/create", type="http", auth="user", website=True, methods=["POST"], csrf=True, sitemap=False)
    def create_quotation(self, **post):
        self._check_access()
        try:
            lines = json.loads(post.get("lines_json") or "[]")
        except json.JSONDecodeError:
            lines = []
        partner_id = self._validate_id("customer", post.get("partner_id"))
        if not partner_id:
            params = urlencode({"error": "A valid Customer is required."})
            return request.redirect(f"/zaintagro/sales?{params}")
        if not lines:
            params = urlencode({"error": "Add at least one quotation line."})
            return request.redirect(f"/zaintagro/sales?{params}")

        SaleOrder = request.env["sale.order"].sudo().with_company(request.env.company)
        vals = self._order_base_vals({**post, "partner_id": partner_id})
        vals.update({
            "partner_id": partner_id,
            "client_order_ref": (post.get("client_order_ref") or "").strip() or False,
            "origin": (post.get("origin") or "").strip() or False,
            "note": post.get("note") or False,
            "require_signature": self._bool(post.get("require_signature")),
            # Odoo 20 stores this field as a ratio (0.50 == 50%).
            "prepayment_percent": max(0.0, min(self._float(post.get("prepayment_percent"), 0.0), 100.0)) / 100.0,
        })
        if "incoterm_location" in SaleOrder._fields:
            vals["incoterm_location"] = (post.get("incoterm_location") or "").strip() or False

        tag_ids = []
        for raw in (post.get("tag_ids") or "").split(","):
            tag_id = self._validate_id("tag", raw)
            if tag_id:
                tag_ids.append(tag_id)
        if "tag_ids" in SaleOrder._fields:
            vals["tag_ids"] = [Command.set(tag_ids)]

        commands = []
        try:
            # Compute one final transient quotation before create.  This is not a
            # second/custom formula: it is the same Odoo 20 sale.order/sale.order.line
            # engine used by the live preview.  It is especially important for the
            # editable Margin / Margin (%) fields because Odoo's native onchange turns
            # those edits into a Unit Price; only that resulting line price needs to be
            # persisted on the real quotation.
            preview_order = self._build_preview_order({**post, "partner_id": partner_id}, lines)
            preview_records = list(preview_order.order_line)

            for payload, preview_line in zip(lines, preview_records):
                line_vals = self._line_vals_from_payload(payload, validate=True)
                if not line_vals:
                    continue
                if (
                    not preview_line.display_type
                    and (payload.get("manual_margin") or payload.get("manual_margin_percent"))
                ):
                    line_vals["price_unit"] = preview_line.price_unit
                commands.append(Command.create(line_vals))
            vals["order_line"] = commands
            order = SaleOrder.create(vals)
        except (ValidationError, UserError, AccessError) as exc:
            params = urlencode({"error": str(exc)})
            return request.redirect(f"/zaintagro/sales?{params}")

        params = urlencode({"success": "1", "created_name": order.name})
        return request.redirect(f"/zaintagro/sales?{params}")
