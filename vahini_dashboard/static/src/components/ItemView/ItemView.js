/** @odoo-module **/
import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const PER_PAGE = 50;
const ALL_COLUMNS = [
    { key:"item_name",  label:"Item Name",   fixed:true,  enabled:true },
    { key:"stock_qty",  label:"Stock Qty",   fixed:false, enabled:true },
    { key:"stock_val",  label:"Stock Val",   fixed:false, enabled:true },
    { key:"avg",        label:"Avg (6)",     fixed:false, enabled:true },
    { key:"sales",      label:"Sales",       fixed:false, enabled:true },
    { key:"interest",   label:"Interest",    fixed:false, enabled:true },
];
const EXTRA_COLUMNS = [
    "Ageing","Batch Tracking No","Category","Company Name","Conversion",
    "Days To Expire","Godown Name","Im 9","Item Alias","Item Group","Item Name",
    "Item Names","Last Billed Date","Last Purchase Date","LBD","LPD","MOQ","Mrps",
    "MSQ","Part No","Product Category","Product Group","Scheme","Subcategory",
    "Tim 10","Tim 20","Units Of Measurement","Vendor","Voucher Type","Weight",
];

export class ItemView extends Component {
    static template = "vahini_dashboard.ItemView";
    static props = { dateFrom: String, dateTo: String };

