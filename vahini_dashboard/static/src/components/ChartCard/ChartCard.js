/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUpdateProps, onWillUnmount, onPatched } from "@odoo/owl";
import { rpc }           from "@web/core/network/rpc";
import { fmt, buildPageNums } from "../../js/utils";

const PER_PAGE = 10;

const CHART_COLOURS = [
    "#6ed9e0","#87c257","#f4c374","#d94f63","#a8d8ea","#c9b1d9","#ffd97d",
    "#a3d977","#e8b89a","#70bfc5","#9db86b","#f9e4b7","#4f6df5","#f97316",
    "#22c55e","#8b5cf6","#ec4899","#14b8a6","#f59e0b","#ef4444",
];

const GROUP_OPTIONS = [
    { value:"area",            label:"Area"               },
    { value:"batch_tracking",  label:"Batch Tracking No"  },
    { value:"billno",          label:"Billno"             },
    { value:"category",        label:"Category"           },
    { value:"city",            label:"City"               },
    { value:"company_name",    label:"Company Name"       },
    { value:"conversion",      label:"Conversion"         },
    { value:"customer_alias",  label:"Customer Alias"     },
    { value:"customer_name",   label:"Customer Name"      },
    { value:"customer_type",   label:"Customer Type"      },
    { value:"district",        label:"District"           },
    { value:"document_type",   label:"Document Type"      },
    { value:"godown_name",     label:"Godown Name"        },
    { value:"gstno",           label:"Gstno"              },
    { value:"im9",             label:"Im 9"               },
    { value:"item_alias",      label:"Item Alias"         },
    { value:"item_group",      label:"Item Group"         },
    { value:"item_name",       label:"Item Name"          },
    { value:"item_names",      label:"Item Names"         },
    { value:"mobileno",        label:"Mobileno"           },
    { value:"mrp",             label:"Mrp"                },
    { value:"mrps",            label:"Mrps"               },
    { value:"part_no",         label:"Part No"            },
    { value:"product_category",label:"Product Category"   },
    { value:"product_group",   label:"Product Group"      },
    { value:"referenceno",     label:"Referenceno"        },
    { value:"scheme",          label:"Scheme"             },
    { value:"state",           label:"State"              },
    { value:"subcategory",     label:"Subcategory"        },
    { value:"tim10",           label:"Tim 10"             },
    { value:"tim20",           label:"Tim 20"             },
    { value:"tim30",           label:"Tim 30"             },
    { value:"uom",             label:"Units Of Measurement"},
    { value:"voucher_type",    label:"Voucher Type"       },
    { value:"weight",          label:"Weight"             },
];

// Map chart card id to default group
const DEFAULT_GROUP = {
    state: "state", district: "district", area: "area", city: "city",
};

export class ChartCard extends Component {
    static template = "vahini_dashboard.ChartCard";
    static props = {
        def:       Object,
        onCompare: Function,
        theme:     String,
        dateFrom:  { type: String, optional: true },
        dateTo:    { type: String, optional: true },
    };

    setup() {
        this.groupOptions = GROUP_OPTIONS;
        const defGroup = DEFAULT_GROUP[this.props.def.id] || "area";

        this.state = useState({
            type:        this.props.def.defaultType,
            page:        1,
            // Group dropdown
            groupBy:     defGroup,
            searchInput: "",
            showDrop:    false,
            // Live chart/table data
            liveData:    [],      // [{name, value, colour}]
            loading:     false,
            // Table view extra columns
            tableRows:   [],
            tableTotal:  0,
            tablePages:  1,
            tablePage:   1,
            tableLoading:false,
        });

        this.canvasRef = useRef("chartCanvas");
        this._chart    = null;

        onMounted(() => {
            this._loadData();
            document.addEventListener("click", this._onDocClick = () => {
                this.state.showDrop = false;
            });
        });
        onWillUpdateProps(() => {
            this._loadData();
        });

        onPatched(() => {
            if (this.state.type !== "table") this._drawChart();
            else this._destroyChart();
        });

        onWillUnmount(() => {
            this._destroyChart();
            document.removeEventListener("click", this._onDocClick);
        });
    }

    // ── Group dropdown ────────────────────────────────────────
    get groupLabel() {
        const opt = this.groupOptions.find(o => o.value === this.state.groupBy);
        return opt ? opt.label : "Area";
    }

    get filteredOptions() {
        const q = (this.state.searchInput || "").toLowerCase();
        if (!q) return this.groupOptions;
        return this.groupOptions.filter(o => o.label.toLowerCase().includes(q));
    }

    toggleDrop(ev) {
        ev.stopPropagation();
        this.state.showDrop = !this.state.showDrop;
    }

    onDropSearch(ev) { this.state.searchInput = ev.target.value; }

    selectGroup(value) {
        this.state.groupBy     = value;
        this.state.showDrop    = false;
        this.state.searchInput = "";
        this.state.page        = 1;
        this._loadData();
    }

