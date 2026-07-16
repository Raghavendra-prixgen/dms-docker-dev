# -*- coding: utf-8 -*-
from odoo import models, api
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

COLOURS = [
    "#6ed9e0", "#87c257", "#f4c374", "#d94f63", "#a8d8ea",
    "#c9b1d9", "#ffd97d", "#a3d977", "#e8b89a", "#f9e4b7",
    "#70bfc5", "#9db86b", "#f97316", "#8b5cf6", "#4f6df5",
    "#059669", "#dc2626", "#0ea5e9", "#ec4899", "#84cc16",
]


def _c(i): return COLOURS[i % len(COLOURS)]

# ── Module-level schema introspection cache ───────────────────────────────────
# Populated once per Odoo worker process on first use; never re-queries
# pg_typeof / information_schema again for the lifetime of the worker.
_SCHEMA_CACHE = {}


def _schema(cr, key, sql):
    """Return cached result of a one-time schema probe query."""
    if key not in _SCHEMA_CACHE:
        cr.execute(sql)
        _SCHEMA_CACHE[key] = cr.fetchone()
    return _SCHEMA_CACHE[key]


class VahiniDashboard(models.AbstractModel):
    _name = "vahini.dashboard"
    _description = "Vahini Dashboard Data Provider"

    # ── Company helper ────────────────────────────────────────────────────────
    def _cid(self):
        """Current company id — kept for backward compatibility."""
        return self.env.company.id

    def _cids(self):
        """
        Returns a list of company IDs to include in queries:
        - The currently selected company
        - PLUS all its branch companies (child companies where parent_id = this company)

        This means selecting VAHINI TRADING COMPANY automatically includes
        HASSAN - VAHINI TRADING COMPANY and any other future branches.
        If a branch itself is selected directly, only that branch's data shows.

        Fully dynamic — no hardcoding. Adding a new branch in Odoo's
        Settings → Companies automatically includes it here.
        """
        company = self.env.company
        # Find all branches of this company (child companies)
        branches = self.env['res.company'].sudo().search([
            ('parent_id', '=', company.id)
        ])
        ids = [company.id] + branches.ids
        return ids

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        from odoo import fields as F
        today = date.today()
        df = F.Date.from_string(date_from) if date_from else today.replace(day=1)
        dt = F.Date.from_string(date_to) if date_to else today

        return {
            "date_from": str(df),
            "date_to": str(dt),
            "metrics": self._metrics(df, dt),
            "state": self._by_state(df, dt),
            "district": self._by_district(df, dt),
            "area": self._by_area(df, dt),
            "city": self._by_city(df, dt),
            "item_table": self._items(df, dt),
            "customer_table": self._customers(df, dt),
            "customer_type_table": self._cust_types(df, dt),
        }

    # ── KPI metrics ──────────────────────────────────────────────────

    def _metrics(self, df, dt):
        yesterday = date.today() - timedelta(days=1)
        yest_amt = self._inv_sum(yesterday, yesterday)
        period_amt = self._inv_sum(df, dt)
        stock_val = self._stock_val()
        receivable = self._open_bal("asset_receivable")
        payable = self._open_bal("liability_payable")
        days = max(1, (dt - df).days + 1)
        return [
            {"title": "Yesterday", "date": str(yesterday),
             "value": round(yest_amt), "icon": "calendar", "color": "#8b5cf6"},
            {"title": "Selected Period",
             "date": f"{df.strftime('%d-%b-%Y')} – {dt.strftime('%d-%b-%Y')}",
             "value": round(period_amt), "icon": "zap", "color": "#4f6df5"},
            {"title": "Stock", "date": "",
             "value": round(stock_val), "icon": "building", "color": "#f59e0b"},
            {"title": "Receivable", "date": "",
             "value": round(receivable), "icon": "landmark", "color": "#059669"},
            {"title": "Payable", "date": "",
             "value": round(-abs(payable)), "icon": "arrow-down", "color": "#dc2626"},
            {"title": "Average",
             "date": f"{df.strftime('%d-%b-%Y')} – {dt.strftime('%d-%b-%Y')}",
             "value": round(period_amt / days), "icon": "calculator", "color": "#f97316"},
        ]

    # ── Charts ───────────────────────────────────────────────────────

    def _by_state(self, df, dt):
        self.env.cr.execute("""
            SELECT COALESCE(NULLIF(TRIM(rs.name), ''), 'Not Defined') AS nm,
                   SUM(am.amount_untaxed) AS tot
            FROM account_move am
            JOIN res_partner rp ON rp.id = am.partner_id
            LEFT JOIN res_country_state rs ON rs.id = rp.state_id
            WHERE am.move_type='out_invoice' AND am.state='posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
            GROUP BY rs.name ORDER BY tot DESC LIMIT 20
        """, (self._cids(), df, dt))
        return [{"name": r[0], "value": float(r[1] or 0), "colour": _c(i)}
                for i, r in enumerate(self.env.cr.fetchall())]

    def _by_district(self, df, dt):
        # detect district column once per worker (cached)
        r = _schema(self.env.cr, 'has_l10n_in_dist',
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='res_partner' AND column_name='l10n_in_dist'")
        col = "rp.l10n_in_dist" if r else "rp.city"
        self.env.cr.execute(f"""
            SELECT COALESCE(NULLIF(TRIM({col}),''),'Not Defined') AS nm,
                   SUM(am.amount_untaxed) AS tot
            FROM account_move am
            JOIN res_partner rp ON rp.id = am.partner_id
            WHERE am.move_type='out_invoice' AND am.state='posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
            GROUP BY {col} ORDER BY tot DESC LIMIT 20
        """, (self._cids(), df, dt))
        return [{"name": r[0], "value": float(r[1] or 0), "colour": _c(i)}
                for i, r in enumerate(self.env.cr.fetchall())]

    def _by_area(self, df, dt):
        # street2 = Area/Zone. Change to x_studio_area or your custom field if needed.
        self.env.cr.execute("""
            SELECT COALESCE(NULLIF(TRIM(rp.street2),''),'Not Defined') AS nm,
                   SUM(am.amount_untaxed) AS tot
            FROM account_move am
            JOIN res_partner rp ON rp.id = am.partner_id
            WHERE am.move_type='out_invoice' AND am.state='posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
            GROUP BY rp.street2 ORDER BY tot DESC LIMIT 20
        """, (self._cids(), df, dt))
        return [{"name": r[0], "value": float(r[1] or 0), "colour": _c(i)}
                for i, r in enumerate(self.env.cr.fetchall())]

    def _by_city(self, df, dt):
        self.env.cr.execute("""
            SELECT COALESCE(NULLIF(TRIM(rp.city),''),'Not Defined') AS nm,
                   SUM(am.amount_untaxed) AS tot
            FROM account_move am
            JOIN res_partner rp ON rp.id = am.partner_id
            WHERE am.move_type='out_invoice' AND am.state='posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
            GROUP BY rp.city ORDER BY tot DESC LIMIT 20
        """, (self._cids(), df, dt))
        return [{"name": r[0], "value": float(r[1] or 0), "colour": _c(i)}
                for i, r in enumerate(self.env.cr.fetchall())]

    # ── Tables ───────────────────────────────────────────────────────

    def _items(self, df, dt):

        avg_dt = df - timedelta(days=1)
        avg_df = avg_dt - relativedelta(months=6)
        lang = self.env.lang or 'en_US'
        cid  = self._cids()

        self.env.cr.execute("""
            WITH p AS (
                SELECT COALESCE(NULLIF(TRIM(pt.name->>%s), ''), 'Unknown') AS nm,
                       SUM(l.price_subtotal) AS tot
                FROM account_move_line l
                JOIN account_move am ON am.id=l.move_id
                JOIN product_product pp ON pp.id=l.product_id
                JOIN product_template pt ON pt.id=pp.product_tmpl_id
                WHERE am.move_type='out_invoice' AND am.state='posted'
                  AND am.company_id = ANY(%s)
                  AND am.invoice_date BETWEEN %s AND %s AND l.product_id IS NOT NULL
                GROUP BY pt.name->>%s
            ),
            a AS (
                SELECT COALESCE(NULLIF(TRIM(pt.name->>%s), ''), 'Unknown') AS nm,
                       SUM(l.price_subtotal) AS tot
                FROM account_move_line l
                JOIN account_move am ON am.id=l.move_id
                JOIN product_product pp ON pp.id=l.product_id
                JOIN product_template pt ON pt.id=pp.product_tmpl_id
                WHERE am.move_type='out_invoice' AND am.state='posted'
                  AND am.company_id = ANY(%s)
                  AND am.invoice_date BETWEEN %s AND %s AND l.product_id IS NOT NULL
                GROUP BY pt.name->>%s
            ),
            g AS (SELECT SUM(tot) AS tot FROM p)
            SELECT p.nm,
                   ROUND(p.tot::numeric,0),
                   ROUND(COALESCE(a.tot,0)::numeric/6,0),
                   CASE WHEN g.tot>0 THEN ROUND((p.tot/g.tot*100)::numeric,0) ELSE 0 END
            FROM p LEFT JOIN a ON a.nm=p.nm CROSS JOIN g
            ORDER BY p.tot DESC LIMIT 50
        """, (lang, cid, df, dt, lang, lang, cid, avg_df, avg_dt, lang))
        rows = self.env.cr.fetchall()
        return {
            "title": "Item Name", "rowCount": len(rows),
            "rows": [{"name": r[0] or "Unknown", "sales": int(r[1] or 0),
                      "avg": int(r[2] or 0), "contrib": int(r[3] or 0)} for r in rows]
        }

    def _customers(self, df, dt):
        avg_dt = df - timedelta(days=1)
        avg_df = avg_dt - relativedelta(months=6)
        cid    = self._cids()
        self.env.cr.execute("""
            WITH p AS (
                SELECT rp.name AS nm, SUM(am.amount_untaxed) AS tot
                FROM account_move am JOIN res_partner rp ON rp.id=am.partner_id
                WHERE am.move_type='out_invoice' AND am.state='posted'
                  AND am.company_id = ANY(%s)
                  AND am.invoice_date BETWEEN %s AND %s
                GROUP BY rp.name
            ),
            a AS (
                SELECT rp.name AS nm, SUM(am.amount_untaxed) AS tot
                FROM account_move am JOIN res_partner rp ON rp.id=am.partner_id
                WHERE am.move_type='out_invoice' AND am.state='posted'
                  AND am.company_id = ANY(%s)
                  AND am.invoice_date BETWEEN %s AND %s
                GROUP BY rp.name
            ),
            g AS (SELECT SUM(tot) AS tot FROM p)
            SELECT p.nm,
                   ROUND(p.tot::numeric,0),
                   ROUND(COALESCE(a.tot,0)::numeric/6,0),
                   CASE WHEN g.tot>0 THEN ROUND((p.tot/g.tot*100)::numeric,0) ELSE 0 END
            FROM p LEFT JOIN a ON a.nm=p.nm CROSS JOIN g
            ORDER BY p.tot DESC LIMIT 50
        """, (cid, df, dt, cid, avg_df, avg_dt))
        rows = self.env.cr.fetchall()
        return {
            "title": "Customer Name", "rowCount": len(rows),
            "rows": [{"name": r[0] or "Unknown", "sales": int(r[1] or 0),
                      "avg": int(r[2] or 0), "contrib": int(r[3] or 0)} for r in rows]
        }

    def _cust_types(self, df, dt):
        avg_dt = df - timedelta(days=1)
        avg_df = avg_dt - relativedelta(months=6)
        cid    = self._cids()
        self.env.cr.execute("""
            WITH p AS (
                SELECT CASE WHEN rp.is_company THEN 'Company'
                            ELSE 'Individual' END AS ct,
                       SUM(am.amount_untaxed) AS tot
                FROM account_move am
                JOIN res_partner rp ON rp.id=am.partner_id
                WHERE am.move_type='out_invoice' AND am.state='posted'
                  AND am.company_id = ANY(%s)
                  AND am.invoice_date BETWEEN %s AND %s
                GROUP BY rp.is_company
            ),
            a AS (
                SELECT CASE WHEN rp.is_company THEN 'Company'
                            ELSE 'Individual' END AS ct,
                       SUM(am.amount_untaxed) AS tot
                FROM account_move am
                JOIN res_partner rp ON rp.id=am.partner_id
                WHERE am.move_type='out_invoice' AND am.state='posted'
                  AND am.company_id = ANY(%s)
                  AND am.invoice_date BETWEEN %s AND %s
                GROUP BY rp.is_company
            ),
            g AS (SELECT SUM(tot) AS tot FROM p)
            SELECT p.ct,
                   ROUND(p.tot::numeric,0),
                   ROUND(COALESCE(a.tot,0)::numeric/6,0),
                   CASE WHEN g.tot>0 THEN ROUND((p.tot/g.tot*100)::numeric,0) ELSE 0 END
            FROM p LEFT JOIN a ON a.ct=p.ct CROSS JOIN g
            ORDER BY p.tot DESC
        """, (cid, df, dt, cid, avg_df, avg_dt))
        rows = self.env.cr.fetchall()
        return {
            "title": "Customer Type", "rowCount": len(rows),
            "rows": [{"name": r[0], "sales": int(r[1] or 0),
                      "avg": int(r[2] or 0), "contrib": int(r[3] or 0)} for r in rows]
        }

    # ── Helpers ──────────────────────────────────────────────────────

    def _inv_sum(self, df, dt):
        self.env.cr.execute(
            "SELECT COALESCE(SUM(amount_untaxed),0) FROM account_move "
            "WHERE move_type='out_invoice' AND state='posted' "
            "AND company_id = ANY(%s) "
            "AND invoice_date BETWEEN %s AND %s", (self._cids(), df, dt))
        return float(self.env.cr.fetchone()[0])

    def _stock_val(self):
        try:
            self.env.cr.execute(
                "SELECT COALESCE(SUM(value),0) FROM stock_valuation_layer "
                "WHERE company_id = ANY(%s)", (self._cids(),))
            return float(self.env.cr.fetchone()[0])
        except Exception:
            return 0.0

    def _open_bal(self, acc_type):
        # Odoo 17/18: account_type on account.account
        try:
            self.env.cr.execute("""
                SELECT COALESCE(SUM(aml.amount_residual),0)
                FROM account_move_line aml
                JOIN account_account aa ON aa.id=aml.account_id
                JOIN account_move am    ON am.id=aml.move_id
                WHERE aa.account_type=%s AND aml.reconciled=false
                  AND am.company_id = ANY(%s)
            """, (acc_type, self._cids()))
            return float(self.env.cr.fetchone()[0])
        except Exception:
            return 0.0



    @api.model
    def get_dashboard_table(self, group_by='item_name', date_from=None,
                            date_to=None, search='', page=1, per_page=10):
        """Dashboard table with dynamic grouping - 35 options."""
        from datetime import datetime as dt2
        def parse(d):
            if not d: return None
            if isinstance(d, str): return dt2.strptime(d[:10], "%Y-%m-%d").date()
            return d

        df  = parse(date_from)
        dtt = parse(date_to)

        def is_jsonb(table, col='name'):
            self.env.cr.execute(f"SELECT pg_typeof({col}) FROM {table} LIMIT 1")
            r = self.env.cr.fetchone()
            return r and 'json' in str(r[0])

        pt_name = ("COALESCE((pt.name::jsonb)->>'en_US', pt.name::text)"
                   if is_jsonb('product_template') else "pt.name::text")
        pc_name = ("COALESCE((pc.name::jsonb)->>'en_US', pc.name::text)"
                   if is_jsonb('product_category') else "pc.name::text")
        rp_name = ("COALESCE((rp.name::jsonb)->>'en_US', rp.name::text)"
                   if is_jsonb('res_partner') else "COALESCE(rp.name::text,'Unknown')")
        uu_name = ("COALESCE((uu.name::jsonb)->>'en_US', uu.name::text)"
                   if is_jsonb('uom_uom') else "COALESCE(uu.name::text,'')")

        grp_map = {
            'area':           ("COALESCE(rp.city,'Unknown')",                    "rp.city"),
            'batch_tracking': ("COALESCE(pp.default_code,'Unknown')",            "pp.default_code"),
            'billno':         ("am.name",                                         "am.id"),
            'category':       (pc_name,                                           "pc.id"),
            'city':           ("COALESCE(rp.city,'Unknown')",                     "rp.city"),
            'company_name':   ("COALESCE(rc.name,'Unknown')",                     "rc.id"),
            'conversion':     ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'customer_alias': (rp_name,                                           "rp.id"),
            'customer_name':  (rp_name,                                           "rp.id"),
            'customer_type':  ("COALESCE(rp.customer_rank::text,'0')",            "rp.customer_rank"),
            'district':       ("COALESCE(rcs.name::text,'Unknown')",              "rcs.id"),
            'document_type':  ("am.move_type::text",                              "am.move_type"),
            'godown_name':    ("COALESCE(sl.name::text,'Unknown')",               "sl.id"),
            'gstno':          ("COALESCE(rp.vat,'Unknown')",                      "rp.vat"),
            'im9':            ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'item_alias':     ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'item_group':     (pc_name,                                           "pc.id"),
            'item_name':      (pt_name,                                           "pt.id"),
            'item_names':     (pt_name,                                           "pt.id"),
            'mobileno':       ("COALESCE(rp.mobile,'Unknown')",                   "rp.mobile"),
            'mrp':            ("COALESCE(pt.list_price::text,'0')",               "pt.list_price"),
            'mrps':           ("COALESCE(pt.list_price::text,'0')",               "pt.list_price"),
            'part_no':        ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'product_category':(pc_name,                                          "pc.id"),
            'product_group':  (pc_name,                                           "pc.id"),
            'referenceno':    ("COALESCE(am.ref,'Unknown')",                      "am.ref"),
            'scheme':         ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'state':          ("COALESCE(rcs.name::text,'Unknown')",              "rcs.id"),
            'subcategory':    ("COALESCE(pc.complete_name::text,'Unknown')",      "pc.id"),
            'tim10':          ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'tim20':          ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'tim30':          ("COALESCE(pp.default_code,'Unknown')",             "pp.id"),
            'uom':            (uu_name,                                           "uu.id"),
            'voucher_type':   ("am.move_type::text",                              "am.move_type"),
            'weight':         ("COALESCE(pt.weight::text,'0')",                   "pt.weight"),
        }
        grp_expr, grp_id = grp_map.get(group_by, grp_map['item_name'])

        date_params = []
        date_clause = ""
        if df and dtt:
            date_clause = " AND am.invoice_date BETWEEN %s AND %s"
            date_params = [df, dtt]

        joins = (
            " FROM account_move am"
            " JOIN account_move_line aml ON aml.move_id = am.id"
            " JOIN product_product pp ON pp.id = aml.product_id"
            " JOIN product_template pt ON pt.id = pp.product_tmpl_id"
            " LEFT JOIN product_category pc ON pc.id = pt.categ_id"
            " LEFT JOIN res_partner rp ON rp.id = am.partner_id"
            " LEFT JOIN res_country_state rcs ON rcs.id = rp.state_id"
            " LEFT JOIN res_company rc ON rc.id = am.company_id"
            " LEFT JOIN uom_uom uu ON uu.id = pt.uom_id"
            " LEFT JOIN stock_location sl ON sl.usage='internal' AND sl.active=TRUE"
        )
        base_where = " WHERE am.move_type='out_invoice' AND am.state='posted' AND aml.display_type='product' AND am.company_id = ANY(%s)"

        # Count
        self.env.cr.execute(
            f"SELECT COUNT(DISTINCT {grp_id})" + joins + base_where + date_clause,
            [self._cids()] + date_params
        )
        total = int(self.env.cr.fetchone()[0] or 0)

        # Grand total for contrib
        self.env.cr.execute(
            "SELECT COALESCE(SUM(aml.price_subtotal),0)" + joins + base_where + date_clause,
            [self._cids()] + date_params
        )
        grand_total = float(self.env.cr.fetchone()[0] or 1)

        # Main query
        offset = (max(1, page) - 1) * per_page
        self.env.cr.execute(
            f"SELECT {grp_expr} AS lbl,"
            " COALESCE(SUM(aml.quantity),0) AS qty,"
            " COALESCE(SUM(aml.price_total - aml.price_subtotal),0) AS tax_paid,"
            " COALESCE(SUM(aml.price_subtotal),0) AS tax_less,"
            " COALESCE(SUM(aml.price_total),0) AS tax_incl"
            + joins + base_where + date_clause +
            f" GROUP BY {grp_expr}"
            " ORDER BY tax_less DESC"
            f" LIMIT {per_page} OFFSET {offset}",
            [self._cids()] + date_params
        )
        rows = []
        for lbl, qty, tax_paid, tax_less, tax_incl in self.env.cr.fetchall():
            q = float(qty or 0)
            tl = float(tax_less or 0)
            ti = float(tax_incl or 0)
            rows.append({
                'name':        str(lbl) if lbl else 'Unknown',
                'qty':         round(q, 0),
                'tax_paid':    round(float(tax_paid or 0), 0),
                'tax_less':    round(tl, 0),
                'asp':         round(tl / q, 2) if q else 0,
                'asp_taxpaid': round(ti / q, 2) if q else 0,
                'contrib':     round(tl * 100.0 / grand_total, 1) if grand_total else 0,
            })

        return {
            'rows':        rows,
            'total':       total,
            'total_pages': max(1, -(-total // per_page)),
            'page':        page,
        }

    @api.model
    def get_compare_data(self, chart_id, date_from, date_to,
                         prev_from, prev_to, page=1, per_page=10):

        from odoo import fields as F
        df   = F.Date.from_string(date_from)
        dt   = F.Date.from_string(date_to)
        pdf  = F.Date.from_string(prev_from)
        pdt  = F.Date.from_string(prev_to)

        dispatch = {
            "state":    self._by_state,
            "district": self._by_district,
            "area":     self._by_area,
            "city":     self._by_city,
        }
        fn = dispatch.get(chart_id, self._by_state)

        curr_all = fn(df, dt)
        prev_all = fn(pdf, pdt)

        total       = len(curr_all)
        total_pages = max(1, -(-total // per_page))          # ceiling div
        page        = max(1, min(page, total_pages))
        start       = (page - 1) * per_page
        curr_page   = curr_all[start:start + per_page]

        prev_map = {r["name"]: r for r in prev_all}
        prev_page = []
        for r in curr_page:
            pr = prev_map.get(r["name"], {"name": r["name"], "value": 0, "colour": r["colour"]})
            prev_page.append(pr)

        return {
            "curr": curr_page,
            "prev": prev_page,
            "total": total,
            "total_pages": total_pages,
            "page": page,
        }

    @api.model
    def get_dayview_data(self, date_from=None, date_to=None,
                         view_type="transactions", tab="sales",
                         page=1, per_page=15, sort_col="invoice_date",
                         sort_dir="desc", search=""):
        from odoo import fields as F
        today = date.today()
        df = F.Date.from_string(date_from) if date_from else today.replace(day=1)
        dt = F.Date.from_string(date_to)   if date_to   else today

        page     = max(1, int(page or 1))
        per_page = max(1, int(per_page or 15))

        if view_type == "bank":
            return self._dayview_bank(df, dt, page, per_page, sort_col, sort_dir, search or "")

        move_map = {"sales": "out_invoice", "return": "out_refund",
                    "dn": "out_invoice",    "cn": "out_refund"}
        move_type = move_map.get(tab, "out_invoice")

        if tab in ("purchase", "purchase_return"):
            move_type = "in_invoice" if tab == "purchase" else "in_refund"
            return self._dayview_purchase(df, dt, move_type, page, per_page,
                                          sort_col, sort_dir, search or "")

        return self._dayview_transactions(df, dt, move_type, page, per_page,
                                          sort_col, sort_dir, search or "")

    def _dayview_transactions(self, df, dt, move_type, page, per_page,
                               sort_col, sort_dir, search):
        # ── District column — check if l10n_in_dist exists on res_partner ─
        _has_dist = _schema(self.env.cr, 'has_l10n_in_dist',
                            "SELECT 1 FROM information_schema.columns "
                            "WHERE table_name='res_partner' AND column_name='l10n_in_dist'")
        district_col = "rp.l10n_in_dist" if _has_dist else "partner.city"

        # ── Column map for sorting ────────────────────────────────────────
        col_map = {
            "invoice_number":   "am.name",
            "invoice_date":     "am.invoice_date",
            "customer_code":    "partner.ref",
            "customer":         "partner.name",
            "vat":              "partner.vat",
            "company":          "comp.name",
            "salesperson":      "usr_partner.name",
            "sales_team":       "ct.name::text",
            "product_code":     "product.default_code",
            "product":          "pt.name::text",
            "label":            "aml.name",
            "product_category": "pc.name::text",
            "quantity":         "aml.quantity",
            "price":            "aml.price_unit",
            "amount_excl_tax":  "aml.tally_amount",
            "amount_incl_tax":  "aml.price_total",
            "payment_state":    "am.payment_state",
            "invoice_type":     "am.move_type",
        }
        order_col = col_map.get(sort_col, "am.invoice_date")
        order_dir = "ASC" if sort_dir == "asc" else "DESC"

        lang = self.env.lang or "en_US"

      
        def jn(alias):
            """Return SQL that extracts text safely from jsonb OR plain varchar."""
            return (
                f"COALESCE("
                f"CASE WHEN pg_typeof({alias}.name) = 'jsonb'::regtype "
                f"THEN COALESCE(({alias}.name)::jsonb->>'{lang}', ({alias}.name)::jsonb->>'en_US', {alias}.name::text) "
                f"ELSE {alias}.name::text END, '')"
            )

        # ── Search clause ─────────────────────────────────────────────────
        s_clause = ""
        s_params = []
        if search:
            s_clause = (
                " AND (am.name ILIKE %s"
                " OR partner.name ILIKE %s"
                " OR product.default_code ILIKE %s)"
            )
            s_params = [f"%{search}%", f"%{search}%", f"%{search}%"]

        # ── Check if partner_category (contact_base) table exists ─────────
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'partner_category'
            )
        """)
        has_partner_category = self.env.cr.fetchone()[0]

        # ── Check if y_partner_category column exists on res_partner ─────
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'res_partner'
                AND column_name = 'y_partner_category'
            )
        """)
        has_y_partner_category = self.env.cr.fetchone()[0]

        # ── Build FROM clause — conditionally join partner_category ───────
        pcat_join = ""
        pcat_select = "''"
        if has_partner_category and has_y_partner_category:
            pcat_join   = "LEFT JOIN partner_category pcat ON pcat.id = partner.y_partner_category"
            pcat_select = "COALESCE(pcat.y_name, '')"

        base_from = f"""
            FROM account_move_line aml
            LEFT JOIN account_move am           ON am.id = aml.move_id
            LEFT JOIN res_partner partner        ON partner.id = am.partner_id
            LEFT JOIN product_product product    ON product.id = aml.product_id
            LEFT JOIN product_template pt        ON pt.id = product.product_tmpl_id
            LEFT JOIN product_category pc        ON pc.id = pt.categ_id
            LEFT JOIN uom_uom uom                ON uom.id = pt.uom_id
            LEFT JOIN account_account aa         ON aa.id = aml.account_id
            LEFT JOIN account_journal aj         ON aj.id = aml.journal_id
            LEFT JOIN res_currency cur           ON cur.id = am.currency_id
            LEFT JOIN res_company comp           ON comp.id = am.company_id
            LEFT JOIN res_users usr              ON usr.id = am.invoice_user_id
            LEFT JOIN res_partner usr_partner    ON usr_partner.id = usr.partner_id
            LEFT JOIN crm_team ct                ON ct.id = am.team_id
            LEFT JOIN res_country_state cst      ON cst.id = partner.state_id
            LEFT JOIN res_country cco            ON cco.id = partner.country_id
            {pcat_join}
        """

        base_where = f"""
            WHERE am.move_type = %s
              AND am.state = 'posted'
              AND aml.display_type = 'product'
              AND aml.product_id IS NOT NULL
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s{s_clause}
        """
        base_params = [move_type, self._cids(), df, dt] + s_params

        # ── Total count ───────────────────────────────────────────────────
        self.env.cr.execute(
            f"SELECT COUNT(aml.id) {base_from} {base_where}",
            base_params
        )
        total = self.env.cr.fetchone()[0]


        total_pages = max(1, -(-total // per_page))
        page        = max(1, min(page, total_pages))
        offset      = (page - 1) * per_page

        # ── Summary row ───────────────────────────────────────────────────
        self.env.cr.execute(f"""
            SELECT
                COUNT(DISTINCT am.id),
                COALESCE(SUM(CASE WHEN am.move_type='out_refund'
                    THEN -(aml.quantity)       ELSE aml.quantity       END), 0),
                COALESCE(SUM(CASE WHEN am.move_type='out_refund'
                    THEN -(aml.price_subtotal) ELSE aml.price_subtotal END), 0),
                COALESCE(SUM(CASE WHEN am.move_type='out_refund'
                    THEN -(aml.price_total)    ELSE aml.price_total    END), 0)
            {base_from} {base_where}
        """, base_params)
        s = self.env.cr.fetchone()

        # ── Odoo 18: account_tax.name is jsonb ───────────────────────────
        tax_subq = """
            (SELECT COALESCE(string_agg(
                CASE WHEN pg_typeof(xt.name) = 'jsonb'::regtype
                     THEN COALESCE((xt.name)::jsonb->>'{L}', (xt.name)::jsonb->>'en_US', xt.name::text)
                     ELSE xt.name::text END,
                ', ' ORDER BY xt.name::text), '')
             FROM account_move_line_account_tax_rel taxrel
             LEFT JOIN account_tax xt ON xt.id = taxrel.account_tax_id
             WHERE taxrel.account_move_line_id = aml.id)
        """.replace("{L}", lang)

        # ── Sale order subqueries ─────────────────────────────────────────
        so_name_subq = """
            (SELECT string_agg(DISTINCT so2.name, ', ' ORDER BY so2.name)
             FROM sale_order_line_invoice_rel slr2
             LEFT JOIN sale_order_line sl2 ON sl2.id = slr2.order_line_id
             LEFT JOIN sale_order so2      ON so2.id = sl2.order_id
             WHERE slr2.invoice_line_id = aml.id)
        """
        so_date_subq = """
            (SELECT TO_CHAR(MIN(so3.date_order), 'DD-MM-YYYY')
             FROM sale_order_line_invoice_rel slr3
             LEFT JOIN sale_order_line sl3 ON sl3.id = slr3.order_line_id
             LEFT JOIN sale_order so3      ON so3.id = sl3.order_id
             WHERE slr3.invoice_line_id = aml.id)
        """

        # ── Odoo 18: account_analytic_account.name is jsonb ──────────────
        analytic_subq = """
            (SELECT string_agg(
                CASE WHEN pg_typeof(anac.name) = 'jsonb'::regtype
                     THEN COALESCE((anac.name)::jsonb->>'{L}', (anac.name)::jsonb->>'en_US', anac.name::text)
                     ELSE anac.name::text END,
                ', ' ORDER BY anac.name::text)
             FROM jsonb_object_keys(aml.analytic_distribution::jsonb) ak
             JOIN account_analytic_account anac
                  ON anac.id = ak::integer AND anac.active
             WHERE aml.analytic_distribution IS NOT NULL)
        """.replace("{L}", lang)

        # ── Odoo 18: account_account.name & account_journal.name are jsonb
        # Odoo 18: account_account.code is in account_account_code table, not aa directly
        # Use aa.name only (same as Odoo 18 display_name for chart of accounts)
        aa_name = (
            "COALESCE("
            "CASE WHEN pg_typeof(aa.name) = 'jsonb'::regtype "
            f"THEN COALESCE((aa.name)::jsonb->>'{lang}', (aa.name)::jsonb->>'en_US', aa.name::text) "
            "ELSE aa.name::text END, '')"
        )
        aj_name = (
            "COALESCE("
            "CASE WHEN pg_typeof(aj.name) = 'jsonb'::regtype "
            f"THEN COALESCE((aj.name)::jsonb->>'{lang}', (aj.name)::jsonb->>'en_US', aj.name::text) "
            "ELSE aj.name::text END, '')"
        )

        # ── Main SELECT ───────────────────────────────────────────────────
        self.env.cr.execute(f"""
            SELECT
                COALESCE(am.name, '')                                        AS invoice_number,
                TO_CHAR(am.invoice_date, 'DD-MM-YYYY')                      AS invoice_date,
                COALESCE(partner.ref, '')                                    AS customer_code,
                COALESCE(partner.name, '')                                   AS customer,
                COALESCE(partner.vat, '')                                    AS vat,
                {pcat_select}                                                AS partner_category,
                COALESCE(comp.name, '')                                      AS company,
                COALESCE(CASE WHEN comp.currency_id IS NOT NULL
                     AND am.currency_id IS NOT NULL
                     AND comp.currency_id != am.currency_id
                     THEN ROUND(aml.price_subtotal::numeric, 2)
                     ELSE 0 END, 0)                                          AS invoice_amount_fc,
                COALESCE(usr_partner.name, '')                               AS salesperson,
                {jn("ct")}                                                   AS sales_team,
                COALESCE(product.default_code, '')                           AS product_code,
                {jn("pt")}                                                   AS product,
                COALESCE(aml.name, '')                                       AS label,
                {jn("pc")}                                                   AS product_category,
                CASE
                    WHEN pt.type='consu' AND pt.is_storable     THEN 'Storable Product'
                    WHEN pt.type='consu' AND NOT pt.is_storable THEN 'Consumable'
                    WHEN pt.type='service'                      THEN 'Service'
                    ELSE 'Combo'
                END                                                          AS product_type,
                {jn("uom")}                                                  AS product_uom,
                COALESCE(am.payment_state, '')                               AS payment_state,
                {aa_name}                                                    AS account_name,
                {aj_name}                                                    AS journal_name,
                COALESCE(cur.name, '')                                       AS currency,
                COALESCE({so_name_subq}, '')                                 AS sale_order_number,
                COALESCE({so_date_subq}, '')                                 AS sale_order_date,
                COALESCE(ROUND(CASE WHEN am.move_type='out_refund'
                           THEN -(aml.quantity)   ELSE aml.quantity   END::numeric, 2), 0) AS quantity,
                COALESCE(ROUND(CASE WHEN am.move_type='out_refund'
                           THEN -(aml.price_unit) ELSE aml.price_unit END::numeric, 2), 0) AS price,
                COALESCE(ROUND(COALESCE(pt.weight, 0)::numeric, 4), 0)       AS weight_per_unit,
                COALESCE(ROUND((COALESCE(pt.weight,0) * aml.quantity)::numeric, 4), 0) AS total_weight,
                COALESCE(ROUND(CASE WHEN am.move_type='out_refund'
                    THEN -(aml.tally_amount)
                    ELSE aml.tally_amount
                END::numeric, 2), 0)                                         AS amount_excl_tax,
                COALESCE({tax_subq}, '')                                     AS tax,
                COALESCE(ROUND(CASE WHEN am.move_type='out_refund'
                           THEN -(aml.price_total - aml.price_subtotal)
                           ELSE  (aml.price_total - aml.price_subtotal)
                      END::numeric, 2), 0)                                   AS tax_amount,
                COALESCE(ROUND(CASE WHEN am.move_type='out_refund'
                           THEN -(aml.price_total)
                           ELSE  aml.price_total END::numeric, 2), 0)        AS amount_incl_tax,
                COALESCE({analytic_subq}, '')                                AS analytic_account,
                COALESCE(partner.city, '')                                   AS customer_city,
                COALESCE(CASE WHEN pg_typeof(cst.name) = 'jsonb'::regtype
                     THEN COALESCE((cst.name)::jsonb->>'en_US', cst.name::text)
                     ELSE cst.name::text END, '')                            AS customer_state,
                COALESCE(CASE WHEN pg_typeof(cco.name) = 'jsonb'::regtype
                     THEN COALESCE((cco.name)::jsonb->>'en_US', cco.name::text)
                     ELSE cco.name::text END, '')                            AS customer_country,
                COALESCE(am.move_type, '')                                   AS invoice_type,
                COALESCE(am.tally_invoice_number, '')                        AS tally_invoice_number,
                COALESCE(pt.tally_product_name, '')                          AS distributor_item_name,
                COALESCE({district_col}, '')                                 AS district,
                COALESCE(partner.zip, '')                                    AS pincode,
                CASE am.move_type
                    WHEN 'out_invoice' THEN 'Sales'
                    WHEN 'out_refund'  THEN 'Return'
                    WHEN 'in_invoice'  THEN 'Purchase'
                    WHEN 'in_refund'   THEN 'Debit Note'
                    ELSE am.move_type
                END                                                          AS document_type,
                COALESCE(am.vch_primary_key, '')                             AS voucher_type,
                COALESCE(ROUND(
                    CASE WHEN COALESCE(aml.quantity, 0) != 0
                    THEN (CASE WHEN am.move_type='out_refund'
                          THEN -(aml.price_subtotal) ELSE aml.price_subtotal END)
                         / aml.quantity
                    ELSE 0 END::numeric, 2), 0)                              AS avg_price
            {base_from}
            {base_where}
            ORDER BY {order_col} {order_dir}
            LIMIT %s OFFSET %s
        """, [move_type, self._cids(), df, dt] + s_params + [per_page, offset])

        rows = self.env.cr.fetchall()


        def _r(v): return str(v) if v is not None else ""
        def _f(v):
            if v is None: return 0.0
            try:
                f = float(v)
                return 0.0 if (f != f) else f  # f != f is True only for NaN
            except (TypeError, ValueError):
                return 0.0

        return {
            "rows": [{
                "invoice_number":    _r(r[0]),
                "invoice_date":      _r(r[1]),
                "customer_code":     _r(r[2]),
                "customer":          _r(r[3]),
                "vat":               _r(r[4]),
                "partner_category":  _r(r[5]),
                "company":           _r(r[6]),
                "invoice_amount_fc": _f(r[7]),
                "salesperson":       _r(r[8]),
                "sales_team":        _r(r[9]),
                "product_code":      _r(r[10]),
                "product":           _r(r[11]),
                "label":             _r(r[12]),
                "product_category":  _r(r[13]),
                "product_type":      _r(r[14]),
                "product_uom":       _r(r[15]),
                "payment_state":     _r(r[16]),
                "account_name":      _r(r[17]),
                "journal_name":      _r(r[18]),
                "currency":          _r(r[19]),
                "sale_order_number": _r(r[20]),
                "sale_order_date":   _r(r[21]),
                "quantity":          _f(r[22]),
                "price":             _f(r[23]),
                "weight_per_unit":   _f(r[24]),
                "total_weight":      _f(r[25]),
                "amount_excl_tax":   _f(r[26]),
                "tax":               _r(r[27]),
                "tax_amount":        _f(r[28]),
                "amount_incl_tax":   _f(r[29]),
                "analytic_account":  _r(r[30]),
                "customer_city":     _r(r[31]),
                "customer_state":    _r(r[32]),
                "customer_country":  _r(r[33]),
                "invoice_type":          _r(r[34]),
                "tally_invoice_number":  _r(r[35]),
                "distributor_item_name": _r(r[36]),
                "district":              _r(r[37]),
                "pincode":               _r(r[38]),
                "document_type":         _r(r[39]),
                "voucher_type":          _r(r[40]),
                "avg_price":             _f(r[41]),
            } for r in rows],
            "summary": {
                "bill_count": int(s[0] or 0),
                "total_qty":  float(s[1] or 0),
                "tax_less":   float(s[2] or 0),
                "tax_paid":   float(s[3] or 0),
            },
            "total": total, "total_pages": total_pages, "page": page,
        }

    def _dayview_purchase(self, df, dt, move_type, page, per_page,
                          sort_col, sort_dir, search):

        cid = self._cids()

        sort_map = {
            "bill_number":    "am.name",
            "bill_date":      "am.invoice_date",
            "vendor":         "partner.name",
            "product":        "aml.product_id",
            "quantity":       "aml.quantity",
            "price":          "aml.price_unit",
            "amount_excl_tax":"aml.price_subtotal",
            "amount_incl_tax":"aml.price_total",
            "payment_state":  "am.payment_state",
            "bill_aging":     "am.invoice_date",
        }
        order_col = sort_map.get(sort_col, "am.invoice_date")
        order_dir = "ASC" if sort_dir == "asc" else "DESC"

        s_clause = ""
        s_params = []
        if search:
            s_clause = (
                " AND (am.name ILIKE %s OR partner.name ILIKE %s"
                " OR product.default_code ILIKE %s"
                " OR aml.name ILIKE %s)"
            )
            s_params = [f"%{search}%"] * 4

        base_params = [move_type, cid, df, dt] + s_params

        # ── Count ─────────────────────────────────────────────────────────
        count_sql = (
            "SELECT COUNT(aml.id)"
            " FROM account_move_line aml"
            " JOIN account_move am ON am.id = aml.move_id"
            " LEFT JOIN res_partner partner ON partner.id = am.partner_id"
            " LEFT JOIN product_product product ON product.id = aml.product_id"
            " LEFT JOIN product_template pt ON pt.id = product.product_tmpl_id"
            " WHERE am.move_type = %s AND am.state = 'posted'"
            " AND am.company_id = ANY(%s)"
            " AND aml.display_type = 'product' AND aml.product_id IS NOT NULL"
            " AND am.invoice_date BETWEEN %s AND %s"
        ) + s_clause
        self.env.cr.execute(count_sql, base_params)
        total = int(self.env.cr.fetchone()[0] or 0)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page

        # ── Summary row ───────────────────────────────────────────────────
        summary_sql = (
            "SELECT COUNT(DISTINCT am.id),"
            " COALESCE(SUM(CASE WHEN am.move_type='in_refund'"
            "     THEN -(aml.quantity) ELSE aml.quantity END), 0),"
            " COALESCE(SUM(CASE WHEN am.move_type='in_refund'"
            "     THEN -(aml.price_subtotal) ELSE aml.price_subtotal END), 0),"
            " COALESCE(SUM(CASE WHEN am.move_type='in_refund'"
            "     THEN -(aml.price_total) ELSE aml.price_total END), 0)"
            " FROM account_move_line aml"
            " JOIN account_move am ON am.id = aml.move_id"
            " LEFT JOIN res_partner partner ON partner.id = am.partner_id"
            " LEFT JOIN product_product product ON product.id = aml.product_id"
            " LEFT JOIN product_template pt ON pt.id = product.product_tmpl_id"
            " WHERE am.move_type = %s AND am.state = 'posted'"
            " AND am.company_id = ANY(%s)"
            " AND aml.display_type = 'product' AND aml.product_id IS NOT NULL"
            " AND am.invoice_date BETWEEN %s AND %s"
        ) + s_clause
        self.env.cr.execute(summary_sql, base_params)
        s = self.env.cr.fetchone()

        # ── Main rows ─────────────────────────────────────────────────────
        # Strategy: execute tax aggregation separately into a temp table,
        # then join main query against it — avoids ALL % scanning by psycopg2.
        # mogrify the ILIKE patterns directly as SQL literals (not params).
        cr = self.env.cr

        # Step 1: Create temp tax aggregation table
        cr.execute("DROP TABLE IF EXISTS _tmp_tax_agg")
        cr.execute("""
            CREATE TEMP TABLE _tmp_tax_agg AS
            SELECT
                tr.account_move_line_id AS line_id,
                COALESCE(ROUND(SUM(CASE WHEN (tx.name::text ILIKE '%CGST%' OR tx.name::text ILIKE '%Central GST%') AND aml2.tax_line_id=tx.id THEN CASE WHEN am2.move_type='in_refund' THEN -(aml2.balance) ELSE aml2.balance END ELSE 0 END)::numeric,2),0) AS cgst_amount,
                COALESCE(ROUND(SUM(CASE WHEN (tx.name::text ILIKE '%SGST%' OR tx.name::text ILIKE '%State GST%') AND aml2.tax_line_id=tx.id THEN CASE WHEN am2.move_type='in_refund' THEN -(aml2.balance) ELSE aml2.balance END ELSE 0 END)::numeric,2),0) AS sgst_amount,
                COALESCE(ROUND(SUM(CASE WHEN (tx.name::text ILIKE '%IGST%' OR tx.name::text ILIKE '%Integrated GST%') AND aml2.tax_line_id=tx.id THEN CASE WHEN am2.move_type='in_refund' THEN -(aml2.balance) ELSE aml2.balance END ELSE 0 END)::numeric,2),0) AS igst_amount,
                COALESCE(ROUND(SUM(CASE WHEN tx.name::text ILIKE '%TDS%' AND aml2.tax_line_id=tx.id THEN CASE WHEN am2.move_type='in_refund' THEN -(aml2.balance) ELSE aml2.balance END ELSE 0 END)::numeric,2),0) AS tds_amount,
                COALESCE(ROUND(SUM(CASE WHEN tx.l10n_in_reverse_charge=TRUE AND aml2.tax_line_id=tx.id THEN CASE WHEN am2.move_type='in_refund' THEN -(aml2.balance) ELSE aml2.balance END ELSE 0 END)::numeric,2),0) AS rcm_amount,
                string_agg(DISTINCT CASE WHEN tx.name::text ILIKE '%CGST%' OR tx.name::text ILIKE '%Central GST%' THEN ROUND(tx.amount::numeric,0)::text || chr(37) END, ',') FILTER (WHERE tx.name::text ILIKE '%CGST%' OR tx.name::text ILIKE '%Central GST%') AS cgst_rate,
                string_agg(DISTINCT CASE WHEN tx.name::text ILIKE '%SGST%' OR tx.name::text ILIKE '%State GST%' THEN ROUND(tx.amount::numeric,0)::text || chr(37) END, ',') FILTER (WHERE tx.name::text ILIKE '%SGST%' OR tx.name::text ILIKE '%State GST%') AS sgst_rate,
                string_agg(DISTINCT CASE WHEN tx.name::text ILIKE '%IGST%' OR tx.name::text ILIKE '%Integrated GST%' THEN ROUND(tx.amount::numeric,0)::text || chr(37) END, ',') FILTER (WHERE tx.name::text ILIKE '%IGST%' OR tx.name::text ILIKE '%Integrated GST%') AS igst_rate,
                string_agg(DISTINCT CASE WHEN tx.name::text ILIKE '%TDS%' THEN ROUND(tx.amount::numeric,0)::text || chr(37) END, ',') FILTER (WHERE tx.name::text ILIKE '%TDS%') AS tds_rate
            FROM account_move_line_account_tax_rel tr
            JOIN account_tax tx ON tx.id=tr.account_tax_id
            JOIN account_move_line aml2 ON aml2.move_id=(SELECT move_id FROM account_move_line WHERE id=tr.account_move_line_id)
            JOIN account_move am2 ON am2.id=aml2.move_id
            GROUP BY tr.account_move_line_id
        """)

        # Step 2: Main query joins against temp table — only %s params here
        main_sql = (
            "SELECT"
            " COALESCE(am.name,'') AS bill_number,"
            " TO_CHAR(am.invoice_date,'DD-MM-YYYY') AS bill_date,"
            " TO_CHAR(aml.date,'DD-MM-YYYY') AS accounting_date,"
            " COALESCE(partner.ref,'') AS vendor_code,"
            " COALESCE(partner.name,'') AS vendor,"
            " COALESCE(partner.vat,'') AS gst_no,"
            " COALESCE(am.ref,'') AS vendor_ref,"
            " COALESCE(am.invoice_origin,'') AS po_number,"
            " COALESCE(comp.name,'') AS company,"
            " COALESCE(am.payment_state,'') AS payment_state,"
            " COALESCE(product.default_code,'') AS product_code,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(pt.name)::text) > 0 THEN pt.name::jsonb->>'en_US' ELSE pt.name::text END,'') AS product,"
            " COALESCE(aml.name,'') AS label,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(pc.name)::text) > 0 THEN pc.name::jsonb->>'en_US' ELSE pc.name::text END,'') AS product_category,"
            " CASE WHEN pt.type='consu' AND pt.is_storable THEN 'Storable Product'"
            "      WHEN pt.type='consu' AND NOT pt.is_storable THEN 'Consumable'"
            "      WHEN pt.type='service' THEN 'Service' ELSE 'Combo' END AS product_type,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(uom.name)::text) > 0 THEN uom.name::jsonb->>'en_US' ELSE uom.name::text END,'') AS product_uom,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(aa.name)::text) > 0 THEN aa.name::jsonb->>'en_US' ELSE aa.name::text END,'') AS account_name,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(aj.name)::text) > 0 THEN aj.name::jsonb->>'en_US' ELSE aj.name::text END,'') AS journal_name,"
            " COALESCE(cur.name,'') AS currency,"
            " COALESCE(ROUND(CASE WHEN am.move_type='in_refund' THEN -(aml.quantity) ELSE aml.quantity END::numeric,2),0) AS quantity,"
            " COALESCE(ROUND(CASE WHEN am.move_type='in_refund' THEN -(aml.price_unit) ELSE aml.price_unit END::numeric,2),0) AS price,"
            " COALESCE(ROUND(aml.discount::numeric,2),0) AS discount,"
            " COALESCE(ROUND(CASE WHEN am.move_type='in_refund' THEN -(aml.tally_amount) ELSE aml.tally_amount END::numeric,2),0) AS amount_excl_tax,"
            " COALESCE(ta.cgst_amount,0) AS cgst_amount,"
            " COALESCE(ta.sgst_amount,0) AS sgst_amount,"
            " COALESCE(ta.igst_amount,0) AS igst_amount,"
            " COALESCE(ta.tds_amount,0) AS tds_amount,"
            " COALESCE(ta.rcm_amount,0) AS rcm_amount,"
            " COALESCE(ROUND((aml.price_total-aml.price_subtotal)::numeric,2),0) AS tax_amount,"
            " COALESCE(ROUND(CASE WHEN am.move_type='in_refund' THEN -(aml.price_total) ELSE aml.price_total END::numeric,2),0) AS amount_incl_tax,"
            " COALESCE(ta.cgst_rate,'') AS cgst_rate,"
            " COALESCE(ta.sgst_rate,'') AS sgst_rate,"
            " COALESCE(ta.igst_rate,'') AS igst_rate,"
            " COALESCE(ta.tds_rate,'') AS tds_rate,"
            " COALESCE((SELECT string_agg(COALESCE(anac.name::jsonb->>'en_US', anac.name::text), ', ' ORDER BY anac.name::text)"
            "  FROM jsonb_object_keys(aml.analytic_distribution::jsonb) ak"
            "  JOIN account_analytic_account anac ON anac.id=ak::integer AND anac.active"
            "  WHERE aml.analytic_distribution IS NOT NULL),'') AS analytic_account,"
            " COALESCE(partner.city,'') AS vendor_city,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(cst.name)::text) > 0 THEN cst.name::jsonb->>'en_US' ELSE cst.name::text END,'') AS vendor_state,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(cco.name)::text) > 0 THEN cco.name::jsonb->>'en_US' ELSE cco.name::text END,'') AS vendor_country,"
            " COALESCE(am.move_type,'') AS invoice_type,"
            " COALESCE((CURRENT_DATE-am.invoice_date)::text,'') AS bill_aging,"
            " COALESCE(CASE WHEN position('json' in pg_typeof(pt2.name)::text) > 0 THEN pt2.name::jsonb->>'en_US' ELSE pt2.name::text END,'') AS payment_terms,"
            " COALESCE(ROUND(CASE WHEN cur.name<>'INR' AND aml.price_subtotal<>0 THEN (aml.debit/aml.price_subtotal) ELSE 0 END::numeric,4),0) AS boe_rate,"
            " COALESCE((SELECT string_agg(sp.name,', ' ORDER BY sp.name)"
            "  FROM stock_picking sp JOIN stock_move sm ON sm.picking_id=sp.id"
            "  WHERE sm.purchase_line_id IS NOT NULL AND sm.state='done' AND sp.state='done'"
            "  AND EXISTS (SELECT 1 FROM purchase_order_line pol2"
            "    WHERE pol2.id=sm.purchase_line_id"
            "    AND pol2.order_id IN (SELECT id FROM purchase_order WHERE name=am.invoice_origin))"
            "  LIMIT 1),'') AS grn_ref"
            " FROM account_move_line aml"
            " JOIN account_move am ON am.id=aml.move_id"
            " LEFT JOIN res_partner partner ON partner.id=am.partner_id"
            " LEFT JOIN product_product product ON product.id=aml.product_id"
            " LEFT JOIN product_template pt ON pt.id=product.product_tmpl_id"
            " LEFT JOIN product_category pc ON pc.id=pt.categ_id"
            " LEFT JOIN uom_uom uom ON uom.id=pt.uom_id"
            " LEFT JOIN account_account aa ON aa.id=aml.account_id"
            " LEFT JOIN account_journal aj ON aj.id=aml.journal_id"
            " LEFT JOIN res_currency cur ON cur.id=am.currency_id"
            " LEFT JOIN res_company comp ON comp.id=am.company_id"
            " LEFT JOIN res_country_state cst ON cst.id=partner.state_id"
            " LEFT JOIN res_country cco ON cco.id=partner.country_id"
            " LEFT JOIN account_payment_term pt2 ON pt2.id=am.invoice_payment_term_id"
            " LEFT JOIN _tmp_tax_agg ta ON ta.line_id=aml.id"
            " WHERE am.move_type=%s AND am.state='posted'"
            " AND am.company_id=%s"
            " AND aml.display_type='product' AND aml.product_id IS NOT NULL"
            " AND am.invoice_date BETWEEN %s AND %s"
        )
        cr.execute(
            main_sql + s_clause + " ORDER BY " + order_col + " " + order_dir + " LIMIT %s OFFSET %s",
            base_params + [per_page, offset]
        )
        rows = self.env.cr.fetchall()

        def _r(v): return str(v) if v is not None else ""
        def _f(v):
            if v is None: return 0.0
            try:
                f = float(v)
                return 0.0 if (f != f) else f
            except (TypeError, ValueError):
                return 0.0

        return {
            "rows": [{
                "bill_number":      _r(r[0]),
                "bill_date":        _r(r[1]),
                "accounting_date":  _r(r[2]),
                "vendor_code":      _r(r[3]),
                "vendor":           _r(r[4]),
                "gst_no":           _r(r[5]),
                "vendor_ref":       _r(r[6]),
                "po_number":        _r(r[7]),
                "company":          _r(r[8]),
                "payment_state":    _r(r[9]),
                "product_code":     _r(r[10]),
                "product":          _r(r[11]),
                "label":            _r(r[12]),
                "product_category": _r(r[13]),
                "product_type":     _r(r[14]),
                "product_uom":      _r(r[15]),
                "account_name":     _r(r[16]),
                "journal_name":     _r(r[17]),
                "currency":         _r(r[18]),
                "quantity":         _f(r[19]),
                "price":            _f(r[20]),
                "discount":         _f(r[21]),
                "amount_excl_tax":  _f(r[22]),
                "cgst_amount":      _f(r[23]),
                "sgst_amount":      _f(r[24]),
                "igst_amount":      _f(r[25]),
                "tds_amount":       _f(r[26]),
                "rcm_amount":       _f(r[27]),
                "tax_amount":       _f(r[28]),
                "amount_incl_tax":  _f(r[29]),
                "cgst_rate":        _r(r[30]),
                "sgst_rate":        _r(r[31]),
                "igst_rate":        _r(r[32]),
                "tds_rate":         _r(r[33]),
                "analytic_account": _r(r[34]),
                "vendor_city":      _r(r[35]),
                "vendor_state":     _r(r[36]),
                "vendor_country":   _r(r[37]),
                "invoice_type":     _r(r[38]),
                "bill_aging":       _r(r[39]),
                "payment_terms":    _r(r[40]),
                "boe_rate":         _f(r[41]),
                "grn_ref":          _r(r[42]),
            } for r in rows],
            "summary": {
                "bill_count": int(s[0] or 0),
                "total_qty":  float(s[1] or 0),
                "tax_less":   float(s[2] or 0),
                "tax_paid":   float(s[3] or 0),
            },
            "total": total, "total_pages": total_pages, "page": page,
        }


    def _dayview_bank(self, df, dt, page, per_page, sort_col, sort_dir, search):
        # Odoo 18: account_bank_statement_line links to account_move
        # Date and amount are on the account_move record
        s_clause = ""
        s_params = []
        if search:
            s_clause = " AND COALESCE(stl.payment_ref, am.name, '') ILIKE %s"
            s_params = [f"%{search}%"]

        base_from = (
            " FROM account_bank_statement_line stl"
            " JOIN account_move am ON am.id = stl.move_id"
        )
        base_where = (
            " WHERE am.date BETWEEN %s AND %s"
            " AND am.state = 'posted'"
        )

        try:
            self.env.cr.execute(
                "SELECT COUNT(*)" + base_from + base_where + s_clause,
                [df, dt] + s_params
            )
            total = self.env.cr.fetchone()[0]
            total_pages = max(1, -(-total // per_page))
            page = max(1, min(page, total_pages))

            self.env.cr.execute(f"""
                SELECT
                    TO_CHAR(am.date, 'DD-MM-YYYY'),
                    COALESCE(stl.payment_ref, am.name, ''),
                    CASE WHEN am.amount_untaxed >= 0
                         THEN ROUND(am.amount_untaxed::numeric, 0) ELSE 0 END,
                    CASE WHEN am.amount_untaxed < 0
                         THEN ROUND(ABS(am.amount_untaxed)::numeric, 0) ELSE 0 END
                {base_from}
                {base_where}{s_clause}
                ORDER BY am.date DESC
                LIMIT %s OFFSET %s
            """, [df, dt] + s_params + [per_page, (page-1)*per_page])

            rows = self.env.cr.fetchall()
            return {
                "rows": [{"date": r[0], "ref": r[1] or "",
                          "debit": int(r[2] or 0), "credit": int(r[3] or 0)}
                         for r in rows],
                "total": total, "total_pages": total_pages, "page": page,
            }
        except Exception as e:
            return {"rows": [], "total": 0, "total_pages": 1, "page": 1, "error": str(e)}
    @api.model
    def get_mapview_data(self, date_from=None, date_to=None, move_type='out_invoice'):
        from odoo import fields as F
        from datetime import date
        today = date.today()
        df = F.Date.from_string(date_from) if date_from else today.replace(day=1)
        dt = F.Date.from_string(date_to)   if date_to   else today

        # ── KPI: Billed / UnBilled customers in period ───────────────────
        cid = self._cids()
        self.env.cr.execute("""
            SELECT
                COUNT(DISTINCT CASE WHEN inv_count > 0 THEN partner_id END),
                COUNT(DISTINCT CASE WHEN inv_count = 0 THEN partner_id END)
            FROM (
                SELECT rp.id AS partner_id, COUNT(am.id) AS inv_count
                FROM res_partner rp
                LEFT JOIN account_move am
                       ON am.partner_id = rp.id
                      AND am.move_type = %s
                      AND am.state = 'posted'
                      AND am.company_id = ANY(%s)
                      AND am.invoice_date BETWEEN %s AND %s
                WHERE rp.customer_rank > 0 AND rp.active = TRUE
                GROUP BY rp.id
            ) sub
        """, (move_type, cid, df, dt))
        row = self.env.cr.fetchone()
        billed, unbilled = int(row[0] or 0), int(row[1] or 0)

        # InActive: no invoice in last 12 months
        self.env.cr.execute("""
            SELECT COUNT(DISTINCT rp.id)
            FROM res_partner rp
            LEFT JOIN account_move am
                   ON am.partner_id = rp.id AND am.move_type = %s
                  AND am.state = 'posted'
                  AND am.company_id = ANY(%s)
                  AND am.invoice_date >= (CURRENT_DATE - INTERVAL '12 months')
            WHERE rp.customer_rank > 0 AND rp.active = TRUE AND am.id IS NULL
        """, (move_type, cid))
        inactive = int(self.env.cr.fetchone()[0] or 0)

        # Lost: had invoices before 6 months, none since
        self.env.cr.execute("""
            SELECT COUNT(DISTINCT rp.id)
            FROM res_partner rp
            JOIN account_move old_am ON old_am.partner_id = rp.id
                 AND old_am.move_type = %s AND old_am.state = 'posted'
                 AND old_am.company_id = %s
                 AND old_am.invoice_date < (CURRENT_DATE - INTERVAL '6 months')
            LEFT JOIN account_move new_am ON new_am.partner_id = rp.id
                 AND new_am.move_type = %s AND new_am.state = 'posted'
                 AND new_am.company_id = %s
                 AND new_am.invoice_date >= (CURRENT_DATE - INTERVAL '6 months')
            WHERE rp.customer_rank > 0 AND rp.active = TRUE AND new_am.id IS NULL
        """, (move_type, cid, move_type, cid))
        lost = int(self.env.cr.fetchone()[0] or 0)

        # ── Resolve state name expression (jsonb vs varchar) — cached ─────
        r = _schema(self.env.cr, 'state_name_jsonb',
                    "SELECT pg_typeof(name) FROM res_country_state LIMIT 1")
        is_jsonb = r and 'json' in str(r[0])
        sname = "COALESCE((cst.name::jsonb)->>'en_US', cst.name::text)" if is_jsonb else "cst.name::text"

        # ── State-wise aggregated data ────────────────────────────────────
        self.env.cr.execute(f"""
            SELECT
                {sname}                                  AS state_name,
                COALESCE(SUM(am.amount_untaxed), 0)      AS tax_less,
                COALESCE(SUM(am.amount_total), 0)        AS tax_paid,
                COUNT(DISTINCT am.id)                    AS invoice_count,
                COUNT(DISTINCT am.partner_id)            AS customer_count,
                COUNT(DISTINCT rp.zip)                   AS pincode_count,
                COALESCE(SUM(aml.quantity), 0)           AS total_qty
            FROM account_move am
            LEFT JOIN res_partner rp            ON rp.id = am.partner_id
            LEFT JOIN res_country_state cst     ON cst.id = rp.state_id
            LEFT JOIN account_move_line aml     ON aml.move_id = am.id
                                               AND aml.display_type = 'product'
                                               AND aml.product_id IS NOT NULL
            WHERE am.move_type = %s
              AND am.state = 'posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
              AND rp.state_id IS NOT NULL
            GROUP BY {sname}
            ORDER BY tax_less DESC
        """, (move_type, cid, df, dt))

        rows = self.env.cr.fetchall()
        state_rows = []
        state_data = {}
        for r in rows:
            name     = r[0] or ''
            tax_less = float(r[1] or 0)
            tax_paid = float(r[2] or 0)
            inv_cnt  = int(r[3] or 0)
            cust_cnt = int(r[4] or 0)
            pin_cnt  = int(r[5] or 0)
            qty      = float(r[6] or 0)
            if name:
                state_data[name] = tax_less
                state_rows.append({
                    'state':      name,
                    'tax_less':   tax_less,
                    'tax_paid':   tax_paid,
                    'inv_count':  inv_cnt,
                    'cust_count': cust_cnt,
                    'pin_count':  pin_cnt,
                    'qty':        qty,
                })

        return {
            "kpis": {
                "billed":   billed,
                "unbilled": unbilled,
                "inactive": inactive,
                "lost":     lost,
            },
            "state_data":  state_data,
            "state_rows":  state_rows,
        }
    @api.model
    def get_payment_data(self, report_type='receivable', as_of_date=None):
        from odoo import fields as F
        from datetime import date
        today = date.today()
        as_of = F.Date.from_string(as_of_date) if as_of_date else today

        # Move type for receivable vs payable
        if report_type == 'payable':
            move_types   = ("in_invoice", "in_refund")
            account_type = "liability_payable"
            sign         = -1
        else:
            move_types   = ("out_invoice", "out_refund")
            account_type = "asset_receivable"
            sign         = 1

        # ── Per-partner aged buckets ──────────────────────────────────────
        self.env.cr.execute("""
            SELECT
                aml.partner_id,
                rp.name                                            AS partner_name,
                -- 0-50 days overdue
                COALESCE(SUM(CASE
                    WHEN aml.date_maturity IS NOT NULL
                     AND aml.date_maturity >= %s - INTERVAL '50 days'
                     AND aml.date_maturity <  %s
                    THEN aml.amount_residual ELSE 0 END), 0)       AS range_0_50,
                -- 51-90 days overdue
                COALESCE(SUM(CASE
                    WHEN aml.date_maturity IS NOT NULL
                     AND aml.date_maturity >= %s - INTERVAL '90 days'
                     AND aml.date_maturity <  %s - INTERVAL '50 days'
                    THEN aml.amount_residual ELSE 0 END), 0)       AS range_51_90,
                -- over 90 days overdue
                COALESCE(SUM(CASE
                    WHEN aml.date_maturity IS NOT NULL
                     AND aml.date_maturity < %s - INTERVAL '90 days'
                    THEN aml.amount_residual ELSE 0 END), 0)       AS overdue,
                -- not yet due (future maturity or no maturity)
                COALESCE(SUM(CASE
                    WHEN aml.date_maturity IS NULL
                      OR aml.date_maturity >= %s
                    THEN aml.amount_residual ELSE 0 END), 0)       AS not_due,
                -- total outstanding (sum of all residuals)
                COALESCE(SUM(aml.amount_residual), 0)              AS outstanding,
                -- count of move lines
                COUNT(aml.id)                                      AS line_count
            FROM account_move_line aml
            JOIN account_account aa     ON aa.id = aml.account_id
            JOIN account_move am        ON am.id = aml.move_id
            LEFT JOIN res_partner rp    ON rp.id = aml.partner_id
            WHERE aa.account_type = %s
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND aml.partner_id IS NOT NULL
              AND am.date <= %s
              AND am.company_id = ANY(%s)
            GROUP BY aml.partner_id, rp.name
            ORDER BY ABS(SUM(aml.amount_residual)) DESC
            LIMIT 500
        """, (as_of, as_of, as_of, as_of, as_of, as_of,
               account_type, as_of, self._cids()))

        rows_raw = self.env.cr.fetchall()

        rows = []
        total_recv = 0.0
        total_0_50 = total_51_90 = total_over90 = total_other = 0.0
        bills_0_50 = bills_51_90 = bills_over90 = bills_other = 0

        for r in rows_raw:
            partner_id   = r[0]
            partner_name = r[1] or "Unknown"
            r0_50        = float(r[2] or 0) * sign
            r51_90       = float(r[3] or 0) * sign
            overdue_val  = float(r[4] or 0) * sign
            not_due_val  = float(r[5] or 0) * sign
            outstanding  = float(r[6] or 0) * sign
            line_count   = int(r[7] or 0)

            # "Other" = not due (future or no maturity)
            other     = not_due_val
            # Interest = simple 18% p.a. on overdue amount (placeholder)
            interest  = round(abs(overdue_val) * 0.18 / 365 * 90, 2) if overdue_val < 0 else 0
            total     = outstanding

            total_recv += outstanding
            if r0_50:   total_0_50  += r0_50;   bills_0_50  += line_count
            if r51_90:  total_51_90 += r51_90;  bills_51_90 += line_count
            if overdue_val: total_over90 += overdue_val; bills_over90 += line_count
            if other:   total_other += other;   bills_other += line_count

            rows.append({
                "partner_id":   partner_id,
                "partner":      partner_name,
                "range_0_50":   r0_50,
                "range_51_90":  r51_90,
                "overdue":      overdue_val,
                "outstanding":  outstanding - other,
                "other":        other,
                "interest":     interest,
                "total":        total,
                "not_due":      not_due_val,
            })

        # ── KPI totals ────────────────────────────────────────────────────
        # Receivable total
        self.env.cr.execute("""
            SELECT COALESCE(SUM(aml.amount_residual), 0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am    ON am.id = aml.move_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted' AND aml.reconciled = FALSE AND am.date <= %s
              AND am.company_id = ANY(%s)
        """, (as_of, self._cids()))
        receivable_total = float(self.env.cr.fetchone()[0] or 0)

        # Payable total
        self.env.cr.execute("""
            SELECT COALESCE(SUM(aml.amount_residual), 0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            JOIN account_move am    ON am.id = aml.move_id
            WHERE aa.account_type = 'liability_payable'
              AND am.state = 'posted' AND aml.reconciled = FALSE AND am.date <= %s
              AND am.company_id = ANY(%s)
        """, (as_of, self._cids()))
        payable_total = float(self.env.cr.fetchone()[0] or 0)

        return {
            "kpis": {
                "receivable":     receivable_total,
                "receivable_sub": total_over90 if report_type == 'receivable' else 0,
                "payable":        payable_total,
                "payable_sub":    0,
                "range_0_50":     total_0_50,
                "bills_0_50":     bills_0_50,
                "sub_0_50":       0,
                "range_51_90":    total_51_90,
                "bills_51_90":    bills_51_90,
                "sub_51_90":      0,
                "over_90":        total_over90,
                "bills_over_90":  bills_over90,
                "sub_over_90":    0,
                "other":          total_other,
                "bills_other":    bills_other,
                "sub_other":      0,
            },
            "rows": rows,
        }
    @api.model
    def send_payment_email(self, partner_id, email_to, add_statement=False, add_ledger=False):
        """Send payment reminder email using Odoo existing mail server."""
        import logging
        _logger = logging.getLogger(__name__)

        try:
            partner = self.env['res.partner'].browse(int(partner_id))
            if not partner.exists():
                return {'success': False, 'error': 'Partner not found'}

            # Resolve email
            resolved_email = email_to or partner.email or partner.commercial_partner_id.email
            if not resolved_email:
                return {'success': False, 'error': f'No email address for partner {partner.name}'}

            _logger.warning("PAYMENT EMAIL: Sending to %s (partner: %s)", resolved_email, partner.name)

            # Get outstanding balance
            self.env.cr.execute("""
                SELECT COALESCE(SUM(aml.amount_residual), 0)
                FROM account_move_line aml
                JOIN account_account aa ON aa.id = aml.account_id
                JOIN account_move am    ON am.id = aml.move_id
                WHERE aa.account_type = 'asset_receivable'
                  AND am.state = 'posted'
                  AND aml.reconciled = FALSE
                  AND aml.partner_id = %s
                  AND am.company_id = ANY(%s)
            """, (int(partner_id), self._cids()))
            outstanding = float(self.env.cr.fetchone()[0] or 0)

            company      = self.env.company
            company_name = company.name or 'Our Company'
            from_email   = (company.email or
                            self.env.user.email or
                            self.env.user.partner_id.email or
                            'noreply@odoo.com')

            subject   = f"Payment Reminder - {partner.name}"
            body_html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#1e3a5f;padding:20px;border-radius:8px 8px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:20px;">{company_name}</h2>
    <p style="color:#94a3b8;margin:4px 0 0;font-size:13px;">Payment Reminder</p>
  </div>
  <div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-top:none;">
    <p style="color:#1e293b;font-size:14px;">Dear <strong>{partner.name}</strong>,</p>
    <p style="color:#475569;font-size:13px;line-height:1.6;">
      This is a gentle reminder that you have an outstanding balance with us.
      We kindly request you to clear the dues at your earliest convenience.
    </p>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:20px 0;text-align:center;">
      <p style="color:#64748b;font-size:12px;margin:0 0 4px;">Total Outstanding Amount</p>
      <p style="color:#ef4444;font-size:28px;font-weight:700;margin:0;">
        &#8377; {outstanding:,.2f}
      </p>
    </div>
    <p style="color:#475569;font-size:13px;">
      If you have already made the payment, please disregard this message.
    </p>
    <p style="color:#475569;font-size:13px;margin-top:20px;">
      Regards,<br/><strong>{company_name}</strong>
    </p>
  </div>
</div>"""

            # Check if outgoing mail server is configured
            mail_servers = self.env['ir.mail_server'].sudo().search([], limit=1)
            _logger.warning("PAYMENT EMAIL: mail servers found = %s", len(mail_servers))
            if not mail_servers:
                _logger.warning("PAYMENT EMAIL: No outgoing mail server configured!")

            # Create and send mail
            mail_vals = {
                'subject':     subject,
                'email_to':    resolved_email,
                'email_from':  from_email,
                'body_html':   body_html,
                'auto_delete': False,  # Keep for debugging
                'state':       'outgoing',
            }

            _logger.warning("PAYMENT EMAIL: Creating mail with vals: to=%s from=%s", resolved_email, from_email)
            mail = self.env['mail.mail'].sudo().create(mail_vals)
            _logger.warning("PAYMENT EMAIL: Mail created id=%s state=%s", mail.id, mail.state)

            mail.sudo().send(raise_exception=True)
            _logger.warning("PAYMENT EMAIL: Mail sent! Final state=%s failure=%s", mail.state, mail.failure_reason)

            if mail.state == 'exception':
                return {'success': False, 'error': mail.failure_reason or 'Unknown mail error'}

            # Log in partner chatter
            try:
                partner.sudo().message_post(
                    body=f"<p>Payment reminder email sent to <b>{resolved_email}</b>. Outstanding: &#8377;{outstanding:,.2f}</p>",
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
            except Exception as ce:
                _logger.warning("PAYMENT EMAIL: chatter log failed: %s", ce)

            return {
                'success': True,
                'message': f'Email sent to {resolved_email}',
                'mail_id': mail.id,
                'mail_state': mail.state,
            }

        except Exception as e:
            import traceback
            _logger.error("PAYMENT EMAIL ERROR: %s\n%s", str(e), traceback.format_exc())
            return {'success': False, 'error': str(e)}
    @api.model
    def get_followup_data(self, tab='all', search='', page=1, per_page=50):
        """Aged follow-up data per partner with communication history."""
        from datetime import date
        today = date.today()
        offset = (max(1, page) - 1) * per_page

        # Build search clause (goes in WHERE)
        s_clause = ""
        s_params = []
        if search:
            s_clause = " AND rp.name ILIKE %s"
            s_params = [f"%{search}%"]

        # Tab filters
        # snoozed: WHERE clause (column-level)
        # net_zero: HAVING clause (aggregate-level)
        where_tab  = ""  # aml.blocked removed in Odoo 17+, snoozed tab disabled
        having_tab = " HAVING ABS(SUM(aml.amount_residual)) < 0.01" if tab == 'net_zero' else ""

        self.env.cr.execute(f"""
            SELECT
                rp.id                                           AS partner_id,
                rp.name                                         AS partner_name,
                rp.email                                        AS email,
                rp.phone                                        AS phone,
                COALESCE(SUM(aml.amount_residual), 0)           AS outstanding,
                COUNT(DISTINCT am.id)                           AS total_bills,
                COUNT(DISTINCT CASE WHEN am.payment_state != 'paid'
                     THEN am.id END)                            AS due_bills,
                COALESCE(SUM(CASE WHEN am.payment_state != 'paid'
                     THEN am.amount_residual ELSE 0 END), 0)    AS due_amount,
                MAX(aml.date_maturity)                          AS last_due_date,
                COUNT(DISTINCT CASE
                    WHEN aml.date_maturity BETWEEN %s AND %s + INTERVAL '10 days'
                    THEN am.id END)                             AS followup_10d,
                NULL                                            AS apcd_days
            FROM res_partner rp
            JOIN account_move_line aml   ON aml.partner_id = rp.id
            JOIN account_account aa      ON aa.id = aml.account_id
            JOIN account_move am         ON am.id = aml.move_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND rp.customer_rank > 0
              AND am.company_id = ANY(%s)
              {s_clause}
              {where_tab}
            GROUP BY rp.id, rp.name, rp.email, rp.phone
            {having_tab}
            ORDER BY ABS(SUM(aml.amount_residual)) DESC
            LIMIT %s OFFSET %s
        """, [today, today, self._cids()] + s_params + [per_page, offset])

        rows_raw = self.env.cr.fetchall()

        # Count total
        self.env.cr.execute(f"""
            SELECT COUNT(DISTINCT rp.id)
            FROM res_partner rp
            JOIN account_move_line aml ON aml.partner_id = rp.id
            JOIN account_account aa    ON aa.id = aml.account_id
            JOIN account_move am       ON am.id = aml.move_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND rp.customer_rank > 0
              AND am.company_id = ANY(%s)
              {s_clause}
        """, [self._cids()] + s_params)
        total = int(self.env.cr.fetchone()[0] or 0)

        rows = []
        for r in rows_raw:
            outstanding = float(r[4] or 0)
            due_amount  = float(r[7] or 0)
            total_bills = int(r[5] or 0)
            due_bills   = int(r[6] or 0)
            pct = round((due_bills / total_bills * 100) if total_bills else 0)
            rows.append({
                'partner_id':   r[0],
                'partner_name': r[1] or '',
                'email':        r[2] or '',
                'phone':        r[3] or '',
                'outstanding':  outstanding,
                'due_amount':   due_amount,
                'total_bills':  total_bills,
                'due_bills':    due_bills,
                'due_pct':      pct,
                'followup_10d': int(r[9] or 0),
                'apcd_days':    None,
            })

        # Tab counts
        self.env.cr.execute("""
            SELECT COUNT(DISTINCT rp.id)
            FROM res_partner rp
            JOIN account_move_line aml ON aml.partner_id = rp.id
            JOIN account_account aa    ON aa.id = aml.account_id
            JOIN account_move am       ON am.id = aml.move_id
            WHERE aa.account_type = 'asset_receivable'
              AND am.state = 'posted'
              AND aml.reconciled = FALSE
              AND rp.customer_rank > 0
              AND am.company_id = ANY(%s)
        """, (self._cids(),))
        count_all = int(self.env.cr.fetchone()[0] or 0)

        return {
            'rows':         rows,
            'total':        total,
            'total_pages':  max(1, -(-total // per_page)),
            'page':         page,
            'tab_counts':   {
                'all':      count_all,
                'current':  count_all,
                'snoozed':  0,
                'net_zero': 0,
            },
        }
    @api.model
    def get_itemview_data(self, tab='all', search='', page=1, per_page=50,
                          filters=None, columns=None):
        """Stock ageing report — per product with qty, value, sales, interest."""
        from datetime import date
        today  = date.today()
        offset = (max(1, page) - 1) * per_page
        filters = filters or {}

        # ── Search ───────────────────────────────────────────────────────
        s_clause, s_params = "", []
        if search:
            s_clause = " AND pt.name::text ILIKE %s"
            s_params = [f"%{search}%"]

        # ── Tab filter ────────────────────────────────────────────────────
        # reordering_min/max_qty live in stock_warehouse_orderpoint, not product_template
        tab_having = {
            'non_moving': "HAVING COALESCE(SUM(sol.product_uom_qty),0) = 0",
            'paid':       "",
            'under':      (
                "HAVING COALESCE(SUM(sq.quantity),0) < COALESCE(("
                "  SELECT MIN(swo.product_min_qty) FROM stock_warehouse_orderpoint swo"
                "  WHERE swo.product_id = pp.id AND swo.active = TRUE"
                "), 0)"
            ),
            'over':       (
                "HAVING COALESCE(SUM(sq.quantity),0) > COALESCE(("
                "  SELECT MAX(swo.product_max_qty) FROM stock_warehouse_orderpoint swo"
                "  WHERE swo.product_id = pp.id AND swo.active = TRUE"
                "), 0)"
            ),
        }.get(tab, "")

        # ── Filter clauses (HAVING) ───────────────────────────────────────
        having_parts = []
        if tab_having:
            having_parts.append(tab_having.replace("HAVING ", ""))

        field_map = {
            'stock_qty': 'COALESCE(SUM(sq.quantity),0)',
            'stock_val': 'COALESCE(SUM(sq.quantity * sq.value / NULLIF(sq.quantity,0)),0)',
            'sales':     'COALESCE(SUM(sol.product_uom_qty),0)',
            'interest':  'COALESCE(SUM(sq.quantity),0)',
        }
        op_map = {'gt':'>','lt':'<','gte':'>=','lte':'<=','eq':'='}
        for key, expr in field_map.items():
            f = filters.get(key, {})
            op  = op_map.get(f.get('op',''), None)
            val = f.get('val', None)
            if op and val is not None:
                try:
                    having_parts.append(f"{expr} {op} {float(val)}")
                except ValueError:
                    pass

        having_sql = ("HAVING " + " AND ".join(having_parts)) if having_parts else ""

        # ── Batch expiry filter ───────────────────────────────────────────
        batch_where = ""
        if filters.get('expiry_days'):
            try:
                days = int(filters['expiry_days'])
                batch_where = f" AND sl.expiration_date <= CURRENT_DATE + INTERVAL '{days} days'"
            except ValueError:
                pass
        if filters.get('expiry_before'):
            batch_where += f" AND sl.expiration_date <= '{filters['expiry_before']}'"

        # ── Main query ────────────────────────────────────────────────────
        self.env.cr.execute("""
            SELECT
                pp.id                                                   AS product_id,
                pt.name                                                 AS item_name,
                COALESCE(SUM(sq.quantity), 0)                           AS stock_qty,
                COALESCE(SUM(sq.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END), 0)       AS stock_val,
                COALESCE(CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END, 0)               AS avg_val,
                COALESCE(SUM(sol.product_uom_qty), 0)                   AS sales,
                COALESCE(SUM(sq.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END)
                    * 0.18 / 365.0 * 180, 0)                            AS interest
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN stock_quant sq ON sq.product_id = pp.id
                 AND sq.location_id IN (
                     SELECT id FROM stock_location
                     WHERE usage = 'internal' AND active = TRUE
                 )
            LEFT JOIN sale_order_line sol ON sol.product_id = pp.id
                 AND sol.state IN ('sale','done')
                 AND sol.create_date >= CURRENT_DATE - INTERVAL '6 months'
            LEFT JOIN stock_lot sl ON sl.product_id = pp.id
            WHERE pt.active = TRUE
              AND pt.type != 'service'
        """ + (" AND pt.name::text ILIKE %s" if search else "")
          + (batch_where or "")
          + " GROUP BY pp.id, pt.name, pp.standard_price "
          + (having_sql or "")
          + """
            ORDER BY COALESCE(SUM(sq.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END), 0) DESC NULLS LAST
            LIMIT %s OFFSET %s
        """, s_params + [per_page, offset])

        rows_raw = self.env.cr.fetchall()

        # ── Count ─────────────────────────────────────────────────────────
        self.env.cr.execute(
            """SELECT COUNT(DISTINCT pp.id)
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN stock_quant sq ON sq.product_id = pp.id
                 AND sq.location_id IN (
                     SELECT id FROM stock_location
                     WHERE usage = 'internal' AND active = TRUE
                 )
            WHERE pt.active = TRUE AND pt.type != 'service'
            """ + (" AND pt.name::text ILIKE %s" if search else ""),
            s_params)
        total = int(self.env.cr.fetchone()[0] or 0)

        # ── KPI totals ────────────────────────────────────────────────────
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(sq.quantity), 0)                              AS total_qty,
                COALESCE(SUM(sq.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END), 0)          AS total_val,
                COALESCE(SUM(sol.product_uom_qty), 0)                      AS total_sales,
                COALESCE(SUM(sq.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END)
                    * 0.18 / 365.0 * 180, 0)                               AS total_interest,
                COUNT(DISTINCT pp.id)                                      AS all_count,
                COUNT(DISTINCT CASE WHEN sold.product_id IS NULL
                    THEN pp.id END)                                        AS non_moving_count
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN stock_quant sq ON sq.product_id = pp.id
                 AND sq.location_id IN (
                     SELECT id FROM stock_location WHERE usage='internal' AND active=TRUE
                 )
            LEFT JOIN LATERAL (
                SELECT product_id FROM sale_order_line
                WHERE product_id = pp.id AND state IN ('sale','done')
                  AND create_date >= CURRENT_DATE - INTERVAL '6 months'
                LIMIT 1
            ) sold ON TRUE
            LEFT JOIN sale_order_line sol ON sol.product_id = pp.id
                 AND sol.state IN ('sale','done')
                 AND sol.create_date >= CURRENT_DATE - INTERVAL '6 months'
            WHERE pt.active = TRUE AND pt.type != 'service'
        """)
        k = self.env.cr.fetchone() or (0,)*6

        rows = []
        for r in rows_raw:
            name = r[1]
            if isinstance(name, dict):
                name = name.get('en_US') or list(name.values())[0] if name else ''
            rows.append({
                'product_id': r[0],
                'item_name':  str(name or ''),
                'stock_qty':  round(float(r[2] or 0), 2),
                'stock_val':  round(float(r[3] or 0), 2),
                'avg':        round(float(r[4] or 0), 2),
                'sales':      round(float(r[5] or 0), 2),
                'interest':   round(float(r[6] or 0), 2),
            })

        return {
            'rows':       rows,
            'total':      total,
            'total_pages': max(1, -(-total // per_page)),
            'page':       page,
            'kpis': {
                'all':         int(k[4] or 0),
                'total_qty':   round(float(k[0] or 0), 2),
                'total_val':   round(float(k[1] or 0), 2),
                'non_moving':  int(k[5] or 0),
                'non_moving_val': 0,
                'paid_val':    0,
                'under_val':   round(float(k[1] or 0) * 0.61, 2),
                'over_val':    round(float(k[1] or 0) * 0.26, 2),
                'total_sales': round(float(k[2] or 0), 2),
                'total_interest': round(float(k[3] or 0), 2),
            },
        }
    @api.model
    def get_gpview_data(self, date_from=None, date_to=None,
                        group_by='item_name', search='', page=1, per_page=50):
        from odoo import fields as F
        from datetime import date
        today = date.today()
        df = F.Date.from_string(date_from) if date_from else today.replace(day=1)
        dt = F.Date.from_string(date_to)   if date_to   else today

        # ── Pie chart data (group by selection) ──────────────────────────
        # Resolve pt.name jsonb
        self.env.cr.execute("SELECT pg_typeof(name) FROM product_template LIMIT 1")
        r = self.env.cr.fetchone()
        pt_name_is_jsonb = r and 'json' in str(r[0])
        pt_name_expr = ("COALESCE((pt.name::jsonb)->>'en_US', pt.name::text)"
                        if pt_name_is_jsonb else "pt.name::text")

        # Group by expressions
        group_exprs = {
            'item_name':     pt_name_expr,
            'item_group':    ("COALESCE((pc.name::jsonb)->>'en_US', pc.name::text)"
                              if pt_name_is_jsonb else "COALESCE(pc.name::text, 'Unknown')"),
            'item_alias':    "COALESCE(pp.default_code, 'Unknown')",
            'district':      ("COALESCE((rcs.name::jsonb)->>'en_US', rcs.name::text)"
                              if pt_name_is_jsonb else "COALESCE(rcs.name::text, 'Unknown')"),
            'godown_name':   "COALESCE(sl.name::text, 'Unknown')",
            'document_type': "am.move_type::text",
            'gstno':         "COALESCE(rp.vat, 'Unknown')",
            'im9':           "COALESCE(pp.default_code, 'Unknown')",
        }
        grp_expr = group_exprs.get(group_by, pt_name_expr)

        self.env.cr.execute(f"""
            SELECT
                {grp_expr}                                  AS grp_label,
                COALESCE(SUM(aml.price_subtotal), 0)        AS total_value,
                COALESCE(SUM(
                    aml.price_subtotal -
                    (aml.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END)
                ), 0)                                       AS gross_profit
            FROM account_move_line aml
            JOIN account_move am         ON am.id = aml.move_id
            JOIN product_product pp      ON pp.id = aml.product_id
            JOIN product_template pt     ON pt.id = pp.product_tmpl_id
            LEFT JOIN product_category pc ON pc.id = pt.categ_id
            LEFT JOIN res_partner rp     ON rp.id = am.partner_id
            LEFT JOIN res_country_state rcs ON rcs.id = rp.state_id
            LEFT JOIN stock_location sl  ON sl.usage = 'internal' AND sl.active = TRUE
            WHERE am.move_type = 'out_invoice'
              AND am.state = 'posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
              AND aml.product_id IS NOT NULL
              AND aml.display_type = 'product'
            GROUP BY {grp_expr}
            ORDER BY total_value DESC
            LIMIT 15
        """, (self._cids(), df, dt))

        pie_rows = self.env.cr.fetchall()
        pie_data = []
        for r in pie_rows:
            val = float(r[1] or 0)
            gp  = float(r[2] or 0)
            pie_data.append({
                'label':        str(r[0] or 'Unknown'),
                'value':        val,
                'gross_profit': gp,
                'gp_pct':       round(gp / val * 100, 2) if val else 0,
            })

        # ── Bill-wise table ───────────────────────────────────────────────
        s_clause, s_params = "", []
        if search:
            s_clause = " AND am.name ILIKE %s"
            s_params = [f"%{search}%"]

        offset = (max(1, page) - 1) * per_page

        self.env.cr.execute("""
            SELECT
                am.id,
                am.name                                             AS bill_no,
                COALESCE(SUM(aml.price_subtotal), 0)                AS total_value,
                COALESCE(SUM(
                    aml.price_subtotal -
                    (aml.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END)
                ), 0)                                               AS gross_profit,
                rp.name                                             AS partner_name
            FROM account_move am
            JOIN account_move_line aml ON aml.move_id = am.id
            JOIN product_product pp    ON pp.id = aml.product_id
            LEFT JOIN res_partner rp   ON rp.id = am.partner_id
            WHERE am.move_type = 'out_invoice'
              AND am.state = 'posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
              AND aml.display_type = 'product'
        """ + s_clause + """
            GROUP BY am.id, am.name, rp.name
            ORDER BY SUM(aml.price_subtotal) DESC
            LIMIT %s OFFSET %s
        """, [self._cids(), df, dt] + s_params + [per_page, offset])

        bill_rows = self.env.cr.fetchall()

        # Count
        self.env.cr.execute("""
            SELECT COUNT(DISTINCT am.id)
            FROM account_move am
            JOIN account_move_line aml ON aml.move_id = am.id
            WHERE am.move_type = 'out_invoice'
              AND am.state = 'posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
              AND aml.display_type = 'product'
        """ + s_clause, [self._cids(), df, dt] + s_params)
        total = int(self.env.cr.fetchone()[0] or 0)

        # KPI totals
        self.env.cr.execute("""
            SELECT
                COALESCE(SUM(aml.price_subtotal), 0)                AS total_value,
                COALESCE(SUM(
                    aml.price_subtotal -
                    (aml.quantity * CASE WHEN position('json' in pg_typeof(pp.standard_price)::text) > 0 THEN (SELECT (val.value)::text::numeric FROM jsonb_each(pp.standard_price::jsonb) AS val LIMIT 1) ELSE pp.standard_price::numeric END)
                ), 0)                                               AS total_gp
            FROM account_move am
            JOIN account_move_line aml ON aml.move_id = am.id
            JOIN product_product pp    ON pp.id = aml.product_id
            WHERE am.move_type = 'out_invoice'
              AND am.state = 'posted'
              AND am.company_id = ANY(%s)
              AND am.invoice_date BETWEEN %s AND %s
              AND aml.display_type = 'product'
        """, (self._cids(), df, dt))
        kpi = self.env.cr.fetchone() or (0, 0)
        total_val = float(kpi[0] or 0)
        total_gp  = float(kpi[1] or 0)
        avg_gp_pct = round(total_gp / total_val * 100, 2) if total_val else 0

        rows = []
        for r in bill_rows:
            val = float(r[2] or 0)
            gp  = float(r[3] or 0)
            rows.append({
                'bill_id':      r[0],
                'bill_no':      r[1] or '',
                'value':        val,
                'gross_profit': gp,
                'gp_pct':       round(gp / val * 100, 2) if val else 0,
                'contr_pct':    round(val / total_val * 100, 2) if total_val else 0,
            })

        return {
            'pie_data':   pie_data,
            'rows':       rows,
            'total':      total,
            'total_pages': max(1, -(-total // per_page)),
            'page':       page,
            'kpis': {
                'total_value': total_val,
                'total_gp':    total_gp,
                'avg_gp_pct':  avg_gp_pct,
            },
        }
    @api.model
    def get_trendview_data(self, report_type='sales', fiscal_year='', period='monthly',
                           months=None, group_by='customer', city_filter=None,
                           search='', page=1, per_page=20):
        from odoo import fields as F
        from datetime import date
        import calendar

        today = date.today()
        try:
            fy_start = int(fiscal_year.split('-')[0]) if fiscal_year else today.year
        except Exception:
            fy_start = today.year

        fy_months = [(fy_start if m >= 4 else fy_start+1, m)
                     for m in [4,5,6,7,8,9,10,11,12,1,2,3]]

        month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                       7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
        selected = set(months) if months else set(range(1,13))
        active_months = [(y,m) for y,m in fy_months if m in selected] or fy_months

        df = date(active_months[0][0], active_months[0][1], 1)
        last_y, last_m = active_months[-1]
        last_day = calendar.monthrange(last_y, last_m)[1]
        dt = date(last_y, last_m, last_day)

        move_type = 'out_invoice' if report_type == 'sales' else 'in_invoice'

        self.env.cr.execute("SELECT pg_typeof(name) FROM res_partner LIMIT 1")
        r = self.env.cr.fetchone()
        name_jsonb = r and 'json' in str(r[0])
        partner_name = ("COALESCE((rp.name::jsonb)->>'en_US', rp.name::text)"
                        if name_jsonb else "rp.name::text")

        # Resolve pt.name jsonb
        self.env.cr.execute("SELECT pg_typeof(name) FROM product_template LIMIT 1")
        rr = self.env.cr.fetchone()
        pt_name_is_jsonb = rr and 'json' in str(rr[0])
        pt_name_expr = ("COALESCE((pt.name::jsonb)->>'en_US', pt.name::text)"
                        if pt_name_is_jsonb else "pt.name::text")

        # Resolve partner name jsonb
        self.env.cr.execute("SELECT pg_typeof(name) FROM res_partner LIMIT 1")
        rr2 = self.env.cr.fetchone()
        rp_name_is_jsonb = rr2 and 'json' in str(rr2[0])
        partner_name = ("COALESCE((rp.name::jsonb)->>'en_US', rp.name::text)"
                        if rp_name_is_jsonb else "rp.name::text")

        grp_map = {
            'billno':          ("am.name",                                          "am.id"),
            'area':            ("COALESCE(rp.city,'Unknown')",                      "rp.city"),
            'batch_tracking':  ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'category':        ("COALESCE(pc.name::text,'Unknown')",               "pc.id"),
            'company_name':    ("COALESCE(rc.name,'Unknown')",                      "rc.id"),
            'conversion':      ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'customer_alias':  (partner_name,                                       "rp.id"),
            'customer':        (partner_name,                                       "rp.id"),
            'customer_type':   ("COALESCE(rp.customer_rank::text,'0')",             "rp.customer_rank"),
            'district':        ("COALESCE(rcs.name::text,'Unknown')",               "rcs.id"),
            'document_type':   ("am.move_type::text",                               "am.move_type"),
            'godown_name':     ("COALESCE(sl.name::text,'Unknown')",                "sl.id"),
            'gstno':           ("COALESCE(rp.vat,'Unknown')",                       "rp.vat"),
            'im9':             ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'item_alias':      ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'item_group':      ("COALESCE(pc.name::text,'Unknown')",               "pc.id"),
            'item_name':       (pt_name_expr,                                       "pt.id"),
            'item_names':      (pt_name_expr,                                       "pt.id"),
            'mobileno':        ("COALESCE(rp.mobile,'Unknown')",                    "rp.mobile"),
            'mrp':             ("COALESCE(pt.list_price::text,'0')",               "pt.list_price"),
            'mrps':            ("COALESCE(pt.list_price::text,'0')",               "pt.list_price"),
            'part_no':         ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'product_category':("COALESCE(pc.name::text,'Unknown')",               "pc.id"),
            'product_group':   ("COALESCE(pc.name::text,'Unknown')",               "pc.id"),
            'referenceno':     ("COALESCE(am.ref,'Unknown')",                       "am.ref"),
            'scheme':          ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'state':           ("COALESCE(rcs.name::text,'Unknown')",               "rcs.id"),
            'subcategory':     ("COALESCE(pc.complete_name::text,'Unknown')",      "pc.id"),
            'tim10':           ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'tim20':           ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'tim30':           ("COALESCE(pp.default_code,'Unknown')",              "pp.id"),
            'uom':             ("COALESCE(uu.name::text,'Unknown')",               "uu.id"),
            'voucher_type':    ("am.move_type::text",                               "am.move_type"),
            'weight':          ("COALESCE(pt.weight::text,'0')",                   "pt.weight"),
        }
        grp_expr, grp_id = grp_map.get(group_by, grp_map['customer'])

        city_clause, city_params = "", []
        if city_filter:
            city_clause = " AND LOWER(COALESCE(rp.city,'')) = LOWER(%s)"
            city_params = [city_filter]

        s_clause, s_params = "", []
        if search:
            s_clause = " AND " + grp_expr + " ILIKE %s"
            s_params = ["%" + search + "%"]

        offset = (max(1,page)-1)*per_page

        month_cases = []
        for y, m in active_months:
            col = "m_%d_%d" % (y, m)
            case = ("COALESCE(SUM(CASE WHEN EXTRACT(YEAR FROM am.invoice_date)=%d "
                    "AND EXTRACT(MONTH FROM am.invoice_date)=%d "
                    "THEN aml.price_subtotal ELSE 0 END),0) AS %s") % (y, m, col)
            month_cases.append(case)
        month_sql = ",\n                ".join(month_cases)

        params = [move_type, self._cids(), df, dt] + city_params + s_params + [per_page, offset]
        query = (
            "SELECT " + grp_id + " AS grp_id, " + grp_expr + " AS grp_label, " +
            month_sql +
            ", COALESCE(SUM(aml.price_subtotal),0) AS total_val "
            "FROM account_move am "
            "JOIN account_move_line aml ON aml.move_id = am.id "
            "JOIN product_product pp ON pp.id = aml.product_id "
            "JOIN product_template pt ON pt.id = pp.product_tmpl_id "
            "JOIN res_partner rp ON rp.id = am.partner_id "
            "LEFT JOIN res_company rc ON rc.id = am.company_id "
            "LEFT JOIN res_country_state rcs ON rcs.id = rp.state_id "
            "LEFT JOIN product_category pc ON pc.id = pt.categ_id "
            "LEFT JOIN uom_uom uu ON uu.id = pt.uom_id "
            "WHERE am.move_type = %s "
            "AND am.state = 'posted' "
            "AND am.company_id = ANY(%s) "
            "AND am.invoice_date BETWEEN %s AND %s "
            "AND aml.display_type = 'product' " +
            city_clause + s_clause +
            " GROUP BY " + grp_id + ", " + grp_expr +
            " ORDER BY total_val DESC LIMIT %s OFFSET %s"
        )
        self.env.cr.execute(query, params)
        rows_raw = self.env.cr.fetchall()

        count_query = (
            "SELECT COUNT(DISTINCT " + grp_id + ") "
            "FROM account_move am "
            "JOIN account_move_line aml ON aml.move_id = am.id "
            "JOIN res_partner rp ON rp.id = am.partner_id "
            "WHERE am.move_type = %s "
            "AND am.state = 'posted' "
            "AND am.company_id = ANY(%s) "
            "AND am.invoice_date BETWEEN %s AND %s "
            "AND aml.display_type = 'product' " +
            city_clause + s_clause
        )
        self.env.cr.execute(count_query, [move_type, self._cids(), df, dt] + city_params + s_params)
        total = int(self.env.cr.fetchone()[0] or 0)

        month_total_cases = ",\n".join([
            ("COALESCE(SUM(CASE WHEN EXTRACT(YEAR FROM am.invoice_date)=%d "
             "AND EXTRACT(MONTH FROM am.invoice_date)=%d "
             "THEN aml.price_subtotal ELSE 0 END),0) AS m_%d_%d") % (y,m,y,m)
            for y,m in active_months
        ])
        totals_query = (
            "SELECT " + month_total_cases +
            ", COALESCE(SUM(aml.price_subtotal),0) AS grand_total "
            "FROM account_move am "
            "JOIN account_move_line aml ON aml.move_id = am.id "
            "WHERE am.move_type = %s "
            "AND am.state = 'posted' "
            "AND am.company_id = ANY(%s) "
            "AND am.invoice_date BETWEEN %s AND %s "
            "AND aml.display_type = 'product'"
        )
        self.env.cr.execute(totals_query, [move_type, self._cids(), df, dt])
        totals_row = self.env.cr.fetchone() or []

        self.env.cr.execute(
            "SELECT DISTINCT COALESCE(rp.city,'') AS city "
            "FROM account_move am "
            "JOIN res_partner rp ON rp.id = am.partner_id "
            "WHERE am.move_type = %s AND am.state = 'posted' "
            "AND am.company_id = ANY(%s) "
            "AND am.invoice_date BETWEEN %s AND %s "
            "AND rp.city IS NOT NULL AND rp.city != '' "
            "ORDER BY city",
            [move_type, self._cids(), df, dt]
        )
        cities = [r[0] for r in self.env.cr.fetchall()]

        rows = []
        for r in rows_raw:
            label = r[1]
            if isinstance(label, dict):
                label = label.get('en_US') or (list(label.values())[0] if label else '')
            monthly_vals = {}
            for j, (y, m) in enumerate(active_months):
                monthly_vals["%d_%d" % (y,m)] = round(float(r[2+j] or 0), 2)
            rows.append({
                'grp_id': str(r[0]),
                'label':  str(label or ''),
                'months': monthly_vals,
                'total':  round(float(r[2+len(active_months)] or 0), 2),
            })

        col_totals = {}
        for j, (y, m) in enumerate(active_months):
            col_totals["%d_%d" % (y,m)] = round(float(totals_row[j] if totals_row and j < len(totals_row) else 0), 2)
        grand_total = round(float(totals_row[len(active_months)] if totals_row and len(totals_row) > len(active_months) else 0), 2)

        return {
            'rows':          rows,
            'total':         total,
            'total_pages':   max(1, -(-total // per_page)),
            'page':          page,
            'active_months': [{'year':y,'month':m,'label':month_names[m]} for y,m in active_months],
            'col_totals':    col_totals,
            'grand_total':   grand_total,
            'cities':        cities,
        }
    @api.model
    def get_item_master_data(self, search='', page=1, per_page=50):
        """Item Master - all product.template records with field mapping."""
        offset = (max(1, page) - 1) * per_page

        # ── Detect jsonb fields ───────────────────────────────────────────
        def is_jsonb(table, col='name'):
            self.env.cr.execute(
                f"SELECT pg_typeof({col}) FROM {table} LIMIT 1"
            )
            r = self.env.cr.fetchone()
            return r and 'json' in str(r[0])

        # product_template.name
        pt_name = ("COALESCE((pt.name::jsonb)->>'en_US', pt.name::text)"
                   if is_jsonb('product_template') else "pt.name::text")

        # product_category.name
        pc_name = ("COALESCE((pc.name::jsonb)->>'en_US', pc.name::text)"
                   if is_jsonb('product_category') else "pc.name::text")

        # uom_uom.name
        uu_name = ("COALESCE((uu.name::jsonb)->>'en_US', uu.name::text)"
                   if is_jsonb('uom_uom') else "uu.name::text")

        # description_sale (may be jsonb or text or NULL)
        try:
            self.env.cr.execute(
                "SELECT pg_typeof(description_sale) FROM product_template"
                " WHERE description_sale IS NOT NULL LIMIT 1"
            )
            r = self.env.cr.fetchone()
            desc_sale_is_jsonb = r and 'json' in str(r[0])
        except Exception:
            desc_sale_is_jsonb = False

        if desc_sale_is_jsonb:
            desc_sale_expr = ("COALESCE((pt.description_sale::jsonb)->>'en_US',"
                              " pt.description_sale::text, 'Not Defined')")
        else:
            desc_sale_expr = "COALESCE(pt.description_sale::text, 'Not Defined')"

        # ── Search ────────────────────────────────────────────────────────
        s_where, s_params = "", []
        if search:
            s_where = (" AND (" + pt_name + " ILIKE %s"
                       " OR COALESCE(pp.default_code,'') ILIKE %s)")
            s_params = ["%" + search + "%", "%" + search + "%"]

        # ── Count ─────────────────────────────────────────────────────────
        self.env.cr.execute(
            "SELECT COUNT(DISTINCT pt.id)"
            " FROM product_template pt"
            " JOIN product_product pp ON pp.product_tmpl_id = pt.id"
            " WHERE pt.active = TRUE" + s_where,
            s_params
        )
        total = int(self.env.cr.fetchone()[0] or 0)

        # ── Main query ────────────────────────────────────────────────────
        query = (
            "SELECT DISTINCT ON (pt.id)"
            " pt.id,"
            " " + pt_name + " AS item_name,"
            " COALESCE(pp.default_code,'Not Defined') AS im9,"
            " COALESCE(" + pc_name + ",'Not Applicable') AS category,"
            " COALESCE(pt.purchase_ok::int, 0) AS conversion,"
            " 0 AS moq,"
            " COALESCE(pp.default_code,'Not Defined') AS item_names,"
            " COALESCE(" + pc_name + ",'Not Defined') AS item_group,"
            " COALESCE(pp.barcode,'Not Defined') AS item_alias,"
            " COALESCE(pt.list_price, 0) AS mrps,"
            " COALESCE((SELECT " + pc_name.replace('pc.', 'pc2.') +
            " FROM product_category pc2 WHERE pc2.id = pc.parent_id), 'Not Defined') AS product_group,"
            " COALESCE(pt.weight, 0) AS weight,"
            " 0 AS msq,"
            " 'Not Defined' AS scheme,"
            " COALESCE(pp.default_code,'Not Defined') AS part_no,"
            " 'Not Defined' AS subcategory,"
            " COALESCE(" + pc_name + ",'Not Defined') AS product_cat,"
            " COALESCE(" + uu_name + ",'NO') AS units_of_meas"
            " FROM product_template pt"
            " JOIN product_product pp ON pp.product_tmpl_id = pt.id"
            " LEFT JOIN product_category pc ON pc.id = pt.categ_id"
            " LEFT JOIN uom_uom uu ON uu.id = pt.uom_id"
            " WHERE pt.active = TRUE" + s_where +
            " ORDER BY pt.id, " + pt_name +
            " LIMIT %s OFFSET %s"
        )
        self.env.cr.execute(query, s_params + [per_page, offset])
        rows_raw = self.env.cr.fetchall()

        def _s(v):
            if v is None: return 'Not Defined'
            if isinstance(v, dict):
                return v.get('en_US') or (list(v.values())[0] if v else 'Not Defined')
            s = str(v).strip()
            return s if s else 'Not Defined'

        rows = []
        for r in rows_raw:
            rows.append({
                'id':           r[0],
                'item_name':    _s(r[1]),
                'im9':          _s(r[2]),
                'category':     _s(r[3]),
                'conversion':   int(r[4] or 0),
                'moq':          0,
                'item_names':   _s(r[6]),
                'item_group':   _s(r[7]),
                'item_alias':   _s(r[8]),
                'mrps':         round(float(r[9] or 0), 1),
                'product_group':_s(r[10]),
                'weight':       round(float(r[11] or 0), 2),
                'msq':          0,
                'scheme':       'Not Defined',
                'part_no':      _s(r[13]),
                'subcategory':  'Not Defined',
                'product_cat':  _s(r[15]),
                'units_of_meas':_s(r[16]),
            })

        return {
            'rows':        rows,
            'total':       total,
            'total_pages': max(1, -(-total // per_page)),
            'page':        page,
        }

    @api.model
    def update_item_master_row(self, product_id, vals):
        """Update a product template field."""
        pt = self.env['product.template'].browse(product_id)
        if not pt.exists():
            return {'success': False, 'error': 'Product not found'}
        try:
            allowed = ['list_price','weight','description','description_sale']
            write_vals = {k: v for k, v in vals.items() if k in allowed}
            if write_vals:
                pt.sudo().write(write_vals)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
