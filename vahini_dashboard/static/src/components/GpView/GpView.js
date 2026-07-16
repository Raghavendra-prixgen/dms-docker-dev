/** @odoo-module **/
import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const PER_PAGE = 50;
const PIE_COLORS = [
    "#f59e0b","#3b82f6","#22c55e","#ef4444","#8b5cf6",
    "#06b6d4","#f97316","#84cc16","#ec4899","#14b8a6",
    "#6366f1","#a78bfa","#fb923c","#34d399","#60a5fa",
];
const GROUP_OPTIONS = [
    { value:"item_name",    label:"Item Name"     },
    { value:"item_group",   label:"Item Group"    },
    { value:"item_alias",   label:"Item Alias"    },
    { value:"district",     label:"District"      },
    { value:"godown_name",  label:"Godown Name"   },
    { value:"document_type",label:"Document Type" },
    { value:"gstno",        label:"Gstno"         },
    { value:"im9",          label:"Im 9"          },
];

export class GpView extends Component {
    static template = "vahini_dashboard.GpView";
    static props = { dateFrom: String, dateTo: String };

    setup() {
        this.state = useState({
            loading:     true,
            groupBy:     "item_name",
            groupOpen:   false,
            search:      "",
            pieData:     [],
            rows:        [],
            page:        1,
            totalPages:  1,
            total:       0,
            kpis:        {},
            hoveredPie:  null,
            sortCol:     "value",
            sortDir:     "desc",
        });
        this.pieColors = PIE_COLORS;
        this.groupOptions = GROUP_OPTIONS;
        onMounted(async () => { await this._load(); });
        onWillUpdateProps(async (np) => {
            if (np.dateFrom !== this.props.dateFrom || np.dateTo !== this.props.dateTo) {
                await this._load(np.dateFrom, np.dateTo);
            }
        });
    }

    async _load(df, dt) {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/gpview", {
                date_from: df || this.props.dateFrom,
                date_to:   dt || this.props.dateTo,
                group_by:  this.state.groupBy,
                search:    this.state.search,
                page:      this.state.page,
                per_page:  PER_PAGE,
            });
            this.state.pieData    = res.pie_data    || [];
            this.state.rows       = res.rows        || [];
            this.state.total      = res.total       || 0;
            this.state.totalPages = res.total_pages || 1;
            this.state.page       = res.page        || 1;
            this.state.kpis       = res.kpis        || {};
        } catch(e) {
            console.error("GpView error:", e);
        } finally {
            this.state.loading = false;
        }
    }

    async setGroupBy(v) {
        this.state.groupBy   = v;
        this.state.groupOpen = false;
        this.state.page      = 1;
        await this._load();
    }

    toggleGroupDD() { this.state.groupOpen = !this.state.groupOpen; }

    get groupLabel() {
        return this.groupOptions.find(o => o.value === this.state.groupBy)?.label || "Item Name";
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._st);
        this._st = setTimeout(async () => { this.state.page=1; await this._load(); }, 400);
    }

    sortBy(col) {
        this.state.sortDir = this.state.sortCol===col ? (this.state.sortDir==="asc"?"desc":"asc") : "desc";
        this.state.sortCol = col;
        this.state.rows = [...this.state.rows].sort((a,b) => {
            return this.state.sortDir === "asc" ? a[col]-b[col] : b[col]-a[col];
        });
    }

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
    async goPage(p) { if(typeof p==="number"){ this.state.page=p; await this._load(); } }
    async prevPage() { if(this.state.page>1){ this.state.page--; await this._load(); } }
    async nextPage() { if(this.state.page<this.state.totalPages){ this.state.page++; await this._load(); } }

    // ── Pie chart SVG ─────────────────────────────────────────────────────
    get pieSlices() {
        const data = this.state.pieData;
        if (!data.length) return [];
        const total = data.reduce((s,d) => s + d.value, 0);
        if (!total) return [];

        // Single item — draw a full circle
        if (data.length === 1) {
            const d = data[0];
            const cx=160, cy=160, r=140;
            return [{
                path:  `M${cx},${cy-r} A${r},${r} 0 1,1 ${cx-0.001},${cy-r} Z`,
                color: PIE_COLORS[0],
                label: d.label, value: d.value, pct: 100,
            }];
        }

        const cx=160, cy=160, r=140, ir=0;
        let angle = -Math.PI / 2;
        return data.map((d, i) => {
            const pct    = d.value / total;
            const sweep  = pct * 2 * Math.PI;
            const x1     = cx + r * Math.cos(angle);
            const y1     = cy + r * Math.sin(angle);
            angle       += sweep;
            const x2     = cx + r * Math.cos(angle);
            const y2     = cy + r * Math.sin(angle);
            const large  = sweep > Math.PI ? 1 : 0;
            const path   = ir === 0
                ? `M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${large},1 ${x2},${y2} Z`
                : `M${x1},${y1} A${r},${r} 0 ${large},1 ${x2},${y2} L${cx+ir*Math.cos(angle)},${cy+ir*Math.sin(angle)} A${ir},${ir} 0 ${large},0 ${cx+ir*Math.cos(angle-sweep)},${cy+ir*Math.sin(angle-sweep)} Z`;
            return { path, color: PIE_COLORS[i % PIE_COLORS.length], label: d.label, value: d.value, pct: Math.round(pct*100) };
        });
    }

    onPieHover(slice) { this.state.hoveredPie = slice; }
    onPieLeave()      { this.state.hoveredPie = null; }

    // ── Download ──────────────────────────────────────────────────────────
    downloadPDF() {
        let html=`<html><head><style>body{font-family:Arial;font-size:10px;padding:20px;}h2{color:#1e293b;}table{width:100%;border-collapse:collapse;}th{background:#1e3a5f;color:#fff;padding:6px 8px;}td{padding:5px 8px;border-bottom:1px solid #e2e8f0;}.num{text-align:right;}</style></head><body>
<h2>GP View — Gross Profit Report</h2>
<table><thead><tr><th>Bill No</th><th class="num">Value</th><th class="num">Gross Profit</th><th class="num">GP%</th><th class="num">Contr%</th></tr></thead><tbody>`;
        for(const r of this.state.rows)
            html+=`<tr><td>${r.bill_no}</td><td class="num">${this.fmt(r.value)}</td><td class="num">${this.fmt(r.gross_profit)}</td><td class="num">${r.gp_pct}</td><td class="num">${r.contr_pct}</td></tr>`;
        html+=`</tbody></table></body></html>`;
        const w=window.open("","_blank"); w.document.write(html); w.document.close();
        setTimeout(()=>{w.print();w.close();},400);
    }

    fmt(v) {
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
    sortIcon(col) {
        if(this.state.sortCol!==col) return "⇅";
        return this.state.sortDir==="asc" ? "↑" : "↓";
    }
}
