from odoo import api, fields, models, _
from odoo.exceptions import ValidationError,UserError

class ResUser(models.Model):
    _inherit = 'res.users'
    
    y_user_code_ids = fields.Many2many('user.approval.code',string="Approval Code")

class UserCodes(models.Model):
    _name = "user.approval.code"
    _description = "User Code"
    _rec_name = 'y_code'
    
    active = fields.Boolean(default=True,readonly=True)
    y_code = fields.Char(string='Code',required=True)
    y_description = fields.Char(string="Description")
    y_model_ids = fields.Many2many('ir.model',string="Group")
    y_activity_type_id = fields.Many2one('mail.activity.type',string="Activity Type")

    @api.constrains('y_code','active')
    def _check_duplicate(self):
        for rec in self:
            domain = [('y_code','=',rec.y_code)]
            existing_ids = self.env['user.approval.code'].search(domain)
            if len(existing_ids) > 1:
                raise UserError (_("Oops, looks like we've got a duplicate record!"))

    