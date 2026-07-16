/** @odoo-module **/

import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const PER_PAGE = 50;

export class FollowUpView extends Component {
    static template = "vahini_dashboard.FollowUpView";
    static props = { dateFrom: String, dateTo: String };

    setup() {
        this.state = useState({
            loading:      true,
            tab:          "all",
            search:       "",
            compact:      true,
            rows:         [],
            page:         1,
            totalPages:   1,
            total:        0,
            tabCounts:    { all:0, current:0, snoozed:0, net_zero:0 },
            selected:     {},
            // Communication popup
            commRow:      null,
            activePopup:  null,
            // Snooze
            snoozeRemark: "",
            snoozeUntil:  "",
            // Call
            callStatus:   "unanswered",
            callNote:     "",
            callStatusOpen: false,
            // WhatsApp
            waNumber:     "",
            waMessage:    "",
            waAddStatement: false,
            waAddLedger:  false,
            // Email
            emailTo:      "",
            emailAddStatement: false,
            emailAddLedger: false,
            emailSending: false,
        });
        onMounted(async () => { await this._load(); });
        onWillUpdateProps(async () => { await this._load(); });
    }

    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/followup", {
                tab:      this.state.tab,
                search:   this.state.search,
                page:     this.state.page,
                per_page: PER_PAGE,
            });
            this.state.rows       = res.rows       || [];
            this.state.total      = res.total      || 0;
            this.state.totalPages = res.total_pages || 1;
            this.state.page       = res.page       || 1;
            this.state.tabCounts  = res.tab_counts || {};
        } catch(e) {
            console.error("FollowUpView error:", e);
        } finally {
            this.state.loading = false;
        }
    }

    async setTab(t) {
        this.state.tab = t; this.state.page = 1; await this._load();
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(async () => {
            this.state.page = 1; await this._load();
        }, 400);
    }

    toggleCompact() { this.state.compact = !this.state.compact; }

    get pageNums() {
        const t=this.state.totalPages, c=this.state.page;
        if (t<=7) return Array.from({length:t},(_,i)=>i+1);
        const p=[1];
        if (c>3) p.push("...");
        for(let i=Math.max(2,c-1);i<=Math.min(t-1,c+1);i++) p.push(i);
        if(c<t-2) p.push("...");
        p.push(t);
        return p;
    }

    async goPage(p) { if(typeof p==="number"){ this.state.page=p; await this._load(); } }
    async prevPage() { if(this.state.page>1){ this.state.page--; await this._load(); } }
    async nextPage() { if(this.state.page<this.state.totalPages){ this.state.page++; await this._load(); } }

    toggleSelect(id) {
        if (this.state.selected[id]) delete this.state.selected[id];
        else this.state.selected[id] = true;
    }
    toggleAll() {
        const ids = this.state.rows.map(r=>r.partner_id);
        const allSelected = ids.every(id=>this.state.selected[id]);
        if (allSelected) { this.state.selected = {}; }
        else { ids.forEach(id => this.state.selected[id]=true); }
    }
    get allSelected() { return this.state.rows.length && this.state.rows.every(r=>this.state.selected[r.partner_id]); }

    // ── Communication actions ─────────────────────────────────────────────
    openAction(row, type) {
        this.state.commRow     = row;
        this.state.activePopup = type;
        this.state.waNumber    = row.phone || "";
        this.state.emailTo     = row.email || "";
        this.state.waMessage   = `Hello ${row.partner_name}, this is a gentle reminder regarding your pending payment of ₹${this.fmt(Math.abs(row.outstanding))}.`;
    }
    closePopup() { this.state.activePopup = null; this.state.commRow = null; }

    // Snooze
    onSnoozeRemark(ev) { this.state.snoozeRemark = ev.target.value; }
    onSnoozeUntil(ev)  { this.state.snoozeUntil  = ev.target.value; }
    submitSnooze() {
        if (!this.state.snoozeUntil) return;
        alert(`Snoozed ${this.state.commRow.partner_name} until ${this.state.snoozeUntil}`);
        this.state.snoozeRemark=""; this.state.snoozeUntil="";
        this.closePopup();
    }

    // Call
    onCallNote(ev)   { this.state.callNote = ev.target.value; }
    toggleCallDD()   { this.state.callStatusOpen = !this.state.callStatusOpen; }
    setCallStatus(s) { this.state.callStatus = s; this.state.callStatusOpen = false; }
    submitCall() {
        alert(`Call logged for ${this.state.commRow.partner_name}: ${this.state.callStatus}`);
        this.state.callNote=""; this.closePopup();
    }

    // WhatsApp
    onWaNumber(ev)      { this.state.waNumber  = ev.target.value; }
    onWaMessage(ev)     { this.state.waMessage = ev.target.value; }
    toggleWaStatement() { this.state.waAddStatement = !this.state.waAddStatement; }
    toggleWaLedger()    { this.state.waAddLedger    = !this.state.waAddLedger; }
    submitWhatsApp() {
        const num = this.state.waNumber.replace(/\D/g,"");
        if (!num) return;
        window.open(`https://wa.me/${num}?text=${encodeURIComponent(this.state.waMessage)}`, "_blank");
        this.closePopup();
    }

    // Email
    onEmailTo(ev)             { this.state.emailTo = ev.target.value; }
    toggleEmailStatement()    { this.state.emailAddStatement = !this.state.emailAddStatement; }
    toggleEmailLedger()       { this.state.emailAddLedger    = !this.state.emailAddLedger; }
    async submitEmail() {
        if (!this.state.emailTo) { alert("Please enter an email address."); return; }
        this.state.emailSending = true;
        try {
            const res = await rpc("/vahini_dashboard/send_email", {
                partner_id:    this.state.commRow.partner_id,
                email_to:      this.state.emailTo,
                add_statement: this.state.emailAddStatement,
                add_ledger:    this.state.emailAddLedger,
            });
            if (res && res.success) {
                alert(`Email sent to ${this.state.emailTo}`);
                this.closePopup();
            } else {
                alert("Email Error: " + ((res && res.error) || "Unknown error"));
            }
        } catch(e) {
            alert("Failed to send email. Check Outgoing Mail Server in Odoo Settings.");
        } finally {
            this.state.emailSending = false;
        }
    }

    // Download statement PDF for one partner
    downloadStatement(row) {
        const label = row.partner_name;
        let html = `<html><head><style>body{font-family:Arial;font-size:11px;padding:20px;}h2{color:#1e293b;}table{width:100%;border-collapse:collapse;}th{background:#1e3a5f;color:#fff;padding:7px 10px;}td{padding:6px 10px;border-bottom:1px solid #e2e8f0;}.num{text-align:right;}</style></head><body>
<h2>Outstanding Statement – ${label}</h2>
<table><thead><tr><th>Detail</th><th class="num">Value</th></tr></thead><tbody>
<tr><td>Total Outstanding</td><td class="num">₹ ${this.fmt(row.outstanding)}</td></tr>
<tr><td>Due Amount</td><td class="num">₹ ${this.fmt(row.due_amount)}</td></tr>
<tr><td>Due Bills / Total Bills</td><td class="num">${row.due_bills} / ${row.total_bills}</td></tr>
<tr><td>Follow-up in 10 Days</td><td class="num">${row.followup_10d}</td></tr>
</tbody></table></body></html>`;
        const w = window.open("","_blank"); w.document.write(html); w.document.close();
        setTimeout(()=>{w.print();w.close();},400);
    }

    // ── Follow Up Report (bulk PDF) ───────────────────────────────────────
    downloadReport() {
        let html = `<html><head><style>body{font-family:Arial;font-size:10px;padding:20px;}h2{color:#1e293b;margin-bottom:4px;}table{width:100%;border-collapse:collapse;}th{background:#1e3a5f;color:#fff;padding:6px 8px;font-size:9px;}td{padding:5px 8px;border-bottom:1px solid #e2e8f0;}.num{text-align:right;}.neg{color:#ef4444;}</style></head><body>
<h2>Follow-Up Report</h2><p>Generated: ${new Date().toLocaleDateString("en-IN")}</p>
<table><thead><tr><th>Customer</th><th class="num">Due / Outstanding</th><th class="num">Due Bills / Total</th><th class="num">Follow-up 10d</th></tr></thead><tbody>`;
        for(const r of this.state.rows) {
            html += `<tr><td>${r.partner_name}</td>
<td class="num ${r.outstanding<0?'neg':''}">${this.fmt(r.due_amount)} / ${this.fmt(r.outstanding)}</td>
<td class="num">${r.due_bills} / ${r.total_bills}</td>
<td class="num">${r.followup_10d}</td></tr>`;
        }
        html += `</tbody></table></body></html>`;
        const w=window.open("","_blank"); w.document.write(html); w.document.close();
        setTimeout(()=>{w.print();w.close();},400);
    }

    // ── Helpers ───────────────────────────────────────────────────────────
    fmt(v) {
        const n = parseFloat(v)||0;
        if (!n) return "0";
        return n.toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:0});
    }
    cls(v) { return parseFloat(v)<0 ? "fup-neg" : ""; }
}
