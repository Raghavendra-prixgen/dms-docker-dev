/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

export class SnapHeader extends Component {
    static template = "vahini_dashboard.SnapHeader";
    static props = {
        title: { type: String, optional: true },
        theme:           String,
        dateFrom:        String,
        dateTo:          String,
        dateDisplay:     String,
        onThemeToggle:   Function,
        onDateChange:    Function,
        onRefresh:       Function,
    };

    setup() {
        this.state = useState({
            pickerOpen:      false,
            draftFrom:       this.props.dateFrom,
            draftTo:         this.props.dateTo,
            companies:       [],
            groups:          [],   // grouped: [{id, name, is_group, branches:[]}]
            currentCompany:  { id: 0, name: "Loading..." },
            companyOpen:     false,
        });

        onMounted(async () => {
            await this._loadCompanies();
        });
    }

    // ── Load allowed companies ────────────────────────────────────────────────
    async _loadCompanies() {
        try {
            const result = await rpc("/vahini_dashboard/companies", {});
            // Use grouped structure if available, fall back to flat list
            this.state.groups    = result.groups    || [];
            this.state.companies = result.companies || [];
            this.state.currentCompany = result.current || { id: 0, name: "" };
        } catch(e) {
            console.error("Could not load companies:", e);
        }
    }

    // ── Switch company ────────────────────────────────────────────────────────
    async switchCompany(company) {
        this.state.companyOpen    = false;
        this.state.currentCompany = company;

        try {
            // Call backend to update user's active company in session
            const result = await rpc("/vahini_dashboard/switch_company", {
                company_id: company.id,
            });

            if (result.success) {
                // Reload page — Odoo will pick up the new company from session
                window.location.reload();
            } else {
                console.error("Company switch failed:", result.message);
            }
        } catch(e) {
            console.error("Company switch error:", e);
            window.location.reload();
        }
    }

    get themeIcon() { return this.props.theme === "light" ? "🌙" : "☀"; }

    onToggle()  { this.props.onThemeToggle(); }
    onRefresh() { this.props.onRefresh(); }

    openPicker() {
        this.state.draftFrom  = this.props.dateFrom;
        this.state.draftTo    = this.props.dateTo;
        this.state.pickerOpen = true;
    }

    closePicker() { this.state.pickerOpen = false; }

    applyDates() {
        if (this.state.draftFrom && this.state.draftTo) {
            this.props.onDateChange(this.state.draftFrom, this.state.draftTo);
        }
        this.state.pickerOpen = false;
    }

    onFromChange(ev)  { this.state.draftFrom = ev.target.value; }
    onToChange(ev)    { this.state.draftTo   = ev.target.value; }

    toggleCompanyMenu(ev) {
        if (ev) ev.stopPropagation();
        this.state.companyOpen = !this.state.companyOpen;
    }

    closeCompanyMenu() { this.state.companyOpen = false; }
}
