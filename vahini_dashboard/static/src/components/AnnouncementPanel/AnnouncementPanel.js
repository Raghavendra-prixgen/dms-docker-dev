/** @odoo-module **/
import { Component, useState, onMounted } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const TYPE_CONFIG = {
    scheme:   { label: "Scheme / Offer",      color: "#16a34a", bg: "#dcfce7", icon: "🎯" },
    launch:   { label: "New Product Launch",   color: "#9333ea", bg: "#f3e8ff", icon: "🚀" },
    discount: { label: "Discount",             color: "#ea580c", bg: "#ffedd5", icon: "💰" },
    general:  { label: "General",              color: "#2563eb", bg: "#dbeafe", icon: "📢" },
};

export class AnnouncementPanel extends Component {
    static template = "vahini_dashboard.AnnouncementPanel";
    static props = {};

    setup() {
        this.typeConfig = TYPE_CONFIG;
        this.typeOptions = Object.entries(TYPE_CONFIG).map(([v, c]) => ({
            value: v, label: c.label, icon: c.icon,
        }));

        this.state = useState({
            announcements: [],
            loading:       true,
            isManager:     false,
            // Form
            showForm:      false,
            saving:        false,
            form: {
                id:          null,
                title:       "",
                message:     "",
                ann_type:    "general",
                link:        "",
                expiry_date: "",
                pin_top:     false,
            },
            // Delete confirm
            deleteId:      null,
        });

        onMounted(() => this._load());
    }

    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/announcements", {});
            this.state.announcements = res || [];
            this.state.isManager     = res.length ? res[0].is_manager : false;
            // Also check via first call
            if (!res.length) {
                const check = await rpc("/vahini_dashboard/announcements", {});
                this.state.isManager = check[0]?.is_manager || false;
            }
        } catch(e) { console.error("Announcements:", e); }
        finally    { this.state.loading = false; }
    }

    typeConf(type) { return TYPE_CONFIG[type] || TYPE_CONFIG.general; }

    // ── Form ──────────────────────────────────────────────────
    openCreate() {
        this.state.form = { id:null, title:"", message:"", ann_type:"general", link:"", expiry_date:"", pin_top:false };
        this.state.showForm = true;
    }

    openEdit(ann) {
        this.state.form = {
            id:          ann.id,
            title:       ann.title,
            message:     ann.message,
            ann_type:    ann.ann_type,
            link:        ann.link,
            expiry_date: ann.expiry_date,
            pin_top:     ann.pin_top,
        };
        this.state.showForm = true;
    }

    closeForm() { this.state.showForm = false; }

    onField(field, ev) {
        this.state.form[field] = ev.target.type === "checkbox"
            ? ev.target.checked : ev.target.value;
    }

    async save() {
        if (!this.state.form.title || !this.state.form.message) return;
        this.state.saving = true;
        try {
            await rpc("/vahini_dashboard/announcement_save", { ...this.state.form });
            this.state.showForm = false;
            await this._load();
        } catch(e) { console.error("Save:", e); }
        finally    { this.state.saving = false; }
    }

    // ── Delete ────────────────────────────────────────────────
    confirmDelete(id) { this.state.deleteId = id; }
    cancelDelete()    { this.state.deleteId = null; }

    async doDelete() {
        const id = this.state.deleteId;
        this.state.deleteId = null;
        try {
            await rpc("/vahini_dashboard/announcement_delete", { ann_id: id });
            await this._load();
        } catch(e) { console.error("Delete:", e); }
    }
}
