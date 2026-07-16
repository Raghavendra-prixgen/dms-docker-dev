from odoo import models, fields, _, api
from odoo.exceptions import ValidationError

class CreateSaleQuotation(models.TransientModel):
    _name = "create.sale.quotation"


    def create_quotation(self):
        blanket_order_obj = self.env['sale.order'].browse(self._context.get('active_id'))

        for line in self.y_line_ids:
            if line.y_order_qty <= 0:
                raise ValidationError(_('''New Quotation Quantity must be greater than zero for all the products'''))
            if not line.y_partner_id:
                raise ValidationError(_('''Please add Customer in all lines'''))
            if line.y_order_qty > line.y_remaining_qty:
                raise ValidationError(_('''You can not order '%s' quantity of '%s' because Remaining Quantity of it is '%s' ''') %
                                      (line.y_order_qty, line.y_product_id.name, line.y_remaining_qty))
        customer_dict = {}
        for line in self.y_line_ids:
            if line.y_partner_id.id not in customer_dict:
                customer_dict.update({line.y_partner_id.id: [line]})
            else:
                customer_dict[line.y_partner_id.id].append(line)

        if customer_dict:
            blanket_id = self.y_line_ids[0].y_sale_line_id.order_id
            consumed_qty_dict = {}
            new_quotations = []
            for value in customer_dict:
                partner_id = self.env['res.partner'].browse(int(value))
                if partner_id:
                    data = []
                    for line in customer_dict[value]:
                        data.append((0, 0,{'product_id': line.y_product_id.id,
                                           'product_uom': line.y_sale_line_id.product_uom.id,
                                           'product_uom_qty': line.y_order_qty,
                                           'price_unit': line.y_sale_line_id.price_unit,
                                           'name': line.y_sale_line_id.name,
                        }))
                        consumed_qty_dict.update({line.y_sale_line_id.id: line.y_order_qty})
                    if data:
                        # quotation_id = self.env['sale.order'].create({'partner_id': partner_id.id,
                        #                                               'payment_term_id'
                        #                                               'order_line': data})
                        quotation_id = blanket_order_obj.copy()
                        if quotation_id:
                            new_quotations.append(quotation_id.id)

                        quotation_id.y_blanket_order_id = blanket_order_obj.id

            if new_quotations:
                for quote in new_quotations:
                    blanket_id.y_blanket_order_ids = [(4, quote)]
                if consumed_qty_dict:
                    for qty_val in consumed_qty_dict:
                        blanket_line_id = self.env['sale.order.line'].browse(int(qty_val))
                        if blanket_line_id:
                            blanket_line_id.consumed_qty += float(consumed_qty_dict[qty_val])
        all_lines_fulfilled = True
        for line in blanket_order_obj.order_line:
            if line.product_uom_qty > line.so_qo_quantity:
                all_lines_fulfilled = False
                break

        if all_lines_fulfilled:
            blanket_order_obj.y_blanket_state = 'closed'
            blanket_order_obj.state = 'sale'

        # if sum(self.y_line_ids.mapped('y_remaining_qty')) == sum(self.y_line_ids.mapped('y_order_qty')):
        #     blanket_order_obj.y_blanket_state = 'closed'
        #     blanket_order_obj.state = 'sale'

    y_line_ids = fields.One2many('create.sale.quotation.line', 'y_create_quote_id', string="Lines")

class CreateSaleQuotationLine(models.TransientModel):
    _name = "create.sale.quotation.line"

    y_create_quote_id = fields.Many2one('create.sale.quotation', string='Create Sale Quotation')
    y_sale_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    y_product_id = fields.Many2one('product.product', related='y_sale_line_id.product_id')
    y_remaining_qty = fields.Float(string='Remaining Quantity', related='y_sale_line_id.remaining_qty')
    y_partner_id = fields.Many2one('res.partner', string='Customer',related='y_sale_line_id.order_id.partner_id')
    y_order_qty = fields.Float(string='New Quotation Quantity')