    setup() {
        this.state = useState({
            loading:      true,
            tab:          "all",
            search:       "",
            rows:         [],
            page:         1,
            totalPages:   1,
            total:        0,
            kpis:         {},
            // Filter popup
            filterOpen:   false,
            filters: {
                stock_qty:    { op:"", val:"" },
                stock_val:    { op:"", val:"" },
                sales:        { op:"", val:"" },
                interest:     { op:"", val:"" },
                expiry_days:  "",
                expiry_before:"",
            },
            activeFilters: [],
            // Column chooser popup
            colOpen:      false,
            columns:      ALL_COLUMNS.map(c=>({...c})),
            colSearch:    "",
            // Include 0 total stocks
            includeZero:  false,
        });
        this.allExtraColumns = EXTRA_COLUMNS;
        onMounted(async () => { await this._load(); });
        onWillUpdateProps(async () => { await this._load(); });
    }

    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/itemview", {
                tab:      this.state.tab,
                search:   this.state.search,
                page:     this.state.page,
                per_page: PER_PAGE,
                filters:  this._buildFilters(),
            });
            this.state.rows       = res.rows       || [];
            this.state.total      = res.total      || 0;
            this.state.totalPages = res.total_pages || 1;
            this.state.page       = res.page       || 1;
            this.state.kpis       = res.kpis       || {};
        } catch(e) {
            console.error("ItemView error:", e);
        } finally {
            this.state.loading = false;
        }
    }

    _buildFilters() {
        const f = {};
        for (const key of ['stock_qty','stock_val','sales','interest']) {
            const v = this.state.filters[key];
            if (v.op && v.val) f[key] = { op: v.op, val: v.val };
        }
        if (this.state.filters.expiry_days)   f.expiry_days   = this.state.filters.expiry_days;
        if (this.state.filters.expiry_before) f.expiry_before = this.state.filters.expiry_before;
        return f;
    }

    async setTab(t) { this.state.tab=t; this.state.page=1; await this._load(); }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._st);
        this._st = setTimeout(async()=>{ this.state.page=1; await this._load(); }, 400);
    }

    get visibleColumns() { return this.state.columns.filter(c=>c.enabled); }

    get pageNums() {
        const t=this.state.totalPages, c=this.state.page;
        if(t<=7) return Array.from({length:t},(_,i)=>i+1);
        const p=[1];
        if(c>3) p.push("...");
        for(let i=Math.max(2,c-1);i<=Math.min(t-1,c+1);i++) p.push(i);
        if(c<t-2) p.push("...");
        p.push(t);
        return p;
    }
    async goPage(p){ if(typeof p==="number"){ this.state.page=p; await this._load(); } }
    async prevPage(){ if(this.state.page>1){ this.state.page--; await this._load(); } }
    async nextPage(){ if(this.state.page<this.state.totalPages){ this.state.page++; await this._load(); } }

    // ── Filters ───────────────────────────────────────────────────────────
    openFilter()  { this.state.filterOpen = true; }
    closeFilter() { this.state.filterOpen = false; }

    setFilterOp(field, ev)  { this.state.filters[field].op  = ev.target.value; }
    setFilterVal(field, ev) { this.state.filters[field].val = ev.target.value; }
    setExpiryDays(ev)       { this.state.filters.expiry_days   = ev.target.value; }
    setExpiryBefore(ev)     { this.state.filters.expiry_before = ev.target.value; }

    resetFilters() {
        this.state.filters = {
            stock_qty:{op:"",val:""}, stock_val:{op:"",val:""},
            sales:{op:"",val:""}, interest:{op:"",val:""},
            expiry_days:"", expiry_before:"",
        };
        this.state.activeFilters = [];
    }

    async applyFilters() {
        const active = [];
        for(const k of ['stock_qty','stock_val','sales','interest']) {
            const v=this.state.filters[k];
            if(v.op && v.val) active.push(`${k} ${v.op} ${v.val}`);
        }
        if(this.state.filters.expiry_days) active.push(`Expiry ≤ ${this.state.filters.expiry_days}d`);
        if(this.state.filters.expiry_before) active.push(`Expiry before ${this.state.filters.expiry_before}`);
        this.state.activeFilters = active;
        this.state.filterOpen = false;
        this.state.page = 1;
        await this._load();
    }

    get filterCount() { return this.state.activeFilters.length; }

    // ── Column chooser ────────────────────────────────────────────────────
    openCols()  { this.state.colOpen = true; }
    closeCols() { this.state.colOpen = false; }
    onColSearch(ev) { this.state.colSearch = ev.target.value; }

    get filteredExtraCols() {
        const q = this.state.colSearch.toLowerCase();
        return q ? this.allExtraColumns.filter(c=>c.toLowerCase().includes(q)) : this.allExtraColumns;
    }

    toggleCol(key) {
        const col = this.state.columns.find(c=>c.key===key);
        if(col && !col.fixed) col.enabled = !col.enabled;
    }

    async applyCols() { this.state.colOpen = false; await this._load(); }

    // ── Download ──────────────────────────────────────────────────────────
    downloadPDF() {
        const cols = this.visibleColumns;
        let html=`<html><head><style>body{font-family:Arial;font-size:10px;padding:20px;}h2{color:#1e293b;}table{width:100%;border-collapse:collapse;}th{background:#1e3a5f;color:#fff;padding:6px 8px;}td{padding:5px 8px;border-bottom:1px solid #e2e8f0;}.num{text-align:right;}</style></head><body>
<h2>Item View — Stock Ageing Report</h2>
<table><thead><tr>${cols.map(c=>`<th>${c.label}</th>`).join('')}</tr></thead><tbody>`;
        for(const r of this.state.rows) {
            html+=`<tr>${cols.map(c=>`<td class="${c.key!=='item_name'?'num':''}">${this.fmt(r[c.key])}</td>`).join('')}</tr>`;
        }
        html+=`</tbody></table></body></html>`;
        const w=window.open("","_blank"); w.document.write(html); w.document.close();
        setTimeout(()=>{w.print();w.close();},400);
    }

    // ── Format ────────────────────────────────────────────────────────────
    fmt(v) {
        if(v===null||v===undefined) return "";
        if(typeof v==="string") return v;
        const n=parseFloat(v)||0;
        if(!n) return "0";
        return n.toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:2});
    }
    fmtKpi(v) {
        const n=parseFloat(v)||0;
        if(Math.abs(n)>=10000000) return (n/10000000).toFixed(2)+" Cr";
        if(Math.abs(n)>=100000)   return (n/100000).toFixed(2)+" L";
        return n.toLocaleString("en-IN",{maximumFractionDigits:0});
    }
}
