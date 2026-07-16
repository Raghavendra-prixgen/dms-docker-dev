from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError, ValidationError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    y_external_document_number = fields.Char("Vendor Invoice/DC Number",copy=False)
    y_external_document_date = fields.Date("Vendor Invoice/DC Date",copy=False)
    y_lr_date = fields.Date(string="LR Date",copy=False)
    y_lr_number = fields.Char(string="LR Number",copy=False)
    y_is_edit_vendor_invoice = fields.Boolean(compute="_compute_vendor_invoice_dc_edit_access",string="Is Edit Vendor Invoice")

    def _compute_vendor_invoice_dc_edit_access(self):
        for picking in self:
            picking.y_is_edit_vendor_invoice = False
            if picking.env.user.has_group('picking_to_accounts.vendor_invoice_dc_edit_access'):
                picking.y_is_edit_vendor_invoice = True


    def button_validate(self):
        if self.picking_type_code == 'incoming' and self.purchase_id:
            if not self.y_external_document_number or not self.y_external_document_date:
                raise ValidationError(_('''Vendor Invoice/DC Number and Vendor Invoice/DC Date required to validate.'''))
        return super().button_validate()

    @api.constrains('y_external_document_number','y_external_document_date','purchase_id','company_id')
    def _check_vendor_invoice_number_date(self):
        for picking in self:
            if picking.picking_type_code == 'incoming' and picking.y_external_document_number and picking.y_external_document_date and self.purchase_id:
                query = """ SELECT 
                                picking.id 
                            FROM 
                                stock_picking as picking 
                            LEFT JOIN 
                                stock_picking_type pick_type ON pick_type.id = picking.picking_type_id
                            LEFT JOIN 
                                stock_move move ON move.picking_id = picking.id
                            LEFT JOIN
                                purchase_order_line purchase_line_id ON purchase_line_id.id = move.purchase_line_id 
                            WHERE pick_type.code = 'incoming'
                                AND picking.company_id = {company_id}
                                AND picking.y_external_document_number = '{document_number}'
                                AND picking.y_external_document_date = '{document_date}'
                                AND move.purchase_line_id is not null 
                                AND purchase_line_id.partner_id = {vendor_id}
                                AND picking.state != 'cancel'
                                AND picking.id != {picking}""".format(company_id=picking.company_id.id,
                                                                        document_number=picking.y_external_document_number,
                                                                        document_date=picking.y_external_document_date,
                                                                        picking=picking.id,
                                                                        vendor_id=picking.purchase_id.partner_id.id)

                self.env.cr.execute(query)
                duplicated_moves = self.browse([r[0] for r in self._cr.fetchall()])
                if duplicated_moves:
                    raise ValidationError(_('Duplicated Vendor Invoice/DC Number detected:\n%s') % "\n".join(
                        duplicated_moves.mapped(lambda m: "%(name)s - %(ref)s" % {
                            'ref': m.y_external_document_number,
                            'name': "{}".format(m.display_name),
                        })
                    ))      


class AccountMoveLine(models.Model):
    _inherit ="account.move.line"

    y_stock_picking_ref = fields.Many2one('stock.picking', string="GRN / Delivery",copy=False)
    y_stock_move_id = fields.Many2one('stock.move',string="Stock Move",copy=False)
    y_sale_order_id = fields.Many2one('sale.order',copy=False,string="Sale Order")
    y_with_goods = fields.Selection([('with_goods',"With Reference"),('without_goods','Without Reference')],default="with_goods",string="Posting Type",tracking=True)
    y_is_required_get_picking = fields.Boolean(default=True,compute="_compute_is_required_get_picking",string="Is Required Get Picking")

    @api.depends('move_id.move_type','product_id','purchase_line_id','sale_line_ids','y_stock_picking_ref','y_stock_move_id','y_with_goods')
    def _compute_is_required_get_picking(self):
        is_required_get_picking = False
        for line in self:
            if line.move_id.move_type != 'entry':
                if (line.product_id and line.product_id.type == 'consu' and line.product_id.is_storable and (line.purchase_line_id or line.sale_line_ids) and not line.y_stock_picking_ref) or (line.product_id and line.product_id.type == 'consu' and line.product_id.is_storable and (not line.purchase_line_id or not line.sale_line_ids) and not line.y_stock_picking_ref):
                    if line.y_with_goods == 'with_goods':
                        is_required_get_picking = True

                if line.move_id.move_type == 'out_invoice' and (line.sale_line_ids.sudo().purchase_line_ids and not line.sale_line_ids.order_id.picking_ids):
                    is_required_get_picking = False
            
            line.y_is_required_get_picking = is_required_get_picking
    
