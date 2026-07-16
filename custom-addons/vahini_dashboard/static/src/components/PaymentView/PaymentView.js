/** @odoo-module **/

import { Component, useState, onMounted, onWillUpdateProps } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

const PER_PAGE = 50;

export class PaymentView extends Component {
    static template = "vahini_dashboard.PaymentView";
    static props = { dateFrom: String, dateTo: String };

    setup() {
        this.state = useState({
            loading:         true,
            reportType:      "receivable",
            filterOverDue:   true,
            filterNotDue:    true,
            filterPostDated: true,
            dueFilter:       "all",
            asOfDate:        "",
            search:          "",
            kpis:            {},
            rows:            [],
            filteredRows:    [],
            page:            1,
            totalPages:      1,
            sortCol:         "partner",
            sortDir:         "asc",

            // Reminder popup
            reminderOpen:    false,
            reminderCount:   0,

            // Communication panel
            commOpen:        false,
            commPartner:     null,   // { id, name, phone, email }
            commHistory:     [],
            commRemark:      "",
            commRemarkType:  "remark",

            // Sub-popups
            activePopup:     null,   // snooze | call | whatsapp | email

            // Snooze
            snoozeRemark:    "",
            snoozeUntil:     "",

            // Call
            callStatus:      "unanswered",
            callNote:        "",
            callStatusOpen:  false,

            // WhatsApp
            waNumber:        "",
            waMessage:       "",
            waAddStatement:  false,
            waAddLedger:     false,

            // Email
            emailTo:         "",
            emailAddStatement: false,
            emailAddLedger:  false,
            emailSending:   false,
        });
        onMounted(async () => { await this._load(); });
        onWillUpdateProps(async () => { await this._load(); });
    }

