/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class ZencoreZaintagroSalesPortal extends Interaction {
    static selector = ".zencore_zaintagro_sales_portal";

    setup() {
        this.searchSerial = new WeakMap();
        this.activeIndex = new WeakMap();
        this.multiSelections = new WeakMap();
        this.currencySymbol = "";
        this.currencyPosition = "after";
        this.lineCounter = 0;
        this.previewSerial = 0;
        this.optionalLineColumns = [
            "product", "product_variant", "lead_time", "margin", "margin_percent",
            "taxes", "unit_cost", "tax_excl", "tax_incl",
        ];
        this.visibleLineColumns = new Set(["taxes"]);
    }

    start() {
        this._setupFlashMessages();
        this._setupTabs();
        this._setupTaxMode();
        this._setupColumnChooser();

        for (const autocomplete of this.el.querySelectorAll(".js_zzsp_autocomplete")) {
            this._setupAutocomplete(autocomplete);
        }

        const addLine = this.el.querySelector(".js_zzsp_add_line");
        const addSection = this.el.querySelector(".js_zzsp_add_section");
        const addNote = this.el.querySelector(".js_zzsp_add_note");
        if (addLine) this.addListener(addLine, "click", () => this._addProductLine());
        if (addSection) this.addListener(addSection, "click", () => this._addDisplayLine("line_section"));
        if (addNote) this.addListener(addNote, "click", () => this._addDisplayLine("line_note"));

        const form = this.el.querySelector(".js_zzsp_form");
        if (form) this.addListener(form, "submit", (ev) => this._onSubmit(ev));
        const pickingPolicy = this.el.querySelector(".js_zzsp_picking_policy");
        if (pickingPolicy) this.addListener(pickingPolicy, "change", () => this._applyOrderOnchange("picking_policy"));

        const clientErrorClose = this.el.querySelector(".js_zzsp_client_error_close");
        if (clientErrorClose) this.addListener(clientErrorClose, "click", () => this._hideClientError());

        this.addListener(this.el.ownerDocument, "pointerdown", (ev) => {
            for (const autocomplete of this.el.querySelectorAll(".js_zzsp_autocomplete")) {
                if (!autocomplete.contains(ev.target)) this._closeAutocomplete(autocomplete);
            }
            const chooser = this.el.querySelector(".js_zzsp_column_menu");
            const chooserWrap = this.el.querySelector(".zzsp-column-chooser-wrap");
            if (chooser && chooserWrap && !chooserWrap.contains(ev.target) && !chooser.contains(ev.target)) {
                chooser.classList.remove("show");
            }
        });
        const closeFloatingMenus = () => {
            for (const autocomplete of this.el.querySelectorAll(".js_zzsp_autocomplete")) {
                this._closeAutocomplete(autocomplete);
            }
            this.el.querySelector(".js_zzsp_column_menu")?.classList.remove("show");
        };
        this.addListener(window, "scroll", closeFloatingMenus);
        this.addListener(window, "resize", closeFloatingMenus);
        const linesShell = this.el.querySelector(".js_zzsp_lines_shell");
        if (linesShell) this.addListener(linesShell, "scroll", closeFloatingMenus);

        // Start with one empty order line, like the backend form.
        if (!this.el.querySelector(".js_zzsp_line")) this._addProductLine();
    }

    _setupFlashMessages() {
        for (const flash of this.el.querySelectorAll(".js_zzsp_flash")) {
            const close = flash.querySelector(".js_zzsp_flash_close");
            const remove = () => flash.isConnected && flash.remove();
            if (close) this.addListener(close, "click", remove);
            if (flash.dataset.flashType === "success") setTimeout(remove, 5000);
        }
    }

    _setupTabs() {
        for (const tab of this.el.querySelectorAll(".js_zzsp_tab")) {
            this.addListener(tab, "click", () => {
                const target = tab.dataset.tab;
                for (const other of this.el.querySelectorAll(".js_zzsp_tab")) {
                    other.classList.toggle("active", other === tab);
                }
                for (const panel of this.el.querySelectorAll(".js_zzsp_tab_panel")) {
                    panel.classList.toggle("active", panel.dataset.panel === target);
                }
            });
        }
    }

    _setupTaxMode() {
        const wrapper = this.el.querySelector(".js_zzsp_tax_mode");
        const hidden = this.el.querySelector(".js_zzsp_tax_mode_value");
        if (!wrapper || !hidden) return;
        for (const button of wrapper.querySelectorAll(".zzsp-segment")) {
            button.classList.toggle("active", button.dataset.value === hidden.value);
            this.addListener(button, "click", async () => {
                hidden.value = button.dataset.value;
                for (const other of wrapper.querySelectorAll(".zzsp-segment")) {
                    other.classList.toggle("active", other === button);
                }
                await this._refreshAllProductLines();
            });
        }
    }

    _setupColumnChooser() {
        const button = this.el.querySelector(".js_zzsp_column_chooser_btn");
        const menu = this.el.querySelector(".js_zzsp_column_menu");
        if (!button || !menu) return;

        try {
            const stored = JSON.parse(window.localStorage.getItem("zzsp_order_line_columns_v2") || "null");
            if (Array.isArray(stored)) {
                this.visibleLineColumns = new Set(stored.filter((name) => this.optionalLineColumns.includes(name)));
            }
        } catch (_) {
            // Local-storage preferences are optional; ignore malformed or blocked storage.
        }
        for (const checkbox of menu.querySelectorAll("[data-col-toggle]")) {
            const name = checkbox.dataset.colToggle;
            checkbox.checked = this.visibleLineColumns.has(name);
            this.addListener(checkbox, "change", () => {
                if (checkbox.checked) this.visibleLineColumns.add(name);
                else this.visibleLineColumns.delete(name);
                try {
                    window.localStorage.setItem("zzsp_order_line_columns_v2", JSON.stringify([...this.visibleLineColumns]));
                } catch (_) {}
                this._applyColumnVisibility();
                if (menu.classList.contains("show")) this._positionColumnMenu(button, menu);
            });
        }
        const closeMenu = () => menu.classList.remove("show");
        this.addListener(button, "click", (ev) => {
            ev.stopPropagation();
            menu.classList.toggle("show");
            if (menu.classList.contains("show")) this._positionColumnMenu(button, menu);
        });
        this.addListener(window, "scroll", closeMenu);
        this.addListener(window, "resize", () => {
            closeMenu();
            this._applyColumnVisibility();
        });
        this.addListener(this.el.ownerDocument, "keydown", (ev) => {
            if (ev.key === "Escape") closeMenu();
        });
        this._applyColumnVisibility();
    }

    _positionColumnMenu(button, menu) {
        const rect = button.getBoundingClientRect();
        const width = menu.offsetWidth || 190;
        const viewportWidth = window.innerWidth || this.el.ownerDocument.documentElement.clientWidth;
        const left = Math.max(8, Math.min(rect.right - width, viewportWidth - width - 8));
        menu.style.top = `${rect.bottom + 4}px`;
        menu.style.left = `${left}px`;
    }

    _lineGridTemplate() {
        // One shared grid definition is used by the header and every normal row.
        // This keeps optional columns perfectly aligned and makes horizontal scrolling
        // predictable when many optional columns are enabled.
        const columns = [
            ["description", 220, 2.2],
            ["product", 140, 1.15],
            ["product_variant", 160, 1.25],
            ["quantity", 80, 0.65],
            ["unit_price", 100, 0.8],
            ["lead_time", 80, 0.65],
            ["margin", 95, 0.75],
            ["margin_percent", 95, 0.7],
            ["taxes", 170, 1.15],
            ["unit_cost", 95, 0.75],
            ["tax_excl", 95, 0.75],
            ["tax_incl", 95, 0.75],
            ["amount", 100, 0.8],
        ].filter(([name]) => !this.optionalLineColumns.includes(name) || this.visibleLineColumns.has(name));
        const gap = 10;
        const sidePadding = 24;
        const removeColumn = 40;
        const tracks = columns.map(([, min, fr]) => `minmax(${min}px, ${fr}fr)`).concat(`${removeColumn}px`);
        const minWidth = columns.reduce((sum, [, min]) => sum + min, removeColumn) + gap * columns.length + sidePadding;
        return { grid: tracks.join(" "), minWidth };
    }

    _applyColumnVisibility() {
        const { grid, minWidth } = this._lineGridTemplate();
        const shell = this.el.querySelector(".js_zzsp_lines_shell");
        if (shell) {
            shell.style.setProperty("--zzsp-line-grid", grid);
            shell.style.setProperty("--zzsp-line-min", `${minWidth}px`);
            shell.classList.toggle("is-scroll", minWidth > shell.clientWidth);
        }
        for (const node of this.el.querySelectorAll("[data-col]")) {
            const col = node.dataset.col;
            if (this.optionalLineColumns.includes(col)) node.hidden = !this.visibleLineColumns.has(col);
        }
    }

    _setupAutocomplete(autocomplete) {
        if (autocomplete.dataset.zzspReady === "1") return;
        autocomplete.dataset.zzspReady = "1";
        const input = autocomplete.querySelector(".js_zzsp_ac_input");
        const trigger = autocomplete.querySelector(".js_zzsp_dropdown_trigger");
        const hidden = autocomplete.querySelector(".js_zzsp_ac_value");
        const multiple = autocomplete.dataset.multiple === "1";
        if (!input || !autocomplete.dataset.kind) return;

        if (multiple && !this.multiSelections.has(autocomplete)) {
            this.multiSelections.set(autocomplete, new Map());
        }

        const debouncedSearch = this.debounced(() => this._searchAutocomplete(autocomplete, 12), 180);
        this.addListener(input, "focus", () => this._searchAutocomplete(autocomplete, 12));
        this.addListener(input, "input", () => {
            if (!multiple && hidden) hidden.value = "";
            debouncedSearch();
        });
        this.addListener(input, "keydown", (ev) => this._onAutocompleteKeydown(ev, autocomplete));
        if (trigger) {
            this.addListener(trigger, "click", () => {
                input.focus();
                this._searchAutocomplete(autocomplete, 12);
            });
        }
    }

    async _searchAutocomplete(autocomplete, limit = 12) {
        const input = autocomplete.querySelector(".js_zzsp_ac_input");
        const menu = autocomplete.querySelector(".js_zzsp_ac_menu");
        const kind = autocomplete.dataset.kind;
        if (!input || !menu || !kind) return;

        const serial = (this.searchSerial.get(autocomplete) || 0) + 1;
        this.searchSerial.set(autocomplete, serial);
        this.activeIndex.set(autocomplete, -1);
        this._renderMessage(menu, "Searching…", "zzsp-ac-status");
        menu.classList.add("show");
        this._positionAutocompleteMenu(autocomplete);

        const params = new URLSearchParams({ kind, term: input.value.trim(), limit: String(limit) });
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 12000);
            let response;
            try {
                response = await fetch(`/zaintagro/sales/search?${params.toString()}`, {
                    method: "GET",
                    credentials: "same-origin",
                    headers: { Accept: "application/json" },
                    signal: controller.signal,
                });
            } finally {
                clearTimeout(timeoutId);
            }
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const payload = await response.json();
            if (this.searchSerial.get(autocomplete) !== serial || !this.el.isConnected) return;
            this._renderAutocomplete(autocomplete, payload?.items || [], Boolean(payload?.has_more));
            this._positionAutocompleteMenu(autocomplete);
        } catch (error) {
            if (this.searchSerial.get(autocomplete) !== serial || !this.el.isConnected) return;
            this._renderMessage(menu, error?.name === "AbortError" ? "Search timed out" : "Unable to load results", "zzsp-ac-status zzsp-ac-error");
            menu.classList.add("show");
            this._positionAutocompleteMenu(autocomplete);
            console.error("[zencore_zaintagro_sales_portal] dropdown search failed", error);
        }
    }

    _positionAutocompleteMenu(autocomplete) {
        const inputShell = autocomplete.querySelector(".zzsp-input-shell") || autocomplete;
        const menu = autocomplete.querySelector(".js_zzsp_ac_menu");
        if (!inputShell || !menu) return;
        const rect = inputShell.getBoundingClientRect();
        const viewportWidth = window.innerWidth || this.el.ownerDocument.documentElement.clientWidth;
        const viewportHeight = window.innerHeight || this.el.ownerDocument.documentElement.clientHeight;
        const preferredWidth = Math.max(rect.width, autocomplete.classList.contains("zzsp-tax-ac") ? 250 : 220);
        const width = Math.min(preferredWidth, Math.max(180, viewportWidth - 16));
        const left = Math.max(8, Math.min(rect.left, viewportWidth - width - 8));
        const estimatedHeight = Math.min(menu.scrollHeight || 280, 280);
        const roomBelow = viewportHeight - rect.bottom - 8;
        const showAbove = roomBelow < 180 && rect.top > roomBelow;
        menu.style.width = `${width}px`;
        menu.style.left = `${left}px`;
        menu.style.right = "auto";
        menu.style.top = showAbove ? `${Math.max(8, rect.top - estimatedHeight - 4)}px` : `${rect.bottom + 4}px`;
    }

    _renderAutocomplete(autocomplete, items, hasMore) {
        const menu = autocomplete.querySelector(".js_zzsp_ac_menu");
        if (!menu) return;
        const multiple = autocomplete.dataset.multiple === "1";
        const selected = this.multiSelections.get(autocomplete) || new Map();
        menu.replaceChildren();
        let rendered = 0;
        for (const item of items) {
            if (multiple && selected.has(Number(item.id))) continue;
            rendered += 1;
            const option = this.el.ownerDocument.createElement("button");
            option.type = "button";
            option.className = "zzsp-ac-option js_zzsp_ac_option";
            option.setAttribute("role", "option");
            const primary = this.el.ownerDocument.createElement("span");
            primary.className = "zzsp-ac-primary";
            primary.textContent = item.name || "";
            option.appendChild(primary);
            if (item.secondary) {
                const secondary = this.el.ownerDocument.createElement("span");
                secondary.className = "zzsp-ac-secondary";
                secondary.textContent = item.secondary;
                option.appendChild(secondary);
            }
            this.addListener(option, "click", () => this._selectAutocompleteItem(autocomplete, item));
            menu.appendChild(option);
        }
        if (!rendered) this._renderMessage(menu, "No results found", "zzsp-ac-status");
        if (rendered && hasMore) {
            const more = this.el.ownerDocument.createElement("button");
            more.type = "button";
            more.className = "zzsp-ac-search-more";
            more.textContent = "Search more…";
            this.addListener(more, "click", () => this._searchAutocomplete(autocomplete, 50));
            menu.appendChild(more);
        }
        menu.classList.add("show");
    }

    async _selectAutocompleteItem(autocomplete, item) {
        const input = autocomplete.querySelector(".js_zzsp_ac_input");
        const hidden = autocomplete.querySelector(".js_zzsp_ac_value");
        const multiple = autocomplete.dataset.multiple === "1";
        const kind = autocomplete.dataset.kind;
        const field = autocomplete.dataset.field;

        if (multiple) {
            const selected = this.multiSelections.get(autocomplete) || new Map();
            selected.set(Number(item.id), item);
            this.multiSelections.set(autocomplete, selected);
            this._renderChips(autocomplete);
            if (input) input.value = "";
            this._closeAutocomplete(autocomplete);
            if (field === "tag_ids") this._syncOrderTagIds();
            if (kind === "tax") {
                const row = autocomplete.closest(".js_zzsp_line");
                if (row) {
                    row.dataset.manualTaxes = "1";
                    await this._refreshOrderPreview();
                }
            }
            return;
        }

        if (hidden) hidden.value = String(item.id);
        if (input) input.value = item.name || "";
        this._closeAutocomplete(autocomplete);

        if (field === "partner_id") {
            await this._applyCustomerDefaults(item.id);
        } else if (field === "sale_order_template_id") {
            await this._applyTemplate(item.id);
        } else if ([
            "payment_term_id", "user_id", "team_id", "fiscal_position_id",
            "preferred_payment_method_line_id", "journal_id", "incoterm",
            "warehouse_id", "opportunity_id", "campaign_id", "medium_id", "source_id"
        ].includes(field)) {
            await this._applyOrderOnchange(field);
            if (["fiscal_position_id", "warehouse_id"].includes(field)) {
                await this._refreshAllProductLines();
            }
        } else if (field === "product_id") {
            const row = autocomplete.closest(".js_zzsp_line");
            if (row) {
                row.dataset.manualPrice = "0";
                row.dataset.manualTaxes = "0";
                row.dataset.manualLeadTime = "0";
                row.dataset.manualUnitCost = "0";
                row.dataset.manualMargin = "0";
                row.dataset.manualMarginPercent = "0";
                row.dataset.manualDescription = "0";
                const description = row.querySelector(".js_zzsp_line_name");
                if (description) description.value = "";
                row.dataset.priceStateReady = "0";
                row.dataset.technicalPriceUnit = "";
                row.dataset.recomputePrice = "0";
                await this._refreshOrderPreview();
            }
        } else if (field === "product_variant_id") {
            const row = autocomplete.closest(".js_zzsp_line");
            if (row) {
                const canonical = row.querySelector('.js_zzsp_autocomplete[data-field="product_id"]');
                if (canonical) {
                    const canonicalHidden = canonical.querySelector(".js_zzsp_ac_value");
                    const canonicalInput = canonical.querySelector(".js_zzsp_ac_input");
                    if (canonicalHidden) canonicalHidden.value = String(item.id);
                    if (canonicalInput) canonicalInput.value = item.name || "";
                }
                row.dataset.manualPrice = "0";
                row.dataset.manualTaxes = "0";
                row.dataset.manualLeadTime = "0";
                row.dataset.manualUnitCost = "0";
                row.dataset.manualMargin = "0";
                row.dataset.manualMarginPercent = "0";
                row.dataset.manualDescription = "0";
                const description = row.querySelector(".js_zzsp_line_name");
                if (description) description.value = "";
                row.dataset.priceStateReady = "0";
                row.dataset.technicalPriceUnit = "";
                row.dataset.recomputePrice = "0";
                await this._refreshOrderPreview();
            }
        }
    }

    _renderChips(autocomplete) {
        const list = autocomplete.querySelector(".js_zzsp_chip_list");
        if (!list) return;
        list.replaceChildren();
        const selected = this.multiSelections.get(autocomplete) || new Map();
        for (const [id, item] of selected) {
            const chip = this.el.ownerDocument.createElement("span");
            chip.className = "zzsp-chip";
            const text = this.el.ownerDocument.createElement("span");
            text.textContent = item.name || "";
            const remove = this.el.ownerDocument.createElement("button");
            remove.type = "button";
            remove.textContent = "×";
            remove.setAttribute("aria-label", `Remove ${item.name || "item"}`);
            this.addListener(remove, "click", async () => {
                selected.delete(id);
                this._renderChips(autocomplete);
                if (autocomplete.dataset.field === "tag_ids") this._syncOrderTagIds();
                if (autocomplete.dataset.kind === "tax") {
                    const row = autocomplete.closest(".js_zzsp_line");
                    if (row) {
                        row.dataset.manualTaxes = "1";
                        await this._refreshOrderPreview();
                    }
                }
            });
            chip.append(text, remove);
            list.appendChild(chip);
        }
    }

    _setMultipleItems(autocomplete, items) {
        if (!autocomplete) return;
        const selected = new Map();
        for (const item of items || []) selected.set(Number(item.id), item);
        this.multiSelections.set(autocomplete, selected);
        this._renderChips(autocomplete);
    }

    _onAutocompleteKeydown(ev, autocomplete) {
        const menu = autocomplete.querySelector(".js_zzsp_ac_menu");
        if (!menu?.classList.contains("show")) {
            if (ev.key === "ArrowDown") {
                ev.preventDefault();
                this._searchAutocomplete(autocomplete, 12);
            }
            return;
        }
        const options = [...menu.querySelectorAll(".js_zzsp_ac_option")];
        if (!options.length) {
            if (ev.key === "Escape") this._closeAutocomplete(autocomplete);
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
        } else return;
        this.activeIndex.set(autocomplete, index);
        options.forEach((node, nodeIndex) => node.classList.toggle("active", nodeIndex === index));
        options[index]?.scrollIntoView({ block: "nearest" });
    }

    _renderMessage(menu, message, className) {
        menu.replaceChildren();
        const node = this.el.ownerDocument.createElement("div");
        node.className = className;
        node.textContent = message;
        menu.appendChild(node);
    }

    _closeAutocomplete(autocomplete) {
        autocomplete.querySelector(".js_zzsp_ac_menu")?.classList.remove("show");
        this.activeIndex.set(autocomplete, -1);
    }

    _setAutocompleteField(fieldName, payload) {
        const autocomplete = this.el.querySelector(`.js_zzsp_autocomplete[data-field="${fieldName}"]`);
        if (!autocomplete) return;
        const input = autocomplete.querySelector(".js_zzsp_ac_input");
        const hidden = autocomplete.querySelector(".js_zzsp_ac_value");
        if (input) input.value = payload?.name || "";
        if (hidden) hidden.value = payload?.id || "";
    }

    async _postJSON(url, values = {}) {
        const formData = new FormData();
        const csrf = this.el.querySelector(".js_zzsp_csrf")?.value;
        if (csrf) formData.append("csrf_token", csrf);
        for (const [key, value] of Object.entries(values)) formData.append(key, value ?? "");
        const response = await fetch(url, { method: "POST", credentials: "same-origin", body: formData, headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(`Request failed with HTTP ${response.status}`);
        return response.json();
    }

    async _applyCustomerDefaults(partnerId) {
        try {
            const payload = await this._postJSON("/zaintagro/sales/customer-defaults", { partner_id: partnerId });
            if (!payload?.ok) throw new Error(payload?.message || "Unable to load customer defaults");
            this._applyOrderDefaults(payload, { keepTemplate: false });
            await this._refreshAllProductLines();
        } catch (error) {
            this._showClientError(error.message || "Unable to load customer defaults.");
        }
    }

    async _applyOrderOnchange(fieldName) {
        try {
            const payload = await this._postJSON("/zaintagro/sales/order-onchange", {
                order: JSON.stringify(this._collectOrderContext()),
                field: fieldName,
            });
            if (!payload?.ok) throw new Error(payload?.message || "Unable to apply Odoo defaults");
            this._applyOrderDefaults(payload, { keepTemplate: true });
        } catch (error) {
            this._showClientError(error.message || "Unable to apply Odoo sales behaviour.");
        }
    }

    _applyOrderDefaults(payload, { keepTemplate = true } = {}) {
        const mappings = [
            "payment_term_id", "user_id", "team_id", "fiscal_position_id",
            "preferred_payment_method_line_id", "journal_id", "incoterm", "warehouse_id",
            "opportunity_id", "campaign_id", "medium_id", "source_id"
        ];
        if (keepTemplate) mappings.push("sale_order_template_id");
        for (const field of mappings) {
            if (payload[field]) this._setAutocompleteField(field, payload[field]);
        }
        if (payload.validity_date !== undefined) {
            const input = this.el.querySelector(".js_zzsp_validity_date");
            if (input) input.value = payload.validity_date || "";
        }
        if (payload.note !== undefined) {
            const note = this.el.querySelector(".js_zzsp_note");
            if (note) note.value = this._htmlToText(payload.note || "");
        }
        if (payload.require_signature !== undefined) {
            const node = this.el.querySelector(".js_zzsp_require_signature");
            if (node) node.checked = Boolean(payload.require_signature);
        }
        if (payload.prepayment_percent !== undefined) {
            const node = this.el.querySelector(".js_zzsp_prepayment");
            if (node) node.value = payload.prepayment_percent ?? 0;
        }
        if (payload.picking_policy) {
            const node = this.el.querySelector(".js_zzsp_picking_policy");
            if (node) node.value = payload.picking_policy;
        }
        if (payload.incoterm_location !== undefined) {
            const node = this.el.querySelector(".js_zzsp_incoterm_location");
            if (node) node.value = payload.incoterm_location || "";
        }
        if (payload.document_tax_mode) this._setTaxMode(payload.document_tax_mode);
        if (payload.currency_symbol !== undefined) this.currencySymbol = payload.currency_symbol || "";
        if (payload.currency_position) this.currencyPosition = payload.currency_position;
    }

    async _applyTemplate(templateId) {
        const partnerId = this.el.querySelector(".js_zzsp_partner_id")?.value || "";
        try {
            const payload = await this._postJSON("/zaintagro/sales/template-defaults", { partner_id: partnerId, template_id: templateId });
            if (!payload?.ok) throw new Error(payload?.message || "Unable to load template");
            this._applyOrderDefaults(payload, { keepTemplate: true });
            const body = this.el.querySelector(".js_zzsp_lines_body");
            if (body) body.replaceChildren();
            for (const line of payload.lines || []) this._addLineFromPayload(line);
            if (!(payload.lines || []).length) this._addProductLine();
            this._updateTotalsFromPayload(payload);
        } catch (error) {
            this._showClientError(error.message || "Unable to load quotation template.");
        }
    }

    _setTaxMode(value) {
        const hidden = this.el.querySelector(".js_zzsp_tax_mode_value");
        const wrapper = this.el.querySelector(".js_zzsp_tax_mode");
        if (hidden) hidden.value = value || "tax_excluded";
        if (wrapper) {
            for (const button of wrapper.querySelectorAll(".zzsp-segment")) button.classList.toggle("active", button.dataset.value === hidden.value);
        }
    }

    _addProductLine() {
        const row = this._createLineRow(false);
        this.el.querySelector(".js_zzsp_lines_body")?.appendChild(row);
        this._applyColumnVisibility();
        row.querySelector(".js_zzsp_ac_input")?.focus();
        return row;
    }

    _addDisplayLine(displayType) {
        const row = this._createLineRow(displayType);
        this.el.querySelector(".js_zzsp_lines_body")?.appendChild(row);
        row.querySelector(".js_zzsp_display_name")?.focus();
        this._refreshOrderPreview();
        return row;
    }

    _createLineRow(displayType = false) {
        this.lineCounter += 1;
        const row = this.el.ownerDocument.createElement("div");
        row.className = `zzsp-line js_zzsp_line ${displayType ? "zzsp-display-line" : ""}`;
        row.dataset.lineId = String(this.lineCounter);
        row.dataset.displayType = displayType || "";
        row.dataset.manualPrice = "0";
        row.dataset.manualTaxes = "0";
        row.dataset.manualLeadTime = "0";
        row.dataset.manualUnitCost = "0";
        row.dataset.manualMargin = "0";
        row.dataset.manualMarginPercent = "0";
        row.dataset.manualDescription = "0";
        // Mirrors Odoo's stored sale.order.line price state.  Once a product price has
        // been computed, keep both displayed and technical prices across document-tax
        // mode changes so Tax Excl./Tax Incl. never rewrites Unit Price.
        row.dataset.priceStateReady = "0";
        row.dataset.technicalPriceUnit = "";
        row.dataset.recomputePrice = "0";

        if (displayType) {
            const nameWrap = this.el.ownerDocument.createElement("div");
            nameWrap.className = "zzsp-line-display-name";
            const input = displayType === "line_note" ? this.el.ownerDocument.createElement("textarea") : this.el.ownerDocument.createElement("input");
            input.className = "zzsp-input js_zzsp_display_name";
            input.placeholder = displayType === "line_section" ? "Section title" : "Note";
            if (input.tagName === "TEXTAREA") input.rows = 2;
            this.addListener(input, "input", this.debounced(() => this._refreshOrderPreview(), 180));
            nameWrap.appendChild(input);
            row.appendChild(nameWrap);
            const badge = this.el.ownerDocument.createElement("div");
            badge.className = "zzsp-display-badge";
            badge.textContent = displayType === "line_section" ? "Section" : "Note";
            row.appendChild(badge);
        } else {
            const makeTextCell = (col, className = "") => {
                const cell = this.el.ownerDocument.createElement("div");
                cell.dataset.col = col;
                cell.className = `zzsp-line-cell ${className}`.trim();
                cell.textContent = "—";
                row.appendChild(cell);
                return cell;
            };

            const desc = this.el.ownerDocument.createElement("div");
            desc.className = "zzsp-line-description";
            desc.dataset.col = "description";
            desc.innerHTML = `
                <div class="zzsp-autocomplete js_zzsp_autocomplete" data-kind="product" data-field="product_id">
                    <div class="zzsp-input-shell"><input type="text" class="zzsp-input js_zzsp_ac_input" autocomplete="off" placeholder="Search product..."/><button type="button" class="zzsp-dropdown-trigger js_zzsp_dropdown_trigger">⌄</button></div>
                    <input type="hidden" class="js_zzsp_ac_value js_zzsp_product_id"/>
                    <div class="zzsp-ac-menu js_zzsp_ac_menu" role="listbox"></div>
                </div>
                <button type="button" class="zzsp-description-toggle js_zzsp_description_toggle" title="Edit line description" aria-label="Edit line description">✎</button>
                <textarea rows="1" class="zzsp-line-name js_zzsp_line_name" aria-label="Line description"></textarea>`;
            row.appendChild(desc);

            makeTextCell("product", "js_zzsp_col_product");

            const variantWrap = this.el.ownerDocument.createElement("div");
            variantWrap.dataset.col = "product_variant";
            variantWrap.innerHTML = `
                <div class="zzsp-autocomplete js_zzsp_autocomplete" data-kind="product" data-field="product_variant_id">
                    <div class="zzsp-input-shell"><input type="text" class="zzsp-input js_zzsp_ac_input js_zzsp_variant_input" autocomplete="off" placeholder="Product variant..."/><button type="button" class="zzsp-dropdown-trigger js_zzsp_dropdown_trigger">⌄</button></div>
                    <input type="hidden" class="js_zzsp_ac_value js_zzsp_variant_id"/>
                    <div class="zzsp-ac-menu js_zzsp_ac_menu" role="listbox"></div>
                </div>`;
            row.appendChild(variantWrap);

            const qtyWrap = this.el.ownerDocument.createElement("div");
            qtyWrap.dataset.col = "quantity";
            qtyWrap.innerHTML = `<input type="number" min="0" step="0.01" value="1" class="zzsp-input zzsp-number js_zzsp_qty"/>`;
            row.appendChild(qtyWrap);

            const priceWrap = this.el.ownerDocument.createElement("div");
            priceWrap.dataset.col = "unit_price";
            priceWrap.innerHTML = `<input type="number" step="0.01" value="0" class="zzsp-input zzsp-number js_zzsp_price"/>`;
            row.appendChild(priceWrap);

            const leadWrap = this.el.ownerDocument.createElement("div");
            leadWrap.dataset.col = "lead_time";
            leadWrap.innerHTML = `<input type="number" min="0" step="1" value="0" class="zzsp-input zzsp-number js_zzsp_lead_time"/>`;
            row.appendChild(leadWrap);
            const marginWrap = this.el.ownerDocument.createElement("div");
            marginWrap.dataset.col = "margin";
            marginWrap.innerHTML = `<input type="number" step="0.01" value="0" class="zzsp-input zzsp-number js_zzsp_margin"/>`;
            row.appendChild(marginWrap);
            const marginPercentWrap = this.el.ownerDocument.createElement("div");
            marginPercentWrap.dataset.col = "margin_percent";
            marginPercentWrap.innerHTML = `<div class="zzsp-percent"><input type="number" step="0.01" value="0" class="zzsp-input zzsp-number js_zzsp_margin_percent"/><span>%</span></div>`;
            row.appendChild(marginPercentWrap);

            const taxWrap = this.el.ownerDocument.createElement("div");
            taxWrap.dataset.col = "taxes";
            taxWrap.innerHTML = `
                <div class="zzsp-autocomplete zzsp-tax-ac js_zzsp_autocomplete" data-kind="tax" data-field="tax_ids" data-multiple="1">
                    <div class="zzsp-chip-list js_zzsp_chip_list"></div>
                    <div class="zzsp-input-shell"><input type="text" class="zzsp-input js_zzsp_ac_input" autocomplete="off" placeholder="Taxes..."/><button type="button" class="zzsp-dropdown-trigger js_zzsp_dropdown_trigger">⌄</button></div>
                    <div class="zzsp-ac-menu js_zzsp_ac_menu" role="listbox"></div>
                </div>`;
            row.appendChild(taxWrap);

            const costWrap = this.el.ownerDocument.createElement("div");
            costWrap.dataset.col = "unit_cost";
            costWrap.innerHTML = `<input type="number" min="0" step="0.01" value="0" class="zzsp-input zzsp-number js_zzsp_unit_cost"/>`;
            row.appendChild(costWrap);
            makeTextCell("tax_excl", "zzsp-number js_zzsp_col_tax_excl");
            makeTextCell("tax_incl", "zzsp-number js_zzsp_col_tax_incl");

            const amount = this.el.ownerDocument.createElement("div");
            amount.dataset.col = "amount";
            amount.className = "zzsp-line-amount js_zzsp_line_amount";
            amount.textContent = "0.00";
            row.appendChild(amount);

            for (const ac of row.querySelectorAll(".js_zzsp_autocomplete")) this._setupAutocomplete(ac);
            const qty = row.querySelector(".js_zzsp_qty");
            const price = row.querySelector(".js_zzsp_price");
            const leadTime = row.querySelector(".js_zzsp_lead_time");
            const unitCost = row.querySelector(".js_zzsp_unit_cost");
            const margin = row.querySelector(".js_zzsp_margin");
            const marginPercent = row.querySelector(".js_zzsp_margin_percent");
            const name = row.querySelector(".js_zzsp_line_name");
            if (qty) this.addListener(qty, "change", () => {
                // Native sale.order.line price depends on quantity (pricelist tiers).
                // Ask Odoo to recompute it only for this genuine price dependency.
                if (row.dataset.manualPrice !== "1") row.dataset.recomputePrice = "1";
                this._refreshOrderPreview();
            });
            if (price) this.addListener(price, "change", () => {
                row.dataset.manualPrice = "1";
                row.dataset.manualMargin = "0";
                row.dataset.manualMarginPercent = "0";
                this._refreshOrderPreview();
            });
            if (leadTime) this.addListener(leadTime, "change", () => { row.dataset.manualLeadTime = "1"; this._refreshOrderPreview(); });
            if (unitCost) this.addListener(unitCost, "change", () => {
                row.dataset.manualUnitCost = "1";
                row.dataset.manualMargin = "0";
                row.dataset.manualMarginPercent = "0";
                this._refreshOrderPreview();
            });
            if (margin) this.addListener(margin, "change", () => {
                row.dataset.manualMargin = "1";
                row.dataset.manualMarginPercent = "0";
                row.dataset.manualPrice = "0";
                this._refreshOrderPreview();
            });
            if (marginPercent) this.addListener(marginPercent, "change", () => {
                row.dataset.manualMargin = "0";
                row.dataset.manualMarginPercent = "1";
                row.dataset.manualPrice = "0";
                this._refreshOrderPreview();
            });
            if (name) {
                const resizeDescription = () => {
                    name.style.height = "auto";
                    name.style.height = `${Math.max(22, name.scrollHeight)}px`;
                };
                const toggle = row.querySelector(".js_zzsp_description_toggle");
                if (toggle) {
                    this.addListener(toggle, "click", () => {
                        row.classList.add("zzsp-description-editing");
                        name.hidden = false;
                        resizeDescription();
                        name.focus();
                        name.setSelectionRange(name.value.length, name.value.length);
                    });
                }
                this.addListener(name, "input", () => {
                    row.dataset.manualDescription = "1";
                    resizeDescription();
                    this._syncLineDescriptionPresentation(row, { forceOpen: true });
                });
                this.addListener(name, "change", () => this._refreshOrderPreview());
                this.addListener(name, "blur", () => {
                    row.classList.remove("zzsp-description-editing");
                    this._syncLineDescriptionPresentation(row);
                });
                resizeDescription();
                this._syncLineDescriptionPresentation(row);
            }
        }

        const remove = this.el.ownerDocument.createElement("button");
        remove.type = "button";
        remove.className = "zzsp-line-remove";
        remove.textContent = "×";
        remove.title = "Remove line";
        this.addListener(remove, "click", () => { row.remove(); this._refreshOrderPreview(); });
        row.appendChild(remove);
        this._applyColumnVisibility();
        return row;
    }

    _syncLineDescriptionPresentation(row, { forceOpen = false } = {}) {
        const description = row?.querySelector(".js_zzsp_line_name");
        if (!description) return;
        const productInput = row.querySelector('.js_zzsp_autocomplete[data-field="product_id"] .js_zzsp_ac_input');
        const productLabel = (productInput?.value || "").trim();
        const descriptionValue = (description.value || "").trim();
        const hasExtraDescription = Boolean(
            descriptionValue && productLabel && descriptionValue.toLocaleLowerCase() !== productLabel.toLocaleLowerCase()
        );
        const open = forceOpen || row.classList.contains("zzsp-description-editing") || hasExtraDescription;
        description.hidden = !open;
        row.classList.toggle("zzsp-has-line-description", hasExtraDescription);
    }

    _addLineFromPayload(payload) {
        if (payload.display_type) {
            const row = this._createLineRow(payload.display_type);
            const name = row.querySelector(".js_zzsp_display_name");
            if (name) name.value = payload.name || "";
            this.el.querySelector(".js_zzsp_lines_body")?.appendChild(row);
            return row;
        }
        const row = this._createLineRow(false);
        this.el.querySelector(".js_zzsp_lines_body")?.appendChild(row);
        const productAc = row.querySelector('.js_zzsp_autocomplete[data-kind="product"]');
        if (productAc) {
            productAc.querySelector(".js_zzsp_ac_input").value = payload.product_name || "";
            productAc.querySelector(".js_zzsp_ac_value").value = payload.product_id || "";
        }
        const description = row.querySelector(".js_zzsp_line_name");
        if (description) {
            description.value = payload.name || "";
            description.style.height = "auto";
            description.style.height = `${Math.max(22, description.scrollHeight)}px`;
            row.dataset.manualDescription = "0";
        }
        row.querySelector(".js_zzsp_qty").value = payload.qty ?? 1;
        row.querySelector(".js_zzsp_price").value = payload.price_unit ?? 0;
        const variantAc = row.querySelector('.js_zzsp_autocomplete[data-field="product_variant_id"]');
        if (variantAc) {
            variantAc.querySelector(".js_zzsp_ac_input").value = payload.product_variant_name || payload.product_name || "";
            variantAc.querySelector(".js_zzsp_ac_value").value = payload.product_id || "";
        }
        const leadTime = row.querySelector(".js_zzsp_lead_time");
        if (leadTime) leadTime.value = payload.lead_time ?? 0;
        const unitCost = row.querySelector(".js_zzsp_unit_cost");
        if (unitCost) unitCost.value = payload.unit_cost ?? 0;
        const margin = row.querySelector(".js_zzsp_margin");
        if (margin) margin.value = payload.margin ?? 0;
        const marginPercent = row.querySelector(".js_zzsp_margin_percent");
        if (marginPercent) marginPercent.value = payload.margin_percent ?? 0;
        const taxAc = row.querySelector('.js_zzsp_autocomplete[data-kind="tax"]');
        this._setMultipleItems(taxAc, payload.taxes || []);
        this._updateLineMetrics(row, payload);
        this._syncLineDescriptionPresentation(row);
        return row;
    }

    _updateLineMetrics(row, payload) {
        const setText = (selector, value) => {
            const node = row.querySelector(selector);
            if (node) node.textContent = value;
        };
        setText(".js_zzsp_col_product", payload.product_template_name || payload.product_name || "—");
        const variantAc = row.querySelector('.js_zzsp_autocomplete[data-field="product_variant_id"]');
        if (variantAc) {
            const variantInput = variantAc.querySelector(".js_zzsp_ac_input");
            const variantHidden = variantAc.querySelector(".js_zzsp_ac_value");
            if (variantInput && this.el.ownerDocument.activeElement !== variantInput) {
                variantInput.value = payload.product_variant_name || payload.product_name || "";
            }
            if (variantHidden) variantHidden.value = payload.product_id || "";
        }
        const leadTime = row.querySelector(".js_zzsp_lead_time");
        if (leadTime && row.dataset.manualLeadTime !== "1") leadTime.value = payload.lead_time ?? 0;
        const margin = row.querySelector(".js_zzsp_margin");
        if (margin && row.dataset.manualMargin !== "1") margin.value = Number(payload.margin || 0).toFixed(2);
        const marginPercent = row.querySelector(".js_zzsp_margin_percent");
        if (marginPercent && row.dataset.manualMarginPercent !== "1") marginPercent.value = Number(payload.margin_percent || 0).toFixed(2);
        const unitCost = row.querySelector(".js_zzsp_unit_cost");
        if (unitCost && row.dataset.manualUnitCost !== "1") unitCost.value = payload.unit_cost ?? 0;
        if (payload.product_id) {
            row.dataset.priceStateReady = "1";
            row.dataset.technicalPriceUnit = String(
                payload.technical_price_unit ?? payload.price_unit ?? 0
            );
        }
        setText(".js_zzsp_col_tax_excl", this._formatAmount(payload.subtotal || 0));
        setText(".js_zzsp_col_tax_incl", this._formatAmount(payload.total || 0));
        // Odoo's default sale-order-line Amount column is the tax-excluded subtotal.
        setText(".js_zzsp_line_amount", this._formatAmount(payload.subtotal || 0));
        this._applyColumnVisibility();
    }

    _collectOrderContext() {
        const value = (name) => this.el.querySelector(`[name="${name}"]`)?.value || "";
        return {
            partner_id: value("partner_id"),
            payment_term_id: value("payment_term_id"),
            user_id: value("user_id"),
            team_id: value("team_id"),
            sale_order_template_id: value("sale_order_template_id"),
            fiscal_position_id: value("fiscal_position_id"),
            preferred_payment_method_line_id: value("preferred_payment_method_line_id"),
            journal_id: value("journal_id"),
            incoterm: value("incoterm"),
            warehouse_id: value("warehouse_id"),
            opportunity_id: value("opportunity_id"),
            campaign_id: value("campaign_id"),
            medium_id: value("medium_id"),
            source_id: value("source_id"),
            date_order: value("date_order"),
            validity_date: value("validity_date"),
            commitment_date: value("commitment_date"),
            document_tax_mode: value("document_tax_mode"),
            picking_policy: value("picking_policy"),
        };
    }

    _collectLine(row, { forPreview = false } = {}) {
        const displayType = row.dataset.displayType || false;
        if (displayType) {
            return { display_type: displayType, name: row.querySelector(".js_zzsp_display_name")?.value || "" };
        }
        const productId = row.querySelector(".js_zzsp_product_id")?.value || "";
        const data = {
            display_type: false,
            product_id: productId,
            name: row.querySelector(".js_zzsp_line_name")?.value || "",
            qty: row.querySelector(".js_zzsp_qty")?.value || "1",
            manual_price: row.dataset.manualPrice === "1",
            manual_taxes: row.dataset.manualTaxes === "1",
            manual_lead_time: row.dataset.manualLeadTime === "1",
            manual_unit_cost: row.dataset.manualUnitCost === "1",
            manual_margin: row.dataset.manualMargin === "1",
            manual_margin_percent: row.dataset.manualMarginPercent === "1",
            tax_ids: [...(this.multiSelections.get(row.querySelector('.js_zzsp_autocomplete[data-kind="tax"]')) || new Map()).keys()],
        };
        if (row.dataset.priceStateReady === "1") {
            data.price_state_ready = true;
            data.price_unit = row.querySelector(".js_zzsp_price")?.value || "0";
            data.technical_price_unit = row.dataset.technicalPriceUnit || data.price_unit;
        } else if (row.dataset.manualPrice === "1") {
            data.price_unit = row.querySelector(".js_zzsp_price")?.value || "0";
        }
        if (row.dataset.recomputePrice === "1") data.recompute_price = true;
        if (row.dataset.manualLeadTime === "1") data.lead_time = row.querySelector(".js_zzsp_lead_time")?.value || "0";
        if (row.dataset.manualUnitCost === "1") data.unit_cost = row.querySelector(".js_zzsp_unit_cost")?.value || "0";
        if (row.dataset.manualMargin === "1") data.margin = row.querySelector(".js_zzsp_margin")?.value || "0";
        if (row.dataset.manualMarginPercent === "1") data.margin_percent = row.querySelector(".js_zzsp_margin_percent")?.value || "0";
        if (row.dataset.manualTaxes !== "1") delete data.tax_ids;
        return data;
    }

    async _refreshOrderPreview() {
        // All editable order lines are sent in one request and computed on one transient
        // sale.order.  The browser never reproduces Odoo's price, tax, margin, or total
        // formulas.  This preserves document-level Tax Excl./Tax Incl. behaviour while
        // each line keeps its own product taxes/fiscal-position mapping.
        const rows = [...this.el.querySelectorAll(".js_zzsp_line")];
        const lines = rows
            .map((row) => this._collectLine(row))
            .filter((line) => line.display_type || line.product_id);

        if (!lines.length) {
            this._updateTotalsFromPayload({ amount_untaxed: 0, amount_tax: 0, amount_total: 0 });
            return;
        }

        const serial = ++this.previewSerial;
        try {
            const payload = await this._postJSON("/zaintagro/sales/totals-preview", {
                order: JSON.stringify(this._collectOrderContext()),
                lines: JSON.stringify(lines),
            });
            if (serial !== this.previewSerial || !this.el.isConnected) return;
            if (!payload?.ok) throw new Error(payload?.message || "Unable to recompute quotation");

            this.currencySymbol = payload.currency_symbol || this.currencySymbol;
            this.currencyPosition = payload.currency_position || this.currencyPosition;
            if (payload.document_tax_mode) this._setTaxMode(payload.document_tax_mode);

            const backendNormalLines = (payload.lines || []).filter((line) => !line.display_type);
            const productRows = rows.filter(
                (row) => !row.dataset.displayType && row.querySelector(".js_zzsp_product_id")?.value
            );

            productRows.forEach((row, index) => {
                const linePayload = backendNormalLines[index];
                if (!linePayload) return;
                const name = row.querySelector(".js_zzsp_line_name");
                const qty = row.querySelector(".js_zzsp_qty");
                const price = row.querySelector(".js_zzsp_price");
                const leadTime = row.querySelector(".js_zzsp_lead_time");
                const unitCost = row.querySelector(".js_zzsp_unit_cost");
                const margin = row.querySelector(".js_zzsp_margin");
                const marginPercent = row.querySelector(".js_zzsp_margin_percent");
                if (name && row.dataset.manualDescription !== "1") {
                    name.value = linePayload.name || "";
                    name.style.height = "auto";
                    name.style.height = `${Math.max(22, name.scrollHeight)}px`;
                    this._syncLineDescriptionPresentation(row);
                }
                if (qty && linePayload.qty != null) qty.value = linePayload.qty;
                if (price && row.dataset.manualPrice !== "1") price.value = linePayload.price_unit ?? price.value;
                if (leadTime && row.dataset.manualLeadTime !== "1") leadTime.value = linePayload.lead_time ?? leadTime.value;
                if (unitCost && row.dataset.manualUnitCost !== "1") unitCost.value = linePayload.unit_cost ?? unitCost.value;
                if (margin && row.dataset.manualMargin !== "1") margin.value = Number(linePayload.margin || 0).toFixed(2);
                if (marginPercent && row.dataset.manualMarginPercent !== "1") marginPercent.value = Number(linePayload.margin_percent || 0).toFixed(2);
                if (row.dataset.manualMargin === "1" || row.dataset.manualMarginPercent === "1") {
                    // Odoo's sale_margin onchange changes Unit Price. Persist that backend-computed
                    // price on save so the created quotation line keeps the exact edited margin.
                    row.dataset.manualPrice = "1";
                    if (price) price.value = linePayload.price_unit ?? price.value;
                }
                if (row.dataset.manualTaxes !== "1") {
                    this._setMultipleItems(
                        row.querySelector('.js_zzsp_autocomplete[data-kind="tax"]'),
                        linePayload.taxes || []
                    );
                }
                this._updateLineMetrics(row, linePayload);
                row.dataset.recomputePrice = "0";
            });

            this._updateTotalsFromPayload(payload);
        } catch (error) {
            this._showClientError(error.message || "Unable to recompute quotation.");
        }
    }

    // Backward-compatible aliases for any existing event path in this module.
    async _refreshAllProductLines() {
        return this._refreshOrderPreview();
    }

    async _refreshTotals() {
        return this._refreshOrderPreview();
    }

    _updateTotalsFromPayload(payload) {
        const untaxed = this.el.querySelector(".js_zzsp_amount_untaxed");
        const tax = this.el.querySelector(".js_zzsp_amount_tax");
        const total = this.el.querySelector(".js_zzsp_amount_total");
        if (untaxed) untaxed.textContent = this._formatAmount(payload.amount_untaxed || 0);
        const taxAmount = Number(payload.amount_tax || 0);
        if (tax) tax.textContent = this._formatAmount(taxAmount);
        this.el.querySelector(".js_zzsp_tax_total_row")?.classList.toggle("d-none", Math.abs(taxAmount) < 0.0000001);
        if (total) total.textContent = this._formatAmount(payload.amount_total || 0);
    }

    _formatAmount(value) {
        const number = Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (!this.currencySymbol) return number;
        return this.currencyPosition === "before" ? `${this.currencySymbol} ${number}` : `${number} ${this.currencySymbol}`;
    }

    _syncOrderTagIds() {
        const ac = this.el.querySelector('.js_zzsp_autocomplete[data-field="tag_ids"]');
        const hidden = this.el.querySelector(".js_zzsp_tag_ids");
        if (!hidden || !ac) return;
        hidden.value = [...(this.multiSelections.get(ac) || new Map()).keys()].join(",");
    }

    _onSubmit(ev) {
        this._hideClientError();
        const customer = this.el.querySelector(".js_zzsp_partner_id")?.value;
        if (!customer) {
            ev.preventDefault();
            this._showClientError("Please select a valid Customer.");
            return;
        }
        const lines = [...this.el.querySelectorAll(".js_zzsp_line")]
            .map((row) => this._collectLine(row))
            .filter((line) => line.display_type || line.product_id);
        const productLines = lines.filter((line) => !line.display_type);
        if (!productLines.length) {
            ev.preventDefault();
            this._showClientError("Add at least one product line before saving the quotation.");
            return;
        }
        this._syncOrderTagIds();
        const hidden = this.el.querySelector(".js_zzsp_lines_json");
        if (hidden) hidden.value = JSON.stringify(lines);
    }

    _showClientError(message) {
        const alert = this.el.querySelector(".js_zzsp_client_error");
        const text = this.el.querySelector(".js_zzsp_client_error_text");
        if (text) text.textContent = message || "Something went wrong.";
        alert?.classList.remove("d-none");
        alert?.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    _hideClientError() {
        this.el.querySelector(".js_zzsp_client_error")?.classList.add("d-none");
    }

    _htmlToText(html) {
        const div = this.el.ownerDocument.createElement("div");
        div.innerHTML = html || "";
        return div.textContent || div.innerText || "";
    }

}

registry.category("public.interactions").add("zencore_zaintagro_sales_portal.sales_portal", ZencoreZaintagroSalesPortal);
