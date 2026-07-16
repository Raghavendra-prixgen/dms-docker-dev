# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError

class CustomSaleDocType(models.Model):
    _name = 'sale.doc.type'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _description = 'Sale Order Document Type'
    _rec_name = 'y_name'

    active = fields.Boolean(default=True)
    y_name = fields.Char(string='Name')
    y_description = fields.Char(string='Description')
    y_sequence_id = fields.Many2one('ir.sequence' ,string='Sequence')
    y_company_id = fields.Many2one('res.company',string="Company",default=lambda self: self.env.company.id, index=1)

    @api.constrains('y_name','y_company_id')
    def check_document_name(self):
        for rec in self:
            docs=rec.env['sale.doc.type'].search([('y_name','=',rec.y_name),('y_company_id','=',rec.y_company_id.id)])
            if len(docs) > 1:
                raise ValidationError(_("""name already exists!"""))
                
class CustomSaleOrder(models.Model):
    _inherit = 'sale.order'

    y_doc_type_id = fields.Many2one('sale.doc.type', string="Document Type", ondelete="restrict",  store=True,copy=False,tracking=True)
    y_quotation_number = fields.Char(copy=False,string="RFQ Ref")
    y_parent_company_id = fields.Many2one(related="company_id.parent_id")
    y_requested_delivery_date = fields.Datetime(string="Requested Delivery Date")

    @api.constrains('y_requested_delivery_date','date_order')
    def check_requested_date(self):
        for rec in self:
            if rec.y_requested_delivery_date and rec.date_order:
                if rec.y_requested_delivery_date.date() < rec.date_order.date():
                    raise ValidationError(_("Requested delivery date should be greater than order date"))

    def unlink(self):
        for sale in self:
            if sale.picking_ids:
                raise ValidationError(_("You're not allowed to delete it once the pickings are generated."))
        return super().unlink()


    def action_cancel(self):
        for sale in self:
            if sale.picking_ids.filtered(lambda x:x.state == 'done'):
                raise ValidationError(_("You're not allowed to cancel it once the pickings are done."))
        return super().action_cancel()

    @api.onchange('partner_id')
    def get_document_type(self):
        for rec in self:
            if rec.partner_id:
                sale_doc_type_id = rec.partner_id.with_company(rec.company_id).y_sale_doc_type_id
                if not sale_doc_type_id and rec.company_id.sudo().parent_id:
                    sale_doc_type_id = rec.partner_id.sudo().with_company(rec.company_id.sudo().parent_id).y_sale_doc_type_id
                rec.y_doc_type_id = sale_doc_type_id.id
            else:
                rec.y_doc_type_id = False

    def action_sale_order_sequence(self):
        for order in self:
            order.y_quotation_number = order.name
            order.name = order.y_doc_type_id.y_sequence_id.next_by_id()


    def action_confirm(self):
        for rec in self:
            if not rec.y_doc_type_id:
                raise ValidationError(_("""Mapping Document type is required to confirm a Sales Quotation"""))
            rec.action_sale_order_sequence()
        return super(CustomSaleOrder, self).action_confirm()
    
    # def action_draft(self):
    #     if self.state not in ('to_approve','reject','cancel'):
    #         raise ValidationError(_("""Invalid Action"""))
    #     return super().action_draft()

class CustomResPartnerNew(models.Model):
    _inherit = "res.partner"

    y_parent_company_id = fields.Many2one(related="company_id.parent_id")
    y_sale_doc_type_id = fields.Many2one('sale.doc.type', string="Document Type",company_dependent=True)
