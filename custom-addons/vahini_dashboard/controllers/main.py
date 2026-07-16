# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class VahiniDashboardController(http.Controller):

    @http.route(
        "/vahini_dashboard/companies",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def get_companies(self, **kwargs):
        """Return companies grouped by parent — branches appear under their
        parent company, not as flat separate entries."""
        user = request.env.user
        current = request.env.company
        allowed = user.company_ids

        # ── Build grouped structure ───────────────────────────────────────────
        # Separate top-level companies (no parent, or parent not in allowed)
        # from branches (has a parent that IS in allowed list).
        top_level = allowed.filtered(
            lambda c: not c.parent_id or c.parent_id not in allowed
        ).sorted('name')

        groups = []
        for parent in top_level:
            # Find all branches of this parent that the user has access to
            branches = allowed.filtered(
                lambda c: c.parent_id and c.parent_id.id == parent.id
            ).sorted('name')

            entry = {
                'id':       parent.id,
                'name':     parent.name,
                'color':    '#6366f1',
                'is_group': bool(branches),   # True = has branches beneath it
                'branches': [
                    {
                        'id':       b.id,
                        'name':     b.name,
                        'color':    '#6366f1',
                        'parent_name': parent.name,
                    }
                    for b in branches
                ],
            }
            groups.append(entry)

        return {
            'groups':  groups,
            # flat list still provided for backward compat (switch_company etc.)
            'companies': [
                {'id': co.id, 'name': co.name, 'color': '#6366f1'}
                for co in allowed.sorted('name')
            ],
            'current': {'id': current.id, 'name': current.name},
        }

    @http.route(
        "/vahini_dashboard/switch_company",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def switch_company(self, company_id=None, **kwargs):
        """Switch the current user's active company."""
        if not company_id:
            return {'success': False, 'message': 'company_id required'}

        user = request.env.user
        company = request.env['res.company'].sudo().browse(int(company_id))

        if not company.exists():
            return {'success': False, 'message': 'Company not found'}

        # Check user is allowed for this company
        if company not in user.company_ids:
            return {'success': False, 'message': 'Not allowed'}

        # Set as active company
        user.sudo().write({'company_id': company.id})
        request.session['_company_ids'] = [company.id]

        return {
            'success': True,
            'company_id': company.id,
            'company_name': company.name,
        }

    @http.route(
        "/vahini_dashboard/data",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def get_dashboard_data(self, date_from=None, date_to=None, **kwargs):
        return request.env["vahini.dashboard"].get_dashboard_data(
            date_from=date_from,
            date_to=date_to,
        )

    @http.route(
        "/vahini_dashboard/compare",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_compare_data(self, chart_id, date_from, date_to,
                         prev_from, prev_to, page=1, per_page=10, **kwargs):
        return request.env["vahini.dashboard"].get_compare_data(
            chart_id=chart_id,
            date_from=date_from,
            date_to=date_to,
            prev_from=prev_from,
            prev_to=prev_to,
            page=int(page),
            per_page=int(per_page),
        )


    @http.route(
        "/vahini_dashboard/dayview",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_dayview_data(self, date_from=None, date_to=None,
                         view_type="transactions", tab="sales",
                         page=1, per_page=15, sort_col="invoice_date",
                         sort_dir="desc", search="", **kwargs):
        return request.env["vahini.dashboard"].get_dayview_data(
            date_from=date_from, date_to=date_to,
            view_type=view_type, tab=tab,
            page=int(page), per_page=int(per_page),
            sort_col=sort_col, sort_dir=sort_dir, search=search,
        )
    @http.route(
        "/vahini_dashboard/mapview",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_mapview_data(self, date_from=None, date_to=None,
                         move_type='out_invoice', **kwargs):
        return request.env["vahini.dashboard"].get_mapview_data(
            date_from=date_from, date_to=date_to, move_type=move_type,
        )
    @http.route(
        "/vahini_dashboard/payment",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_payment_data(self, report_type="receivable", as_of_date=None, **kwargs):
        return request.env["vahini.dashboard"].get_payment_data(
            report_type=report_type, as_of_date=as_of_date,
        )
    @http.route(
        "/vahini_dashboard/send_email",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def send_payment_email(self, partner_id, email_to,
                           add_statement=False, add_ledger=False, **kwargs):
        return request.env["vahini.dashboard"].send_payment_email(
            partner_id=partner_id,
            email_to=email_to,
            add_statement=add_statement,
            add_ledger=add_ledger,
        )
    @http.route(
        "/vahini_dashboard/followup",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_followup_data(self, tab="all", search="", page=1, per_page=50, **kwargs):
        return request.env["vahini.dashboard"].get_followup_data(
            tab=tab, search=search, page=int(page), per_page=int(per_page),
        )
    @http.route(
        "/vahini_dashboard/itemview",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_itemview_data(self, tab="all", search="", page=1, per_page=50,
                          filters=None, columns=None, **kwargs):
        return request.env["vahini.dashboard"].get_itemview_data(
            tab=tab, search=search, page=int(page), per_page=int(per_page),
            filters=filters or {}, columns=columns,
        )
    @http.route(
        "/vahini_dashboard/gpview",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_gpview_data(self, date_from=None, date_to=None,
                        group_by="item_name", search="", page=1, per_page=50, **kw):
        return request.env["vahini.dashboard"].get_gpview_data(
            date_from=date_from, date_to=date_to,
            group_by=group_by, search=search,
            page=int(page), per_page=int(per_page),
        )
    @http.route(
        "/vahini_dashboard/trendview",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_trendview_data(self, report_type="sales", fiscal_year="",
                           period="monthly", months=None, group_by="customer",
                           city_filter=None, search="", page=1, per_page=20, **kw):
        return request.env["vahini.dashboard"].get_trendview_data(
            report_type=report_type, fiscal_year=fiscal_year,
            period=period, months=months, group_by=group_by,
            city_filter=city_filter, search=search,
            page=int(page), per_page=int(per_page),
        )
    @http.route(
        "/vahini_dashboard/item_master",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_item_master_data(self, search="", page=1, per_page=50, **kw):
        return request.env["vahini.dashboard"].get_item_master_data(
            search=search, page=int(page), per_page=int(per_page),
        )

    @http.route(
        "/vahini_dashboard/item_master_update",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def update_item_master_row(self, product_id, vals, **kw):
        return request.env["vahini.dashboard"].update_item_master_row(
            product_id=product_id, vals=vals,
        )

    @http.route(
        "/vahini_dashboard/dashboard_table",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_dashboard_table(self, group_by="item_name", date_from=None,
                            date_to=None, search="", page=1, per_page=10, **kw):
        return request.env["vahini.dashboard"].get_dashboard_table(
            group_by=group_by,
            date_from=date_from,
            date_to=date_to,
            search=search,
            page=int(page),
            per_page=int(per_page),
        )
    @http.route(
        "/vahini_dashboard/announcements",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def get_announcements(self, **kw):
        return request.env["vahini.announcement"].get_active_announcements()

    @http.route(
        "/vahini_dashboard/announcement_save",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def save_announcement(self, **kw):
        return request.env["vahini.announcement"].save_announcement(kw)

    @http.route(
        "/vahini_dashboard/announcement_delete",
        type="json", auth="user", methods=["POST"], csrf=False,
    )
    def delete_announcement(self, ann_id=None, **kw):
        return request.env["vahini.announcement"].delete_announcement(int(ann_id))
