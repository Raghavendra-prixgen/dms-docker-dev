from odoo import api, fields,models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta,date
from lxml.etree import Element
from odoo.tools import html2plaintext


class ResCompany(models.Model):
    _inherit = 'res.company'

    y_is_contact_approval_required = fields.Boolean(string="Contact Approval Required")
   
    
class ResConfigSetting(models.TransientModel):
    _inherit = 'res.config.settings'   

    y_is_contact_approval_required = fields.Boolean(string="Contact Approval Required",readonly=False,related="company_id.y_is_contact_approval_required")

    @api.onchange('y_is_contact_approval_required')
    def get_is_contact(self):
        for rec in self:
            if rec.y_is_contact_approval_required:
                user = self.env.user
                groups = self.env.ref('contact_base.approve_contacts_required_approval')
                groups.users = [(4, user.id)]  
                rec.y_is_contact_approval_required = True
            else:
                user = self.env.user
                groups = self.env.ref('contact_base.approve_contacts_required_approval')
                groups.users = [(3, user.id)]
                rec.y_is_contact_approval_required = False



def get_selection_label(self, object, field_name, field_value):
    return (dict(self.env[object].fields_get(allfields=[field_name])[field_name]['selection'])[field_value])

class UserApprovalCode(models.Model):
    _inherit = 'user.approval.code'

    def unlink(self):
        domain = [('y_approval_code_id','=',self.id),('active','=',True)]
        existing_ids = self.env['res.partner.approval.master.line'].sudo().search(domain)
        if existing_ids:
            raise ValidationError("Once the approval code is used, it cannot be deleted.")
        return super().unlink()

    def write(self,vals):
        if vals.get('y_code'):
            domain = [('y_approval_code_id','=',self.id),('active','=',True)]
            existing_ids = self.env['res.partner.approval.master.line'].sudo().search(domain)
            if existing_ids:
                raise ValidationError("Once the approval code is used, it cannot be modified.")
        return super().write(vals)


class ResPartnerApprovalMaster(models.Model):
    _name = 'res.partner.approval.master'
    _description = "Partner Approval"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']
    _rec_name = 'y_name'

    def get_parent_company(self):
        company_id = self.env.company
        if self.env.company.sudo().parent_id:
            company_id = self.env.company.sudo().parent_id
        return company_id

    active = fields.Boolean(default=True)
    y_parent_company_id = fields.Many2one(related="y_company_id.parent_id")
    y_name = fields.Char("Name")    
    y_res_partner_approval_lines_ids = fields.One2many("res.partner.approval.master.line","y_partner_approval_id",string="Approval Lines")
    y_company_id = fields.Many2one('res.company',string="Company",index=1,domain="[('parent_id','=',False)]",default=get_parent_company)
    
    @api.constrains('active','y_company_id')
    def _check_duplicate(self):
        domain = [('y_company_id','=',self.y_company_id.id),('active','=',True)]
        existing_id=self.env['res.partner.approval.master'].sudo().search(domain)
        if len(existing_id) > 1:
            raise UserError (_("Oops, looks like we've got a duplicate record!"))

    def write(self,vals):
        new_dist = []
        if vals.get('y_res_partner_approval_lines_ids'):
            new_list = []
            for list1 in vals.get('y_res_partner_approval_lines_ids'):
                if list1[-1] != False:
                    new_list.append(list1)
                    approval_lvlamt_line_ids = self.y_res_partner_approval_lines_ids.filtered(lambda x:x.id in [value[1] for value in new_list])
                    new_dist = []
                    for dicts in approval_lvlamt_line_ids:
                        for newval in new_list:
                            if not isinstance(newval[-1],int):
                                if newval[1] == dicts.id:
                                    if newval[-1].get('y_approval_for'):
                                        new_approval_level = get_selection_label(self,'res.partner.approval.master.line','y_approval_for',newval[-1].get('y_approval_for'))
                                        old_approval_level = get_selection_label(self,'res.partner.approval.master.line','y_approval_for',dicts.y_approval_for)
                                        new_dist.append('{}{} ---> {}'.format("Approval Level : ",old_approval_level,new_approval_level))
                                    if newval[-1].get('y_approval_code_id'):
                                        new_product_id = self.env['user.approval.code'].sudo().search([('id','=',newval[-1].get('y_approval_code_id'))])
                                        new_dist.append('{}{}--->{}'.format("Code :",dicts.y_approval_code_id.y_code,new_product_id.y_code))

            if new_dist:
                msg = ', '.join(dic for dic in new_dist)
                if self.env.user:
                    self.message_post(body=msg)                
        
        return super(ResPartnerApprovalMaster,self).write(vals)

