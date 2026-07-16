from odoo import models, fields, api, _
import itertools
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError
from odoo.tools import SQL

class ResPartner(models.Model):
    _inherit = 'res.partner'


    y_is_contact_approval_required = fields.Boolean(string="Contact Approval Required",copy=False,compute="fetch_contact_approval_required")
    y_partner_category = fields.Many2one('partner.category',string="Partner Category",domain="[('y_active_id', '=', True)]")
    y_customer = fields.Boolean('Customer',copy=False,company_dependent=True)
    y_vendor = fields.Boolean('Vendor',copy=False,company_dependent=True)
    y_contact = fields.Boolean('Contacts' ,compute='is_contact',store=True,copy=False)
    y_partner = fields.Boolean('Partner',copy=False)
    ref = fields.Char(tracking=True)
    y_sequence_present = fields.Boolean(compute="check_seqnece_presence",store=True,string="Sequence Availble",copy=False)

    def fetch_contact_approval_required(self):
        for rec in self:
            company_id = self.env.company
            if company_id.sudo().parent_id:
                company_id = company_id.sudo().parent_id
            if company_id.y_is_contact_approval_required:
                rec.write({'y_is_contact_approval_required':company_id.y_is_contact_approval_required})
            else:
                rec.write({'y_is_contact_approval_required':False})

           

    @api.depends('y_partner_category')
    def check_seqnece_presence(self):
        for rec in self:
            if rec.y_partner_category.y_partner_category:
                rec.y_sequence_present = True
            else:
                rec.y_sequence_present = False

    @api.onchange('y_customer')
    def onchange_customer(self):
        for each_sale in self:
            if each_sale.y_customer:
                each_sale.customer_rank = 1
 
    @api.onchange('y_vendor')
    def onchange_vendor(self):
        for each_sale in self:
            if each_sale.y_vendor:
                each_sale.supplier_rank = 1   

    @api.depends('y_customer','y_vendor')
    def is_contact(self):
        for each in self:
            if each.y_vendor or each.y_customer:
                each.y_contact= False
            else:
                each.y_contact = True

    @api.model
    def create(self, vals):
        if 'y_partner' in vals and vals['y_partner']:
            sequence_type =  vals.get('y_partner_category')
            sequence_type = self.env['partner.category'].browse(sequence_type)
            if sequence_type:
                vals['ref'] = sequence_type.y_partner_category.next_by_id()
        return super(ResPartner, self).create(vals)

    def write(self, vals):
        if 'y_partner_category' in vals and vals['y_partner_category']:
            partner_category =  self.env['partner.category'].browse(vals.get('y_partner_category'))
            sequence_type = partner_category.y_partner_category
            if sequence_type:
                vals['ref'] = sequence_type.next_by_id()
        return super(ResPartner, self).write(vals)
    
    @api.onchange('y_partner_category')
    def onchange_partner(self):
        for l in self:
            if l.y_partner_category.y_partner_category:
                l.y_partner = True
            else:
                l.y_partner = False

    def approve_customer(self):
        self.message_post(body='Customer Approved')
        res = self.write({'y_customer':True})
        return res

    def approve_vendor(self):
        self.message_post(body='Vendor Approved')
        res = self.write({'y_vendor':True})
        return res


