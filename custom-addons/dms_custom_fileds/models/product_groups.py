# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError


class ItemGroup(models.Model):
    _name = "item.group"
    _description = "Item Group"
    _rec_name = 'y_name'
    # _sql_constraints = [('code_unique', 'unique(code)', 'code already exists!')]

    y_name = fields.Char(string="Name")
    y_code = fields.Char(string="Code")
    y_company_id = fields.Many2one('res.company',string="Company",default=lambda self: self.env.company.id, index=1)
    active = fields.Boolean(default=True)

    @api.constrains('y_code','company_id')
    def check_item_group_code(self):
        for rec in self:
            docs=rec.env['item.group'].search([('y_code','=',rec.y_code),('y_company_id','=',rec.y_company_id.id)])
            if len(docs) > 1:
                raise ValidationError(_("""code already exists!"""))



class ProductGroup1(models.Model):
    _name = "product.group.1"
    _description = "Product Group 1"
    _rec_name = 'y_name'
    # _sql_constraints = [('code_unique', 'unique(code)', 'code already exists!')]

    y_name = fields.Char(string="Name")
    y_code = fields.Char(string="Code")
    y_product_category_id = fields.Many2one('product.category',string="Product Category")
    y_company_id = fields.Many2one('res.company',string="Company",default=lambda self: self.env.company.id, index=1)
    active = fields.Boolean(default=True)

    @api.constrains('y_code','y_company_id')
    def check_item_group_code(self):
        for rec in self:
            docs=rec.env['product.group.1'].search([('y_code','=',rec.y_code),('y_company_id','=',rec.y_company_id.id)])
            if len(docs) > 1:
                raise ValidationError(_("""code already exists!"""))

class ProductTemplate(models.Model):
    _inherit = "product.template"

    y_item_group = fields.Many2one('item.group', ondelete='restrict',string="Item Group")
    y_product_group_1 = fields.Many2one('product.group.1', domain="[('y_product_category_id', '=', categ_id)]", ondelete='restrict',string="Product Group 1")

class ProductProduct(models.Model):
    _inherit = "product.product"

    y_item_group = fields.Many2one(related='product_tmpl_id.y_item_group', store=True,string="Item Group")
    y_product_group_1 = fields.Many2one(related='product_tmpl_id.y_product_group_1',store=True,string="Product Group 1")