    // ── Data loading ──────────────────────────────────────────────────────
    async _load() {
        this.state.loading = true;
        try {
            const res = await rpc("/vahini_dashboard/payment", {
                report_type: this.state.reportType,
                as_of_date:  this.state.asOfDate || null,
            });
            this.state.kpis = res.kpis || {};
            this.state.rows = res.rows || [];
            this._applyFilters();
        } catch(e) {
            console.error("PaymentView error:", e);
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    _applyFilters() {
        let rows = [...this.state.rows];
        const q = this.state.search.trim().toLowerCase();
        if (q) rows = rows.filter(r => r.partner.toLowerCase().includes(q));
        if (!this.state.filterOverDue)   rows = rows.filter(r => r.overdue >= 0);
        if (!this.state.filterNotDue)    rows = rows.filter(r => r.not_due <= 0);
        if (!this.state.filterPostDated) rows = rows.filter(r => r.other >= 0);
        if (this.state.dueFilter === "overdue")    rows = rows.filter(r => r.overdue !== 0);
        if (this.state.dueFilter === "not_due")    rows = rows.filter(r => r.not_due !== 0);
        if (this.state.dueFilter === "post_dated") rows = rows.filter(r => r.other < 0);
        rows = this._sort(rows);
        this.state.totalPages  = Math.max(1, Math.ceil(rows.length / PER_PAGE));
        this.state.page        = Math.min(this.state.page, this.state.totalPages);
        this.state.filteredRows = rows;
    }

    _sort(rows) {
        const col = this.state.sortCol, dir = this.state.sortDir === "asc" ? 1 : -1;
        return [...rows].sort((a,b) => {
            const av = a[col] ?? a.partner ?? 0, bv = b[col] ?? b.partner ?? 0;
            return typeof av === "string" ? dir * av.localeCompare(bv) : dir*(av-bv);
        });
    }

    get pageRows() {
        const s = (this.state.page-1)*PER_PAGE;
        return this.state.filteredRows.slice(s, s+PER_PAGE);
    }

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

    // ── Report controls ───────────────────────────────────────────────────
    async switchType(t) {
        if (this.state.reportType===t) return;
        this.state.reportType=t; this.state.page=1; await this._load();
    }
    toggleFilter(f) { this.state[f]=!this.state[f]; this.state.page=1; this._applyFilters(); }
    onDueFilterChange(ev) { this.state.dueFilter=ev.target.value; this.state.page=1; this._applyFilters(); }
    onDateChange(ev) { this.state.asOfDate=ev.target.value; }
    async applyDate() { this.state.page=1; await this._load(); }
    onSearch(ev) { this.state.search=ev.target.value; this.state.page=1; this._applyFilters(); }
    sortBy(col) {
        this.state.sortDir = this.state.sortCol===col ? (this.state.sortDir==="asc"?"desc":"asc") : (col==="partner"?"asc":"desc");
        this.state.sortCol=col; this.state.page=1; this._applyFilters();
    }
    goPage(p) { if(typeof p==="number") this.state.page=p; }
    prevPage() { if(this.state.page>1) this.state.page--; }
    nextPage() { if(this.state.page<this.state.totalPages) this.state.page++; }
    isSorted(col,dir) { return this.state.sortCol===col && this.state.sortDir===dir; }

    // ── Reminder popup ────────────────────────────────────────────────────
    openReminder() {
        this.state.reminderCount = this.state.filteredRows.filter(r=>r.overdue<0).length;
        this.state.reminderOpen  = true;
    }
    closeReminder() { this.state.reminderOpen=false; }
    confirmReminder() { this.state.reminderOpen=false; alert(`Reminders queued for ${this.state.reminderCount} customer(s).`); }

    // ── Communication panel ───────────────────────────────────────────────
    openComm(row) {
        this.state.commPartner   = { id: row.partner_id, name: row.partner, phone: row.phone||"", email: row.email||"" };
        this.state.commHistory   = row.comm_history || [];
        this.state.commRemark    = "";
        this.state.commRemarkType= "remark";
        this.state.activePopup   = null;
        this.state.commOpen      = true;
        // Pre-fill WhatsApp/email from partner
        this.state.waNumber      = row.phone || "";
        this.state.emailTo       = row.email || "";
        this.state.waMessage     = `Hello ${row.partner}, this is a gentle reminder regarding your pending payment.`;
    }
    closeComm() { this.state.commOpen=false; this.state.activePopup=null; }

    openPopup(type) { this.state.activePopup=type; }
    closePopup()    { this.state.activePopup=null; }

    // Snooze
    onSnoozeRemark(ev) { this.state.snoozeRemark=ev.target.value; }
    onSnoozeUntil(ev)  { this.state.snoozeUntil=ev.target.value; }
    submitSnooze() {
        if (!this.state.snoozeUntil) return;
        this.state.commHistory.unshift({ type:"snooze", text:`Snoozed until ${this.state.snoozeUntil}. ${this.state.snoozeRemark}`, date: new Date().toLocaleString("en-IN") });
        this.state.snoozeRemark=""; this.state.snoozeUntil="";
        this.closePopup();
    }

    // Call
    onCallNote(ev)      { this.state.callNote=ev.target.value; }
    setCallStatus(s)    { this.state.callStatus=s; this.state.callStatusOpen=false; }
    toggleCallDD()      { this.state.callStatusOpen=!this.state.callStatusOpen; }
    submitCall() {
        this.state.commHistory.unshift({ type:"call", text:`Call ${this.state.callStatus==="answered"?"Answered":"Unanswered"}. ${this.state.callNote}`, date: new Date().toLocaleString("en-IN") });
        this.state.callNote=""; this.closePopup();
    }

    // WhatsApp
    onWaNumber(ev)      { this.state.waNumber=ev.target.value; }
    onWaMessage(ev)     { this.state.waMessage=ev.target.value; }
    toggleWaStatement() { this.state.waAddStatement=!this.state.waAddStatement; }
    toggleWaLedger()    { this.state.waAddLedger=!this.state.waAddLedger; }
    submitWhatsApp() {
        const num = this.state.waNumber.replace(/\D/g,"");
        if (!num) return;
        const url = `https://wa.me/${num}?text=${encodeURIComponent(this.state.waMessage)}`;
        window.open(url,"_blank");
        this.state.commHistory.unshift({ type:"whatsapp", text:`WhatsApp sent: ${this.state.waMessage.slice(0,60)}...`, date: new Date().toLocaleString("en-IN") });
        this.closePopup();
    }

    // Email
    onEmailTo(ev)             { this.state.emailTo=ev.target.value; }
    toggleEmailStatement()    { this.state.emailAddStatement=!this.state.emailAddStatement; }
    toggleEmailLedger()       { this.state.emailAddLedger=!this.state.emailAddLedger; }
    async submitEmail() {
        if (!this.state.emailTo) {
            alert("Please enter an email address.");
            return;
        }
        this.state.emailSending = true;
        try {
            const res = await rpc("/vahini_dashboard/send_email", {
                partner_id:     this.state.commPartner.id,
                email_to:       this.state.emailTo,
                add_statement:  this.state.emailAddStatement,
                add_ledger:     this.state.emailAddLedger,
            });
            if (res && res.success) {
                this.state.commHistory.unshift({
                    type: "email",
                    text: `Email sent to ${this.state.emailTo}`,
                    date: new Date().toLocaleString("en-IN")
                });
                this.closePopup();
            } else {
                const errMsg = (res && res.error) || "Failed to send email.";
                alert("Email Error: " + errMsg);
            }
        } catch(e) {
            alert("Failed to send email. Please check your Odoo mail server configuration in Settings → Technical → Outgoing Mail Servers.");
        } finally {
            this.state.emailSending = false;
        }
    }

    // Remark
    onRemarkInput(ev)   { this.state.commRemark=ev.target.value; }
    onRemarkTypeChange(ev) { this.state.commRemarkType=ev.target.value; }
    submitRemark() {
        if (!this.state.commRemark.trim()) return;
        this.state.commHistory.unshift({ type: this.state.commRemarkType, text: this.state.commRemark, date: new Date().toLocaleString("en-IN") });
        this.state.commRemark="";
    }

    // ── Download PDF ──────────────────────────────────────────────────────
    downloadPDF() {
        const label = this.state.reportType==="receivable"?"Receivable":"Payable";
        let html=`<html><head><style>body{font-family:Arial,sans-serif;font-size:10px;padding:20px;}h2{color:#1e293b;margin-bottom:4px;}p{color:#64748b;margin:0 0 12px;}table{width:100%;border-collapse:collapse;}th{background:#1e3a5f;color:#fff;padding:6px 8px;text-align:left;font-size:9px;white-space:nowrap;}td{padding:5px 8px;border-bottom:1px solid #e2e8f0;font-size:9px;}tr:nth-child(even)td{background:#f8fafc;}.num{text-align:right;}</style></head><body><h2>Payment Report — ${label}</h2><p>Generated: ${new Date().toLocaleDateString("en-IN")}</p><table><thead><tr><th>Customer/Vendor</th><th class="num">0-50</th><th class="num">51-90</th><th class="num">Over 90</th><th class="num">Outstanding</th><th class="num">Other</th><th class="num">Interest</th><th class="num">Total Outstanding</th></tr></thead><tbody>`;
        for(const r of this.state.filteredRows) html+=`<tr><td>${r.partner}</td><td class="num">${this.fmt(r.range_0_50)}</td><td class="num">${this.fmt(r.range_51_90)}</td><td class="num">${this.fmt(r.overdue)}</td><td class="num">${this.fmt(r.outstanding)}</td><td class="num">${this.fmt(r.other)}</td><td class="num">${this.fmt(r.interest)}</td><td class="num">${this.fmt(r.total)}</td></tr>`;
        html+=`</tbody></table></body></html>`;
        const w=window.open("","_blank"); w.document.write(html); w.document.close();
        setTimeout(()=>{w.print();w.close();},400);
    }

    // ── Formatters ────────────────────────────────────────────────────────
    fmt(v)    { const n=parseFloat(v)||0; if(!n) return "0"; return n.toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:0}); }
    fmtKpi(v) { const n=parseFloat(v)||0; if(Math.abs(n)>=10000000) return (n/10000000).toFixed(2)+" Cr"; if(Math.abs(n)>=100000) return (n/100000).toFixed(2)+" L"; return n.toLocaleString("en-IN",{maximumFractionDigits:0}); }
    cls(v)    { const n=parseFloat(v)||0; return n<0?"pvw-neg":n>0?"pvw-pos":""; }
    histIcon(type) { return {remark:"💬",snooze:"🔔",call:"📞",whatsapp:"💬",email:"✉️"}[type]||"📝"; }
}
