# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError

class ResPartner(models.Model):
    _inherit = "account.move"

    delivery_address = fields.Char(string="Delivery Address")

class PartnerState(models.Model):
    _inherit = 'res.country.state'
    
    state_primary_key = fields.Char('State Primary Key')
    

class PartnerDistrict(models.Model):
    _name = "partner.district"

    name = fields.Char()
    dist_primary_key = fields.Char('Primary Key')
    y_state_id = fields.Many2one('res.country.state',string='State')
    state_primary_key_id = fields.Char('State Primary key',related="y_state_id.state_primary_key")
    

class PartnerTaluk(models.Model):
    _name = "partner.taluk"

    name = fields.Char()
    taluk_primary_key = fields.Char(string="Primary Key")
    district_id = fields.Many2one('partner.district',string='District')
    y_state_id = fields.Many2one('res.country.state',string='State')
    state_primary_key = fields.Char('State Primary key',related="y_state_id.state_primary_key")
    district_primary_key = fields.Char('District Primary key',related="district_id.dist_primary_key")
    

class ResPartner(models.Model):
    _inherit = "res.partner"

    district_id = fields.Many2one('partner.district',string="District")
    taluk_id = fields.Many2one('partner.taluk',string="Taluk")