#-*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    parent_contact_id = fields.Many2one('res.partner',compute="_compute_paretn_contact",store=True,compute_sudo=True)

    @api.depends('partner_id','partner_id.parent_id')
    def _compute_paretn_contact(self):
        for move in self:
            move.parent_contact_id = move.partner_id.id
            if move.partner_id.parent_id:
                move.parent_contact_id = move.partner_id.parent_id.id