class PartnerCategory(models.Model):
    _name = 'partner.category'
    _description ='Partner Category'
    _parent_name = "y_zparent"
    _parent_store = True
    _rec_name = 'y_full_name'
    _order = 'y_full_name'

    y_name = fields.Char(string='Name',index=True)
    y_full_name = fields.Char(string='Category Name',store=True,compute='_compute_complete_name')
    y_zparent = fields.Many2one('partner.category',string='Parent')
    y_active_id = fields.Boolean(string='Release')
    y_partner_category = fields.Many2one('ir.sequence',string="Sequence")
    parent_path = fields.Char(index=True)
   
    @api.depends('y_name', 'y_zparent.y_name')
    def _compute_complete_name(self):
        for location in self:
            if location.y_zparent:
                location.y_full_name = '%s / %s' % (location.y_zparent.y_full_name, location.y_name)
            else:
                location.y_full_name = location.y_name

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    y_partner_category_id = fields.Many2one('partner.category',string="Partner Category",compute='get_partner_category',store=True)

    @api.onchange('partner_id','company_id')
    def _onchange_check_partner_id(self):
        for order in self:
            if order.partner_id and order.company_id:
                company_id = order.company_id
                if order.company_id.sudo().parent_id:
                    company_id = order.company_id.sudo().parent_id
                if not order.partner_id.sudo().with_company(company_id).y_customer:
                    raise AccessError('This customer is not approved. Kindly get the contact approved')



    @api.depends('partner_id')
    def get_partner_category(self):
        for rec in self:
            if rec.partner_id:
                if rec.partner_id.y_partner_category:
                    rec.y_partner_category_id = rec.partner_id.y_partner_category.id
                else:
                    rec.y_partner_category_id = False
            else:
                rec.y_partner_category_id = False


    def action_confirm(self):
        res = super(SaleOrder,self).action_confirm()
        for order in self:
            if order.partner_id:
                company_id = order.company_id
                if order.company_id.sudo().parent_id:
                    company_id = order.company_id.sudo().parent_id
                if not order.partner_id.sudo().with_company(company_id).y_customer:
                    raise AccessError('This customer is not approved. Kindly get the contact approved')
        return res



class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    READONLY_STATES = {
        'purchase': [('readonly', True)],
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
    }

    # partner_id = fields.Many2one('res.partner', string='Vendor', domain="[('y_vendor', '=', True)]")
    y_partner_category_id = fields.Many2one('partner.category',string="Partner Category",compute='get_partner_category',store=True)

    @api.onchange('partner_id','company_id')
    def _onchange_check_partner_id(self):
        for order in self:
            if order.partner_id and order.company_id:
                company_id = order.company_id
                if order.company_id.sudo().parent_id:
                    company_id = order.company_id.sudo().parent_id
                if not order.partner_id.sudo().with_company(company_id).y_vendor:
                    raise AccessError('This vendor is not approved. Kindly get the contact approved')


    @api.depends('partner_id')
    def get_partner_category(self):
        for rec in self:
            if rec.partner_id:
                if rec.partner_id.y_partner_category:
                    rec.y_partner_category_id =rec.partner_id.y_partner_category.id
                else:
                    rec.y_partner_category_id = False
            else:
                rec.y_partner_category_id = False


    def button_confirm(self):
        res = super(PurchaseOrder,self).button_confirm()
        for order in self:
            if order.partner_id:
                company_id = order.company_id
                if order.company_id.sudo().parent_id:
                    company_id = order.company_id.sudo().parent_id
                if not order.partner_id.sudo().with_company(company_id).y_vendor:
                    raise AccessError('This vendor is not approved. Kindly get the contact approved')
        return res

    def button_approve(self, force=False):        
        res = super(PurchaseOrder, self).button_approve(force)
        for order in self:
            if order.partner_id:
                company_id = order.company_id
                if order.company_id.sudo().parent_id:
                    company_id = order.company_id.sudo().parent_id
                if not order.partner_id.sudo().with_company(company_id).y_vendor:
                    raise AccessError('This vendor is not approved. Kindly get the contact approved')
        return res



class AccountInvoice(models.Model):
    _inherit = "account.move"

    y_is_customer = fields.Boolean('Customer',compute='change_domain',store=True)
    y_is_vendor = fields.Boolean('Vendor',compute='change_domain',store=True)
    y_partner_category_id = fields.Many2one('partner.category',string="Partner Category",compute='get_partner_category',store=True)

    @api.depends('partner_id')
    def get_partner_category(self):
        for rec in self:
            if rec.partner_id:
                if rec.partner_id.y_partner_category:
                    rec.y_partner_category_id =rec.partner_id.y_partner_category.id
                else:
                    rec.y_partner_category_id = False
            else:
                rec.y_partner_category_id = False


    @api.depends('partner_id')
    def change_domain(self):
        for rec in self:
            vendor_lit = ['in_invoice','in_refund','in_receipt']
            customer_lit = ['out_invoice','out_refund','out_receipt']
            if rec.move_type in vendor_lit:
                rec.y_is_vendor = True
            elif rec.move_type in customer_lit:
                rec.y_is_customer = True
            else:
                rec.y_is_vendor = False
                rec.y_is_customer = False

    @api.onchange('partner_id','company_id')
    def _onchange_contact_partner_id(self):
        for move in self:
            if move.partner_id and move.company_id:
                company_id = move.company_id
                if move.company_id.sudo().parent_id:
                    company_id = move.company_id.sudo().parent_id
                if move.move_type in ('in_invoice','in_refund'):
                    if not move.partner_id.sudo().with_company(company_id).y_vendor:
                        raise AccessError('This vendor is not approved. Kindly get the contact approved')

                if move.move_type in ('out_invoice','out_refund'):
                    if not move.partner_id.sudo().with_company(company_id).y_customer:
                        raise AccessError('This customer is not approved. Kindly get the contact approved')

