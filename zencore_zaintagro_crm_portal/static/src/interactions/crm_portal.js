/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

/**
 * Website CRM form behavior.
 *
 * Everything is scoped to the module root.  Relational dropdowns intentionally
 * use a same-origin HTTP JSON endpoint instead of a generic model RPC so the
 * public page never exposes an arbitrary model/method gateway.
 */
export class ZencoreZaintagroCrmPortal extends Interaction {
    static selector = ".zencore_zaintagro_crm_portal";

    setup() {
        this.selectedTags = new Map();
        this.searchSerial = new WeakMap();
        this.activeIndex = new WeakMap();
    }

    start() {
        this._setupFlashMessages();

        for (const autocomplete of this.el.querySelectorAll(".js_zzcp_autocomplete")) {
            this._setupAutocomplete(autocomplete);
        }

        for (const star of this.el.querySelectorAll(".js_zzcp_star")) {
            this.addListener(star, "click", (ev) => this._onStarClick(ev));
        }

        const form = this.el.querySelector(".js_zzcp_form");
        if (form) {
            this.addListener(form, "submit", (ev) => this._onSubmit(ev));
        }

        const assignButton = this.el.querySelector(".js_zzcp_auto_assign_btn");
        if (assignButton) {
            this.addListener(assignButton, "click", (ev) => this._onAutoAssign(ev));
        }

        this.addListener(this.el.ownerDocument, "pointerdown", (ev) => {
            if (!this.el.contains(ev.target)) {
                this._closeAllAutocompleteMenus();
                return;
            }
            for (const autocomplete of this.el.querySelectorAll(".js_zzcp_autocomplete")) {
                if (!autocomplete.contains(ev.target)) {
                    this._closeAutocomplete(autocomplete);
                }
            }
        });
    }

    _setupFlashMessages() {
        for (const flash of this.el.querySelectorAll(".js_zzcp_flash")) {
            const closeButton = flash.querySelector(".js_zzcp_flash_close");
            const remove = () => {
                if (flash.isConnected) {
                    flash.remove();
                }
            };

            if (closeButton) {
                this.addListener(closeButton, "click", remove);
            }

            // Success messages are temporary; errors remain until the user closes them.
            if (flash.dataset.flashType === "success") {
                setTimeout(remove, 5000);
            }
        }
    }

    _setupAutocomplete(autocomplete) {
        const input = autocomplete.querySelector(".js_zzcp_ac_input");
        const hidden = autocomplete.querySelector(".js_zzcp_ac_value");
        const multiple = autocomplete.dataset.multiple === "1";
        if (!input || !autocomplete.dataset.kind) {
            return;
        }

        const debouncedSearch = this.debounced(
            () => this._searchAutocomplete(autocomplete, { multiple, limit: 12 }),
            180
        );

        this.addListener(input, "focus", () => {
            this._searchAutocomplete(autocomplete, { multiple, limit: 12 });
        });

        this.addListener(input, "input", () => {
            if (!multiple && hidden) {
                // The visible text no longer represents the previously selected id.
                hidden.value = "";
            }
            debouncedSearch();
        });

        this.addListener(input, "keydown", (ev) => this._onAutocompleteKeydown(ev, autocomplete));
    }

    async _searchAutocomplete(autocomplete, { multiple = false, limit = 12 } = {}) {
        const input = autocomplete.querySelector(".js_zzcp_ac_input");
        const menu = autocomplete.querySelector(".js_zzcp_ac_menu");
        const kind = autocomplete.dataset.kind;
        if (!input || !menu || !kind) {
            return;
        }

        const serial = (this.searchSerial.get(autocomplete) || 0) + 1;
        this.searchSerial.set(autocomplete, serial);
        this.activeIndex.set(autocomplete, -1);

        this._renderMessage(menu, "Searching...", "zzcp-ac-status");
        menu.classList.add("show");

        const params = new URLSearchParams({
            kind,
            term: input.value.trim(),
            limit: String(limit),
        });
        if (kind === "state") {
            const countryId = this.el.querySelector(".js_zzcp_country_id")?.value;
            if (countryId) {
                params.set("country_id", countryId);
            }
        }

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 12000);
            let response;
            try {
                // Keep this request deliberately simple.  The endpoint is already
                // access-controlled server-side and returns normal JSON.  Using the
                // browser promise directly also avoids Interaction lifecycle wrappers
                // swallowing the post-await render callback.
                response = await fetch(`/zaintagro/crm/search?${params.toString()}`, {
                    method: "GET",
                    credentials: "same-origin",
                    headers: { Accept: "application/json" },
                    signal: controller.signal,
                });
            } finally {
                clearTimeout(timeoutId);
            }

