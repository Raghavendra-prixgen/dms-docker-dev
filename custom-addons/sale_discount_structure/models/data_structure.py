# from _typeshed import Self
from odoo import fields,models,api, _
from odoo.exceptions import AccessError, UserError, ValidationError
import pdb

class datastructurez(models.Model):
    _name = 'discount.structure'
    _description = "discount.structure"
    _rec_name = 'y_price_id'

    y_item_group_id = fields.Many2one('item.group', string="Item Group")
    y_state = fields.Selection([('draft','Draft'),('confirm','Confirm'),],string="State")
    y_price_id = fields.Many2one('price.group', string = "Price Group")
    y_doc_type_id = fields.Many2one('sale.doc.type',string="Document Type")
    y_trade_discounts = fields.Float(string="Trade Discount%")
    y_qty_disc = fields.Float(string="Qty Discount%")
    y_spec_discount = fields.Float(string="Special Discount%")
    y_start_date = fields.Date(string="Start Date")
    y_end_date = fields.Date(string="End Date")



    def action_draft(self):
        self.y_state = "draft"

    def action_confirm(self):
        self.y_state = "confirm"
        
    @api.constrains('y_item_group_id')
    def _check_duplicate_boe_no(self):
        moves = self.filtered(lambda move: move.y_item_group_id)
        if not moves:
            return
        self.env["discount.structure"].flush_model([ "y_item_group_id",])
        
        self._cr.execute('''
            SELECT move2.id
            FROM discount_structure move
            INNER JOIN discount_structure move2 ON
                move2.y_item_group_id = move.y_item_group_id
                AND move2.id != move.id
            WHERE move.id IN %s
        ''', [tuple(moves.ids)])
        duplicated_moves = self.browse([r[0] for r in self._cr.fetchall()])
        if duplicated_moves:
            raise ValidationError(_('This Item Group Already Exists, Please Check'))

class supportfield(models.Model):
    _inherit = 'res.partner'
    
    y_price_group_id = fields.Many2one('price.group', string = "Price Group")
  

class pricegroup(models.Model):
    _name = "price.group"
    _description = "price.group"
    _rec_name = 'name'

    name = fields.Char(string="Price Group")

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, access_rights_uid=None):
        
        if self._context.get('filter_price_group'):
            price_group_ids = []            
            discount_structure = self.env['discount.structure'].search([])
            for data in discount_structure:
                price_group_ids.append(data.y_price_id.id)
            args += [('id', 'in', price_group_ids)]
        return super(pricegroup, self)._search(args, offset=offset, limit=limit, order=order, access_rights_uid=access_rights_uid)

    