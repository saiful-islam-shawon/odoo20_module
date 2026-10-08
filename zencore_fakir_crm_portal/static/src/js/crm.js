/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";


publicWidget.registry.CrmOpportunityForm = publicWidget.Widget.extend({
    selector: "#crm_opportunity_form",

    events: {
        "change .crm_tag_option_input": "_onTagChange",
        "click .crm_tag_remove": "_onRemoveTag",
        "input .crm_tag_search": "_onSearchTag",
        "click .crm_tags_dropdown_menu": "_onDropdownMenuClick",

        "input #crm_country_search": "_onCountrySearch",
        "focus #crm_country_search": "_onCountrySearch",
        "click .crm_country_suggestion_item": "_onSelectCountry",

        "input #crm_state_search": "_onStateSearch",
        "focus #crm_state_search": "_onStateSearch",
        "click .crm_state_suggestion_item": "_onSelectState",

        "input #crm_campaign_search": "_onCampaignSearch",
        "focus #crm_campaign_search": "_onCampaignSearch",
        "click .crm_campaign_suggestion_item": "_onSelectCampaign",

        "input #crm_medium_search": "_onMediumSearch",
        "focus #crm_medium_search": "_onMediumSearch",
        "click .crm_medium_suggestion_item": "_onSelectMedium",

        "input #crm_source_search": "_onSourceSearch",
        "focus #crm_source_search": "_onSourceSearch",
        "click .crm_source_suggestion_item": "_onSelectSource",
    },

    async start() {
        await this._super(...arguments);

        this.hiddenInput = this.el.querySelector(
            "#crm_tag_ids"
        );

        this.selectedTagsContainer = this.el.querySelector(
            ".crm_selected_tags"
        );

        this._syncTags();

        this._onDocumentClickBound =
            this._onDocumentClick.bind(this);

        document.addEventListener(
            "click",
            this._onDocumentClickBound
        );
    },

    destroy() {
        if (this._onDocumentClickBound) {
            document.removeEventListener(
                "click",
                this._onDocumentClickBound
            );
        }

        this._super(...arguments);
    },

    _onDropdownMenuClick(event) {
        event.stopPropagation();
    },

    _onTagChange() {
        this._syncTags();
    },

    _onRemoveTag(event) {
        event.preventDefault();
        event.stopPropagation();

        const tagId = event.currentTarget.dataset.tagId;

        const checkbox = Array.from(
            this.el.querySelectorAll(
                ".crm_tag_option_input"
            )
        ).find(
            (item) => item.value === tagId
        );

        if (checkbox) {
            checkbox.checked = false;
        }

        this._syncTags();
    },

    _onSearchTag(event) {
        const searchValue =
            event.currentTarget.value
                .trim()
                .toLowerCase();

        this.el.querySelectorAll(
            ".crm_tag_option"
        ).forEach((option) => {

            const tagName =
                option.dataset.tagName || "";

            option.classList.toggle(
                "d-none",
                !tagName.includes(searchValue)
            );
        });
    },

    _syncTags() {
        if (
            !this.hiddenInput
            || !this.selectedTagsContainer
        ) {
            return;
        }

        const selectedCheckboxes = Array.from(
            this.el.querySelectorAll(
                ".crm_tag_option_input:checked"
            )
        );

        this.hiddenInput.value =
            selectedCheckboxes
                .map((checkbox) => checkbox.value)
                .join(",");

        this._renderSelectedTags(
            selectedCheckboxes
        );
    },

    _renderSelectedTags(selectedCheckboxes) {
        this.selectedTagsContainer.replaceChildren();

        if (!selectedCheckboxes.length) {
            const placeholder =
                document.createElement("span");

            placeholder.className =
                "crm_tag_placeholder";

            placeholder.textContent =
                "Select tags...";

            this.selectedTagsContainer.appendChild(
                placeholder
            );

            return;
        }

        selectedCheckboxes.forEach(
            (checkbox) => {

                const tagChip =
                    document.createElement("span");

                tagChip.className =
                    "crm_selected_tag";

                const name =
                    document.createElement("span");

                name.textContent =
                    checkbox.dataset.tagName
                    || "Unnamed Tag";

                const remove =
                    document.createElement("span");

                remove.className =
                    "crm_tag_remove";

                remove.dataset.tagId =
                    checkbox.value;

                remove.setAttribute(
                    "role",
                    "button"
                );

                remove.setAttribute(
                    "aria-label",
                    `Remove ${
                        checkbox.dataset.tagName
                        || "tag"
                    }`
                );

                remove.textContent = "×";

                tagChip.appendChild(name);
                tagChip.appendChild(remove);

                this.selectedTagsContainer.appendChild(
                    tagChip
                );
            }
        );
    },

    _filterDropdown(
        input,
        dropdown,
        itemSelector,
        extraFilter = null
    ) {
        if (!input || !dropdown) {
            return;
        }

        const searchValue =
            input.value.trim().toLowerCase();

        dropdown.classList.remove("d-none");

        dropdown.querySelectorAll(
            itemSelector
        ).forEach((item) => {

            const name =
                (item.dataset.name || "")
                    .toLowerCase();

            let visible =
                name.includes(searchValue);

            if (visible && extraFilter) {
                visible = extraFilter(item);
            }

            item.classList.toggle(
                "d-none",
                !visible
            );
        });
    },

    _selectAutocomplete(
        item,
        hiddenSelector,
        searchSelector,
        dropdownSelector
    ) {
        const hidden =
            this.el.querySelector(hiddenSelector);

        const search =
            this.el.querySelector(searchSelector);

        const dropdown =
            this.el.querySelector(dropdownSelector);

        if (hidden) {
            hidden.value =
                item.dataset.id || "";
        }

        if (search) {
            search.value =
                item.dataset.name || "";
        }

        if (dropdown) {
            dropdown.classList.add("d-none");
        }
    },

    _onCountrySearch(event) {
        const dropdown =
            this.el.querySelector(
                "#crm_country_suggestions"
            );

        this._filterDropdown(
            event.currentTarget,
            dropdown,
            ".crm_country_suggestion_item"
        );

        const countryId =
            this.el.querySelector(
                "#crm_country_id"
            );

        if (countryId) {
            countryId.value = "";
        }

        this._resetState();
    },

    _onSelectCountry(event) {
        this._selectAutocomplete(
            event.currentTarget,
            "#crm_country_id",
            "#crm_country_search",
            "#crm_country_suggestions"
        );

        this._resetState();
    },

    _onStateSearch(event) {
        const countryId =
            this.el.querySelector(
                "#crm_country_id"
            )?.value || "";

        const dropdown =
            this.el.querySelector(
                "#crm_state_suggestions"
            );

        this._filterDropdown(
            event.currentTarget,
            dropdown,
            ".crm_state_suggestion_item",
            (item) => {
                return (
                    !countryId
                    || item.dataset.countryId
                        === countryId
                );
            }
        );

        const stateId =
            this.el.querySelector(
                "#crm_state_id"
            );

        if (stateId) {
            stateId.value = "";
        }
    },

    _onSelectState(event) {
        this._selectAutocomplete(
            event.currentTarget,
            "#crm_state_id",
            "#crm_state_search",
            "#crm_state_suggestions"
        );
    },

    _resetState() {
        const stateId =
            this.el.querySelector(
                "#crm_state_id"
            );

        const stateSearch =
            this.el.querySelector(
                "#crm_state_search"
            );

        const dropdown =
            this.el.querySelector(
                "#crm_state_suggestions"
            );

        if (stateId) {
            stateId.value = "";
        }

        if (stateSearch) {
            stateSearch.value = "";
        }

        if (dropdown) {
            dropdown.classList.add("d-none");
        }
    },

    _onCampaignSearch(event) {
        const hidden =
            this.el.querySelector(
                "#crm_campaign_id"
            );

        if (hidden) {
            hidden.value = "";
        }

        this._filterDropdown(
            event.currentTarget,
            this.el.querySelector(
                "#crm_campaign_suggestions"
            ),
            ".crm_campaign_suggestion_item"
        );
    },

    _onSelectCampaign(event) {
        this._selectAutocomplete(
            event.currentTarget,
            "#crm_campaign_id",
            "#crm_campaign_search",
            "#crm_campaign_suggestions"
        );
    },

    _onMediumSearch(event) {
        const hidden =
            this.el.querySelector(
                "#crm_medium_id"
            );

        if (hidden) {
            hidden.value = "";
        }

        this._filterDropdown(
            event.currentTarget,
            this.el.querySelector(
                "#crm_medium_suggestions"
            ),
            ".crm_medium_suggestion_item"
        );
    },

    _onSelectMedium(event) {
        this._selectAutocomplete(
            event.currentTarget,
            "#crm_medium_id",
            "#crm_medium_search",
            "#crm_medium_suggestions"
        );
    },

    _onSourceSearch(event) {
        const hidden =
            this.el.querySelector(
                "#crm_source_id"
            );

        if (hidden) {
            hidden.value = "";
        }

        this._filterDropdown(
            event.currentTarget,
            this.el.querySelector(
                "#crm_source_suggestions"
            ),
            ".crm_source_suggestion_item"
        );
    },

    _onSelectSource(event) {
        this._selectAutocomplete(
            event.currentTarget,
            "#crm_source_id",
            "#crm_source_search",
            "#crm_source_suggestions"
        );
    },

    _onDocumentClick(event) {
        const dropdowns = [
            [
                ".crm_country_search_wrapper",
                "#crm_country_suggestions",
            ],
            [
                ".crm_state_search_wrapper",
                "#crm_state_suggestions",
            ],
            [
                ".crm_campaign_search_wrapper",
                "#crm_campaign_suggestions",
            ],
            [
                ".crm_medium_search_wrapper",
                "#crm_medium_suggestions",
            ],
            [
                ".crm_source_search_wrapper",
                "#crm_source_suggestions",
            ],
        ];

        dropdowns.forEach(
            ([wrapperSelector, dropdownSelector]) => {

                const wrapper =
                    this.el.querySelector(
                        wrapperSelector
                    );

                const dropdown =
                    this.el.querySelector(
                        dropdownSelector
                    );

                if (
                    wrapper
                    && dropdown
                    && !wrapper.contains(event.target)
                ) {
                    dropdown.classList.add(
                        "d-none"
                    );
                }
            }
        );
    },
});
// Portal create form product-line editor.
publicWidget.registry.FakirCrmCreateProductEditor = publicWidget.Widget.extend({
    selector: "#crm_opportunity_form",
    events: {
        "click .fpm-add-product-row": "_addRow",
        "click .fpm-remove-product-row": "_removeRow",
        "change .fpm-product-select": "_syncRow",
        "input .fpm-product-quantity": "_recalculateFromEvent",
        "input .fpm-product-price": "_recalculateFromEvent",
        "change .fpm-product-taxes": "_taxesChanged",
    },
    start() {
        const result = this._super(...arguments);
        this.rows = this.el.querySelector(".fpm-product-rows");
        this.template = this.el.querySelector(".fpm-product-row-template");
        return result;
    },
    _addRow() {
        if (!this.rows || !this.template) return;
        this.rows.appendChild(this.template.content.cloneNode(true));
        this._recalculateTotal();
    },
    _removeRow(ev) {
        ev.currentTarget.closest(".fpm-product-row")?.remove();
        this._recalculateTotal();
    },
    _syncRow(ev) {
        const row = ev.currentTarget.closest(".fpm-product-row");
        const option = ev.currentTarget.selectedOptions[0];
        if (!row || !option) return;
        const set = (selector, value) => {
            const cell = row.querySelector(selector);
            if (cell) cell.textContent = value || "-";
        };
        set(".fpm-product-category", option.dataset.category);

        const price = row.querySelector(".fpm-product-price");
        if (price) price.value = option.dataset.price || "0.00";

        const taxes = row.querySelector(".fpm-product-taxes");
        const defaultTaxIds = (option.dataset.defaultTaxes || "").split(",").filter(Boolean);
        if (taxes) {
            Array.from(taxes.options).forEach((taxOption) => {
                taxOption.selected = defaultTaxIds.includes(taxOption.value);
            });
        }
        this._syncTaxHidden(row);
        this._recalculateRow(row);
    },
    _taxesChanged(ev) {
        const row = ev.currentTarget.closest(".fpm-product-row");
        if (!row) return;
        this._syncTaxHidden(row);
        this._recalculateRow(row);
    },
    _recalculateFromEvent(ev) {
        const row = ev.currentTarget.closest(".fpm-product-row");
        if (row) this._recalculateRow(row);
    },
    _syncTaxHidden(row) {
        const taxes = row.querySelector(".fpm-product-taxes");
        const hidden = row.querySelector(".fpm-product-tax-ids");
        if (!taxes || !hidden) return;
        hidden.value = Array.from(taxes.selectedOptions).map((option) => option.value).join(",");
    },
    _recalculateRow(row) {
        const quantity = parseFloat(row.querySelector(".fpm-product-quantity")?.value || "0") || 0;
        const price = parseFloat(row.querySelector(".fpm-product-price")?.value || "0") || 0;
        let total = quantity * price;
        const taxes = row.querySelector(".fpm-product-taxes");
        if (taxes) {
            Array.from(taxes.selectedOptions).forEach((option) => {
                const amount = parseFloat(option.dataset.amount || "0") || 0;
                if (option.dataset.amountType === "percent") total += quantity * price * amount / 100;
                else if (option.dataset.amountType === "fixed") total += quantity * amount;
            });
        }
        row.dataset.total = String(total);
        const amountCell = row.querySelector(".fpm-product-amount");
        if (amountCell) amountCell.textContent = total.toFixed(2);
        this._recalculateTotal();
    },
    _recalculateTotal() {
        if (!this.rows) return;
        let total = 0;
        this.rows.querySelectorAll(".fpm-product-row").forEach((row) => {
            if (row.dataset.total !== undefined) total += parseFloat(row.dataset.total || "0") || 0;
            else {
                const quantity = parseFloat(row.querySelector(".fpm-product-quantity")?.value || "0") || 0;
                const price = parseFloat(row.querySelector(".fpm-product-price")?.value || "0") || 0;
                total += quantity * price;
            }
        });
        const totalEl = this.el.querySelector(".fpm-product-total");
        if (totalEl) totalEl.textContent = total.toFixed(2);
    },
});