class StockMove(models.Model):
    _inherit = "stock.move"

    y_move_line_id = fields.Many2one('account.move.line',string="Invoice Line")
    y_quantity_to_process  = fields.Float(string="Quantity To Process")
    y_purchase_ref_id = fields.Many2one('purchase.order',related="purchase_line_id.order_id",string="Purchase Order")
    y_sale_ref_id = fields.Many2one('sale.order',related="sale_line_id.order_id",string="Sale Order")
    
    # Below Code for get Pending GRN Qunatity in Goods Received Not Invoiced Report
    y_account_move_line_ids = fields.One2many('account.move.line','y_stock_move_id',string="Invoice Lines")
    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder)
        for move in self:
            if move.purchase_line_id or move.sale_line_id:
                move.y_quantity_to_process = move.quantity            
        return res
    # END

    def prepare_purchase_get_picking_line(self,move,quantity,account_val):
        vals =  {
                    'name': move.env['account.move.line']._get_journal_items_full_name(move.purchase_line_id.name, move.product_id.display_name), 
                    'product_id': move.product_id.id,
                    'product_uom_id': move.purchase_line_id.product_uom.id,
                    'quantity': quantity,
                    'price_unit': move.purchase_line_id.price_unit,
                    'discount': move.purchase_line_id.discount,
                    'tax_ids': [(6, 0, move.purchase_line_id.taxes_id.ids)],
                    'purchase_order_id': move.y_purchase_ref_id.id,
                    'purchase_line_id':move.purchase_line_id.id,
                    'y_stock_picking_ref':move.picking_id.id,
                    'y_stock_move_id':move.id,
                    'move_id':account_val.id,                    
                }
        if move.purchase_line_id.analytic_distribution:
            vals['analytic_distribution'] = move.purchase_line_id.analytic_distribution

        return vals


    def prepare_purchase_get_picking(self):
        purchase_order_id = self.purchase_line_id.order_id
        partner_invoice = self.env['res.partner'].browse(purchase_order_id.partner_id.address_get(['invoice'])['invoice'])
        partner_bank_id = purchase_order_id.partner_id.commercial_partner_id.bank_ids.filtered_domain(['|', ('company_id', '=', False), ('company_id', '=', purchase_order_id.company_id.id)])[:1]
        ref = ''
        notes = ''
        for order in purchase_order_id:
            if order.partner_ref:
                ref = ', '.join([ref,order.partner_ref]) if len(ref) else ', '.join([order.partner_ref])
            if order.notes:
                notes = ', '.join([notes,order.notes]) if len(notes) else ', '.join([order.notes])

        if any(self.picking_id.filtered(lambda x:x.y_external_document_number)):
            external_ref = ",".join(list(set(self.picking_id.filtered(lambda x:x.y_external_document_number).mapped('y_external_document_number'))))
            ref = ref + " " + external_ref


        vals =  {
                'ref': ref,
                'narration': notes,
                'currency_id': purchase_order_id.currency_id.id,
                'fiscal_position_id': (purchase_order_id.fiscal_position_id or purchase_order_id.fiscal_position_id._get_fiscal_position(partner_invoice)).id,
                'payment_reference': ref,
                'partner_bank_id': partner_bank_id.id,
                'invoice_origin': ', '.join(purchase_order_id.mapped('name')),
                'invoice_payment_term_id': purchase_order_id[0].payment_term_id.id,
                'company_id': purchase_order_id.company_id.id,
            }

        if any(self.picking_id.filtered(lambda x:x.y_external_document_date)):
            vals['invoice_date'] = self[:1].picking_id.y_external_document_date

        return vals 

    def prepare_sale_get_picking_line(self,move,quantity,account_val):
        vals = {
                    'name': move.env['account.move.line']._get_journal_items_full_name(move.sale_line_id.name, move.product_id.display_name), 
                    'product_id': move.product_id.id,
                    'product_uom_id': move.sale_line_id.product_uom.id,
                    'quantity': quantity,
                    'price_unit': move.sale_line_id.price_unit,
                    'discount': move.sale_line_id.discount,
                    'tax_ids': [(6, 0, move.sale_line_id.tax_id.ids)],
                    'y_sale_order_id': move.sale_line_id.order_id.id,
                    'sale_line_ids':[(6, 0, move.sale_line_id.ids)],
                    'y_stock_picking_ref':move.picking_id.id,
                    'y_stock_move_id':move.id,
                    'move_id':account_val.id,
                    
                }
        if move.sale_line_id.analytic_distribution:
            vals['analytic_distribution'] = move.sale_line_id.analytic_distribution

        return vals



    def prepare_sale_get_picking(self,sale_order_id):
        ref = ''
        reference = ''
        note = ''
        for order in sale_order_id:
            if order.client_order_ref:
                ref = ', '.join([ref,order.client_order_ref]) if len(ref) else ', '.join([order.client_order_ref])
            if order.reference:
                reference = ', '.join([reference,order.reference]) if len(reference) else ', '.join([order.reference])
            if order.note:
                note = ', '.join([note,order.note]) if len(note) else ', '.join([order.note])
        invoice_values = {
                'ref': ref,
                'narration': note,
                'currency_id': sale_order_id[0].currency_id.id,
                'campaign_id': sale_order_id[0].campaign_id.id,
                'medium_id': sale_order_id[0].medium_id.id,
                'source_id': sale_order_id[0].source_id.id,
                'team_id': sale_order_id[0].team_id.id,
                'partner_id': sale_order_id[0].partner_invoice_id.id,
                'partner_shipping_id': sale_order_id[0].partner_shipping_id.id,
                'fiscal_position_id': (sale_order_id[0].fiscal_position_id or sale_order_id[0].fiscal_position_id._get_fiscal_position(sale_order_id[0].partner_invoice_id)).id,
                'invoice_origin': ', '.join(sale_order_id.mapped('name')),
                'invoice_payment_term_id': sale_order_id[0].payment_term_id.id,
                'invoice_user_id': sale_order_id[0].user_id.id,
                'payment_reference': reference,
                'transaction_ids': [Command.set(sale_order_id.transaction_ids.ids)],
                'company_id': sale_order_id[0].company_id.id,
                'user_id': sale_order_id[0].user_id.id,
                }
        if sale_order_id.journal_id:
            invoice_values['journal_id'] = sale_order_id[0].journal_id.id
        return invoice_values
        

    def get_receipt_lines(self):
        invoice_values = {}
        account_val = self.env['account.move'].browse(self._context.get('ref_move_id'))
        if account_val.move_type in ('in_invoice','in_refund'):
            currency_id = set([move.purchase_line_id.order_id.currency_id for move in self])
            if len(currency_id) > 1:
                raise ValidationError(_('In order to proceed, the lines must be in the same currency.'))
            company_id = set([move.purchase_line_id.order_id.company_id for move in self])
            if len(company_id) > 1:
                raise ValidationError(_('In order to proceed, the lines must be in the same company'))
            invoice_values = self.prepare_purchase_get_picking()


        if account_val.move_type in ('out_invoice','out_refund'):
            currency_id = set([move.sale_line_id.order_id.currency_id for move in self])
            if len(currency_id) > 1:
                raise ValidationError(_('In order to proceed, the lines must be in the same currency.'))
            company_id = set([move.sale_line_id.order_id.company_id for move in self])
            if len(company_id) > 1:
                raise ValidationError(_('In order to proceed, the lines must be in the same company'))

            sale_order_id = self.sale_line_id.order_id
            invoice_values = self.prepare_sale_get_picking(sale_order_id)

        is_move_validated = True
        account_move_line_list = []
        for move in self:
            existing_move_lines = account_val.invoice_line_ids.filtered(lambda x:x.y_stock_move_id.id == move.id)
            if existing_move_lines:
                existing_move_lines.unlink()
            quantity = move.y_quantity_to_process
            
            if move.picking_id.picking_type_code == 'dropship':
                move_quantity = move.quantity
                if account_val.move_type == 'in_invoice':
                    if move.product_uom != move.purchase_line_id.product_uom:
                        move_quantity = move.purchase_line_id.product_uom._compute_quantity(move.quantity,move.product_uom)
                    vendor_bill_line_ids = move.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'in_invoice')
                    quantity = move_quantity - sum(vendor_bill_line_ids.mapped('quantity'))
                    if move_quantity <= sum(vendor_bill_line_ids.mapped('quantity')):
                        is_move_validated = False

                elif account_val.move_type == 'in_refund':
                    if move.product_uom != move.purchase_line_id.product_uom:
                        move_quantity = move.purchase_line_id.product_uom._compute_quantity(move.quantity,move.product_uom)
                    vendor_refund_line_ids = move.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'in_refund')
                    quantity = move_quantity - sum(vendor_refund_line_ids.mapped('quantity'))
                    if move_quantity <= sum(vendor_refund_line_ids.mapped('quantity')):
                        is_move_validated = False
                
                elif account_val.move_type == 'out_invoice':
                    if move.product_uom != move.sale_line_id.product_uom:
                        move_quantity = move.sale_line_id.product_uom._compute_quantity(move.quantity,move.product_uom)
                    customer_invoice_line_ids = move.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'out_invoice')
                    quantity = move_quantity - sum(customer_invoice_line_ids.mapped('quantity'))
                    if move_quantity <= sum(customer_invoice_line_ids.mapped('quantity')):
                        is_move_validated = False

                elif account_val.move_type == 'out_refund':
                    if move.product_uom != move.sale_line_id.product_uom:
                        move_quantity = move.sale_line_id.product_uom._compute_quantity(move.quantity,move.product_uom)
                    customer_refund_line_ids = move.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'out_refund')
                    quantity = move_quantity - sum(customer_refund_line_ids.mapped('quantity'))
                    if move_quantity <= sum(customer_refund_line_ids.mapped('quantity')):
                        is_move_validated = False

            if is_move_validated:
                if account_val.move_type in ('in_invoice','in_refund'):
                    if move.product_uom != move.purchase_line_id.product_uom and move.picking_id.picking_type_code != 'dropship':
                        quantity = move.product_uom._compute_quantity(quantity,move.purchase_line_id.product_uom)
                    move_line_vals = self.prepare_purchase_get_picking_line(move,quantity,account_val)
                    account_move_line_list.append((0,0,move_line_vals))

                if account_val.move_type in  ('out_invoice','out_refund'):
                    if move.product_uom != move.sale_line_id.product_uom and move.picking_id.picking_type_code != 'dropship':
                        quantity = move.product_uom._compute_quantity(quantity,move.sale_line_id.product_uom) 
                    move_line_vals = self.prepare_sale_get_picking_line(move,quantity,account_val)
                    account_move_line_list.append((0,0,move_line_vals))             
                existing_non_move_lines = account_val.invoice_line_ids.filtered(lambda x:not x.y_stock_move_id)
                if existing_non_move_lines:
                    existing_non_move_lines.unlink()

        if account_move_line_list:
            # #creating Service Lines which doesn't have stock move ref
            if account_val.move_type in ('in_invoice','in_refund'):
                total_purchase_order = self.mapped('y_purchase_ref_id')
                for purchas_order in total_purchase_order:
                    po_service_lines = purchas_order.order_line.filtered(lambda x:x.product_id.type == 'service')
                    if po_service_lines:
                            #creating service lines if present in po
                            for po_service_line in po_service_lines:
                                account_move_line_list.append((0,0,{
                                    'name': po_service_line.env['account.move.line']._get_journal_items_full_name(po_service_line.name, po_service_line.product_id.display_name), 
                                    'product_id': po_service_line.product_id.id,
                                    'product_uom_id': po_service_line.product_uom.id,
                                    'quantity': po_service_line.product_qty,
                                    'price_unit': po_service_line.price_unit,
                                    'discount': po_service_line.discount,
                                    'tax_ids': [(6, 0, po_service_line.taxes_id.ids)],
                                    'purchase_order_id': purchas_order.id,
                                    'purchase_line_id':po_service_line.id,
                                    'move_id':account_val.id,                    
                                })) 

            elif account_val.move_type in  ('out_invoice','out_refund'):
                total_sale_order = self.mapped('y_sale_ref_id')
                for sale_order in total_sale_order:
                    sale_service_lines = sale_order.order_line.filtered(lambda x:x.product_id.type == 'service')
                    if sale_service_lines:
                        for sale_service_line in sale_service_lines:
                            account_move_line_list.append((0,0,{
                                'name': sale_service_line.env['account.move.line']._get_journal_items_full_name(sale_service_line.name, sale_service_line.product_id.display_name), 
                                'product_id': sale_service_line.product_id.id,
                                'product_uom_id': sale_service_line.product_uom.id,
                                'quantity': sale_service_line.product_uom_qty,
                                'price_unit': sale_service_line.price_unit,
                                'discount': sale_service_line.discount,
                                'tax_ids': [(6, 0, sale_service_line.tax_id.ids)],
                                'y_sale_order_id': sale_service_line.order_id.id,
                                'sale_line_ids':[(6, 0, sale_service_line.ids)],
                                'move_id':account_val.id,
                                
                            })) 

            vals = {'invoice_line_ids':account_move_line_list}
            if invoice_values:
                vals.update(invoice_values)
            account_val.write(vals)
            account_val.y_is_required_get_picking = False


