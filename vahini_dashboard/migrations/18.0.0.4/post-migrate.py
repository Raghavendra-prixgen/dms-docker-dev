# -*- coding: utf-8 -*-
"""
Vahini Dashboard 18.0.0.4 – Multi-company performance indexes
Runs automatically after `odoo-bin -u vahini_dashboard`.
All statements use IF NOT EXISTS so re-running is safe.
"""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    indexes = [
        (
            "idx_account_move_dashboard",
            "account_move",
            """CREATE INDEX IF NOT EXISTS idx_account_move_dashboard
               ON account_move (company_id, move_type, state, invoice_date)""",
        ),
        (
            "idx_account_move_line_dashboard",
            "account_move_line",
            """CREATE INDEX IF NOT EXISTS idx_account_move_line_dashboard
               ON account_move_line (move_id, product_id, display_type)
               WHERE display_type = 'product'""",
        ),
        (
            "idx_aml_receivable",
            "account_move_line",
            """CREATE INDEX IF NOT EXISTS idx_aml_receivable
               ON account_move_line (partner_id, reconciled, account_id)
               WHERE reconciled = FALSE""",
        ),
        (
            "idx_stock_quant_dashboard",
            "stock_quant",
            """CREATE INDEX IF NOT EXISTS idx_stock_quant_dashboard
               ON stock_quant (product_id, location_id)""",
        ),
        (
            "idx_svl_company",
            "stock_valuation_layer",
            """CREATE INDEX IF NOT EXISTS idx_svl_company
               ON stock_valuation_layer (company_id)""",
        ),
        (
            "idx_res_partner_geo",
            "res_partner",
            """CREATE INDEX IF NOT EXISTS idx_res_partner_geo
               ON res_partner (state_id, city)""",
        ),
    ]

    for idx_name, table, sql in indexes:
        try:
            cr.execute(sql)
            _logger.info("Vahini Dashboard: index %s on %s — OK", idx_name, table)
        except Exception as e:
            # Non-fatal: log and continue so the rest of the upgrade succeeds
            _logger.warning(
                "Vahini Dashboard: could not create index %s on %s: %s",
                idx_name, table, e,
            )
