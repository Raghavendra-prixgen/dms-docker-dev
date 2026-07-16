from odoo import models, fields, api
from odoo import tools


class SalesRegisterReportInherit(models.Model):
    _inherit = "sales.register.report"

    y_product_description = fields.Char(
        string="Product Description",
        readonly=True,
    )

    def _select_query(self):
        return super()._select_query() + """,
            COALESCE(
                regexp_replace(pt.description_sale->>'en_US', '<[^>]+>', '', 'g'),
                ''
            ) AS y_product_description
        """

    @api.model
    def init(self):
        # Must recreate the view so the new column is included
        tools.drop_view_if_exists(self._cr, 'sales_register_report')
        self._cr.execute("""
            CREATE OR REPLACE VIEW sales_register_report AS (
                SELECT
                    row_number() OVER () AS id,
                    {select}
                    {from_}
                    {where}
            )""".format(
            select=self._select_query(),
            from_=self._from_query(),
            where=self._where_query(),
        ))