class AccountMove(models.Model):
    _inherit = "account.move"

    y_is_required_get_picking = fields.Boolean(default=True,compute="_compute_is_required_get_picking",string="Is Required Get Picking")
    y_with_goods = fields.Selection([('with_goods',"With Goods"),('without_goods','Without Goods')],default="with_goods",string="Credit Note",tracking=True)


    def check_account_move_get_picking_is_required(self):
        is_required_get_picking = False
        for move in self:
            if move.move_type != 'entry':
                for line in move.invoice_line_ids:
                    if (line.product_id and line.product_id.type == 'consu' and line.product_id.is_storable and (line.purchase_line_id or line.sale_line_ids) and not line.y_stock_picking_ref) or (line.product_id and line.product_id.type == 'consu' and line.product_id.is_storable and (not line.purchase_line_id or not line.sale_line_ids) and not line.y_stock_picking_ref):
                        if line.y_with_goods == 'with_goods':
                            is_required_get_picking = True

                    if move.move_type == 'out_invoice' and (move.invoice_line_ids.sale_line_ids.sudo().purchase_line_ids and not move.invoice_line_ids.sale_line_ids.order_id.picking_ids):
                        is_required_get_picking = False
                    line.y_is_required_get_picking = is_required_get_picking

        return is_required_get_picking

    @api.depends('move_type','invoice_line_ids','y_with_goods')
    def _compute_is_required_get_picking(self):
        for move in self:
            move.y_is_required_get_picking = False
            if any(move.invoice_line_ids.filtered(lambda x:x.y_is_required_get_picking)):
                move.y_is_required_get_picking = True

            
    def _stock_account_prepare_anglo_saxon_out_lines_vals(self):
        lines_vals_list = super()._stock_account_prepare_anglo_saxon_out_lines_vals()
        with_reference_lines_vals_list = []
        for line in lines_vals_list:
            if line.get('cogs_origin_id'):
                invoice_line_id = self.invoice_line_ids.filtered(lambda x:x.id == line.get('cogs_origin_id'))
                if invoice_line_id.y_with_goods != 'without_goods' or invoice_line_id.move_id.move_type == 'entry':
                    with_reference_lines_vals_list.append(line)
            else:
                with_reference_lines_vals_list.append(line)
                
        return with_reference_lines_vals_list
        
    def display_stock_move_details(self):
        if not self.partner_id:
            partner = "Vendor" if self.move_type in ('in_invoice','in_refund') else "Customer"
            raise ValidationError("{} is required to proceed".format(partner))

        tree_view_id = self.env.ref('picking_to_accounts.stock_move_inherit_tree_view').id
        action = {
                'name': 'Stock Move',
                'view_mode': 'list',
                'views': [[tree_view_id, 'list']],
                'res_model': 'stock.move',
                'type': 'ir.actions.act_window',
                'target': 'new',
                }
        purchase_line_ids = self.invoice_line_ids.mapped('purchase_line_id')
        if purchase_line_ids:
            if len(purchase_line_ids) == 1:
                purchase_line_domain = [('purchase_line_id','=',purchase_line_ids.ids[0])]
            else:
                purchase_line_domain = [('purchase_line_id','in',purchase_line_ids.ids)]

        sale_line_ids = self.invoice_line_ids.mapped('sale_line_ids')
        if sale_line_ids:
            if len(sale_line_ids) == 1:
                sale_line_domain = [('sale_line_id','=',sale_line_ids.ids[0])]
            else:
                sale_line_domain = [('sale_line_id','in',sale_line_ids.ids)]

        domain = [('company_id','=',self.company_id.id),('state','=','done'),('y_quantity_to_process','>',0)]
        if self.move_type == 'in_invoice':
            domain += [('picking_code', 'in', ('incoming','dropship')),('purchase_line_id','!=',False),('purchase_line_id.partner_id','in',(self.partner_id + self.partner_id.sudo().parent_id).ids)]
            if purchase_line_ids:
                domain += purchase_line_domain
            action.update({'domain': domain,
                           'context':{'ref_move_id':self.id,'ref_move_type':self.move_type},
                           })
            

        if self.move_type == 'in_refund':
            domain += [('picking_code', 'in', ('outgoing','dropship')),('purchase_line_id','!=',False),('purchase_line_id.partner_id','in',(self.partner_id + self.partner_id.sudo().parent_id).ids)]
            if purchase_line_ids:
                domain += purchase_line_domain
            action.update({'domain': domain,
                           'context':{'ref_move_id':self.id,'ref_move_type':self.move_type},
                           })
                
        if self.move_type == 'out_invoice':
            domain += [('picking_code', 'in', ('outgoing','dropship')),('sale_line_id','!=',False),('sale_line_id.order_partner_id','in',(self.partner_id + self.partner_id.sudo().parent_id).ids)]
            if sale_line_ids:
                domain += sale_line_domain
            action.update({'domain': domain,
                           'context':{'ref_move_id':self.id,'ref_move_type':self.move_type},
                           })
            
        if self.move_type == 'out_refund':
            domain += [('picking_code', '=', ('incoming','dropship')),('sale_line_id','!=',False),('sale_line_id.order_partner_id','in',(self.partner_id + self.partner_id.sudo().parent_id).ids)]
            if sale_line_ids:
                domain += sale_line_domain
            action.update({'domain': domain,
                           'context':{'ref_move_id':self.id,'ref_move_type':self.move_type},
                           })
            
        return action


    def action_check_get_picking_required(self):
        for move in self:
            if move.move_type != 'entry' and any(move.invoice_line_ids.filtered(lambda x:x.y_is_required_get_picking)):
                if move.move_type in ('out_refund','in_refund','out_invoice'):
                    if move.move_type in ('out_invoice','in_refund'):
                        return "Get Shipment Mandatory"
                    if move.move_type in ('in_invoice','out_refund'):
                        return "Get Receipt Mandatory"
                else:
                    if move.move_type in ('out_invoice','in_refund'):
                        return "Get Shipment Mandatory"
                    if move.move_type in ('in_invoice','out_refund'):
                        return "Get Receipt Mandatory"
        return False
        

    def action_post(self):     
        message = self.action_check_get_picking_required()
        if message:
            raise ValidationError(_("{}".format(message)))

        res = super(AccountMove,self).action_post()
        for move in self:
            if move.move_type != 'entry':
                for line in move.invoice_line_ids:
                    if line.y_stock_move_id:
                        if line.y_stock_move_id.picking_id.picking_type_code != 'dropship':
                            quantities = sum(line.y_stock_move_id.filtered(lambda x: x.product_id == line.product_id).mapped('quantity'))
                            if move.env.user.has_group('picking_to_accounts.group_access_restrict_for_validation'):
                                if line.quantity > quantities:
                                    raise ValidationError(_('The quantity on the invoice line exceeds available stock quantity.'))

                            quantity = line.quantity
                            if line.product_uom_id != line.y_stock_move_id.product_uom:
                                quantity = line.product_uom_id._compute_quantity(quantity,line.y_stock_move_id.product_uom)
                            
                            diff_quantity_processed = line.y_stock_move_id.y_quantity_to_process - quantity
                            line.y_stock_move_id.write({'y_quantity_to_process':diff_quantity_processed})
                        else:
                            move_quantity = line.y_stock_move_id.quantity
                            if move.move_type in ('in_invoice','out_invoice'):
                                if line.y_stock_move_id.product_uom != line.y_stock_move_id.purchase_line_id.product_uom:
                                    move_quantity = line.y_stock_move_id.purchase_line_id.product_uom._compute_quantity(line.y_stock_move_id.quantity,line.y_stock_move_id.product_uom)
                                vendor_bill_line_ids = line.y_stock_move_id.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'in_invoice')
                                customer_invoice_line_ids = line.y_stock_move_id.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'out_invoice')
                                if move_quantity <= sum(vendor_bill_line_ids.mapped('quantity')) and move_quantity <= sum(customer_invoice_line_ids.mapped('quantity')):
                                    line.y_stock_move_id.write({'y_quantity_to_process':0}) 
                            
                            if move.move_type in ('in_refund','out_refund'):
                                if line.y_stock_move_id.product_uom != line.y_stock_move_id.purchase_line_id.product_uom:
                                    move_quantity = line.y_stock_move_id.purchase_line_id.product_uom._compute_quantity(line.y_stock_move_id.quantity,line.y_stock_move_id.product_uom)
                                vendor_refund_line_ids = line.y_stock_move_id.filtered(lambda x:x.picking_id.return_id).y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'in_refund')
                                customer_refund_line_ids = line.y_stock_move_id.filtered(lambda x:x.picking_id.return_id).y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'out_refund')
                                if move_quantity <= sum(vendor_refund_line_ids.mapped('quantity')) and move_quantity <= sum(customer_refund_line_ids.mapped('quantity')):
                                    line.y_stock_move_id.write({'y_quantity_to_process':0}) 
                            
        return res
    
    def button_draft(self):
        posted_ids = self.filtered(lambda x:x.state == 'posted')
        res = super(AccountMove,self).button_draft()
        for move in posted_ids:
            if move.move_type != 'entry':
                for line in move.invoice_line_ids:
                    if line.y_stock_move_id:
                        if line.y_stock_move_id.picking_id.picking_type_code != 'dropship':
                            quantity = line.quantity
                            if line.product_uom_id != line.y_stock_move_id.product_uom:
                                quantity = line.product_uom_id._compute_quantity(quantity,line.y_stock_move_id.product_uom)
                            sum_quantity_processed = line.y_stock_move_id.y_quantity_to_process + quantity
                            line.y_stock_move_id.write({'y_quantity_to_process':sum_quantity_processed})
                        else:
                            move_quantity = line.y_stock_move_id.quantity
                            if move.move_type in ('in_invoice','out_invoice'):
                                if line.y_stock_move_id.product_uom != line.y_stock_move_id.purchase_line_id.product_uom:
                                    move_quantity = line.y_stock_move_id.purchase_line_id.product_uom._compute_quantity(line.y_stock_move_id.quantity,line.y_stock_move_id.product_uom)
                                vendor_bill_line_ids = line.y_stock_move_id.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'in_invoice')
                                customer_invoice_line_ids = line.y_stock_move_id.y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'out_invoice')
                                if move_quantity > sum(vendor_bill_line_ids.mapped('quantity')) or move_quantity > sum(customer_invoice_line_ids.mapped('quantity')):
                                    line.y_stock_move_id.write({'y_quantity_to_process':line.y_stock_move_id.quantity}) 
                            
                            if move.move_type in ('in_refund','out_refund'):
                                if line.y_stock_move_id.product_uom != line.y_stock_move_id.purchase_line_id.product_uom:
                                    move_quantity = line.y_stock_move_id.purchase_line_id.product_uom._compute_quantity(line.y_stock_move_id.quantity,line.y_stock_move_id.product_uom)
                                vendor_refund_line_ids = line.y_stock_move_id.filtered(lambda x:x.picking_id.return_id).y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'in_refund')
                                customer_refund_line_ids = line.y_stock_move_id.filtered(lambda x:x.picking_id.return_id).y_account_move_line_ids.filtered(lambda x:x.move_id.state == 'posted' and x.move_id.move_type == 'out_refund')
                                if move_quantity > sum(vendor_refund_line_ids.mapped('quantity')) or move_quantity > sum(customer_refund_line_ids.mapped('quantity')):
                                    line.y_stock_move_id.write({'y_quantity_to_process':line.y_stock_move_id.quantity}) 
                        line.unlink()
        return res