class ResPartnerApprovalMasterLine(models.Model):
    _name = "res.partner.approval.master.line"
    _description = "Partner Approval Line"

    def _group_internal_users(self):
        group = self.env.ref('base.group_user', raise_if_not_found=False)
        return [('groups_id', 'in', group.ids)] if group else []

    active = fields.Boolean(default=True)
    y_partner_approval_id = fields.Many2one("res.partner.approval.master")
    y_approval_for = fields.Selection(selection=[
            ('customer', 'Customer'),
            ('vendor', 'Vendor'),
            ],string='Approval For',copy=False)
    y_approval_code_id = fields.Many2one("user.approval.code",string="Code",domain="[('y_model_ids.model','=','res.partner')]")

    @api.constrains('y_approval_for','y_approval_code_id')
    def _check_duplicate(self):
        for line in self:
            duplicates = line.y_partner_approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == line.y_approval_for)
            if len(duplicates) > 1:
                approval_level = get_selection_label(self,'res.partner.approval.master','y_approval_for',line.y_approval_for)
                raise UserError("{} Already Exists".format(approval_level))
            


class ResPartnerApprovalWizard(models.Model):
    _name = 'res.partner.approval.wizard'
    _description = "Request Approval"

    y_is_customer = fields.Boolean(string="Customer")
    y_is_vendor = fields.Boolean(string="Vendor")
    y_is_both = fields.Boolean(string="Both")
    y_partner_id = fields.Many2one('res.partner')
    y_company_id = fields.Many2one('res.company',string="Company",domain="[('parent_id','=',False)]")

    y_approval_for = fields.Selection([('customer','Customer'),('vendor','Vendor'),('both','Both')],string="Approval For")

    @api.onchange('y_is_both','y_is_vendor','y_is_customer')
    def _onchange_customer_vendor(self):
        for wizard in self:
            if wizard.y_is_both:
                wizard.y_is_customer = False
                wizard.y_is_vendor = False
            else:
                wizard.y_is_both = False

    @api.constrains('y_is_customer','y_is_vendor','y_is_both','y_partner_id','y_company_id')
    def _check_approval(self):
        for wizard in self:
            if wizard.y_is_customer or wizard.y_is_vendor or wizard.y_is_both:
                approval_id = wizard.env['res.partner.approval.master'].sudo().search([('y_company_id','=',self.y_company_id.id),('active','=',True)])
                if not approval_id:
                    return ValidationError("Approval Not Configured.")
                if wizard.y_is_both:
                    approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'customer')
                    if not approval_line_id:
                        raise ValidationError("Customer Approval Not Configured")
                
                    approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'vendor')
                    if not approval_line_id:
                        raise ValidationError("Vendor Approval Not Configured")

                elif wizard.y_is_customer:
                    approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'customer')
                    if not approval_line_id:
                        raise ValidationError("Customer Approval Not Configured")
                else:
                    approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'vendor')
                    if not approval_line_id:
                        raise ValidationError("Vendor Approval Not Configured")
            else:
                raise UserError("Choose option to process")

    def action_create_activity(self,partner,line,contact_type):        
        subject = 'Customer Approval Request' if contact_type == 'customer' else 'Vendor Approval Request'
        # Activity for Customer First Approval   
        res_model = self.env['ir.model'].sudo().search([('model','=',partner._name)])
        company_ids = self.y_company_id + self.y_company_id.sudo().parent_id
        user_ids = self.env['res.users'].sudo().search([('y_user_code_ids','=',line.y_approval_code_id.id),('company_id','in',company_ids.ids)])
        for user in user_ids:
            body = f'The "{self.env.user.name}" has requested approval for the {contact_type} "{partner.name}"'
            vals={
                'res_model_id':res_model.id,
                'res_model':partner._name,
                'res_id':partner.id,
                'activity_type_id':line.y_approval_code_id.y_activity_type_id.id,
                'user_id':user.id,
                'date_deadline':date.today(),
                'summary': subject,
                'note': html2plaintext(body)                            
            }
            activity = self.env['mail.activity'].sudo().create(vals)
        # Activity END




    def action_get_approval(self):
        for wizard in self:
            company_id = wizard.y_company_id
            if wizard.y_company_id.sudo().parent_id:
                company_id = wizard.y_company_id.sudo().parent_id
            if self.y_partner_id.with_company(company_id).y_customer and self.y_partner_id.with_company(company_id).y_vendor:
                raise ValidationError("Customer/Vendor Already Approved.")            
            if self.y_partner_id.with_company(company_id).y_customer and self.y_is_customer:
                raise ValidationError("Customer Already Approved.")
            if self.y_partner_id.with_company(company_id).y_vendor and self.y_is_vendor:
                raise ValidationError("Vendor Already Approved.")
                
            if self.y_partner_id.with_company(company_id).y_to_approve_states == 'cus_ven_approval':
                raise ValidationError("Customer/Vendor Approvals Inprogress.")
            if self.y_partner_id.with_company(company_id).y_to_approve_states == 'vendor_approval' and self.y_is_vendor:
                raise ValidationError("Vendor Approvals Inprogress.")
            if self.y_partner_id.with_company(company_id).y_to_approve_states == 'customer_approval' and self.y_is_customer:
                raise ValidationError("Customer Approvals Inprogress.")
                
            if wizard.y_is_customer or wizard.y_is_vendor or wizard.y_is_both:
                approval_id = wizard.env['res.partner.approval.master'].sudo().search([('y_company_id','=',self.y_company_id.id),('active','=',True)])
                if not approval_id:
                    raise ValidationError("Approval Not Configured.")
                if wizard.y_is_both:
                    customer_approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'customer')
                    if not customer_approval_line_id:
                        raise ValidationError("Customer Approval Not Configured")

                    vendor_approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'vendor')
                    if not vendor_approval_line_id:
                        raise ValidationError("Vendor Approval Not Configured")

                    wizard.y_partner_id.with_company(company_id).write({'y_to_approve_states':'cus_ven_approval',
                                               'y_res_partner_approval_ids':[(0,0,{'y_approval_for':customer_approval_line_id.y_approval_for,
                                                                                   'y_approval_code_id':customer_approval_line_id.y_approval_code_id.id,
                                                                                   'y_company_id':company_id.id,
                                                                                   }),
                                                                             (0,0,{'y_approval_for':vendor_approval_line_id.y_approval_for,
                                                                                   'y_approval_code_id':vendor_approval_line_id.y_approval_code_id.id,
                                                                                   'y_company_id':company_id.id,
                                                                                   })
                                                                            ]})


                    self.action_create_activity(self.y_partner_id,customer_approval_line_id,'customer')
                    self.action_create_activity(self.y_partner_id,vendor_approval_line_id,'vendor')
                    
    
                elif wizard.y_is_customer:
                    approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'customer')
                    if not approval_line_id:
                        raise ValidationError("Customer Approval Not Configured")
                    approval_for = 'customer_approval'
                    customer_approval_line_id = wizard.y_partner_id.y_res_partner_approval_ids.filtered(lambda x:x.y_approval_for == 'customer' and x.y_approval_status == 'approval_pending')
                    if customer_approval_line_id:
                        approval_for = 'cus_ven_approval'

                    wizard.y_partner_id.with_company(company_id).write({'y_to_approve_states':approval_for,
                                               'y_res_partner_approval_ids':[(0,0,{'y_approval_for':approval_line_id.y_approval_for,
                                               'y_approval_code_id':approval_line_id.y_approval_code_id.id,
                                               'y_company_id':company_id.id,
                                               })]})

                    self.action_create_activity(self.y_partner_id,approval_line_id,'customer')
                else:
                    approval_line_id = approval_id.y_res_partner_approval_lines_ids.filtered(lambda x:x.y_approval_for == 'vendor')
                    if not approval_line_id:
                        raise ValidationError("Vendor Approval Not Configured")
                    approval_for = 'vendor_approval'
                    vendor_approval_line_id = wizard.y_partner_id.y_res_partner_approval_ids.filtered(lambda x:x.y_approval_for == 'vendor' and x.y_approval_status == 'approval_pending')
                    if vendor_approval_line_id:
                        approval_for = 'cus_ven_approval'

                    wizard.y_partner_id.with_company(company_id).write({'y_to_approve_states':approval_for,
                                               'y_res_partner_approval_ids':[(0,0,{'y_approval_for':approval_line_id.y_approval_for,
                                               'y_approval_code_id':approval_line_id.y_approval_code_id.id,
                                               'y_company_id':company_id.id,
                                               })]})
                    self.action_create_activity(self.y_partner_id,approval_line_id,'vendor')
                
            else:
                raise UserError("Choose option to process")