    // ── Data loading ──────────────────────────────────────────
    async _loadData() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/dashboard_table", {
                group_by:  this.state.groupBy,
                date_from: this.props.dateFrom || "",
                date_to:   this.props.dateTo   || "",
                page:      1,
                per_page:  50,
            });
            const rows = res.rows || [];
            // Build chart data from taxless (main value)
            this.state.liveData = rows.map((r, i) => ({
                name:   r.name,
                value:  r.tax_less,
                colour: CHART_COLOURS[i % CHART_COLOURS.length],
                ...r,
            }));
        } catch(e) { console.error("ChartCard data:", e); }
        finally    { this.state.loading = false; }
    }

    // ── Chart data (uses live data when available) ────────────
    get data() {
        return this.state.liveData.length
            ? this.state.liveData
            : this.props.def.data;
    }

    get totalPages() { return Math.max(1, Math.ceil(this.data.length / PER_PAGE)); }

    get pageData() {
        const s = (this.state.page - 1) * PER_PAGE;
        return this.data.slice(s, s + PER_PAGE);
    }

    get pageNums() { return buildPageNums(this.totalPages, this.state.page); }

    isActive(t)    { return this.state.type === t; }
    isCurrentPage(p){ return p === this.state.page; }
    isPrevDisabled(){ return this.state.page === 1; }
    isNextDisabled(){ return this.state.page === this.totalPages; }

    setType(type) {
        this.state.type = type;
        this.state.page = 1;
    }

    prevPage()  { if (this.state.page > 1) this.state.page--; }
    nextPage()  { if (this.state.page < this.totalPages) this.state.page++; }
    goPage(p)   { if (typeof p === "number") this.state.page = p; }

    // ── Inner table (table view) ──────────────────────────────
    innerTableRows() {
        return this.pageData.map((r, i) => ({
            num:         (this.state.page - 1) * PER_PAGE + i + 1,
            name:        r.name,
            qty:         r.qty        != null ? fmt(r.qty)         : fmt(r.value),
            tax_paid:    r.tax_paid   != null ? fmt(r.tax_paid)    : "-",
            tax_less:    r.tax_less   != null ? fmt(r.tax_less)    : fmt(r.value),
            asp:         r.asp        != null ? fmt(r.asp)         : "-",
            asp_taxpaid: r.asp_taxpaid!= null ? fmt(r.asp_taxpaid) : "-",
            contrib:     r.contrib    != null ? r.contrib + "%"    : "-",
        }));
    }

    legendRows() {
        return this.pageData.map(e => ({
            colour: e.colour,
            name:   e.name,
            value:  fmt(e.value || e.tax_less || 0),
        }));
    }

    // ── Download ──────────────────────────────────────────────
    downloadChart() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        const a = document.createElement("a");
        a.download = this.groupLabel + ".png";
        a.href = canvas.toDataURL();
        a.click();
    }

    openCompare() {
        this.props.onCompare(
            this.props.def,
            this.pageData,
            this.state.type
        );
    }

    // ── Chart rendering ───────────────────────────────────────
    _drawChart() {
        if (this.state.type === "table") { this._destroyChart(); return; }
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        if (!window.Chart) { setTimeout(() => this._drawChart(), 100); return; }

        this._destroyChart();

        const d       = this.pageData;
        if (!d.length) return;
        const labels  = d.map(x => x.name);
        const values  = d.map(x => x.value || x.tax_less || 0);
        const colours = d.map(x => x.colour);
        const isDark  = this.props.theme === "dark";
        const fg      = isDark ? "#e2e8f0" : "#1e293b";
        const gridClr = isDark ? "rgba(255,255,255,.06)" : "rgba(0,0,0,.06)";

        let cfg;
        if (this.state.type === "bar") {
            cfg = {
                type: "bar",
                data: { labels, datasets: [{ data: values, backgroundColor: colours, borderRadius: 3, borderSkipped: false }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false },
                        tooltip: { callbacks: { label: c => ` ${fmt(c.raw)}` } } },
                    scales: {
                        x: { ticks: { color: fg, font: { size: 10 } }, grid: { display: false } },
                        y: { ticks: { color: fg, font: { size: 10 }, callback: v => fmt(v) },
                             grid: { color: gridClr, borderDash: [4,4] } }
                    }
                }
            };
        } else {
            cfg = {
                type: this.state.type === "donut" ? "doughnut" : "pie",
                data: { labels, datasets: [{ data: values, backgroundColor: colours, borderWidth: 1 }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    cutout: this.state.type === "donut" ? "55%" : 0,
                    plugins: { legend: { display: false },
                        tooltip: { callbacks: { label: c => ` ${c.label}: ${fmt(c.raw)}` } } }
                }
            };
        }
        this._chart = new window.Chart(canvas, cfg);
    }

    _destroyChart() {
        if (this._chart) { this._chart.destroy(); this._chart = null; }
    }
}
