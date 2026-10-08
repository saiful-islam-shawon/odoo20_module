/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

// The portal list now uses a self-contained native interaction.
// Keep the existing Chatter and Product Editor widgets unchanged.

publicWidget.registry.FakirPortalCrmChatter =
    publicWidget.Widget.extend({

        // =====================================================
        // WIDGET ROOT
        // =====================================================

        selector: "#fpmCrmChatter",


        // =====================================================
        // EVENTS
        // =====================================================

        events: {

            "click #fpmCrmSendMessageButton":
                "_onSendMessageClick",

            "click #fpmCrmLogNoteButton":
                "_onLogNoteClick",

            "click #fpmCrmChatterCancel":
                "_onCancelClick",

            "input #fpmCrmChatterTextarea":
                "_onTextareaInput",

            "keydown #fpmCrmChatterTextarea":
                "_onTextareaKeydown",

            "submit #fpmCrmChatterForm":
                "_onComposerSubmit",
        },


        // =====================================================
        // START
        // =====================================================

        start() {

            // -------------------------------------------------
            // Find Chatter elements.
            // -------------------------------------------------

            this.sendMessageButton =
                this.el.querySelector(
                    "#fpmCrmSendMessageButton"
                );

            this.logNoteButton =
                this.el.querySelector(
                    "#fpmCrmLogNoteButton"
                );

            this.composer =
                this.el.querySelector(
                    "#fpmCrmChatterComposer"
                );

            this.form =
                this.el.querySelector(
                    "#fpmCrmChatterForm"
                );

            this.modeInput =
                this.el.querySelector(
                    "#fpmCrmChatterMode"
                );

            this.textarea =
                this.el.querySelector(
                    "#fpmCrmChatterTextarea"
                );

            this.submitButton =
                this.el.querySelector(
                    "#fpmCrmChatterSubmit"
                );

            this.cancelButton =
                this.el.querySelector(
                    "#fpmCrmChatterCancel"
                );

            this.timeline =
                this.el.querySelector(
                    "#fpmCrmChatterTimeline"
                );


            // -------------------------------------------------
            // Current composer mode.
            //
            // message = Send Message
            // note    = Log Note
            // -------------------------------------------------

            this.composerMode = "message";


            // -------------------------------------------------
            // Initially hide composer.
            // -------------------------------------------------

            if (this.composer) {
                this.composer.classList.add(
                    "d-none"
                );
            }


            // -------------------------------------------------
            // Initial submit button state.
            // -------------------------------------------------

            this._updateSubmitButtonState();


            return this._super(...arguments);
        },


        // =====================================================
        // SEND MESSAGE BUTTON
        // =====================================================

        _onSendMessageClick(ev) {

            ev.preventDefault();

            this._openComposer(
                "message"
            );
        },


        // =====================================================
        // LOG NOTE BUTTON
        // =====================================================

        _onLogNoteClick(ev) {

            ev.preventDefault();

            this._openComposer(
                "note"
            );
        },


        // =====================================================
        // OPEN COMPOSER
        // =====================================================

        _openComposer(mode) {

            // Only allow known modes.
            if (
                mode !== "message" &&
                mode !== "note"
            ) {
                mode = "message";
            }


            this.composerMode =
                mode;


            // -------------------------------------------------
            // Hidden form value.
            // -------------------------------------------------

            if (this.modeInput) {
                this.modeInput.value =
                    mode;
            }


            // -------------------------------------------------
            // Show composer.
            // -------------------------------------------------

            if (this.composer) {
                this.composer.classList.remove(
                    "d-none"
                );
            }


            // -------------------------------------------------
            // Button appearance.
            // -------------------------------------------------

            this._updateModeButtons();


            // -------------------------------------------------
            // Textarea appearance / placeholder.
            // -------------------------------------------------

            this._updateComposerAppearance();


            // -------------------------------------------------
            // Submit button.
            // -------------------------------------------------

            this._updateSubmitButtonState();


            // -------------------------------------------------
            // Focus textarea.
            // -------------------------------------------------

            if (this.textarea) {

                window.requestAnimationFrame(
                    () => {

                        this.textarea.focus();

                        this.textarea.setSelectionRange(
                            this.textarea.value.length,
                            this.textarea.value.length
                        );
                    }
                );
            }
        },


        // =====================================================
        // CLOSE COMPOSER
        // =====================================================

        _closeComposer() {

            if (this.composer) {
                this.composer.classList.add(
                    "d-none"
                );
            }


            // -------------------------------------------------
            // Clear text.
            // -------------------------------------------------

            if (this.textarea) {
                this.textarea.value = "";
            }


            // -------------------------------------------------
            // Reset mode.
            // -------------------------------------------------

            this.composerMode =
                "message";


            if (this.modeInput) {
                this.modeInput.value =
                    "message";
            }


            // -------------------------------------------------
            // Reset button state.
            // -------------------------------------------------

            this._clearModeButtonState();

            this._updateComposerAppearance();

            this._updateSubmitButtonState();
        },


        // =====================================================
        // CANCEL
        // =====================================================

        _onCancelClick(ev) {

            ev.preventDefault();

            this._closeComposer();
        },


        // =====================================================
        // UPDATE MODE BUTTONS
        // =====================================================

        _updateModeButtons() {

            // -------------------------------------------------
            // Send Message
            // -------------------------------------------------

            if (this.sendMessageButton) {

                if (
                    this.composerMode ===
                    "message"
                ) {

                    this.sendMessageButton.classList.remove(
                        "btn-outline-primary"
                    );

                    this.sendMessageButton.classList.remove(
                        "btn-outline-secondary"
                    );

                    this.sendMessageButton.classList.add(
                        "btn-primary"
                    );

                } else {

                    this.sendMessageButton.classList.remove(
                        "btn-primary"
                    );

                    this.sendMessageButton.classList.add(
                        "btn-outline-primary"
                    );
                }
            }


            // -------------------------------------------------
            // Log Note
            // -------------------------------------------------

            if (this.logNoteButton) {

                if (
                    this.composerMode ===
                    "note"
                ) {

                    this.logNoteButton.classList.remove(
                        "btn-outline-secondary"
                    );

                    this.logNoteButton.classList.remove(
                        "btn-outline-primary"
                    );

                    this.logNoteButton.classList.add(
                        "btn-secondary"
                    );

                } else {

                    this.logNoteButton.classList.remove(
                        "btn-secondary"
                    );

                    this.logNoteButton.classList.add(
                        "btn-outline-secondary"
                    );
                }
            }
        },


        // =====================================================
        // CLEAR MODE BUTTON STATE
        // =====================================================

        _clearModeButtonState() {

            if (this.sendMessageButton) {

                this.sendMessageButton.classList.remove(
                    "btn-primary"
                );

                this.sendMessageButton.classList.add(
                    "btn-outline-primary"
                );
            }


            if (this.logNoteButton) {

                this.logNoteButton.classList.remove(
                    "btn-secondary"
                );

                this.logNoteButton.classList.add(
                    "btn-outline-secondary"
                );
            }
        },


        // =====================================================
        // COMPOSER APPEARANCE
        // =====================================================

        _updateComposerAppearance() {

            if (!this.textarea) {
                return;
            }


            // -------------------------------------------------
            // MESSAGE MODE
            // -------------------------------------------------

            if (
                this.composerMode ===
                "message"
            ) {

                this.textarea.placeholder =
                    "Write a message...";

                this.textarea.classList.remove(
                    "fpm-crm-chatter-note-input"
                );

                this.textarea.classList.add(
                    "fpm-crm-chatter-message-input"
                );


                if (this.submitButton) {

                    this.submitButton.innerHTML =
                        '<i class="fa fa-paper-plane me-1"></i>' +
                        "Send Message";

                    this.submitButton.classList.remove(
                        "btn-secondary"
                    );

                    this.submitButton.classList.add(
                        "btn-primary"
                    );
                }

                return;
            }


            // -------------------------------------------------
            // NOTE MODE
            // -------------------------------------------------

            this.textarea.placeholder =
                "Log an internal note...";

            this.textarea.classList.remove(
                "fpm-crm-chatter-message-input"
            );

            this.textarea.classList.add(
                "fpm-crm-chatter-note-input"
            );


            if (this.submitButton) {

                this.submitButton.innerHTML =
                    '<i class="fa fa-sticky-note-o me-1"></i>' +
                    "Log Note";

                this.submitButton.classList.remove(
                    "btn-primary"
                );

                this.submitButton.classList.add(
                    "btn-secondary"
                );
            }
        },


        // =====================================================
        // TEXTAREA INPUT
        // =====================================================

        _onTextareaInput() {

            this._updateSubmitButtonState();

            this._autoResizeTextarea();
        },


        // =====================================================
        // AUTO RESIZE TEXTAREA
        // =====================================================

        _autoResizeTextarea() {

            if (!this.textarea) {
                return;
            }


            // Reset height first.
            this.textarea.style.height =
                "auto";


            // Maximum composer height.
            const maximumHeight =
                180;


            const desiredHeight =
                Math.min(
                    this.textarea.scrollHeight,
                    maximumHeight
                );


            this.textarea.style.height =
                `${desiredHeight}px`;


            if (
                this.textarea.scrollHeight >
                maximumHeight
            ) {

                this.textarea.style.overflowY =
                    "auto";

            } else {

                this.textarea.style.overflowY =
                    "hidden";
            }
        },


        // =====================================================
        // SUBMIT BUTTON STATE
        // =====================================================

        _updateSubmitButtonState() {

            if (!this.submitButton) {
                return;
            }


            const hasText =
                Boolean(
                    this.textarea &&
                    this.textarea.value.trim()
                );


            this.submitButton.disabled =
                !hasText;
        },


        // =====================================================
        // KEYBOARD SHORTCUT
        //
        // Ctrl + Enter
        // or
        // Cmd + Enter
        //
        // submits composer.
        // =====================================================

        _onTextareaKeydown(ev) {

            if (
                ev.key !== "Enter" ||
                (!ev.ctrlKey && !ev.metaKey)
            ) {
                return;
            }


            ev.preventDefault();


            if (
                !this.form ||
                !this.textarea ||
                !this.textarea.value.trim()
            ) {
                return;
            }


            if (
                typeof this.form.requestSubmit ===
                "function"
            ) {

                this.form.requestSubmit();

            } else {

                this.form.submit();
            }
        },


        // =====================================================
        // FORM SUBMIT
        // =====================================================

        _onComposerSubmit(ev) {

            if (!this.textarea) {
                return;
            }


            const message =
                this.textarea.value.trim();


            // -------------------------------------------------
            // Prevent blank messages.
            // -------------------------------------------------

            if (!message) {

                ev.preventDefault();

                this.textarea.focus();

                this._updateSubmitButtonState();

                return;
            }


            // -------------------------------------------------
            // Make sure current mode reaches controller.
            // -------------------------------------------------

            if (this.modeInput) {
                this.modeInput.value =
                    this.composerMode;
            }


            // -------------------------------------------------
            // Prevent double submit.
            // -------------------------------------------------

            if (this.submitButton) {

                this.submitButton.disabled =
                    true;


                if (
                    this.composerMode ===
                    "note"
                ) {

                    this.submitButton.innerHTML =
                        '<i class="fa fa-spinner fa-spin me-1"></i>' +
                        "Logging...";

                } else {

                    this.submitButton.innerHTML =
                        '<i class="fa fa-spinner fa-spin me-1"></i>' +
                        "Sending...";
                }
            }
        },
    });


// ============================================================================
// EXPORT
// ============================================================================

export default
    publicWidget.registry.FakirPortalCrmOpportunityList;
// Opportunity detail product-line editor.
publicWidget.registry.FakirPortalCrmProductEditor = publicWidget.Widget.extend({
    selector: ".fpm-crm-record-card",
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
