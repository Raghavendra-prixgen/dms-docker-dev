/** @odoo-module **/

import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { buildPageNums, fmt } from "../../js/utils";

const PER_PAGE = 15;

export class PurchaseView extends Component {
    static template = "vahini_dashboard.PurchaseView";
    static props = {
        dateFrom: String,
        dateTo:   String,
        onBack:   Function,
    };

    setup() {
        this.state = useState({
            tab:        "purchase",   // "purchase" | "purchase_return"
            page:       1,
            totalPages: 1,
            total:      0,
            loading:    true,
            rows:       [],
            summary:    { bill_count: 0, total_qty: 0, tax_less: 0, tax_paid: 0 },
            sortCol:    "bill_date",
            sortDir:    "desc",
            search:     "",
            pickerOpen:  false,
            draftFrom:   this.props.dateFrom,
            draftTo:     this.props.dateTo,
            dateFrom:    this.props.dateFrom,
            dateTo:      this.props.dateTo,
            colMenuOpen: false,
            colSearch:   "",
            colMenuTop:  0,
            colMenuRight: 0,
            columns: [
                { key: "bill_number",      label: "Bill Number",       visible: true  },
                { key: "bill_date",        label: "Bill Date",         visible: true  },
                { key: "accounting_date",  label: "Accounting Date",   visible: false },
                { key: "vendor_code",      label: "Vendor Code",       visible: false },
                { key: "vendor",           label: "Vendor",            visible: true  },
                { key: "gst_no",           label: "GST No",            visible: false },
                { key: "vendor_ref",       label: "Vendor Ref",        visible: false },
                { key: "po_number",        label: "PO Number",         visible: true  },
                { key: "company",          label: "Company",           visible: false },
                { key: "payment_state",    label: "Payment State",     visible: true  },
                { key: "product_code",     label: "Product Code",      visible: false },
                { key: "product",          label: "Product",           visible: true  },
                { key: "label",            label: "Label",             visible: false },
                { key: "product_category", label: "Product Category",  visible: false },
                { key: "product_type",     label: "Product Type",      visible: false },
                { key: "product_uom",      label: "UOM",               visible: true  },
                { key: "account_name",     label: "Account",           visible: false },
                { key: "journal_name",     label: "Journal",           visible: false },
                { key: "currency",         label: "Currency",          visible: false },
                { key: "quantity",         label: "Quantity",          visible: true  },
                { key: "price",            label: "Price",             visible: true  },
                { key: "discount",         label: "Discount %",        visible: false },
                { key: "amount_excl_tax",  label: "Amt Excl Tax",      visible: true  },
                { key: "cgst_rate",        label: "CGST %",            visible: false },
                { key: "cgst_amount",      label: "CGST Amt",          visible: false },
                { key: "sgst_rate",        label: "SGST %",            visible: false },
                { key: "sgst_amount",      label: "SGST Amt",          visible: false },
                { key: "igst_rate",        label: "IGST %",            visible: false },
                { key: "igst_amount",      label: "IGST Amt",          visible: false },
                { key: "tds_rate",         label: "TDS %",             visible: false },
                { key: "tds_amount",       label: "TDS Amt",           visible: false },
                { key: "rcm_amount",       label: "RCM Amt",           visible: false },
                { key: "tax_amount",       label: "Total Tax",         visible: true  },
                { key: "amount_incl_tax",  label: "Amt Incl Tax",      visible: true  },
                { key: "analytic_account", label: "Analytic Account",  visible: false },
                { key: "vendor_city",      label: "Vendor City",       visible: false },
                { key: "vendor_state",     label: "Vendor State",      visible: false },
                { key: "vendor_country",   label: "Vendor Country",    visible: false },
                { key: "invoice_type",     label: "Type",              visible: false },
                { key: "bill_aging",       label: "Bill Aging (days)", visible: false },
                { key: "payment_terms",    label: "Payment Terms",     visible: false },
                { key: "boe_rate",         label: "BOE Rate",          visible: false },
                { key: "grn_ref",          label: "GRN Ref",           visible: false },
            ],
        });

        onMounted(async () => { await this._load(); });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.dateFrom !== this.state.dateFrom ||
                nextProps.dateTo   !== this.state.dateTo) {
                this.state.dateFrom  = nextProps.dateFrom;
                this.state.dateTo    = nextProps.dateTo;
                this.state.draftFrom = nextProps.dateFrom;
                this.state.draftTo   = nextProps.dateTo;
                this.state.page      = 1;
                await this._load();
            }
        });
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    get pageNums()       { return buildPageNums(this.state.totalPages, this.state.page); }
    isCurrentPage(p)     { return p === this.state.page; }
    isPrevDisabled()     { return this.state.page === 1; }
    isNextDisabled()     { return this.state.page === this.state.totalPages; }
    isTabActive(t)       { return this.state.tab === t; }
    fmtNum(v)            { return fmt(v); }

    get displayDateRange() {
        return `${this._fmtD(this.state.dateFrom)} - ${this._fmtD(this.state.dateTo)}`;
    }

    _fmtD(s) {
        if (!s) return "";
        const [y, m, d] = s.split("-");
        const months = ["Jan","Feb","Mar","Apr","May","Jun",
                        "Jul","Aug","Sep","Oct","Nov","Dec"];
        return `${d}-${months[parseInt(m,10)-1]}-${y}`;
    }

    get visibleColumns() {
        return this.state.columns.filter(c => c.visible);
    }

    get filteredCols() {
        const q = (this.state.colSearch || "").toLowerCase();
        return q ? this.state.columns.filter(c => c.label.toLowerCase().includes(q))
                 : this.state.columns;
    }

    isColVisible(key) {
        const c = this.state.columns.find(c => c.key === key);
        return c ? c.visible : true;
    }

    // ── Data load ─────────────────────────────────────────────────────────────
    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/dayview", {
                date_from: this.state.dateFrom,
                date_to:   this.state.dateTo,
                tab:       this.state.tab,
                page:      this.state.page,
                per_page:  PER_PAGE,
                sort_col:  this.state.sortCol,
                sort_dir:  this.state.sortDir,
                search:    this.state.search,
            });
            this.state.rows       = res.rows       || [];
            this.state.summary    = res.summary    || { bill_count:0, total_qty:0, tax_less:0, tax_paid:0 };
            this.state.total      = res.total      || 0;
            this.state.totalPages = res.total_pages|| 1;
            this.state.page       = res.page       || 1;
        } catch(e) {
            console.error("PurchaseView load error:", e);
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    // ── Actions ───────────────────────────────────────────────────────────────
    async setTab(tab) {
        if (this.state.tab === tab) return;
        this.state.tab  = tab;
        this.state.page = 1;
        await this._load();
    }

    async sortBy(col) {
        if (this.state.sortCol === col) {
            this.state.sortDir = this.state.sortDir === "asc" ? "desc" : "asc";
        } else {
            this.state.sortCol = col;
            this.state.sortDir = "desc";
        }
        this.state.page = 1;
        await this._load();
    }

    async onSearch(ev) {
        this.state.search = ev.target.value;
        this.state.page   = 1;
        await this._load();
    }

    async goToPage(p) {
        if (p < 1 || p > this.state.totalPages || p === this.state.page) return;
        this.state.page = p;
        await this._load();
    }

    async prevPage() { await this.goToPage(this.state.page - 1); }
    async nextPage() { await this.goToPage(this.state.page + 1); }

    // ── Date picker ───────────────────────────────────────────────────────────
    openPicker()  { this.state.pickerOpen = true;  }
    closePicker() { this.state.pickerOpen = false; }

    onDraftFrom(ev) { this.state.draftFrom = ev.target.value; }
    onDraftTo(ev)   { this.state.draftTo   = ev.target.value; }

    async applyDates() {
        this.state.dateFrom  = this.state.draftFrom;
        this.state.dateTo    = this.state.draftTo;
        this.state.page      = 1;
        this.state.pickerOpen = false;
        await this._load();
    }

    // ── Column menu ───────────────────────────────────────────────────────────
    toggleColMenu(ev) {
        if (ev) ev.stopPropagation();
        if (!this.state.colMenuOpen) {
            const btn  = ev.currentTarget;
            const rect = btn.getBoundingClientRect();
            this.state.colMenuTop   = rect.bottom + 4;
            this.state.colMenuRight = window.innerWidth - rect.right;
        }
        this.state.colMenuOpen = !this.state.colMenuOpen;
        this.state.colSearch   = "";
    }

    closeColMenu() { this.state.colMenuOpen = false; }

    onColSearch(ev) { this.state.colSearch = ev.target.value; }

    toggleCol(key) {
        const col = this.state.columns.find(c => c.key === key);
        if (col) col.visible = !col.visible;
    }

    // ── CSV download ──────────────────────────────────────────────────────────
    async downloadCsv() {
        const vis = this.state.columns.filter(c => c.visible);
        this.state.loading = true;
        try {
            // Step 1: get actual total line count
            const count = await rpc("/vahini_dashboard/dayview", {
                date_from: this.state.dateFrom,
                date_to:   this.state.dateTo,
                tab:       this.state.tab,
                page:      1,
                per_page:  1,
                sort_col:  this.state.sortCol,
                sort_dir:  this.state.sortDir,
                search:    this.state.search || "",
            });
            const totalLines = count.total || 0;
            if (!totalLines) { alert("No data to download."); return; }

            // Step 2: fetch all lines in safe-sized chunks — avoids a single
            // very large request that can time out or have its connection
            // dropped on big date ranges.
            const CHUNK_SIZE = 500;
            const totalPages = Math.ceil(totalLines / CHUNK_SIZE);
            let allRows = [];

            for (let p = 1; p <= totalPages; p++) {
                const chunk = await rpc("/vahini_dashboard/dayview", {
                    date_from: this.state.dateFrom,
                    date_to:   this.state.dateTo,
                    tab:       this.state.tab,
                    page:      p,
                    per_page:  CHUNK_SIZE,
                    sort_col:  this.state.sortCol,
                    sort_dir:  this.state.sortDir,
                    search:    this.state.search || "",
                });
                allRows = allRows.concat(chunk.rows || []);
            }

            const header  = vis.map(c => `"${c.label}"`).join(",");
            const body    = allRows.map(row =>
                vis.map(c => {
                    const v = row[c.key] != null ? String(row[c.key]) : "";
                    return v.includes(",") || v.includes('"')
                        ? `"${v.replace(/"/g, '""')}"` : v;
                }).join(",")
            ).join("\n");
            const bom  = "\uFEFF";
            const blob = new Blob([bom + header + "\n" + body], { type: "text/csv;charset=utf-8;" });
            const a    = document.createElement("a");
            a.href     = URL.createObjectURL(blob);
            a.download = `purchaseview_${this.state.tab}_${this.state.dateFrom}_${this.state.dateTo}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(a.href);
        } catch(e) {
            console.error("Download failed:", e);
        } finally {
            this.state.loading = false;
        }
    }
}