class PartnerRemarks(models.TransientModel):
    _name = 'partner.approval.remarks'
    _description = 'Partner Approval Remarks'

    y_remarks = fields.Char( string='Remaks', required=True)
    y_partner_id = fields.Many2one('res.partner',string="Partner")
    y_partner_approval_id = fields.Many2one('res.partner.approval')
    
    def reject_order(self):
        user = self.env.user
        for line in self:
            company_id = line.y_partner_approval_id.y_company_id
            if line.y_partner_approval_id.y_company_id.sudo().parent_id:
                company_id = line.y_partner_approval_id.y_company_id.sudo().parent_id
            if line.y_partner_approval_id.y_is_approval_completed == False:
                if line.y_partner_approval_id.y_approval_code_id.id in user.y_user_code_ids.ids:
                    line.y_partner_approval_id.write({'y_approval_status':'rejected',
                                                      'y_approved_date':datetime.now(),
                                                      'y_remarks':self.y_remarks})

                    vendor_approval_line_id = line.y_partner_id.y_res_partner_approval_ids.filtered(lambda x:x.y_approval_for == 'vendor' and x.y_approval_status == 'approval_pending')
                    if vendor_approval_line_id:
                        line.y_partner_id.with_company(company_id).write({'y_to_approve_states':'vendor_approval'})
                    else:
                        line.y_partner_id.with_company(company_id).write({'y_to_approve_states':False})

                    customer_approval_line_id = line.y_partner_id.y_res_partner_approval_ids.filtered(lambda x:x.y_approval_for == 'customer' and x.y_approval_status == 'approval_pending')
                    if customer_approval_line_id:
                        line.y_partner_id.with_company(company_id).write({'y_to_approve_states':'customer_approval'})
                    
                    if not vendor_approval_line_id and not customer_approval_line_id:
                        line.y_partner_id.with_company(company_id).write({'y_to_approve_states':False})
                
                    line.y_partner_id.message_post(body=_("Reject Reason :%s ")% (self.y_remarks))
                else:
                    raise UserError (_("You can't reject the order"))

