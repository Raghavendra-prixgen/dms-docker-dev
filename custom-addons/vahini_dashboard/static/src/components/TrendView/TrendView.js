/** @odoo-module **/
import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const PER_PAGE = 20;

const GROUP_OPTIONS = [
    { value: "customer",          label: "Customer Name" },
    { value: "item_name",         label: "Item Name" },
    { value: "category",          label: "Product Category" },
    { value: "area",              label: "City / Area" },
    { value: "state",             label: "State" },
    { value: "district",          label: "District" },
    { value: "salesperson",       label: "Salesperson" },
    { value: "sales_team",        label: "Sales Team" },
    { value: "gstno",             label: "GST No" },
    { value: "voucher_type",      label: "Voucher Type" },
    { value: "document_type",     label: "Document Type" },
    { value: "company_name",      label: "Company" },
];

const MONTHS = [
    {num:4,label:"April"},{num:5,label:"May"},{num:6,label:"June"},
    {num:7,label:"July"},{num:8,label:"August"},{num:9,label:"September"},
    {num:10,label:"October"},{num:11,label:"November"},{num:12,label:"December"},
    {num:1,label:"January"},{num:2,label:"February"},{num:3,label:"March"},
];

export class TrendView extends Component {
    static template = "vahini_dashboard.TrendView";
    static props = { dateFrom: String, dateTo: String };

