/** @odoo-module **/
import { Component, useState, onMounted } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const PER_PAGE = 50;

export class ItemMaster extends Component {
    static template = "vahini_dashboard.ItemMaster";
    static props = {};

    setup() {
        this.state = useState({
            loading:    true,
            rows:       [],
            page:       1,
            totalPages: 1,
            total:      0,
            search:     "",
            editId:     null,
            editVals:   {},
            saving:     false,
        });
        onMounted(async () => { await this._load(); });
    }

    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/item_master", {
                search:   this.state.search,
                page:     this.state.page,
                per_page: PER_PAGE,
            });
            this.state.rows       = res.rows       || [];
            this.state.total      = res.total      || 0;
            this.state.totalPages = res.total_pages || 1;
            this.state.page       = res.page       || 1;
        } catch(e) { console.error("ItemMaster:", e); }
        finally    { this.state.loading = false; }
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._st);
        this._st = setTimeout(async () => { this.state.page=1; await this._load(); }, 400);
    }

    get pageNums() {
        const t=this.state.totalPages, c=this.state.page;
        if(t<=7) return Array.from({length:t},(_,i)=>i+1);
        const p=[1]; if(c>3) p.push("...");
        for(let i=Math.max(2,c-1);i<=Math.min(t-1,c+1);i++) p.push(i);
        if(c<t-2) p.push("..."); p.push(t); return p;
    }
    async goPage(p)    { if(typeof p==="number"){ this.state.page=p; await this._load(); } }
    async prevPage()   { if(this.state.page>1){ this.state.page--; await this._load(); } }
    async nextPage()   { if(this.state.page<this.state.totalPages){ this.state.page++; await this._load(); } }

    startEdit(row) {
        this.state.editId   = row.id;
        this.state.editVals = { ...row };
    }
    cancelEdit() { this.state.editId=null; this.state.editVals={}; }
    onFieldChange(f, ev) { this.state.editVals[f] = ev.target.value; }

    async saveEdit() {
        this.state.saving = true;
        try {
            await rpc("/vahini_dashboard/item_master_update", {
                product_id: this.state.editId,
                vals: { list_price: parseFloat(this.state.editVals.mrps)||0,
                        weight:     parseFloat(this.state.editVals.weight)||0 },
            });
            const row = this.state.rows.find(r=>r.id===this.state.editId);
            if (row) Object.assign(row, this.state.editVals);
            this.cancelEdit();
        } catch(e) { alert("Save failed"); }
        finally    { this.state.saving=false; }
    }

    fmt(v, decimals=1) {
        if (v===null||v===undefined) return '-';
        const n = parseFloat(v);
        if (isNaN(n)) return String(v)||'-';
        if (n===0) return '0';
        return n.toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:decimals});
    }

    trunc(v, n=12) {
        if (!v || v==='Not Defined') return v||'';
        return v.length>n ? v.slice(0,n)+'...' : v;
    }
}
