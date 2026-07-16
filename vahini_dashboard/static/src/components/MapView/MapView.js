/** @odoo-module **/

import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

export class MapView extends Component {
    static template = "vahini_dashboard.MapView";
    static props = { dateFrom: String, dateTo: String };

    setup() {
        this.state = useState({
            loading:    true,
            viewMode:   "trend",
            moveType:   "out_invoice",
            kpis:       { billed:0, unbilled:0, inactive:0, lost:0 },
            stateData:  {},
            stateRows:  [],
            maxVal:     1,
            hovered:    null,
        });
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
            const res = await rpc("/vahini_dashboard/mapview", {
                date_from: df || this.props.dateFrom,
                date_to:   dt || this.props.dateTo,
                move_type: this.state.moveType,
            });
            this.state.kpis      = res.kpis       || { billed:0, unbilled:0, inactive:0, lost:0 };
            this.state.stateData = res.state_data  || {};
            this.state.stateRows = res.state_rows  || [];
            const vals = Object.values(res.state_data || {}).filter(v => v > 0);
            this.state.maxVal    = vals.length ? Math.max(...vals) : 1;
        } catch(e) {
            console.error("MapView load error:", e);
        } finally {
            this.state.loading = false;
        }
    }

    async setMoveType(t) {
        if (this.state.moveType === t) return;
        this.state.moveType = t;
        await this._load();
    }

    setViewMode(m) { this.state.viewMode = m; }

    get topStates() {
        return Object.entries(this.state.stateData)
            .sort((a,b) => b[1]-a[1]).slice(0,10);
    }

    get totalSalesFormatted() {
        return this.fmt(Object.values(this.state.stateData).reduce((a,b)=>a+b,0));
    }

    get sortedRows() {
        return [...this.state.stateRows].sort((a,b) => b.tax_less - a.tax_less);
    }

    intensity(name) {
        const v = this.state.stateData[name] || 0;
        return v > 0 ? v / this.state.maxVal : 0;
    }

    fillColor(name) {
        const t = this.intensity(name);
        if (t === 0) return "#334155";
        const r = Math.round(20  + (34  - 20)  * (1-t));
        const g = Math.round(83  + (197 - 83)  * t);
        const b = Math.round(45  + (94  - 45)  * (1-t));
        return `rgb(${r},${g},${b})`;
    }

    stateLabel(name) {
        const m = this.state.viewMode;
        // Name mode: always show state name
        if (m === "name") return name;
        const row = this.state.stateRows.find(r => r.state === name);
        if (!row) return "0 | 0";
        if (m === "count") return `${row.cust_count} | ${row.inv_count}`;
        if (m === "trend") return this.fmt(row.tax_less);
        return "";
    }

    stateLabelX(name) {
        // Approximate center X for label - use centroid heuristic
        return "50%";
    }

    onStateHover(ev, name) {
        const row  = this.state.stateRows.find(r => r.state === name) || {};
        const rect = ev.currentTarget.closest("svg").getBoundingClientRect();
        this.state.hovered = {
            name,
            tax_less: row.tax_less   || 0,
            tax_paid: row.tax_paid   || 0,
            qty:      row.qty        || 0,
            cust:     row.cust_count || 0,
            inv:      row.inv_count  || 0,
            x: ev.clientX - rect.left + 12,
            y: ev.clientY - rect.top  - 55,
        };
    }

    onStateLeave() { this.state.hovered = null; }

    fmt(v) {
        const n = parseFloat(v) || 0;
        if (n >= 10000000) return (n/10000000).toFixed(2) + " Cr";
        if (n >= 100000)   return (n/100000).toFixed(2)   + " L";
        if (n >= 1000)     return (n/1000).toFixed(1)     + " K";
        return n.toLocaleString("en-IN", {maximumFractionDigits:0});
    }

    fmtFull(v) {
        return (parseFloat(v)||0).toLocaleString("en-IN", {maximumFractionDigits:2});
    }

    fmtKpi(v) {
        return typeof v === "number" ? v.toLocaleString("en-IN") : "0";
    }

    downloadPDF() {
        const label = this.state.moveType === "out_invoice" ? "Sales" : "Purchase";
        let html = `<html><head><style>
body{font-family:Arial,sans-serif;font-size:11px;padding:20px;}
h2{color:#1e293b;margin-bottom:4px;}p{color:#64748b;margin:0 0 12px;}
table{width:100%;border-collapse:collapse;}
th{background:#1e3a5f;color:#fff;padding:7px 10px;text-align:left;font-size:10px;}
td{padding:6px 10px;border-bottom:1px solid #e2e8f0;}
tr:nth-child(even) td{background:#f8fafc;}.num{text-align:right;}
</style></head><body>
<h2>Map View — ${label} Register</h2>
<p>Period: ${this.props.dateFrom} to ${this.props.dateTo}</p>
<table><thead><tr>
<th>State</th><th class="num">Customers</th><th class="num">Pincodes</th>
<th class="num">Qty</th><th class="num">TaxLess</th><th class="num">TaxPaid</th>
</tr></thead><tbody>`;
        for (const r of this.sortedRows) {
            html += `<tr><td>${r.state}</td>
<td class="num">${r.cust_count}</td><td class="num">${r.pin_count}</td>
<td class="num">${this.fmtFull(r.qty)}</td>
<td class="num">&#8377; ${this.fmtFull(r.tax_less)}</td>
<td class="num">&#8377; ${this.fmtFull(r.tax_paid)}</td></tr>`;
        }
        html += `</tbody></table></body></html>`;
        const w = window.open("","_blank");
        w.document.write(html);
        w.document.close();
        setTimeout(() => { w.print(); w.close(); }, 400);
    }
}
