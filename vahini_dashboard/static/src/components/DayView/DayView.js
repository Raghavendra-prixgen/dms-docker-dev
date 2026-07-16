/** @odoo-module **/

import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { buildPageNums, fmt } from "../../js/utils";

const PER_PAGE = 15;

export class DayView extends Component {
    static template = "vahini_dashboard.DayView";
    static props = {
        dateFrom:   String,
        dateTo:     String,
        onBack:     Function,
        defaultTab: { type: String, optional: true },
    };

    setup() {
        this.state = useState({
            viewType:   "transactions",
            tab:        this.props.defaultTab || "sales",
            page:       1,
            totalPages: 1,
            total:      0,
            loading:    true,
            rows:       [],
            summary:    { bill_count: 0, total_qty: 0, tax_less: 0, tax_paid: 0 },
            sortCol:    "invoice_date",
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

            // ── Moved inside useState so OWL reactivity tracks visibility changes ──
            columns: [
                { key: "invoice_number",    label: "Invoice Number",       visible: true  },
                { key: "invoice_date",      label: "Invoice Date",         visible: true  },
                { key: "customer_code",     label: "Customer Code",        visible: false },
                { key: "customer",          label: "Customer",             visible: true  },
                { key: "vat",               label: "VAT",                  visible: false },
                { key: "partner_category",  label: "Partner Category",     visible: false },
                { key: "company",           label: "Company",              visible: false },
                { key: "invoice_amount_fc", label: "Invoice Amount FC",    visible: false },
                { key: "salesperson",       label: "Salesperson",          visible: false },
                { key: "sales_team",        label: "Sales Team",           visible: false },
                { key: "product_code",      label: "Product Code",         visible: false },
                { key: "product",           label: "Product",              visible: true  },
                { key: "label",             label: "Label",                visible: false },
                { key: "product_category",  label: "Product Category",     visible: false },
                { key: "product_type",      label: "Product Type",         visible: false },
                { key: "product_uom",       label: "Product UOM",          visible: false },
                { key: "payment_state",     label: "Payment State",        visible: true  },
                { key: "account_name",      label: "Account Name",         visible: false },
                { key: "journal_name",      label: "Journal Name",         visible: false },
                { key: "currency",          label: "Currency",             visible: false },
                { key: "sale_order_number", label: "Sale Order Number",    visible: false },
                { key: "sale_order_date",   label: "Sale Order Date",      visible: false },
                { key: "quantity",          label: "Quantity",             visible: true  },
                { key: "price",             label: "Price",                visible: true  },
                { key: "weight_per_unit",   label: "Weight Per Unit",      visible: false },
                { key: "total_weight",      label: "Total Weight",         visible: false },
                { key: "amount_excl_tax",   label: "Amount Exclusive Tax", visible: true  },
                { key: "tax",               label: "Tax",                  visible: true  },
                { key: "amount",            label: "Amount",               visible: false },
                { key: "amount_incl_tax",   label: "Amount Inclusive Tax", visible: true  },
                { key: "analytic_account",  label: "Analytic Account",     visible: false },
                { key: "customer_city",     label: "Customer City",        visible: false },
                { key: "customer_state",    label: "Customer State",       visible: false },
                { key: "customer_country",  label: "Customer Country",     visible: false },
                { key: "invoice_type",          label: "Invoice Type",          visible: false },
                { key: "tally_invoice_number",  label: "Tally Invoice No",      visible: false },
                { key: "distributor_item_name", label: "Distributor Item Name", visible: false },
                { key: "district",              label: "District",              visible: false },
                { key: "pincode",               label: "Pincode",               visible: false },
                { key: "document_type",         label: "Document Type",         visible: false },
                { key: "voucher_type",          label: "Voucher Type",          visible: false },
                { key: "avg_price",             label: "Avg Price",             visible: false },
            ],
        });

        onMounted(async () => { await this._load(); });

        onWillUpdateProps(async (nextProps) => {
            if (nextProps.dateFrom !== this.state.dateFrom ||
                nextProps.dateTo   !== this.state.dateTo) {
                this.state.dateFrom    = nextProps.dateFrom;
                this.state.dateTo      = nextProps.dateTo;
                this.state.draftFrom   = nextProps.dateFrom;
                this.state.draftTo     = nextProps.dateTo;
                this.state.page        = 1;
                await this._load();
            }
        });
    }