class PartnerApprovalRevoke(models.TransientModel):
    _name = 'partner.approval.revoke'
    _description = 'Partner Approval Reject'

    y_remarks = fields.Char( string='Remaks', required=True)
    y_partner_id = fields.Many2one('res.partner',string="Partner")
    y_partner_approval_id = fields.Many2one('res.partner.approval')
    
    def revoke_order(self):
        user = self.env.user
        for line in self:
            company_id = line.y_partner_approval_id.y_company_id
            if line.y_partner_approval_id.y_company_id.sudo().parent_id:
                company_id = line.y_partner_approval_id.y_company_id.sudo().parent_id
            if line.y_partner_approval_id.y_approval_status == 'approved':
                line.y_partner_approval_id.write({'y_approval_status':'revoked',
                                                  'y_approved_date':datetime.now(),
                                                  'y_remarks':self.y_remarks})
                line.y_partner_id.message_post(body=_("Revoke Reason :%s ")% (self.y_remarks))
                if line.y_partner_approval_id.y_approval_for == 'customer':
                    line.y_partner_id.with_company(company_id).write({'y_customer':False})
                    for child in line.y_partner_id.child_ids:
                        child.sudo().with_company(company_id).write({'y_customer':False})
                    

                if line.y_partner_approval_id.y_approval_for == 'vendor':
                    line.y_partner_id.with_company(company_id).write({'y_vendor':False})
                    for child in line.y_partner_id.child_ids:
                        child.sudo().with_company(company_id).write({'y_vendor':False})
                    

                
