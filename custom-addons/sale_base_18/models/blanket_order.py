from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import date

class res_partner(models.Model):
    _inherit = "res.partner"

    def action_view_balnket_order(self):
        action = self.env.ref('sale_base_18.action_Blanket_orderss').read()[0]
        balnket_order = self.env['sale.order'].search([('partner_id','=',self.id),('y_order_type','=','blanket')])
        if not balnket_order:
            raise ValidationError(_("No Balnket Order"))
        if len(balnket_order) > 1:
            action['domain'] = [('id', 'in', balnket_order.ids)]
        elif balnket_order:
            action['views'] = [(self.env.ref('sale_base_18.form_dev_blanket_sale_order').id, 'form')]
            action['res_id'] = balnket_order.id
        return action


class SaleOrder(models.Model):
    _inherit = "sale.order"

    y_blanket_order_id = fields.Many2one('sale.order',string="Blanket order")
    y_blanket_state = fields.Selection(selection=[('draft', 'New'),
                                                ('open', 'Open'),
                                                ('expired', 'Expired'),
                                                ('cancelled', 'Cancelled'),
                                                ('closed','Closed')], string='Blanket State', default='draft', copy=False, tracking=True)
    y_order_type = fields.Selection(selection=[('sale', 'Sale'), ('blanket', 'Blanket')], string='Type of Order')
    y_blanket_expiry_date = fields.Date(string='Expiry Date')
    y_blanket_order_ids = fields.Many2many(comodel_name='sale.order', relation='sale', column1='y_order_type', column2='y_blanket_expiry_date', string='Blanket Quotation')
    y_sale_quote_count = fields.Integer(string='Sale Orders', compute='compute_sale_quote_count')
    y_blanket_sale_order_ids = fields.One2many('sale.order','y_blanket_order_id',string="Balnket Orders")

    def action_cancel(self):
        res = super().action_cancel()
        if self.y_blanket_order_id and self.y_blanket_order_id.y_blanket_state == 'closed':
            self.y_blanket_order_id.y_blanket_state = 'open'
        return res

    @api.onchange('partner_id')
    def _onchange_blanket_partner_id_warning(self):
        if self.partner_id and self.y_blanket_order_id:
            if self.partner_id != self.y_blanket_order_id.partner_id:
                raise ValidationError("You can't change the Customer for a Blanket Sale Order")
        balnket_order_ids = self.env['sale.order'].search([('partner_id','=',self.partner_id.id),('y_order_type','=','blanket')])
        if self.partner_id and self.y_order_type == 'blanket' and balnket_order_ids:
            msg= "Blanket order already created"
            return { 'warning': {'title': 'Blanket Order Created', 'message':msg } }


    def create_sale_quotation(self):
        lines_to_add = self.order_line.filtered(lambda line: line.product_uom_qty > line.so_qo_quantity)
        if not lines_to_add:
            raise ValidationError(_('''There are no order lines with remaining quantity to add'''))

        data = []
        for line in lines_to_add:
            data.append((0, 0, {'y_sale_line_id': line.id}))

        if data:
            create_quote_id = self.env['create.sale.quotation'].create({'y_line_ids': data})
            if create_quote_id:
                action = self.env.ref('sale_base_18.action_create_sale_quotation').read()[0]
                action.update({'res_id': create_quote_id.id})
                return action

    # def create_sale_quotation(self):
    #     if not self.order_line:
    #         raise ValidationError(_('''Please add some order lines'''))
    #     data = []
    #     for line in self.order_line:
    #         data.append((0, 0, {'y_sale_line_id': line.id}))
    #     if data:
    #         create_quote_id = self.env['create.sale.quotation'].create({'y_line_ids': data})
    #         if create_quote_id:
    #             action = self.env.ref('sale_base_18.action_create_sale_quotation').read()[0]
    #             action.update({'res_id': create_quote_id.id})
    #             return action

    @api.model
    def create(self, vals):
        if self._context.get('default_y_order_type') == 'blanket':
            vals['name'] = self.env['ir.sequence'].next_by_code('sale.blanket') or '/'
        return super(SaleOrder, self).create(vals)

    def open_blanket_order(self):
        self.y_blanket_state = 'open'

    def cancel_blanket_order(self):
        self.y_blanket_state = 'cancelled'

    def set_to_new_blanket_order(self):
        self.y_blanket_state = 'draft'

    def compute_sale_quote_count(self):
        for rec in self:
            rec.y_sale_quote_count = len(rec.y_blanket_sale_order_ids)

    def view_sale_quotations(self):
        orders = self.mapped('y_blanket_sale_order_ids')
        action = self.env.ref('sale.action_orders').read()[0]
        if len(orders) > 1:
            action['domain'] = [('id', 'in', orders.ids)]
        elif len(orders) == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = orders.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    def expire_blanket_orders(self):
        blanket_ids = self.env['sale.order'].search([('y_blanket_expiry_date', '=', date.today()),
                                                     ('y_order_type', '=', 'blanket')])
        if blanket_ids:
            for blanket_id in blanket_ids:
                blanket_id.y_blanket_state = 'expired'


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    delivered_qty = fields.Float(string="Delivery Quantity",compute='compute_delivered_qty',digits='Product Unit of Measure',readonly=False, copy=False)
    invoiced_qty = fields.Float(string="Invoiced Quantity",compute='compute_invoiced_qty',digits='Product Unit of Measure',)
    remaining_qty = fields.Float(string='Remaining Quantity', compute='compute_remaining_qty')
    consumed_qty = fields.Float(string='Consumed Quantity')
    so_quantity = fields.Float(string="SO Quantity",compute="_compute_so_quantity")
    so_qo_quantity = fields.Float(string="SO/SQ Quantity",compute="_compute_so_sq_quantity")
    
    y_sequence = fields.Char(string='Serial No', compute='_compute_serial_number')

    @api.depends('order_id', 'sequence')
    def _compute_serial_number(self):
        for order in self.mapped('order_id'):
            number = 1
            for line in order.order_line:
                if line.product_id:
                    line.y_sequence = str(number)
                    number += 1
                else:
                    line.y_sequence = str(number)
           

    @api.depends('order_id.y_blanket_sale_order_ids')
    def _compute_so_quantity(self):
        for line in self:
            sale_order_lines_with_same_product = line.order_id.y_blanket_sale_order_ids.filtered(lambda x:x.state =='sale').order_line.filtered(
                lambda sol: sol.product_id == line.product_id
            )
            sum_product_uom_qty = sum(sale_order_lines_with_same_product.mapped('product_uom_qty'))
            line.so_quantity = sum_product_uom_qty

    @api.depends('order_id.y_blanket_sale_order_ids')
    def _compute_so_sq_quantity(self):
        for line in self:
            sale_order_lines_with_same_product = line.order_id.y_blanket_sale_order_ids.filtered(lambda x: x.state != 'cancel').order_line.filtered(
                lambda sol: sol.product_id == line.product_id)
            sum_product_uom_qty = sum(sale_order_lines_with_same_product.mapped('product_uom_qty'))
            line.so_qo_quantity = sum_product_uom_qty


    def compute_delivered_qty(self):
        for record in self:    
            delivered_qty = 0.0  
            for line in record.order_id.y_blanket_sale_order_ids.order_line.filtered(
                    lambda sol: sol.product_id == record.product_id):
                delivered_qty += line.qty_delivered  
            record.delivered_qty = delivered_qty

    def compute_invoiced_qty(self):
        for record in self:    
            invoiced_qty = 0.0  
            for line in record.order_id.y_blanket_sale_order_ids.order_line.filtered(
                    lambda sol: sol.product_id == record.product_id):
                invoiced_qty += line.qty_invoiced  
            record.invoiced_qty = invoiced_qty

    def compute_remaining_qty(self):
        for record in self:
            sale_order_lines_with_same_product = record.order_id.y_blanket_sale_order_ids.filtered(lambda x:x.state != 'cancel').order_line.filtered(
                lambda sol: sol.product_id == record.product_id
            )
            sum_product_uom_qty = sum(sale_order_lines_with_same_product.mapped('product_uom_qty'))
            record.remaining_qty = record.product_uom_qty - sum_product_uom_qty