    // ── Pagination helpers ────────────────────────────────────────────────────
    get pageNums()   { return buildPageNums(this.state.totalPages, this.state.page); }
    isCurrentPage(p) { return p === this.state.page; }
    isPrevDisabled() { return this.state.page === 1; }
    isNextDisabled() { return this.state.page === this.state.totalPages; }

    get displayDateRange() {
        return `${this._fmtD(this.state.dateFrom)} - ${this._fmtD(this.state.dateTo)}`;
    }

    isViewActive(v) { return this.state.viewType === v; }
    isTabActive(t)  { return this.state.tab === t; }
    isPurchaseTab() { return this.state.tab === "purchase" || this.state.tab === "purchase_return"; }
    isPurchaseMode() {
        return this.state.tab === "purchase" || this.state.tab === "purchase_return";
    }

    get purchaseColumns() {
        return [
            { key: "bill_number",      label: "Bill Number",      visible: true  },
            { key: "bill_date",        label: "Bill Date",        visible: true  },
            { key: "vendor_code",      label: "Vendor Code",      visible: false },
            { key: "vendor",           label: "Vendor",           visible: true  },
            { key: "gst_no",           label: "GST No",           visible: false },
            { key: "vendor_ref",       label: "Vendor Ref",       visible: false },
            { key: "po_number",        label: "PO Number",        visible: true  },
            { key: "po_date",          label: "PO Date",          visible: false },
            { key: "product_code",     label: "Product Code",     visible: false },
            { key: "product",          label: "Product",          visible: true  },
            { key: "product_category", label: "Product Category", visible: false },
            { key: "product_uom",      label: "UOM",              visible: true  },
            { key: "payment_state",    label: "Payment State",    visible: true  },
            { key: "quantity",         label: "Quantity",         visible: true  },
            { key: "price",            label: "Price",            visible: true  },
            { key: "amount_excl_tax",  label: "Amt Excl Tax",     visible: true  },
            { key: "tax_amount",       label: "Tax",              visible: true  },
            { key: "amount_incl_tax",  label: "Amt Incl Tax",     visible: true  },
            { key: "vendor_city",      label: "Vendor City",      visible: false },
            { key: "vendor_state",     label: "Vendor State",     visible: false },
            { key: "account_name",     label: "Account Name",     visible: false },
            { key: "currency",         label: "Currency",         visible: false },
            { key: "company",          label: "Company",          visible: false },
            { key: "invoice_type",     label: "Type",             visible: false },
        ];
    }

    get activeColumns() {
        if (this.isPurchaseMode()) return this.purchaseColumns.filter(c => c.visible);
        return this.state.columns.filter(c => c.visible);
    }

    get filteredColsList() {
        const q = (this.state.colSearch || "").toLowerCase();
        const cols = this.isPurchaseMode() ? this.purchaseColumns : this.state.columns;
        return q ? cols.filter(c => c.label.toLowerCase().includes(q)) : cols;
    }

    fmtNum(v) { return fmt(v); }


    // ── Column visibility helpers (all now read from this.state.columns) ──────
    get visibleCols() {
        return this.state.columns.filter(c => c.visible);
    }

    get filteredCols() {
        const q = (this.state.colSearch || "").toLowerCase();
        const cols = this.isPurchaseMode() ? this.purchaseColumns : this.state.columns;
        return q ? cols.filter(c => c.label.toLowerCase().includes(q)) : cols;
    }

    isColVisible(key) {
        if (this.isPurchaseMode()) {
            const col = this.purchaseColumns.find(c => c.key === key);
            return col ? col.visible : false;
        }
        const c = this.state.columns.find(c => c.key === key);
        return c ? c.visible : true;
    }

    toggleColMenu(ev) {
        if (ev) ev.stopPropagation();
        if (!this.state.colMenuOpen) {
            // Calculate position from the button
            const btn = ev.currentTarget;
            const rect = btn.getBoundingClientRect();
            this.state.colMenuTop  = rect.bottom + 6;
            this.state.colMenuRight = window.innerWidth - rect.right;
        }
        this.state.colMenuOpen = !this.state.colMenuOpen;
    }

    closeColMenu() {
        this.state.colMenuOpen = false;
    }

    toggleCol(key) {
        const c = this.state.columns.find(c => c.key === key);
        if (c) c.visible = !c.visible;
    }

    onColSearch(ev) {
        this.state.colSearch = ev.target.value;
    }

    showAllCols() {
        this.state.columns.forEach(c => c.visible = true);
    }

