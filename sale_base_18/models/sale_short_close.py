# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo import SUPERUSER_ID, _, api, fields, models

class SaleOrder(models.Model):
    _inherit = "sale.order" 

    y_short_close_reason = fields.Char(string='Short Close Reasons',copy=False)
    y_is_so_short_close = fields.Boolean(copy=False,string="Short Close") 

    def short_close_form_wizard_sale(self):
        eligible_lines = self.order_line.filtered(lambda line: line.y_is_short_close == False and line.product_uom_qty != line.qty_delivered and line.qty_delivered > 0)
        if self.state == 'sale':    
            return {
                'name': ("SaleOrder Short Close Wizard"),

                'type': 'ir.actions.act_window',

                'res_model': 'saleorder.short.close.wizard',

                'view_mode': 'form',

                'views': [(self.env.ref('sale_base_18.view_saleorder_short_close_wizard_form').id, 'form')],

                'target': 'new',

                'context': dict(self._context, create=False,
                    edit=False,default_short_close_reason =self.y_short_close_reason,default_order_id = self.id,
                    default_y_sc_so_lines_ids=eligible_lines.ids)
            }
        else:
            raise UserError(_('SaleOrder Short Close can be processed only if the Order is in Sale Order State!'))
            
class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    y_is_short_close = fields.Boolean(string='Short Close',copy=False)
    y_short_close_description = fields.Char(string='Order Short Close Reason',copy=False)
    y_short_close_reason_id =  fields.Many2one('sales.short.close.reason',string='Short Close Reasons',copy=False)
    y_short_close_reason = fields.Char(string='Short Close Reasons',copy=False)

class StockMove(models.Model):
    _inherit = "stock.move"

    y_is_freeze = fields.Boolean(copy=False,string="Is Freeze")