    setup() {
        this.groupOptions = GROUP_OPTIONS;
        this.allMonths = MONTHS;
        const now = new Date();
        const fy = now.getMonth() >= 3
            ? `${now.getFullYear()}-${now.getFullYear()+1}`
            : `${now.getFullYear()-1}-${now.getFullYear()}`;

        this.state = useState({
            loading:      true,
            reportType:   "sales",
            fiscalYear:   fy,
            period:       "monthly",
            selectedMonths: new Set(MONTHS.map(m => m.num)),
            monthDropOpen: false,
            groupBy:      "customer",
            groupDropOpen: false,
            cityFilter:   null,
            citySearch:   "",
            search:       "",
            rows:         [],
            activeMonths: [],
            colTotals:    {},
            grandTotal:   0,
            page:         1,
            totalPages:   1,
            total:        0,
            cities:       [],
            filteredCities: [],
        });
        onMounted(async () => { await this._load(); });
        onWillUpdateProps(async (np) => {
            if (np.dateFrom !== this.props.dateFrom || np.dateTo !== this.props.dateTo)
                await this._load();
        });
    }

    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/trendview", {
                report_type:   this.state.reportType,
                fiscal_year:   this.state.fiscalYear,
                period:        this.state.period,
                months:        [...this.state.selectedMonths],
                group_by:      this.state.groupBy,
                city_filter:   this.state.cityFilter,
                search:        this.state.search,
                page:          this.state.page,
                per_page:      PER_PAGE,
            });
            this.state.rows         = res.rows         || [];
            this.state.activeMonths = res.active_months|| [];
            this.state.colTotals    = res.col_totals   || {};
            this.state.grandTotal   = res.grand_total  || 0;
            this.state.total        = res.total        || 0;
            this.state.totalPages   = res.total_pages  || 1;
            this.state.page         = res.page         || 1;
            if (res.cities) {
                this.state.cities = res.cities;
                this._filterCities();
            }
        } catch(e) { console.error("TrendView error:", e); }
        finally   { this.state.loading = false; }
    }

    _filterCities() {
        const q = this.state.citySearch.toLowerCase();
        this.state.filteredCities = q
            ? this.state.cities.filter(c => c.toLowerCase().includes(q))
            : [...this.state.cities];
    }

    // Fiscal year options
    get fyOptions() {
        const y = new Date().getFullYear();
        return [`${y-2}-${y-1}`, `${y-1}-${y}`, `${y}-${y+1}`, `${y+1}-${y+2}`];
    }

    get selectedMonthsLabel() {
        const sel = this.state.selectedMonths;
        if (sel.size === 12) return "All Months";
        if (sel.size === 0)  return "No Month";
        const months = this.allMonths || MONTHS;
        const first = months.find(m => sel.has(m.num));
        return first ? `${first.label} + ${sel.size-1} ...` : "";
    }

    get allMonthsList() { return this.allMonths || MONTHS; }
    get groupLabel() {
        const opt = GROUP_OPTIONS.find(o => o.value === this.state.groupBy);
        return opt ? opt.label : "Customer Name";
    }

    // Getters
    get pageNums() {
        const t=this.state.totalPages, c=this.state.page;
        if(t<=7) return Array.from({length:t},(_,i)=>i+1);
        const p=[1]; if(c>3) p.push("...");
        for(let i=Math.max(2,c-1);i<=Math.min(t-1,c+1);i++) p.push(i);
        if(c<t-2) p.push("..."); p.push(t); return p;
    }

    // Events
    async setReportType(t) { this.state.reportType=t; this.state.page=1; await this._load(); }
    async setFY(y)          { this.state.fiscalYear=y; this.state.page=1; await this._load(); }
    async setPeriod(p)      { this.state.period=p; this.state.page=1; await this._load(); }
    async setGroupBy(g)     { this.state.groupBy=g; this.state.groupDropOpen=false; this.state.page=1; await this._load(); }

    toggleMonth(n) {
        if (this.state.selectedMonths.has(n)) {
            if (this.state.selectedMonths.size > 1) this.state.selectedMonths.delete(n);
        } else {
            this.state.selectedMonths.add(n);
        }
    }

    async submit() { this.state.page=1; this.state.monthDropOpen=false; await this._load(); }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._st);
        this._st = setTimeout(async()=>{ this.state.page=1; await this._load(); }, 400);
    }

    onCitySearch(ev) { this.state.citySearch=ev.target.value; this._filterCities(); }

    async setCity(c) {
        this.state.cityFilter = this.state.cityFilter===c ? null : c;
        this.state.page=1; await this._load();
    }

    async goPage(p) { if(typeof p==="number"){ this.state.page=p; await this._load(); } }
    async prevPage() { if(this.state.page>1){ this.state.page--; await this._load(); } }
    async nextPage() { if(this.state.page<this.state.totalPages){ this.state.page++; await this._load(); } }

    // Formatting
    fmt(v) {
        const n=parseFloat(v)||0; if(!n) return "-";
        return n.toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:0});
    }
    fmtHeader(v) {
        const n=parseFloat(v)||0;
        if(Math.abs(n)>=100000) return (n/100000).toFixed(2)+" L";
        return n.toLocaleString("en-IN",{maximumFractionDigits:0});
    }
    cellCls(v) { return parseFloat(v)<0 ? "tvw-neg" : ""; }

    downloadPDF() {
        const cols = this.state.activeMonths;
        let html=`<html><head><style>body{font-family:Arial;font-size:9px;padding:12px;}h2{color:#1e293b;}table{width:100%;border-collapse:collapse;}th{background:#1e3a5f;color:#fff;padding:5px 7px;}td{padding:4px 7px;border-bottom:1px solid #e2e8f0;}.num{text-align:right;}</style></head><body><h2>Trend View — ${this.state.reportType}</h2><table><thead><tr><th>Name</th>${cols.map(m=>`<th class="num">${m.label}</th>`).join('')}<th class="num">Total</th></tr></thead><tbody>`;
        for(const r of this.state.rows)
            html+=`<tr><td>${r.label}</td>${cols.map(m=>`<td class="num">${this.fmt(r.months[m.year+'_'+m.month])}</td>`).join('')}<td class="num">${this.fmt(r.total)}</td></tr>`;
        html+=`</tbody></table></body></html>`;
        const w=window.open("","_blank"); w.document.write(html); w.document.close();
        setTimeout(()=>{w.print();w.close();},400);
    }
}