class ResPartnerAppovel(models.Model):
    _name = 'res.partner.approval'
    _description = "Partner Approval Line"

    y_partner_id = fields.Many2one("res.partner")
    y_approval_for = fields.Selection(selection=[
            ('customer', 'Customer'),
            ('vendor', 'Vendor'),
            ],string='Approval For',copy=False)
    y_approval_code_id = fields.Many2one("user.approval.code",string="Code")
    y_is_approval_completed = fields.Boolean(default=False,string="IS Approval Completed")
    y_approval_status = fields.Selection([('approval_pending','Approval Pending'),('approved','Approved'),('rejected','Rejected'),('revoked','Revoked')],default="approval_pending",string="Approval Status")
    y_approved_date = fields.Datetime("Approved Date")
    y_remarks = fields.Char(string="Remarks")
    y_approver_id = fields.Many2one('res.users',string="Approved By")
    y_is_revoked = fields.Boolean(string="Is Revoked")
    y_company_id = fields.Many2one('res.company',string="Company")

    def view_code_users(self):
        context = dict(self.env.context)
        context.update({'create':False,'edit':False})
        tree_view_id = self.env.ref('user_approval_code.res_users_view_approval_code_tree').id
        return {
                'name': "Users",
                'res_model': 'res.users',
                'type': 'ir.actions.act_window',
                'view_mode': 'list',
                'target': 'new',
                'view_id': self.env.ref("user_approval_code.res_users_view_approval_code_tree").id,
                'views': [[tree_view_id, 'list']],
                'context':context,
                'domain': [('y_user_code_ids', '=', self.y_approval_code_id.id)],  
            }

    def button_partner_approve(self):
        user = self.env.user
        for line in self:
            company_id = self.y_company_id
            if self.y_company_id.sudo().parent_id:
                company_id = self.y_company_id.sudo().parent_id
            if line.y_is_approval_completed == False:
                if line.y_approval_code_id.id in user.y_user_code_ids.ids:
                    line.write({'y_approval_status':'approved',
                                        'y_approved_date':datetime.now(),
                                        'y_is_approval_completed': True,
                                        'y_approver_id':user.id,
                                        })
                    if line.y_approval_for == 'customer':
                        line.y_partner_id.with_company(company_id).approve_customer()
                        for child in line.y_partner_id.child_ids:
                            child.sudo().with_company(company_id).write({'y_customer':line.y_partner_id.sudo().with_company(company_id).y_customer})
                    
                        vendor_approval_line_id = line.y_partner_id.y_res_partner_approval_ids.filtered(lambda x:x.y_approval_for == 'vendor' and x.y_approval_status == 'approval_pending')
                        if vendor_approval_line_id:
                            line.y_partner_id.with_company(company_id).write({'y_to_approve_states':'vendor_approval'})
                        else:
                            line.y_partner_id.with_company(company_id).write({'y_to_approve_states':False})

                        activity_ids = line.y_partner_id.activity_ids.filtered(lambda x:x.state != 'done' and x.summary == 'Customer Approval Request')
                        user_activity_ids = activity_ids.filtered(lambda x:x.user_id == user)
                        non_user_activity_ids = activity_ids.filtered(lambda x:x.user_id != user)
                        user_activity_ids.action_done()
                        non_user_activity_ids.action_cancel()
                        

                    elif line.y_approval_for == 'vendor':
                        line.y_partner_id.with_company(company_id).approve_vendor()
                        for child in line.y_partner_id.child_ids:
                            child.sudo().with_company(company_id).write({'y_vendor':line.y_partner_id.sudo().with_company(company_id).y_vendor})
                    
                        customer_approval_line_id = line.y_partner_id.y_res_partner_approval_ids.filtered(lambda x:x.y_approval_for == 'customer' and x.y_approval_status == 'approval_pending')
                        if customer_approval_line_id:
                            line.y_partner_id.with_company(company_id).write({'y_to_approve_states':'customer_approval'})
                        else:
                            line.y_partner_id.with_company(company_id).write({'y_to_approve_states':False})

                        activity_ids = line.y_partner_id.activity_ids.filtered(lambda x:x.state != 'done' and x.summary == 'Vendor Approval Request')
                        user_activity_ids = activity_ids.filtered(lambda x:x.user_id == user)
                        non_user_activity_ids = activity_ids.filtered(lambda x:x.user_id != user)
                        user_activity_ids.action_done()
                        non_user_activity_ids.action_cancel()


                            
                else:
                    raise UserError (_("Oops!!!! You can't approve"))

        # data = self.y_partner_id.y_res_partner_approval_ids.mapped('y_is_approval_completed')  
        # if all(data) == True:
        #     self.y_partner_id.with_company(company_id).write({'y_to_approve_states':False})

    def button_partner_reject(self):
        action = self.env["ir.actions.actions"]._for_xml_id("contact_base.action_partner_approval_remarks")
        action['views'] = [(self.env.ref('contact_base.partner_approval_remarks_form').id,'form')]
        action['context'] = {'default_y_partner_approval_id':self.id,'default_y_partner_id':self.y_partner_id.id}
        return action 

    def button_revoke(self):
        user = self.env.user
        for line in self:
            if self.env.user.has_group('contact_base.approve_contacts_revoke_approval'):
                action = self.env["ir.actions.actions"]._for_xml_id("contact_base.action_partner_approval_revoke_remarks")
                action['views'] = [(self.env.ref('contact_base.partner_approval_revoke_remarks_form').id,'form')]
                action['context'] = {'default_y_partner_approval_id':self.id,'default_y_partner_id':self.y_partner_id.id}
                return action
            else:
                raise ValidationError("Oops!!!! You can't revoke")
   
class ResPartner(models.Model):
    _inherit = 'res.partner'

    y_res_partner_approval_ids = fields.One2many('res.partner.approval','y_partner_id',string="Partner Approval")
    y_to_approve_states = fields.Selection([('customer_approval','Customer Approval Pending'),
                                            ('vendor_approval','Vendor Approval Pending'),
                                            ('cus_ven_approval','Cust/Ven Approval Pending')],string="Approval Status",company_dependent=True)

    def button_partner_request_approval(self):
        return {
                'name': ("Request Approval For"),
                'type': 'ir.actions.act_window',
                'res_model': 'res.partner.approval.wizard',
                'view_mode': 'form',
                'views': [(self.env.ref('contact_base.view_partner_request_approval_wizard_form').id, 'form')],
                'target': 'new',
                'context': dict(self._context, 
                                create=False,
                                edit=False,
                                default_y_partner_id = self.id)
                }