            if (!response.ok) {
                throw new Error(`Search request failed with HTTP ${response.status}`);
            }

            const payload = await response.json();

            // Ignore stale searches and do not touch DOM after this interaction
            // has been removed from the page.
            if (this.searchSerial.get(autocomplete) !== serial || !this.el.isConnected) {
                return;
            }

            this._renderAutocomplete(
                autocomplete,
                Array.isArray(payload?.items) ? payload.items : [],
                multiple,
                Boolean(payload?.has_more)
            );
        } catch (error) {
            if (this.searchSerial.get(autocomplete) !== serial || !this.el.isConnected) {
                return;
            }
            const text = error?.name === "AbortError" ? "Search timed out" : "Unable to load results";
            this._renderMessage(menu, text, "zzcp-ac-status zzcp-ac-error");
            menu.classList.add("show");
            console.error("[zencore_zaintagro_crm_portal] dropdown search failed", error);
        }
    }

    _renderAutocomplete(autocomplete, items, multiple, hasMore) {
        const input = autocomplete.querySelector(".js_zzcp_ac_input");
        const hidden = autocomplete.querySelector(".js_zzcp_ac_value");
        const menu = autocomplete.querySelector(".js_zzcp_ac_menu");
        const kind = autocomplete.dataset.kind;
        if (!input || !menu) {
            return;
        }

        menu.replaceChildren();
        this.activeIndex.set(autocomplete, -1);
        let rendered = 0;

        for (const item of items) {
            if (multiple && this.selectedTags.has(item.id)) {
                continue;
            }
            rendered += 1;
            const option = this.el.ownerDocument.createElement("button");
            option.type = "button";
            option.className = "zzcp-ac-option js_zzcp_ac_option";
            option.setAttribute("role", "option");
            option.dataset.recordId = String(item.id);

            const primary = this.el.ownerDocument.createElement("span");
            primary.className = "zzcp-ac-primary";
            primary.textContent = item.name || "";
            option.appendChild(primary);

            if (item.secondary) {
                const secondary = this.el.ownerDocument.createElement("span");
                secondary.className = "zzcp-ac-secondary";
                secondary.textContent = item.secondary;
                option.appendChild(secondary);
            }

            this.addListener(option, "click", () => {
                this._selectAutocompleteItem(autocomplete, item, multiple, hidden, input, kind);
            });
            menu.appendChild(option);
        }

        if (!rendered) {
            this._renderMessage(menu, "No results found", "zzcp-ac-status");
        } else if (hasMore) {
            const searchMore = this.el.ownerDocument.createElement("button");
            searchMore.type = "button";
            searchMore.className = "zzcp-ac-search-more";
            searchMore.textContent = "Search more...";
            this.addListener(searchMore, "click", () => {
                this._searchAutocomplete(autocomplete, { multiple, limit: 50 });
            });
            menu.appendChild(searchMore);
        }

        menu.classList.add("show");
    }

    _selectAutocompleteItem(autocomplete, item, multiple, hidden, input, kind) {
        if (multiple) {
            this._addTag(item);
            input.value = "";
            // Keep a tag dropdown useful for rapid multi-selection.
            this._searchAutocomplete(autocomplete, { multiple: true, limit: 12 });
            input.focus();
            return;
        }

        if (hidden) {
            hidden.value = String(item.id);
        }
        input.value = item.name || "";
        this._applyRelatedValues(kind, item);
        this._closeAutocomplete(autocomplete);
    }

    _onAutocompleteKeydown(ev, autocomplete) {
        const menu = autocomplete.querySelector(".js_zzcp_ac_menu");
        if (!menu?.classList.contains("show")) {
            if (ev.key === "ArrowDown") {
                ev.preventDefault();
                this._searchAutocomplete(autocomplete, {
                    multiple: autocomplete.dataset.multiple === "1",
                    limit: 12,
                });
            }
            return;
        }

        const options = [...menu.querySelectorAll(".js_zzcp_ac_option")];
        if (!options.length) {
            if (ev.key === "Escape") {
                this._closeAutocomplete(autocomplete);
            }
            return;
        }

        let index = this.activeIndex.get(autocomplete) ?? -1;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            index = Math.min(index + 1, options.length - 1);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            index = Math.max(index - 1, 0);
        } else if (ev.key === "Enter" && index >= 0) {
            ev.preventDefault();
            options[index].click();
            return;
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            this._closeAutocomplete(autocomplete);
            return;
        } else {
            return;
        }

        this.activeIndex.set(autocomplete, index);
        options.forEach((option, optionIndex) => {
            option.classList.toggle("active", optionIndex === index);
        });
        options[index]?.scrollIntoView({ block: "nearest" });
    }

    _applyRelatedValues(kind, item) {
        if (kind === "partner") {
            // Match the CRM partner onchange experience: selecting a contact
            // prefills the lead/opportunity contact and address fields.  The
            // fields remain editable, and saving never updates res.partner.
            const values = {
                ".js_zzcp_email": item.email || "",
                ".js_zzcp_phone": item.phone || "",
                ".js_zzcp_partner_name": item.partner_name || "",
                ".js_zzcp_contact_name": item.contact_name || "",
                ".js_zzcp_function": item.function || "",
                ".js_zzcp_website": item.website || "",
                ".js_zzcp_street": item.street || "",
                ".js_zzcp_street2": item.street2 || "",
                ".js_zzcp_city": item.city || "",
                ".js_zzcp_zip": item.zip || "",
            };
            for (const [selector, value] of Object.entries(values)) {
                const field = this.el.querySelector(selector);
                if (field) {
                    field.value = value;
                }
            }

            this._setAutocompleteSelection("country", item.country_id, item.country_name);
            this._setAutocompleteSelection("state", item.state_id, item.state_name);
        }

        if (kind === "country") {
            const stateAutocomplete = this.el.querySelector('.js_zzcp_autocomplete[data-kind="state"]');
            if (stateAutocomplete) {
                const stateId = stateAutocomplete.querySelector(".js_zzcp_ac_value");
                const stateInput = stateAutocomplete.querySelector(".js_zzcp_ac_input");
                if (stateId) stateId.value = "";
                if (stateInput) stateInput.value = "";
                this._closeAutocomplete(stateAutocomplete);
            }
        }
    }

    _setAutocompleteSelection(kind, recordId, displayName) {
        const autocomplete = this.el.querySelector(`.js_zzcp_autocomplete[data-kind="${kind}"]`);
        if (!autocomplete) {
            return;
        }
        const hidden = autocomplete.querySelector(".js_zzcp_ac_value");
        const input = autocomplete.querySelector(".js_zzcp_ac_input");
        if (hidden) {
            hidden.value = recordId ? String(recordId) : "";
        }
        if (input) {
            input.value = displayName || "";
        }
        this._closeAutocomplete(autocomplete);
    }

    _renderMessage(menu, text, className) {
        menu.replaceChildren();
        const message = this.el.ownerDocument.createElement("div");
        message.className = className;
        message.textContent = text;
        menu.appendChild(message);
    }

    _closeAutocomplete(autocomplete) {
        autocomplete.querySelector(".js_zzcp_ac_menu")?.classList.remove("show");
        this.activeIndex.set(autocomplete, -1);
    }

    _closeAllAutocompleteMenus() {
        for (const autocomplete of this.el.querySelectorAll(".js_zzcp_autocomplete")) {
            this._closeAutocomplete(autocomplete);
        }
    }

    _addTag(item) {
        this.selectedTags.set(item.id, item);
        this._renderTags();
    }

    _renderTags() {
        const target = this.el.querySelector(".js_zzcp_selected_tags");
        const hidden = this.el.querySelector(".js_zzcp_tag_ids");
        if (!target || !hidden) {
            return;
        }

        target.replaceChildren();
        for (const item of this.selectedTags.values()) {
            const chip = this.el.ownerDocument.createElement("span");
            chip.className = "zzcp-tag-chip";
            chip.append(this.el.ownerDocument.createTextNode(item.name));

            const removeButton = this.el.ownerDocument.createElement("button");
            removeButton.type = "button";
            removeButton.setAttribute("aria-label", `Remove ${item.name}`);
            removeButton.textContent = "×";
            this.addListener(removeButton, "click", () => {
                this.selectedTags.delete(item.id);
                this._renderTags();
            });
            chip.appendChild(removeButton);
            target.appendChild(chip);
        }
        hidden.value = [...this.selectedTags.keys()].join(",");
    }

    _onStarClick(ev) {
        const priority = this.el.querySelector(".js_zzcp_priority_value");
        if (!priority) return;
        const value = Number(ev.currentTarget.dataset.value || 0);
        priority.value = priority.value === String(value) ? "0" : String(value);
        const selected = Number(priority.value || 0);
        for (const star of this.el.querySelectorAll(".js_zzcp_star")) {
            star.classList.toggle("active", Number(star.dataset.value) <= selected);
        }
    }

    async _onAutoAssign(ev) {
        const hidden = this.el.querySelector(".js_zzcp_auto_assign");
        const latitude = this.el.querySelector(".js_zzcp_latitude");
        const longitude = this.el.querySelector(".js_zzcp_longitude");
        const status = this.el.querySelector(".js_zzcp_assignment_status");
        const form = this.el.querySelector(".js_zzcp_form");
        if (!hidden || !latitude || !longitude || !form) {
            return;
        }

        const button = ev.currentTarget;
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = "Locating address...";
        if (status) {
            status.className = "za_assignment_status js_zzcp_assignment_status text-muted";
            status.textContent = "Using Odoo geolocation...";
        }

        const body = new URLSearchParams({
            csrf_token: form.querySelector('input[name="csrf_token"]')?.value || "",
            street: form.querySelector('input[name="street"]')?.value || "",
            city: form.querySelector('input[name="city"]')?.value || "",
            zip: form.querySelector('input[name="zip"]')?.value || "",
            state_id: form.querySelector('input[name="state_id"]')?.value || "",
            country_id: form.querySelector('input[name="country_id"]')?.value || "",
        });

        try {
            const response = await fetch("/zaintagro/crm/geolocate", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                },
                body: body.toString(),
            });
            if (!response.ok) {
                throw new Error(`Geolocation request failed with HTTP ${response.status}`);
            }
            const payload = await response.json();
            if (!payload?.ok) {
                hidden.value = "0";
                button.classList.remove("btn-primary");
                button.classList.add("btn-secondary");
                button.textContent = originalText;
                if (status) {
                    status.className = "za_assignment_status js_zzcp_assignment_status text-danger";
                    status.textContent = payload?.message || "Unable to geolocate this address.";
                }
                return;
            }

            latitude.value = Number(payload.latitude).toFixed(7);
            longitude.value = Number(payload.longitude).toFixed(7);
            hidden.value = "1";
            button.classList.remove("btn-secondary");
            button.classList.add("btn-primary");
            button.textContent = "Automatic Assignment ✓";
            if (status) {
                status.className = "za_assignment_status js_zzcp_assignment_status text-success";
                status.textContent = payload.message || "Address geolocated successfully.";
            }
        } catch (error) {
            hidden.value = "0";
            button.classList.remove("btn-primary");
            button.classList.add("btn-secondary");
            button.textContent = originalText;
            if (status) {
                status.className = "za_assignment_status js_zzcp_assignment_status text-danger";
                status.textContent = "Unable to geolocate the address. Please try again.";
            }
            console.error("[zencore_zaintagro_crm_portal] geolocation failed", error);
        } finally {
            button.disabled = false;
        }
    }

    _onSubmit(ev) {
        const title = this.el.querySelector('input[name="name"]');
        if (!title?.value.trim()) {
            ev.preventDefault();
            title?.focus();
        }
    }
}

registry
    .category("public.interactions")
    .add("zencore_zaintagro_crm_portal.crm_portal", ZencoreZaintagroCrmPortal);
