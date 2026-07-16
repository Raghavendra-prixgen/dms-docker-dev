/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUpdateProps, onPatched, onWillUnmount } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { buildPageNums } from "../../js/utils";

const PER_PAGE = 10;

const PRESETS = [
    { label: "Today",          key: "today" },
    { label: "Yesterday",      key: "yesterday" },
    { label: "This Week",      key: "this_week" },
    { label: "This Month",     key: "this_month" },
    { label: "Last Month",     key: "last_month" },
    { label: "Last 3 Months",  key: "last_3m" },
    { label: "Last 6 Months",  key: "last_6m" },
    { label: "This Year",      key: "this_year" },
    { label: "Last Year",      key: "last_year" },
    { label: "Custom Range",   key: "custom" },
];

export class CompareModal extends Component {
    static template = "vahini_dashboard.CompareModal";
    static props = {
        def:      Object,
        pageData: Array,
        type:     String,
        onClose:  Function,
        dateFrom: String,
        dateTo:   String,
    };

    setup() {
        this.canvas1 = useRef("cmpCanvas1");
        this.canvas2 = useRef("cmpCanvas2");
        this._charts = [];
        this.presets = PRESETS;

        const { prevFrom, prevTo } = this._prevPeriod(
            this.props.dateFrom, this.props.dateTo
        );

        this.state = useState({
            chartType:  this.props.type === "table" ? "bar" : this.props.type,
            page:       1,
            totalPages: 1,
            loading:    true,
            currData:   [],
            prevData:   [],

            // Applied date ranges
            currFrom: this.props.dateFrom,
            currTo:   this.props.dateTo,
            prevFrom,
            prevTo,

            // Panel 1 picker
            currPickerOpen:   false,
            currDraftFrom:    this.props.dateFrom,
            currDraftTo:      this.props.dateTo,
            currActivePreset: "custom",

            prevPickerOpen:   false,
            prevDraftFrom:    prevFrom,
            prevDraftTo:      prevTo,
            prevActivePreset: "custom",
        });

        onMounted(async () => { await this._load(); });
        onWillUpdateProps(async () => { await this._load(); });

        onPatched(() => {
            if (!this.state.loading) {
                Promise.resolve().then(() => this._drawCharts());
            }
        });

        onWillUnmount(() => this._destroyCharts());
    }


    get currLabel() {
        return `${this._fmtD(this.state.currFrom)} – ${this._fmtD(this.state.currTo)}`;
    }
    get prevLabel() {
        return `${this._fmtD(this.state.prevFrom)} – ${this._fmtD(this.state.prevTo)}`;
    }


    get pageNums()   { return buildPageNums(this.state.totalPages, this.state.page); }
    isCurrentPage(p) { return p === this.state.page; }
    isPrevDisabled() { return this.state.page === 1; }
    isNextDisabled() { return this.state.page === this.state.totalPages; }
    isActiveType(t)  { return this.state.chartType === t; }


    openCurrPicker() {
        this.state.currDraftFrom  = this.state.currFrom;
        this.state.currDraftTo    = this.state.currTo;
        this.state.prevPickerOpen = false;
        this.state.currPickerOpen = true;
    }
    closeCurrPicker() { this.state.currPickerOpen = false; }

    onCurrFromChange(ev) {
        this.state.currDraftFrom  = ev.target.value;
        this.state.currActivePreset = "custom";
    }
    onCurrToChange(ev) {
        this.state.currDraftTo    = ev.target.value;
        this.state.currActivePreset = "custom";
    }

    selectCurrPreset(key) {
        const { from, to } = this._resolvePreset(key);
        this.state.currDraftFrom    = from;
        this.state.currDraftTo      = to;
        this.state.currActivePreset = key;
    }

    async applyCurrDates() {
        if (!this.state.currDraftFrom || !this.state.currDraftTo) return;
        this.state.currFrom       = this.state.currDraftFrom;
        this.state.currTo         = this.state.currDraftTo;
        this.state.currPickerOpen = false;
        this.state.page           = 1;
        await this._load();
    }

    isCurrPresetActive(key) { return this.state.currActivePreset === key; }


    openPrevPicker() {
        this.state.prevDraftFrom  = this.state.prevFrom;
        this.state.prevDraftTo    = this.state.prevTo;
        this.state.currPickerOpen = false;
        this.state.prevPickerOpen = true;
    }
    closePrevPicker() { this.state.prevPickerOpen = false; }

    onPrevFromChange(ev) {
        this.state.prevDraftFrom    = ev.target.value;
        this.state.prevActivePreset = "custom";
    }
    onPrevToChange(ev) {
        this.state.prevDraftTo      = ev.target.value;
        this.state.prevActivePreset = "custom";
    }

    selectPrevPreset(key) {
        const { from, to } = this._resolvePreset(key);
        this.state.prevDraftFrom    = from;
        this.state.prevDraftTo      = to;
        this.state.prevActivePreset = key;
    }

    async applyPrevDates() {
        if (!this.state.prevDraftFrom || !this.state.prevDraftTo) return;
        this.state.prevFrom       = this.state.prevDraftFrom;
        this.state.prevTo         = this.state.prevDraftTo;
        this.state.prevPickerOpen = false;
        this.state.page           = 1;
        await this._load();
    }

    isPrevPresetActive(key) { return this.state.prevActivePreset === key; }


    setType(type) {
        this.state.chartType = type;
        Promise.resolve().then(() => this._drawCharts());
    }


    async prevPage() {
        if (this.state.page > 1) { this.state.page--; await this._load(); }
    }
    async nextPage() {
        if (this.state.page < this.state.totalPages) { this.state.page++; await this._load(); }
    }
    async goPage(p) {
        if (typeof p === "number" && p !== this.state.page) {
            this.state.page = p; await this._load();
        }
    }


