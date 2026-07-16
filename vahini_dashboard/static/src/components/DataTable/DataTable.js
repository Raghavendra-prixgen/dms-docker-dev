/** @odoo-module **/

import { Component, useState, onMounted, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { rpc }           from "@web/core/network/rpc";
import { fmt, buildPageNums } from "../../js/utils";

const ROWS_PER_PAGE = 10;

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

export class DataTable extends Component {
    static template = "vahini_dashboard.DataTable";
    static props = {
        tableData:  { type: Object,  optional: true },
        dateFrom:   { type: String,  optional: true },
        dateTo:     { type: String,  optional: true },
        initGroup:  { type: String,  optional: true },
        title:      { type: String,  optional: true },
    };

    setup() {
        this.groupOptions = GROUP_OPTIONS;
        const initGroup = this.props.initGroup || "item_name";

        this.state = useState({
            groupBy:     initGroup,
            searchInput: "",
            showDrop:    false,
            loading:     false,
            rows:        [],
            total:       0,
            totalPages:  1,
            page:        1,
            sortKey:     "sales",
            sortDir:     "desc",
            menuOpen:    false,
        });

        this._docClick = () => {
            this.state.showDrop = false;
            this.state.menuOpen = false;
        };
        onMounted(() => {
            document.addEventListener("click", this._docClick);
            this._load();
        });
        onWillUpdateProps(() => {
            this._load();
        });
        onWillUnmount(() => document.removeEventListener("click", this._docClick));
    }

    // ── Dropdown ──────────────────────────────────────────────
    get groupLabel() {
        const opt = this.groupOptions.find(o => o.value === this.state.groupBy);
        return opt ? opt.label : (this.props.title || "Item Name");
    }

    get filteredOptions() {
        const q = (this.state.searchInput || "").toLowerCase();
        if (!q) return this.groupOptions;
        return this.groupOptions.filter(o => o.label.toLowerCase().includes(q));
    }

    toggleDrop(ev) { ev.stopPropagation(); this.state.showDrop = !this.state.showDrop; }
    onDropSearch(ev) { this.state.searchInput = ev.target.value; }

    selectGroup(value) {
        this.state.groupBy     = value;
        this.state.showDrop    = false;
        this.state.searchInput = "";
        this.state.page        = 1;
        this._load();
    }

    // ── Data loading ──────────────────────────────────────────
    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/dashboard_table", {
                group_by:  this.state.groupBy,
                date_from: this.props.dateFrom || "",
                date_to:   this.props.dateTo   || "",
                page:      this.state.page,
                per_page:  ROWS_PER_PAGE,
            });
            this.state.rows       = res.rows       || [];
            this.state.total      = res.total      || 0;
            this.state.totalPages = res.total_pages || 1;
        } catch(e) { console.error("DataTable:", e); }
        finally    { this.state.loading = false; }
    }

    // ── Sort ──────────────────────────────────────────────────
    sortBy(k) {
        if (this.state.sortKey === k)
            this.state.sortDir = this.state.sortDir === "asc" ? "desc" : "asc";
        else { this.state.sortKey = k; this.state.sortDir = "desc"; }
    }
    sortIndicator(k) {
        if (this.state.sortKey !== k) return "";
        return this.state.sortDir === "asc" ? " ↑" : " ↓";
    }

    get sorted() {
        const { sortKey: k, sortDir: dir } = this.state;
        return [...this.state.rows].sort((a, b) => {
            // map "sales" -> "tax_less", "avg" -> "asp"
            const key = k === "sales" ? "tax_less" : k === "avg" ? "asp" : k;
            const v = typeof a[key] === "string"
                ? a[key].localeCompare(b[key])
                : (a[key] ?? 0) - (b[key] ?? 0);
            return dir === "asc" ? v : -v;
        });
    }

    // ── Pagination ────────────────────────────────────────────
    get pageNums()      { return buildPageNums(this.state.totalPages, this.state.page); }
    isPrevDisabled()    { return this.state.page === 1; }
    isNextDisabled()    { return this.state.page === this.state.totalPages; }
    isCurrentPage(p)    { return p === this.state.page; }

    prevPage()  { if (this.state.page > 1) { this.state.page--; this._load(); } }
    nextPage()  { if (this.state.page < this.state.totalPages) { this.state.page++; this._load(); } }
    goPage(p)   { if (typeof p === "number") { this.state.page = p; this._load(); } }

    // ── Helpers ───────────────────────────────────────────────
    fmtNum(v)       { return fmt(v); }
    fmtCount(n)     { return (n || 0).toLocaleString("en-IN"); }
    toggleMenu(ev)  { ev.stopPropagation(); this.state.menuOpen = !this.state.menuOpen; }
    closeMenu()     { this.state.menuOpen = false; }

    dlExcel() {
        this.closeMenu();
        const rows = this.sorted;
        const csv = [
            `"${this.groupLabel}","Sales","Avg (6)","Contr%"`,
            ...rows.map(r =>
                `"${r.name}",${r.tax_less},${r.asp},${r.contrib}`)
        ].join("\n");
        const a = document.createElement("a");
        a.href = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
        a.download = this.groupLabel + ".csv";
        a.click();
    }
    dlPDF() { this.closeMenu(); }
}
