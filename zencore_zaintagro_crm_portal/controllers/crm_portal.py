from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden, BadRequest
from urllib.parse import urlencode
from odoo.exceptions import UserError, ValidationError


class ZaintagroCrmPortal(http.Controller):
    GROUP_XMLID = "zencore_zaintagro_crm_portal.group_crm_portal_access"

    def _check_access(self):
        user = request.env.user
        if not user.has_group(self.GROUP_XMLID) and not user.has_group("base.group_system"):
            raise Forbidden("You do not have permission to access this CRM page.")

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

    def _allowed_company_ids(self):
        return request.env.user.company_ids.ids or [request.env.company.id]

    def _search_records(self, kind, term="", country_id=False, limit=12):
        """Return a tightly-scoped, Many2one-like search result.

        The public page never receives a generic model name/domain from the
        browser.  Each supported field is explicitly mapped here and searched
        with Odoo's ``name_search`` so matching behaves close to native
        relational fields.
        """
        self._check_access()
        term = (term or "").strip()
        limit = min(max(self._int(limit) or 12, 1), 50)
        fetch_limit = min(limit + 1, 51)
        env = request.env
        company_ids = self._allowed_company_ids()

        mapping = {
            "partner": (
                "res.partner",
                [("active", "=", True), "|", ("company_id", "=", False), ("company_id", "in", company_ids)],
            ),
            "user": (
                "res.users",
                [("active", "=", True), ("share", "=", False), ("company_ids", "in", company_ids)],
            ),
            "tag": ("crm.tag", []),
            "campaign": ("utm.campaign", []),
            "medium": ("utm.medium", []),
            "source": ("utm.source", []),
            "team": (
                "crm.team",
                [("use_opportunities", "=", True), "|", ("company_id", "=", False), ("company_id", "in", company_ids)],
            ),
            "country": ("res.country", []),
            "state": ("res.country.state", []),
            "assigned_partner": (
                "res.partner",
                [("active", "=", True), ("grade_id", "!=", False), "|", ("company_id", "=", False), ("company_id", "in", company_ids)],
            ),
        }
        if kind not in mapping:
            raise BadRequest("Unsupported search type")

        model_name, domain = mapping[kind]
        domain = list(domain)
        if kind == "state":
            country_id = self._int(country_id)
            if country_id:
                domain.append(("country_id", "=", country_id))

        model = env[model_name].sudo()
        pairs = model.name_search(name=term, domain=domain, operator="ilike", limit=fetch_limit)
        has_more = len(pairs) > limit
        pairs = pairs[:limit]
        ids = [record_id for record_id, _display_name in pairs]
        records = {record.id: record for record in model.browse(ids).exists()}

        items = []
        for record_id, display_name in pairs:
            record = records.get(record_id)
            if not record:
                continue
            item = {"id": record_id, "name": display_name}
            if kind == "partner":
                # Return the same contact details that the CRM form uses to
                # prefill lead/opportunity contact information.  These values
                # are only used to prefill the website form; selecting a contact
                # never writes back to res.partner.
                commercial = record.commercial_partner_id
                company_name = ""
                if record.is_company:
                    company_name = record.name or ""
                elif record.parent_id:
                    company_name = record.parent_id.name or ""

                item.update({
                    "email": record.email or "",
                    "phone": record.phone or "",
                    "partner_name": company_name,
                    "contact_name": "" if record.is_company else (record.name or ""),
                    "function": record.function or "",
                    "website": record.website or commercial.website or "",
                    "street": record.street or "",
                    "street2": record.street2 or "",
                    "city": record.city or "",
                    "zip": record.zip or "",
                    "state_id": record.state_id.id or False,
                    "state_name": record.state_id.display_name or "",
                    "country_id": record.country_id.id or False,
                    "country_name": record.country_id.name or "",
                    "secondary": record.email or record.phone or record.contact_address or "",
                })
            elif kind == "user":
                item["secondary"] = record.login or ""
            elif kind == "state":
                item["secondary"] = record.country_id.name or ""
            items.append(item)
        return {"items": items, "has_more": has_more}

    def _validate_id(self, kind, record_id):
        if not record_id:
            return False
        payload = self._search_records(kind, term="", limit=50)
        if any(item["id"] == record_id for item in payload["items"]):
            return record_id
        # For large datasets, verify using an exact-name-independent scoped search.
        company_ids = self._allowed_company_ids()
        env = request.env
        mapping = {
            "partner": ("res.partner", [("active", "=", True), "|", ("company_id", "=", False), ("company_id", "in", company_ids)]),
            "user": ("res.users", [("active", "=", True), ("share", "=", False), ("company_ids", "in", company_ids)]),
            "tag": ("crm.tag", []),
            "campaign": ("utm.campaign", []),
            "medium": ("utm.medium", []),
            "source": ("utm.source", []),
            "team": ("crm.team", [("use_opportunities", "=", True), "|", ("company_id", "=", False), ("company_id", "in", company_ids)]),
            "country": ("res.country", []),
            "state": ("res.country.state", []),
            "assigned_partner": ("res.partner", [("active", "=", True), ("grade_id", "!=", False), "|", ("company_id", "=", False), ("company_id", "in", company_ids)]),
        }
        model_name, domain = mapping[kind]
        return record_id if env[model_name].sudo().search_count(domain + [("id", "=", record_id)], limit=1) else False

    @http.route("/zaintagro/crm", type="http", auth="user", website=True, sitemap=False)
    def crm_page(self, **kwargs):
        self._check_access()
        user = request.env.user
        values = {
            "default_user_id": False if user.share else user.id,
            "default_user_name": "" if user.share else user.name,
        }
        return request.render("zencore_zaintagro_crm_portal.crm_opportunity_page", values)

    @http.route(
        "/zaintagro/crm/search",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
        readonly=True,
        sitemap=False,
    )
    def crm_search(self, kind="", term="", country_id=False, limit=12, **kwargs):
        payload = self._search_records(
            kind,
            term=term,
            country_id=country_id,
            limit=limit,
        )
        return request.make_json_response(payload)


    @http.route(
        "/zaintagro/crm/geolocate",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def crm_geolocate(self, **post):
        """Geolocate the form address with Odoo's native geocoder.

        This deliberately reuses ``base_geolocalize`` through
        ``res.partner._geo_localize``; no browser-side geocoding provider or
        API credential is exposed.
        """
        self._check_access()

        country_id = self._validate_id("country", self._int(post.get("country_id")))
        state_id = self._validate_id("state", self._int(post.get("state_id")))
        if not country_id:
            return request.make_json_response({
                "ok": False,
                "message": "Please select a country before automatic assignment.",
            })

        country = request.env["res.country"].sudo().browse(country_id).exists()
        state = request.env["res.country.state"].sudo().browse(state_id).exists() if state_id else request.env["res.country.state"]
        if state and state.country_id.id != country.id:
            return request.make_json_response({
                "ok": False,
                "message": "The selected state does not belong to the selected country.",
            })

        result = request.env["res.partner"].sudo().with_context(lang="en_US")._geo_localize(
            street=(post.get("street") or "").strip(),
            zip=(post.get("zip") or "").strip(),
            city=(post.get("city") or "").strip(),
            state=state.name if state else "",
            country=country.name,
        )
        if not result:
            return request.make_json_response({
                "ok": False,
                "message": "Odoo could not find coordinates for this address. Please verify the address and Geolocation configuration.",
            })

        return request.make_json_response({
            "ok": True,
            "latitude": result[0],
            "longitude": result[1],
            "message": "Address geolocated. Automatic partner assignment will run when you save the opportunity.",
        })

    def _fallback_no_partner_tag(self):
        """Return the fallback tag used when the user selects no tags."""
        Tag = request.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", "No more partner available")], limit=1)
        if not tag:
            tag = Tag.create({"name": "No more partner available"})
        return tag

    @http.route(
        "/zaintagro/crm/opportunity/create",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def create_opportunity(self, **post):
        self._check_access()
        name = (post.get("name") or "").strip()
        if not name:
            raise BadRequest("Opportunity title is required.")

        partner_id = self._validate_id("partner", self._int(post.get("partner_id")))
        partner = request.env["res.partner"].sudo().browse(partner_id).exists() if partner_id else request.env["res.partner"]

        user_id = self._validate_id("user", self._int(post.get("user_id")))
        team_id = self._validate_id("team", self._int(post.get("team_id")))
        company_id = request.env.company.id
        campaign_id = self._validate_id("campaign", self._int(post.get("campaign_id")))
        medium_id = self._validate_id("medium", self._int(post.get("medium_id")))
        source_id = self._validate_id("source", self._int(post.get("source_id")))
        country_id = self._validate_id("country", self._int(post.get("country_id")))
        state_id = self._validate_id("state", self._int(post.get("state_id")))
        if state_id and country_id:
            state = request.env["res.country.state"].sudo().browse(state_id).exists()
            if not state or state.country_id.id != country_id:
                state_id = False
        assigned_partner_id = self._validate_id("assigned_partner", self._int(post.get("partner_assigned_id")))

        tag_ids = []
        for raw in (post.get("tag_ids") or "").split(","):
            tag_id = self._int(raw.strip())
            if tag_id and self._validate_id("tag", tag_id):
                tag_ids.append(tag_id)

        priority = post.get("priority") if post.get("priority") in {"0", "1", "2", "3"} else "0"
        expected_revenue = max(self._float(post.get("expected_revenue"), 0.0), 0.0)
        vals = {
            "type": "opportunity",
            "name": name,
            "expected_revenue": expected_revenue,
            "partner_id": partner_id,
            "user_id": user_id,
            "team_id": team_id,
            "date_deadline": post.get("date_deadline") or False,
            "priority": priority,
            "tag_ids": [(6, 0, tag_ids)],
            "description": post.get("description") or False,
            "partner_name": (post.get("partner_name") or "").strip() or False,
            "street": (post.get("street") or "").strip() or False,
            "street2": (post.get("street2") or "").strip() or False,
            "city": (post.get("city") or "").strip() or False,
            "state_id": state_id,
            "zip": (post.get("zip") or "").strip() or False,
            "country_id": country_id,
            "contact_name": (post.get("contact_name") or "").strip() or False,
            "function": (post.get("function") or "").strip() or False,
            "website": (post.get("website") or "").strip() or False,
            "campaign_id": campaign_id,
            "medium_id": medium_id,
            "source_id": source_id,
            "referred": (post.get("referred") or "").strip() or False,
            "company_id": company_id,
            "partner_latitude": self._float(post.get("partner_latitude"), 0.0),
            "partner_longitude": self._float(post.get("partner_longitude"), 0.0),
            "partner_assigned_id": assigned_partner_id,
        }

        # Contact selection is only a prefill/link operation.  The website form
        # values are saved on the opportunity itself, even when the selected
        # contact has those fields empty or the user edits the prefilled values.
        # We intentionally never write these values back to res.partner.
        vals.update({
            "email_from": (post.get("email_from") or "").strip() or False,
            "phone": (post.get("phone") or "").strip() or False,
        })


        # sudo is deliberately scoped to the single create operation because portal
        # users do not have generic CRM ACLs. Inputs above are explicitly allowlisted
        # and relational IDs are revalidated server-side.
        try:
            lead = request.env["crm.lead"].sudo().with_company(company_id).create(vals)

            if post.get("automatic_assignment") == "1":
                lead.sudo().action_assign_partner()

            # Custom tag fallback rule:
            # - no user-selected tags -> ensure "No more partner available" exists
            # - one or more user-selected tags -> never keep that fallback tag
            fallback_tag = self._fallback_no_partner_tag()
            if tag_ids:
                if fallback_tag in lead.tag_ids:
                    lead.sudo().write({"tag_ids": [(3, fallback_tag.id)]})
            elif fallback_tag not in lead.tag_ids:
                lead.sudo().write({"tag_ids": [(4, fallback_tag.id)]})

        except (UserError, ValidationError) as exc:
            query = urlencode({"error": str(exc) or "Unable to create the opportunity."})
            return request.redirect(f"/zaintagro/crm?{query}")

        return request.redirect(f"/zaintagro/crm?success=1&lead_id={lead.id}")