    close() { this.props.onClose(); }

    onOverlayClick(ev) {
        if (ev.target === ev.currentTarget) this.close();
    }


    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/compare", {
                chart_id:  this.props.def.id,
                date_from: this.state.currFrom,
                date_to:   this.state.currTo,
                prev_from: this.state.prevFrom,
                prev_to:   this.state.prevTo,
                page:      this.state.page,
                per_page:  PER_PAGE,
            });
            this.state.currData   = res.curr        || [];
            this.state.prevData   = res.prev        || [];
            this.state.totalPages = res.total_pages || 1;
            this.state.page       = res.page        || 1;
        } catch (e) {
            console.error("CompareModal RPC error:", e);
        } finally {
            this.state.loading = false;
            await new Promise(r => setTimeout(r, 0));
            this._drawCharts();
        }
    }


    _destroyCharts() {
        this._charts.forEach(c => { try { c.destroy(); } catch (_) {} });
        this._charts = [];
    }

    _drawCharts() {
        this._destroyCharts();
        if (!window.Chart || this.state.loading) return;

        const type = this.state.chartType;
        const grid = { color: "rgba(0,0,0,.06)", borderDash: [4, 4] };

        [[this.canvas1.el, this.state.currData],
         [this.canvas2.el, this.state.prevData]].forEach(([canvas, d]) => {
            if (!canvas || !d || !d.length) return;
            const labels  = d.map(x => x.name);
            const values  = d.map(x => x.value);
            const colours = d.map(x => x.colour);

            const cfg = type === "bar" ? {
                type: "bar",
                data: { labels, datasets: [{ data: values, backgroundColor: colours,
                    borderRadius: 3, borderSkipped: false }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false },
                        tooltip: { callbacks: { label: c =>
                            ` ${c.raw.toLocaleString("en-IN")}` } } },
                    scales: {
                        x: { grid, ticks: { font: { size: 9 }, maxRotation: 45 } },
                        y: { grid, ticks: { font: { size: 9 } } },
                    },
                },
            } : {
                type: "doughnut",
                data: { labels, datasets: [{ data: values, backgroundColor: colours,
                    borderWidth: 2, borderColor: "#fff" }] },
                options: {
                    cutout: type === "donut" ? "55%" : "0%",
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false },
                        tooltip: { callbacks: { label: c =>
                            ` ${c.label}: ${c.raw.toLocaleString("en-IN")}` } } },
                },
            };
            this._charts.push(new window.Chart(canvas.getContext("2d"), cfg));
        });
    }


    _resolvePreset(key) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        let from, to;

        switch (key) {
            case "today":
                from = to = this._jsDateToStr(today);
                break;
            case "yesterday": {
                const y = new Date(today); y.setDate(y.getDate() - 1);
                from = to = this._jsDateToStr(y);
                break;
            }
            case "this_week": {
                const dow = today.getDay();            // 0=Sun
                const mon = new Date(today);
                mon.setDate(today.getDate() - ((dow + 6) % 7));   // Monday
                from = this._jsDateToStr(mon);
                to   = this._jsDateToStr(today);
                break;
            }
            case "this_month":
                from = this._jsDateToStr(new Date(today.getFullYear(), today.getMonth(), 1));
                to   = this._jsDateToStr(today);
                break;
            case "last_month": {
                const lm = new Date(today.getFullYear(), today.getMonth() - 1, 1);
                const lme = new Date(today.getFullYear(), today.getMonth(), 0);
                from = this._jsDateToStr(lm);
                to   = this._jsDateToStr(lme);
                break;
            }
            case "last_3m": {
                const d3 = new Date(today); d3.setMonth(d3.getMonth() - 3);
                from = this._jsDateToStr(d3);
                to   = this._jsDateToStr(today);
                break;
            }
            case "last_6m": {
                const d6 = new Date(today); d6.setMonth(d6.getMonth() - 6);
                from = this._jsDateToStr(d6);
                to   = this._jsDateToStr(today);
                break;
            }
            case "this_year":
                from = `${today.getFullYear()}-01-01`;
                to   = this._jsDateToStr(today);
                break;
            case "last_year":
                from = `${today.getFullYear() - 1}-01-01`;
                to   = `${today.getFullYear() - 1}-12-31`;
                break;
            default:
                from = this.state.currDraftFrom || this._jsDateToStr(today);
                to   = this.state.currDraftTo   || this._jsDateToStr(today);
        }
        return { from, to };
    }


    _fmtD(s) {
        if (!s) return "";
        const [y, m, d] = s.split("-");
        const mo = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"];
        return `${d}-${mo[parseInt(m, 10) - 1]}-${y}`;
    }

    _prevPeriod(fromStr, toStr) {
        if (!fromStr || !toStr) return { prevFrom: "2026-01-01", prevTo: "2026-01-31" };
        const df   = new Date(fromStr + "T00:00:00");
        const dt   = new Date(toStr   + "T00:00:00");
        const days = Math.round((dt - df) / 86400000) + 1;
        const pdt  = new Date(df); pdt.setDate(pdt.getDate() - 1);
        const pdf  = new Date(pdt); pdf.setDate(pdf.getDate() - (days - 1));
        return { prevFrom: this._jsDateToStr(pdf), prevTo: this._jsDateToStr(pdt) };
    }

    _jsDateToStr(d) {
        return `${d.getFullYear()}-` +
               `${String(d.getMonth() + 1).padStart(2, "0")}-` +
               `${String(d.getDate()).padStart(2, "0")}`;
    }
}