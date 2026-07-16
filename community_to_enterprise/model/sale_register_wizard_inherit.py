from odoo import models


def _get_selection_label(env_obj, model_name, field_name, field_value):
    """Return the human-readable label for a selection field value."""
    field_info = env_obj.env[model_name].fields_get(
        allfields=[field_name]
    )[field_name]['selection']
    return dict(field_info).get(field_value, field_value)


class SaleRegisterWizardInherit(models.TransientModel):
    """
    Inherit sale.register.wizard to insert 'Product Description' as column 12
    in both the Excel export (get_headers + update_worksheet) and keep all
    other columns correctly shifted one place to the right.
    """
    _inherit = "sale.register.wizard"

    # ------------------------------------------------------------------
    # Excel header row
    # ------------------------------------------------------------------
    # Simpler alternative: just add it as the LAST column
    def get_headers(self):
        return super().get_headers() + ["Product Description"]

    def update_worksheet(self, row, worksheet, line, invoice, styles):
        last_col = super().update_worksheet(row, worksheet, line, invoice, styles)
        desc = line.product_id.product_tmpl_id.description_sale or ''
        # Strip basic HTML tags
        import re
        desc = re.sub(r'<[^>]+>', '', desc)
        worksheet.write(row, last_col + 1, desc, styles['left_alignment'])
        return last_col + 1