    resetCols() {
        const def = [
            "invoice_number", "invoice_date", "customer", "product",
            "payment_state", "quantity", "price", "amount_excl_tax",
            "tax", "amount_incl_tax",
        ];
        this.state.columns.forEach(c => c.visible = def.includes(c.key));
    }

    async dlExcel() {
        const vis = this.visibleCols;
        this.state.loading = true;
        try {
            // Step 1: get total line count with per_page=1
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
            if (!totalLines) {
                alert("No data to download.");
                return;
            }

            // Step 2: fetch all lines in safe-sized chunks instead of one
            // giant request. A single request for thousands of rows can
            // time out or have its connection dropped — chunking keeps
            // each individual HTTP call small and fast, and partial
            // progress (already-fetched chunks) is never lost even if a
            // later chunk is slow.
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
            const body    = allRows.map(r =>
                vis.map(c => {
                    const v = r[c.key] != null ? String(r[c.key]) : "";
                    return v.includes(",") || v.includes('"') || v.includes("\n")
                        ? `"${v.replace(/"/g, '""')}"` : v;
                }).join(",")
            ).join("\n");

            const bom  = "\uFEFF";
            const blob = new Blob([bom + header + "\n" + body], { type: "text/csv;charset=utf-8;" });
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement("a");
            a.href     = url;
            a.download = `dayview_${this.state.tab}_${this.state.dateFrom}_${this.state.dateTo}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

        } catch(e) {
            console.error("Download failed:", e);
            alert("Download failed: " + (e.message || "Unknown error"));
        } finally {
            this.state.loading = false;
        }
    }


    // ── Data loading ──────────────────────────────────────────────────────────
    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/dayview", {
                date_from: this.state.dateFrom,
                date_to:   this.state.dateTo,
                view_type: this.state.viewType,
                tab:       this.state.tab,
                page:      this.state.page,
                per_page:  PER_PAGE,
                sort_col:  this.state.sortCol,
                sort_dir:  this.state.sortDir,
                search:    this.state.search,
            });
            this.state.rows       = res.rows        || [];
            this.state.summary    = res.summary     || { bill_count: 0, total_qty: 0, tax_less: 0, tax_paid: 0 };
            this.state.total      = res.total       || 0;
            this.state.totalPages = res.total_pages || 1;
            this.state.page       = res.page        || 1;
        } catch (e) {
            console.error("DayView load error:", e);
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }


    // ── View / tab switching ──────────────────────────────────────────────────
    async setView(v) {
        if (this.state.viewType === v) return;
        this.state.viewType = v;
        this.state.tab      = "sales";
        this.state.page     = 1;
        await this._load();
    }

    async setTab(t) {
        if (this.state.tab === t) return;
        this.state.tab  = t;
        this.state.page = 1;
        await this._load();
    }


    // ── Sorting ───────────────────────────────────────────────────────────────
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


    // ── Pagination ────────────────────────────────────────────────────────────
    async prevPage() {
        if (this.state.page > 1) { this.state.page--; await this._load(); }
    }

    async nextPage() {
        if (this.state.page < this.state.totalPages) { this.state.page++; await this._load(); }
    }

    async goPage(p) {
        if (typeof p === "number" && p !== this.state.page) {
            this.state.page = p;
            await this._load();
        }
    }


    // ── Date picker ───────────────────────────────────────────────────────────
    openPicker() {
        this.state.draftFrom  = this.state.dateFrom;
        this.state.draftTo    = this.state.dateTo;
        this.state.pickerOpen = true;
    }

    closePicker() { this.state.pickerOpen = false; }

    onFromChange(ev) { this.state.draftFrom = ev.target.value; }
    onToChange(ev)   { this.state.draftTo   = ev.target.value; }

    async applyDates() {
        if (!this.state.draftFrom || !this.state.draftTo) return;
        this.state.dateFrom   = this.state.draftFrom;
        this.state.dateTo     = this.state.draftTo;
        this.state.page       = 1;
        this.state.pickerOpen = false;
        await this._load();
    }


    // ── Navigation ────────────────────────────────────────────────────────────
    goBack() { this.props.onBack(); }


    // ── Utilities ─────────────────────────────────────────────────────────────
    _fmtD(s) {
        if (!s) return "";
        const [y, m, d] = s.split("-");
        const mo = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"];
        return `${d}-${mo[parseInt(m, 10) - 1]}-${y}`;
    }
}