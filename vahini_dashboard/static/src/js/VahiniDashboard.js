/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry }     from "@web/core/registry";
import { useService }   from "@web/core/utils/hooks";
import { rpc }          from "@web/core/network/rpc";

import { SideDrawer }   from "../components/SideDrawer/SideDrawer";
import { SnapHeader }   from "../components/SnapHeader/SnapHeader";
import { SnapMetrics }  from "../components/SnapMetrics/SnapMetrics";
import { ChartCard }    from "../components/ChartCard/ChartCard";
import { DataTable }    from "../components/DataTable/DataTable";
import { CompareModal } from "../components/CompareModal/CompareModal";
import { DayView }      from "../components/DayView/DayView";
import { PurchaseView } from "../components/PurchaseView/PurchaseView";
import { MapView }      from "../components/MapView/MapView";
import { PaymentView }  from "../components/PaymentView/PaymentView";
import { FollowUpView } from "../components/FollowUpView/FollowUpView";
import { ItemView }     from "../components/ItemView/ItemView";
import { GpView }       from "../components/GpView/GpView";
import { TrendView }    from "../components/TrendView/TrendView";
import { ItemMaster }   from "../components/ItemMaster/ItemMaster";
import { InvoiceView }        from "../components/InvoiceView/InvoiceView";
import { AnnouncementPanel }   from "../components/AnnouncementPanel/AnnouncementPanel";

export class VahiniDashboard extends Component {
    static template   = "vahini_dashboard.VahiniDashboard";
    static props = { "*": true };
    static components = { ItemMaster, InvoiceView, AnnouncementPanel, SideDrawer, SnapHeader, SnapMetrics, ChartCard, DataTable, CompareModal, DayView, PurchaseView, MapView, PaymentView, FollowUpView, ItemView, GpView, TrendView };

    setup() {
        const today    = new Date();
        // Default to last 3 months so the dashboard shows data
        // even when current month has no invoices yet
        const firstDay = new Date(today.getFullYear(), today.getMonth() - 2, 1);

        this.actionService = useService("action");
        this.state = useState({
            activeView:  "dashboard",    // 'dashboard' | 'dayview' | 'mapview'
            // theme
            theme:       "light",
            // loading
            loading:     true,
            error:       null,
            dateFrom:    this._fmt(firstDay),
            dateTo:      this._fmt(today),
            metrics:     [],
            chartDefs:   [],
            tableDatas:  [],
            compareOpen: false,
            announcements:   [],
            showAnnPopup:    false,
            compareDef:  null,
            compareData: null,
            compareType: "bar",
        });

        onMounted(async () => {
            document.documentElement.setAttribute("data-theme", this.state.theme);
            await this._loadData();
            await this._loadAnnouncements();

            // Company switching is handled by SnapHeader company selector
            // which sets the cids cookie and reloads the page
        });

        onWillUnmount(() => {
            if (this._companyPollInterval) {
                clearInterval(this._companyPollInterval);
            }
        });
    }   // end setup()

    // ── Get current company ids from browser cookie ───────────────────────────
    _getCids() {
        const match = document.cookie.match(/(?:^|;\s*)cids=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    onNavClick(view) {
        this.state.activeView = view;
        if (view === "dashboard" && !this.state.metrics.length) {
            this._loadData();
        }
    }


    async _loadAnnouncements() {
        try {
            const res = await rpc("/vahini_dashboard/announcements", {});
            this.state.announcements = res || [];
            // Show popup if there are active announcements
            // Only once per session using sessionStorage
            const key = "vd_ann_seen_" + (res.map(a=>a.id).join("_"));
            if (res.length && !sessionStorage.getItem(key)) {
                this.state.showAnnPopup = true;
                sessionStorage.setItem(key, "1");
            }
        } catch(e) {}
    }

    dismissAnnPopup() { this.state.showAnnPopup = false; }

    typeConf(type) {
        const T = {
            scheme:   { label:"Scheme / Offer",    color:"#16a34a", bg:"#dcfce7", icon:"🎯" },
            launch:   { label:"New Product Launch", color:"#9333ea", bg:"#f3e8ff", icon:"🚀" },
            discount: { label:"Discount",           color:"#ea580c", bg:"#ffedd5", icon:"💰" },
            general:  { label:"General",            color:"#2563eb", bg:"#dbeafe", icon:"📢" },
        };
        return T[type] || T.general;
    }

    async _loadData() {
        this.state.loading = true;
        this.state.error   = null;
        try {
            const data = await rpc("/vahini_dashboard/data", {
                date_from: this.state.dateFrom,
                date_to:   this.state.dateTo,
            });
            this._applyData(data);
        } catch (e) {
            this.state.error = e.message || "Failed to load dashboard data";
        } finally {
            this.state.loading = false;
        }
    }

    _applyData(data) {
        this.state.metrics = data.metrics || [];
        this.state.chartDefs = [
            { id: "state",    title: "State",    data: data.state    || [], defaultType: "bar" },
            { id: "district", title: "District", data: data.district || [], defaultType: "pie" },
            { id: "area",     title: "Area",     data: data.area     || [], defaultType: "pie" },
            { id: "city",     title: "City",     data: data.city     || [], defaultType: "pie" },
        ];
        this.state.tableDatas = [
            data.item_table          || { title: "Item Name",     rowCount: 0, rows: [] },
            data.customer_table      || { title: "Customer Name", rowCount: 0, rows: [] },
            data.customer_type_table || { title: "Customer Type", rowCount: 0, rows: [] },
        ];
        if (data.date_from) this.state.dateFrom = data.date_from;
        if (data.date_to)   this.state.dateTo   = data.date_to;
    }


    get displayDateRange() {
        return `${this._fmtDisplay(this.state.dateFrom)} – ${this._fmtDisplay(this.state.dateTo)}`;
    }

    async onDateChange(dateFrom, dateTo) {
        this.state.dateFrom = dateFrom;
        this.state.dateTo   = dateTo;
        await this._loadData();
    }

    async onRefresh() { await this._loadData(); }


    toggleTheme() {
        this.state.theme = this.state.theme === "light" ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", this.state.theme);
    }


    openCompare(def, pageData, type) {
        this.state.compareDef  = def;
        this.state.compareData = pageData;
        this.state.compareType = type === "table" ? "bar" : type;
        this.state.compareOpen = true;
    }

    closeCompare() { this.state.compareOpen = false; }


    _fmt(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${day}`;
    }

    _fmtDisplay(s) {
        if (!s) return "";
        const [y, m, d] = s.split("-");
        const mo = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        return `${d}-${mo[parseInt(m,10)-1]}-${y}`;
    }
}

registry.category("actions").add("vahini_dashboard", VahiniDashboard);