class account_payment(models.Model):
    _inherit = "account.payment"

    y_is_customer = fields.Boolean('Customer')
    y_is_vendor = fields.Boolean('Vendor')

    @api.onchange('partner_id','company_id')
    def _onchange_contact_partner_id(self):
        for payment in self:
            if payment.partner_id and payment.company_id:
                company_id = payment.company_id
                if payment.company_id.sudo().parent_id:
                    company_id = payment.company_id.sudo().parent_id
                if payment.partner_type == 'supplier':
                    if not payment.partner_id.sudo().with_company(company_id).y_vendor:
                        raise AccessError('This vendor is not approved. Kindly get the contact approved')

                if payment.partner_type == 'customer':
                    if not payment.partner_id.sudo().with_company(company_id).y_customer:
                        raise AccessError('This customer is not approved. Kindly get the contact approved')

    @api.onchange('partner_type')
    def find_user(self):
        for rec in self:
            if rec.partner_type == 'customer':
                rec.y_is_customer = True
                rec.y_is_vendor = False
            elif rec.partner_type == 'supplier':
                rec.y_is_vendor = True
                rec.y_is_customer = False

class SaleReport(models.Model):
    _inherit = "sale.report"

    y_partner_category_id = fields.Many2one('partner.category',string="Partner Category",readonly=True)

    def _select_additional_fields(self):
        fields = super()._select_additional_fields()
        fields.update({'y_partner_category_id':'y_partner_category_id'})
        return fields

class PurchaseReport(models.Model):
    _inherit = "purchase.report"

    y_partner_category_id = fields.Many2one('partner.category',string="Partner Category",readonly=True)

    def _select(self) -> SQL:
        return SQL("""%s,po.y_partner_category_id as y_partner_category_id""", super()._select())

class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    y_partner_category_id = fields.Many2one('partner.category',string="Partner Category",readonly=True)

    def _select(self) -> SQL:
        return SQL("%s, move.y_partner_category_id AS y_partner_category_id", super()._select())

class Lead2OpportunityPartner(models.TransientModel):
    _inherit = 'crm.lead2opportunity.partner'

    action = fields.Selection(selection_add=[('create', 'Create a new customer/contact')])

class ContactRejectReason(models.TransientModel):
    _name = 'contact.reject.reason'
    _description = 'get reasons for not approved'


    @api.model
    def default_get(self, fields):
        result = super(ContactRejectReason, self).default_get(fields)
        active_id = self.env.context.get('y_active_id')
        cust_type = self.env.context.get('customer_type')        
        result['y_customer_type'] = cust_type
        record = self.env['res.partner'].sudo().browse(active_id)
        if record:
            result['y_partner_id'] = record.id            
        return result 

    y_customer_type = fields.Char(string="Customer Type")
    y_partner_id = fields.Many2one('res.partner',string="Partner")
    y_reasons = fields.Text('Reject Reason')

    def update_reason(self):
        pass
        # # Due to approvals Commented below code
        # if self.y_partner_id:
        #     if self.y_customer_type == 'customer':
        #         if self.y_partner_id.y_customer == True:
        #             mesg =  """Customer Reason For Rejection (%s) . """%(self.y_reasons)  
        #             self.y_partner_id.message_post(body=mesg)
        #             self.y_partner_id.write({'y_customer':False})
        #             return True
        #     if self.y_customer_type == 'vendor':
        #         if self.y_partner_id.y_vendor == True:
        #             mesg =  """Vendor Reason For Rejection (%s) . """%(self.y_reasons)  
        #             self.y_partner_id.message_post(body=mesg)
        #             self.y_partner_id.write({'y_vendor':False})
        #             return True
        # return False