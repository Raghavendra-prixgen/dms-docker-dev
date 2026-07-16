from random import choice
from string import digits
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo import models, fields, api, exceptions, _, SUPERUSER_ID
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from datetime import datetime
import time
from datetime import datetime
from datetime import timedelta
from datetime import time as datetime_time
from dateutil import relativedelta
import logging
import requests
from xmlrpc import client as xmlrpclib
import xmlrpc.client
import base64
import random
from random import choice
import string
import json
import uuid

    

class DraftPartner(models.Model):
    _name = "draft.partner"

    _inherit = ['image.mixin','mail.thread', 'mail.activity.mixin']


    sequence = fields.Char(string="Sequence", default="New")
    name = fields.Char(string="Name")
    street = fields.Char(string="Street")
    street2 = fields.Char(string="Street2")
    city = fields.Char(string="City")
    state_id = fields.Many2one('res.country.state')
    country_id = fields.Many2one('res.country')
    zip = fields.Char()

    mobile = fields.Char(string="Phone Number")
    
    partner_id = fields.Many2one('res.partner',string="Partner Id")
    # current_user = fields.Many2one('draft.partner','Current User', default=lambda self: self.env.id) 
    
     
    active = fields.Boolean(string='active', default=True)
    
    
    
    @api.constrains('mobile')
    def _check_duplicate_draft_partner_mobile(self):
        moves = self.filtered(lambda move: move.mobile)
        if not moves:
            return
        self.env["draft.partner"].flush_model([ "mobile",])
        
        self._cr.execute('''
            SELECT move2.id
            FROM draft_partner move
            INNER JOIN draft_partner move2 ON
                move2.mobile = move.mobile
                AND move2.id != move.id
            WHERE move.id IN %s
        ''', [tuple(moves.ids)])
        duplicated_moves = self.browse([r[0] for r in self._cr.fetchall()])
        if duplicated_moves:
            raise ValidationError(_('Draft Parter Is Exist For This Mobile Number'))



class Resusers(models.Model):
    _inherit = "res.users"

    def _is_public(self):
        if self.env.user:
            self.ensure_one()
            return self.has_group('base.group_public')
        else:
            return False

class ProductCategory(models.Model):
    _inherit = "product.category"

    category_primary_key = fields.Char()



class ProductTemplate(models.Model):
    _inherit = "product.template"

    user_name = fields.Char('User Name',compute="_compute_name")
    server_url = fields.Char('Server URL',compute="_compute_url")
    server_db = fields.Char('Database',compute="_compute_database")
    server_password = fields.Char('Password',compute="_compute_password")
    category_primary_key = fields.Char()
    community_product_template = fields.Integer()
    is_enterprise_community = fields.Boolean()
    company_names = fields.Char()
    company_ids = fields.Many2many('res.company',string="Companies")

    # ===== Tally sync fields =====
    tally_sync_status = fields.Selection([
        ('not_synced', 'Not Synced'),
        ('synced', 'Synced'),
        ('failed', 'Failed'),
        ('partial', 'Partially Synced')
    ], string='Tally Sync Status', default='not_synced', copy=False)
    
    tally_sync_date = fields.Datetime('Last Tally Sync', readonly=True, copy=False)
    tally_sync_error = fields.Text('Tally Sync Error', readonly=True, copy=False)
    tally_company_ids = fields.Many2many(
        'res.company',
        'product_template_tally_company_rel',
        'product_id',
        'company_id',
        string='Synced to Companies',
        help='Companies where this product has been synced to Tally'
    )

    tally_product_name = fields.Char('Tally Product Name', copy=False, help='Product name in Tally')
    tally_guid = fields.Char('Tally GUID', copy=False, help='Unique identifier in Tally')
    is_in_tally = fields.Boolean('Exists in Tally', compute='_compute_is_in_tally', store=True)
    
    @api.depends('tally_sync_status', 'tally_company_ids')
    def _compute_is_in_tally(self):
        for product in self:
            product.is_in_tally = product.tally_sync_status == 'synced' and product.tally_company_ids


    @api.model
    def create(self, vals):
        if vals.get('is_enterprise_community'):
            product_category_obj = self.env['product.category'].search([('category_primary_key','=',vals.get('category_primary_key'))])
            vals['categ_id'] = product_category_obj.id
            company_ids = []
            for company_primary_keys in vals.get('company_names'):
                company_obj = self.env['res.company'].search([('company_primary_key','=',company_primary_keys)], limit=1)
                if company_obj: 
                    company_ids.append(company_obj[0].id) 
            
            if company_ids:
                vals['company_ids'] = [(6, 0, company_ids)]
            
        return super().create(vals)

    @api.model
    def create(self, vals):
        _logger.info("ProductTemplate create vals: %s", vals)

        if vals.get('is_enterprise_community'):
            if vals.get('category_primary_key'):
                product_category_obj = self.env['product.category'].search([
                    ('category_primary_key', '=', vals['category_primary_key'])
                ], limit=1)
                if product_category_obj:
                    vals['categ_id'] = product_category_obj.id

            company_ids = []
            for company_primary_key in vals.get('company_names', []):
                if not company_primary_key:  
                    continue
                company_obj = self.env['res.company'].search([
                    ('company_primary_key', '=', company_primary_key)
                ], limit=1)
                if company_obj:
                    company_ids.append(company_obj.id)

            if company_ids:
                vals['company_ids'] = [(6, 0, company_ids)]

        return super(ProductTemplate, self).create(vals)




    def _compute_url(self):
        for l in self:
            res = self.env['res.company'].search([])
            for u in res:
                l.server_url = u.server_url

    def _compute_database(self):
        for l in self:
            res = self.env['res.company'].search([])
            for d in res:
                l.server_db = d.server_db

    def _compute_name(self):
        for l in self:
            res = self.env['res.company'].search([])
            for n in res:
                l.user_name = n.user_name

    def _compute_password(self):
        for l in self:
            res = self.env['res.company'].search([])
            for r in res:
                l.server_password = r.server_password

    def create_product(self):
        for product in self:
            if product.server_url:
                return {
                    'name': _('Publish Distributor'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'publish.distributor.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {'active_id': product.id},
                }

    # ===== Tally integration methods =====
    def action_push_to_tally_single(self):
        """Button action for single product template - opens wizard"""
        return self._open_tally_push_wizard()
    
    def action_push_to_tally_bulk(self):
        """Button action for multiple product templates - opens wizard"""
        return self._open_tally_push_wizard()
    
    def _open_tally_push_wizard(self):
        """Open wizard to select companies"""
        return {
            'name': _('Push to Tally'),
            'type': 'ir.actions.act_window',
            'res_model': 'tally.push.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_tmpl_ids': self.ids,
            }
        }

    
    # In product.template model

def call_tally_push_api(self, company_ids=None, update_existing=True):
    """Enhanced with update_existing parameter"""
    base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
    api_endpoint = f"{base_url}/web/api/push_product_to_tally"
    
    user_company = self.env.company
    api_token = user_company.api_token
    
    if not api_token:
        raise UserError(_('API Token not configured'))
    
    payload = {
        "jsonrpc": "2.0",
        "params": {
            "api_token": api_token,
            "product_tmpl_ids": self.ids,
            "update_existing": update_existing
        }
    }
    
    if company_ids:
        payload["params"]["company_ids"] = company_ids
    else:
        payload["params"]["company_ids"] = "all"
    
    try:
        response = requests.post(api_endpoint, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get('result', {}).get('success'):
            return result['result']
        else:
            raise UserError(_(result.get('result', {}).get('message', 'Unknown error')))
    except Exception as e:
        raise UserError(_(f'Error: {str(e)}'))
        
    def action_push_new_products_to_tally(self):
        """Push products created within a date range"""
        return {
            'name': _('Push Products by Date'),
            'type': 'ir.actions.act_window',
            'res_model': 'tally.push.date.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_tmpl_ids': self.ids if self else [],
            }
        }          


class Respartner(models.Model):
    _inherit = 'res.partner'

    customer_primary_key = fields.Char()
    draft_partner_id = fields.Many2one('draft.partner',string="Draft Partner")
    y_is_distributor = fields.Boolean(string="Is Distributor")
    
class StockLocation(models.Model):
    _inherit = "stock.location"

    stock_quant_location = fields.Boolean()


class DuplicateSlaeOrder(models.Model):
    _name = "duplicate.sale.order"
    _inherit = [ 'mail.thread', 'mail.activity.mixin']


    user_name = fields.Char('User Name',compute="_compute_name")
    server_url = fields.Char('Server URL',compute="_compute_url")
    server_db = fields.Char('Database',compute="_compute_database")
    server_password = fields.Char('Password',compute="_compute_password")

    name = fields.Char()
    company_id = fields.Many2one('res.company')
    quotation_date = fields.Date()
    deliver_to = fields.Char()
    address = fields.Char()
    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all', tracking=5)
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all', tracking=4)


    delivery_state = fields.Selection([
            ('shipped', 'Shipped'),
            ('pending', 'Not Delivered'),
            ('partial', 'Partially Delivered'),
            ('full', 'Fully Delivered')], string='Delivery Status',tracking=True, copy=False)

    # delivery_state = fields.Selection([
    #     ('pending', 'Not Delivered'),
    #     ('partial', 'Partially Delivered'),
    #     ('full', 'Fully Delivered'),
    # ], string='Delivery Status3', copy=False,store=True)

    
    currency_id = fields.Many2one('res.currency',string="Currency")
    partner_shipping_id = fields.Many2one(
        'res.partner', string='Delivery Address',
       
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",)
    duplicate_sale_order_line_ids = fields.One2many('duplicate.sale.order.line','duplicate_sale_order_id')

    sale_order_no = fields.Integer(string="Sale Order Ref",copy=False)

    def action_type(self):
        if self.server_url:
            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))

            uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
            models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
            order_lines = []
            old_revision = []

            for l in self.duplicate_sale_order_line_ids:
                order_details = {
                    'product_id': 1,
                    'primary_item_code_key':l.product_id.default_code,
                    'is_community_enterprise':True,

                    'product_uom_qty':l.product_uom_qty,
                    'price_unit':l.price_unit,
                }
                order_lines.append((0, 0,order_details))
            value = models.execute_kw(self.server_db, uid, self.server_password, 'sale.order', 'create', [
                {
                'partner_id': self.company_id.id,
                'partner_primary_key':self.company_id.company_primary_key,
                # 'pricelist_id':self.pricelist_id.id,
                'duplicate_sale_entry_id':self.id,
                'client_order_ref':self.name,
                'order_line':order_lines,
                'is_community_enterprise':True
                }])
            if value:
                self.sale_order_no = value


    def prepare_stockquant(self,line,record):
        return {
        'location_id':2,
        'product_id':line.product_id.id,
        'inventory_quantity':record
        }


    def update_quantity(self):
        if self.server_url:
            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
            uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
            models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
            order_lines = []
            old_revision = []
            for line in self.duplicate_sale_order_line_ids:
                ids = models.execute_kw(self.server_db, uid, self.server_password, 'sale.order.line', 'search', [[['default_code', '=', line.product_id.default_code],['order_id','=',line.duplicate_sale_order_id.sale_order_no]]])
                
                record = models.execute_kw(self.server_db, uid, self.server_password, 'sale.order.line', 'read', [ids])

                stock_move_record =  models.execute_kw(self.server_db, uid, self.server_password, 'stock.move', 'read', [record[0].get('move_ids')])
                for stock_move in stock_move_record:
                    if stock_move.get('is_quantity_updated') == False and stock_move.get('state')=='done':

                        stock_quant_location_obj = self.env['stock.location'].with_context(inventory_mode=True).search([('stock_quant_location','=',True)])
                        if not stock_quant_location_obj:
                            raise UserError(_('Please select quant location!'))
                        #need to create stock quant

                        stock_quant_obj_new = self.env['stock.quant'].with_context(inventory_mode=True).search([('product_id.default_code','=',line.product_id.default_code),('location_id','=',stock_quant_location_obj.id)])
                        if not stock_quant_obj_new:
                            stock_quant_obj_new = self.env['stock.quant'].with_context(inventory_mode=True).create({'product_id':line.product_id.id,
                                                                                                            'location_id':stock_quant_location_obj.id,
                                                                                                            'inventory_quantity': 0,
                                                                                                            'lot_id':False,
                                                                                                            'package_id':False,
                                                                                                            'owner_id':False})
                        stock_quant_obj_new.with_context(inventory_mode=True).write({'inventory_quantity':stock_quant_obj_new.inventory_quantity + stock_move.get('quantity')})
                        value = models.execute_kw(self.server_db, uid, self.server_password, 'stock.move', 'write', [[stock_move.get('id')], {'is_quantity_updated': True}])

    def create_vendor_bills(self):
        if self.server_url:
            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
            uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
            models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
            invoice_line_ids = []

            value = models.execute_kw(self.server_db, uid, self.server_password, 'account.move', 'search_read', [[['duplicate_sale_entry_id', '=', self.id]]], {'fields': ['name', 'partner_id', 'invoice_date','invoice_line_ids']})

            if value:
                for line in value[0].get('invoice_line_ids'):
                    line_value = models.execute_kw(self.server_db, uid, self.server_password, 'account.move.line', 'search_read', [[['id', '=', line]]], {'fields': ['product_id', 'name'
                    ,'quantity','price_unit']})
                    product_name = line_value[0].get('product_id')[1]
                    item_code = product_name[product_name.index('[')+len('['):product_name.index(']')]
                    product_obj = self.env['product.product'].search([('default_code','=',item_code)])
                    invoice_line_ids = {
                    'product_id': product_obj.id,
                    'product_uom_qty':line_value[0].get('quantity'),
                    'price_unit':line_value[0].get('price_unit'),
                    }
                    invoice_line_ids.append((0, 0,invoice_line_ids))

                account_move = self.env['account.move'].create({'partner_id':23,
                                                                'invoice_line_ids':invoice_line_ids
                                                                })
            




    @api.depends('duplicate_sale_order_line_ids.price_total')
    def _amount_all(self):
        
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.duplicate_sale_order_line_ids:
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
            order.update({
                'amount_untaxed': amount_untaxed,
                'amount_tax': amount_tax,
                'amount_total': amount_untaxed + amount_tax,
            })

    def _compute_url(self):
        for l in self:
            res = self.env['res.company'].search([])
            for u in res:
                l.server_url = u.server_url

    def _compute_database(self):
        for l in self:
            res = self.env['res.company'].search([])
            for d in res:
                l.server_db = d.server_db

    def _compute_name(self):
        for l in self:
            res = self.env['res.company'].search([])
            for n in res:
                l.user_name = n.user_name

    def _compute_password(self):
        for l in self:
            res = self.env['res.company'].search([])
            for r in res:
                l.server_password = r.server_password


class JournalIds(models.Model):
    _inherit = "account.journal"

    # Store codes in a JSON field or create separate records per company
    tally_codes_json = fields.Text(string="Tally Codes JSON", copy=False)
    journal_tally_id = fields.Char(
        string="Journal Id",
        compute="_compute_journal_tally_id",
        inverse="_inverse_journal_tally_id",
        store=False
    )

    def _compute_journal_tally_id(self):
        for rec in self:
            codes_dict = eval(rec.tally_codes_json or '{}')
            company_id = self.env.company.id
            rec.journal_tally_id = codes_dict.get(str(company_id), False)

    def _inverse_journal_tally_id(self):
        for rec in self:
            codes_dict = eval(rec.tally_codes_json or '{}')
            company_id = str(self.env.company.id)
            codes_dict[company_id] = rec.journal_tally_id
            rec.tally_codes_json = str(codes_dict)

    def action_generate_code(self):
        current_company_id = self.env.company.id
        
        for rec in self:
            codes_dict = eval(rec.tally_codes_json or '{}')
            
            if str(current_company_id) in codes_dict:
                continue
            
            for _ in range(1000):
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                
                conflict = False
                for journal in self.env['account.journal'].search([]):
                    journal_codes = eval(journal.tally_codes_json or '{}')
                    if journal_codes.get(str(current_company_id)) == code:
                        conflict = True
                        break
                
                if not conflict:
                    codes_dict[str(current_company_id)] = code
                    rec.tally_codes_json = str(codes_dict)
                    break

class DuplicateSlaeOrderLine(models.Model):
    _name = "duplicate.sale.order.line"

    product_id = fields.Many2one('product.product',string="Product")         
    product_uom_qty = fields.Float(string="Quantity",default="1.0")
    product_uom = fields.Many2one('uom.uom',string="UOM")
    price_unit = fields.Float(string="Unit Price")
    tax_id = fields.Many2many('account.tax',string="Taxes")
    price_subtotal = fields.Float(string="Subtotal",compute="compute_price_subtotal")
    price_total = fields.Float(string="total",compute="compute_price_subtotal")
    price_tax = fields.Float(compute='compute_price_subtotal', string='Total Tax', readonly=True, store=True)

    duplicate_sale_order_id = fields.Many2one('duplicate.sale.order')


    @api.depends('product_uom_qty', 'price_unit', 'tax_id')
    def compute_price_subtotal(self):
        for line in self:
            price = line.price_unit 
            taxes = line.tax_id.compute_all(price, line.duplicate_sale_order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.duplicate_sale_order_id.partner_shipping_id)
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })



    @api.onchange('product_id')
    def flow_cost_taxes(self):
        for rec in self:
            if rec.product_id:
                rec.price_unit = rec.product_id.lst_price
                rec.tax_id = rec.product_id.taxes_id.ids


    # @api.depends('price_unit', 'product_uom_qty')
    # def compute_price_subtotal(self):
    #     for line in self:
    #         line.price_subtotal = line.price_unit * line.product_uom_qty


class ServerSide(models.Model):
    _inherit = 'sale.order'

    user_name = fields.Char('User Name',compute="_compute_name")
    server_url = fields.Char('Server URL',compute="_compute_url")
    server_db = fields.Char('Database',compute="_compute_database")
    server_password = fields.Char('Password',compute="_compute_password")
    untaxed_amount = fields.Char('Untaxed Amount')
    tax_amount = fields.Char('Taxes')
    total_amount = fields.Char('Total')
    integration_id = fields.Boolean('Integration')

    is_community_enterprise = fields.Boolean(copy=False,store=True,default=False)
    partner_primary_key = fields.Char()
    duplicate_sale_entry_id = fields.Integer()

    delivery_status = fields.Selection([
        ('pending', 'Not Delivered'),
        ('partial', 'Partially Delivered'),
        ('full', 'Fully Delivered'),
    ], string='Delivery Status1', compute='_compute_delivery_status', copy=False,store=True)
    delivery_state = fields.Selection([
        ('pending', 'Not Delivered'),
        ('partial', 'Partially Delivered'),
        ('full', 'Fully Delivered'),
    ], string='Delivery Status3', copy=False,store=True)


    def _prepare_invoice(self):
        res = super()._prepare_invoice()
        res['sale_id'] = self.id
        res['duplicate_sale_entry_id'] = self.duplicate_sale_entry_id
        return res


    #update delivery state to DMS
    def write(self,vals):
        if vals.get('delivery_state') and vals.get('delivery_state') != 'pending':
            if self.server_url:
                common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
                uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
                models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
                order_lines = []
                old_revision = []

                value = models.execute_kw(self.server_db, uid, self.server_password, 'purchase.order', 'write', [[self.duplicate_sale_entry_id], {'sale_delivery_state': vals.get('delivery_state')}])

        return super().write(vals)


    @api.depends('picking_ids', 'picking_ids.state')
    def _compute_delivery_status(self):
        for order in self:
            if not order.picking_ids or all(p.state == 'cancel' for p in order.picking_ids):
                order.delivery_status = False
            elif all(p.state in ['done', 'cancel'] for p in order.picking_ids):
                order.delivery_status = 'full'
                order.delivery_state = 'full'

            elif any(p.state == 'done' for p in order.picking_ids):
                order.delivery_status = 'partial'
                order.delivery_state = 'partial'

            else:
                order.delivery_status = 'pending'
                order.delivery_state = 'pending'

    def _auto_confirm_community_receipt(self, purchase_order_id):
        print("33333333333333333333333333333333333333333333333333",self.server_url)
        """Auto-confirm receipt in Community Odoo when delivery is completed"""
        try:
            if self.server_url:
                common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
                uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
                models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
                
                # Call the accept_receipt method on the purchase order in Community
                result = models.execute_kw(
                    self.server_db, uid, self.server_password,
                    'purchase.order', 'accept_reciept',
                    [[purchase_order_id]]
                )
                
               
                
        except Exception as e:
            _logger.error(f"Failed to auto-confirm receipt for PO{purchase_order_id}: {str(e)}")            


    @api.model
    def create(self,vals):
        if vals.get('is_community_enterprise'):
            partner_obj = self.env['res.partner'].search([('customer_primary_key','=',vals.get('partner_primary_key'))])
            vals['partner_id'] = partner_obj.id
            vals['partner_shipping_id'] = partner_obj.id
            vals['partner_invoice_id'] = partner_obj.id
        return super().create(vals)


    def action_confirm(self):
        res = super().action_confirm()
        if self.server_url:
            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
            uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
            models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
            order_lines = []
            old_revision = []


            value = models.execute_kw(self.server_db, uid, self.server_password, 'purchase.order', 'write', [[self.duplicate_sale_entry_id], {'sale_delivery_state': 'shipped'}])
        return res



    def action_type(self):
        pass

    def _compute_url(self):
        for l in self:
            res = self.env['res.company'].search([])
            for u in res:
                l.server_url = u.server_url

    def _compute_database(self):
        for l in self:
            res = self.env['res.company'].search([])
            for d in res:
                l.server_db = d.server_db

    def _compute_name(self):
        for l in self:
            res = self.env['res.company'].search([])
            for n in res:
                l.user_name = n.user_name

    def _compute_password(self):
        for l in self:
            res = self.env['res.company'].search([])
            for r in res:
                l.server_password = r.server_password

class SaleorderLine(models.Model):
    _inherit = "sale.order.line"

    primary_item_code_key = fields.Char()
    is_community_enterprise = fields.Boolean(copy=False,store=True,default=False)
    default_code = fields.Char(related="product_id.default_code")
    duplicate_sale_line_entry_id = fields.Integer()


    @api.model
    def create(self,vals):
        if vals.get('is_community_enterprise'):
            product_obj = self.env['product.product'].search([('default_code','=',vals.get('primary_item_code_key'))])
            vals['product_id'] = product_obj.id
        return super().create(vals)


class ResCompany(models.Model):
    _inherit = "res.company"

    server_db = fields.Char('Server Database')
    server_url = fields.Char('Server URL')
    user_name = fields.Char('User Name')
    server_password = fields.Char('Password')
    company_primary_key = fields.Char()
    company_code = fields.Char()
    api_token = fields.Char()
    tally_url = fields.Char('Tally Server URL')

    _sql_constraints = [
        ('api_token_unique', 'unique(api_token)', 'API Token must be unique for each company!')
    ]

    def action_generate_code(self):
        """Generate a unique API token using UUID"""
        for company in self:
            # Generate a unique 16-character token from UUID
            unique_token = uuid.uuid4().hex[:16].upper()
            company.api_token = unique_token
        
        return True

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"


    default_code = fields.Char()
    tax_list_ids = fields.Char()
    is_community_enterprise = fields.Boolean(copy=False,store=True,default=False)
    cash_discount = fields.Float(string="Cash Discount(%)",compute="calculate_cash_discount")
    tally_amount = fields.Float(string="Tally Amount")
    tally_product_name = fields.Char('Tally Product Name', copy=False, help='Product name from Tally')
    tally_product_code = fields.Char('Tally Product Code', copy=False, help='Product code from Tally')
    tally_invoice_number = fields.Char(related='move_id.tally_invoice_number',string='Tally Invoice Number',store=True,readonly=True)

    
    @api.depends('tally_amount','price_subtotal')
    def calculate_cash_discount(self):
        for rec in self:
            if rec.price_subtotal:
                rec.cash_discount = ((rec.price_subtotal - rec.tally_amount)*100)/rec.price_subtotal
            else:
                rec.cash_discount = 0


    # @api.model_create_multi
    # def create(self,vals_list):
    #     for vals in vals_list:
    #         if vals.get('is_community_enterprise'):
    #             # tax_ids = []
                
    #             # if vals.get('tax_list_ids'):
    #             #     tax_vals = vals.get('tax_list_ids').split(',')
    #             #     for tax in tax_vals:
    #             #         tax_obj = self.env['account.tax'].search([('name','=',tax)])
    #             #         tax_ids.append(tax_obj.id)

    #             # vals['tax_ids'] = tax_ids
    #             product_obj = self.env['product.product'].search([('default_code','=',vals.get('default_code'))])
    #             vals['product_id'] = product_obj.id
    #     res = super().create(vals_list)
    #     return res

class TallySyncLog(models.Model):
    _name = 'tally.sync.log'
    _description = 'Tally Invoice Sync Log'
    _order = 'create_date desc'

    tally_invoice_number = fields.Char(string='Tally Invoice No')
    tally_master_id = fields.Char(string='Tally Master ID')
    company_id = fields.Many2one('res.company', string='Company')
    invoice_id = fields.Many2one('account.move', string='Odoo Invoice')
    line_product_name = fields.Char(string='Product Name from Tally')
    tally_default_code = fields.Char(string='Code Sent by Tally')
    odoo_default_code = fields.Char(string='Code in Odoo')
    mismatch = fields.Boolean(string='Name Mismatch?', default=False)
    missing_code = fields.Boolean(string='Code Missing?', default=False)
    status = fields.Selection([
        ('ok', 'OK'),
        ('missing', 'Missing Code'),
        ('mismatch', 'Name Mismatch'),
        ('not_found', 'Product Not Found'),
    ], string='Status', default='ok')
    notes = fields.Text(string='Notes')


class AccountMove(models.Model):
    _inherit = "account.move"

    sale_id = fields.Many2one('sale.order')
    duplicate_sale_entry_id = fields.Integer()
    company_code = fields.Char()
    tally_invoice_number = fields.Char(string="Tally Invoice Number")
    is_community_enterprise = fields.Boolean(copy=False,store=True,default=False)
    tally_master_id = fields.Char(string="Tally Master Id")
    tally_taxable_amount = fields.Float(string="Tally Taxable Amount")
    tally_tax_amount = fields.Float(string="Tally Tax Amount")
    special_disc_on_sales = fields.Float(string="Spl Disc on Sales %",compute="calculate_special_discount")
    company_primary_key = fields.Char('Company Primary Key',copy=False)
    vch_primary_key = fields.Char('Voucher Primary Key',copy=False)
    distributor_name = fields.Char('Distributor Name',copy=False)

    _sql_constraints = [
        (
            'unique_tally_invoice_company',
            'unique(tally_invoice_number, company_id)',
            'Tally Invoice Number must be unique per company!'
        ),
        (
            'unique_vch_primary_key',
            'unique(vch_primary_key, company_id)',
            'VCH Primary Key must be unique per company!'
        ),
    ]

    @api.depends('invoice_line_ids','amount_tax_signed')
    def calculate_special_discount(self):
        for rec in self:
            if rec.invoice_line_ids:
                TotalTallyAmnt = sum(rec.invoice_line_ids.mapped('tally_amount'))
                if TotalTallyAmnt != 0:
                    rec.special_disc_on_sales = ((TotalTallyAmnt - rec.tally_taxable_amount)*100)/TotalTallyAmnt
                    
                else:
                    rec.special_disc_on_sales = 0
            else:
                rec.special_disc_on_sales = 0




    @api.model
    def create(self,vals):
        if vals.get('is_community_enterprise'):
            company_obj = self.env['res.company'].search([('company_primary_key','=',vals.get('company_primary_key'))],limit=1)
            vals['company_id'] = company_obj.id
            if vals.get('vat'):
                partner_obj = self.env['res.partner'].search([('vat','=',vals.get('vat')),('company_id','=',company_obj.id)],limit=1)
                if partner_obj:
                    vals['partner_id'] = partner_obj.id
                else:
                    state_obj = self.env['res.country.state'].search([('name','=',vals.get('state_id'))],limit=1)   
                    county_obj = self.env['res.country'].search([('name','=',vals.get('country_id'))],limit=1)
                    partner_obj = self.env['res.partner'].create({
                        'name':vals.get('customer_name'),
                        'state_id':state_obj.id,
                        'country_id':county_obj.id,
                        'street':vals.get('street'),
                        'street2':vals.get('street2'),
                        'zip':vals.get('zip'),
                        'y_customer':True,
                        'l10n_in_gst_treatment':'consumer',
                        'vat':vals.get('vat'),
                        'company_id':company_obj.id,
                        'is_company':True,
                        'customer_rank':1,
                        'company_type':'company',
                        'type':'contact',
                        # 'property_stock_customer':1,
                        # 'property_stock_supplier':1,
                        # 'property_stock_subcontractor':19,
                        # 'active':True,
                        # 'reminder_date_before_receipt':1,
                        # 'property_account_receivable_id':1894,
                        # 'property_account_payable_id':1862

                        })
                    vals['partner_id'] = partner_obj.id

            else:
                state_obj = self.env['res.country.state'].search([('name','=',vals.get('state_id'))],limit=1)
                county_obj = self.env['res.country'].search([('name','=',vals.get('country_id'))],limit=1)
                partner_obj = self.env['res.partner'].create({
                    'name':vals.get('customer_name'),
                    'state_id':state_obj.id,
                    'country_id':county_obj.id,
                    'street':vals.get('street'),
                    'street2':vals.get('street2'),
                    'zip':vals.get('zip'),
                    'y_customer':True,
                    'l10n_in_gst_treatment':'unregistered',

                    'is_company':True,
                    'customer_rank':1,
                    'company_type':'company',
                    'type':'contact',
                    # 'property_stock_customer':1,
                    # 'property_stock_supplier':1,
                    # 'property_stock_subcontractor':19,
                    # 'active':True,
                    # 'reminder_date_before_receipt':1,
                    # 'property_account_receivable_id':1894,
                    # 'property_account_payable_id':1862

                    })
                vals['partner_id'] = partner_obj.id
            # invoice_line_ids = []
            # if vals.get('invoice_line_ids'):
            #     for invoice_line_ids in vals.get('invoice_line_ids'):
            #         if invoice_line_ids[2].get('tax_list_ids'):
            # del vals['customer_primary_key']
            del vals['vat']
            del vals['street']
            del vals['street2']
            del vals['zip']
            del vals['customer_name']
            del vals['state_id']
            del vals['country_id']


            del vals['company_primary_key']

        return super().create(vals)




class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    user_name = fields.Char('User Name',compute="_compute_name")
    server_url = fields.Char('Server URL',compute="_compute_url")
    server_db = fields.Char('Database',compute="_compute_database")
    server_password = fields.Char('Password',compute="_compute_password")
    sale_order_no = fields.Integer(string="Sale Order Ref",copy=False)
    sale_delivery_state = fields.Selection([
            ('shipped', 'Shipped'),
            ('pending', 'Not Delivered'),
            ('partial', 'Partially Delivered'),
            ('full', 'Fully Delivered')], string='Delivery Status',tracking=True, copy=False)

    def accept_reciept(self):
        for rec in self:
            if self.server_url:
                common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
                uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
                models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
                
                # Get delivery data from Enterprise
                delivery_data = self._get_enterprise_deliveries(models, uid)
                
                if delivery_data:
                    # Process deliveries using existing receipt and standard backorder process
                    self._process_deliveries_standard(delivery_data)

    def _get_enterprise_deliveries(self, models, uid):
        """Get delivery data from Enterprise for all PO lines"""
        delivery_moves = []
        
        for line in self.order_line:
            # Find corresponding sale order line in Enterprise
            sale_line_ids = models.execute_kw(
                self.server_db, uid, self.server_password, 
                'sale.order.line', 'search', 
                [[['duplicate_sale_line_entry_id', '=', line.id]]]
            )
            
            if not sale_line_ids:
                continue
                
            # Get sale order line details
            sale_line_record = models.execute_kw(
                self.server_db, uid, self.server_password, 
                'sale.order.line', 'read', 
                [sale_line_ids, ['move_ids']]
            )
            
            if not sale_line_record or not sale_line_record[0].get('move_ids'):
                continue
            
            # Get stock moves for this sale line
            stock_moves = models.execute_kw(
                self.server_db, uid, self.server_password, 
                'stock.move', 'read', 
                [sale_line_record[0].get('move_ids'), [
                    'state', 'quantity', 'product_uom_qty', 
                    'is_quantity_updated', 'picking_id', 'create_date'
                ]]
            )
            
            # Collect delivered quantities for this PO line
            total_delivered = 0.0
            move_ids_to_mark = []
            
            for stock_move in stock_moves:
                if (stock_move.get('state') == 'done' and 
                    not stock_move.get('is_quantity_updated')):
                    total_delivered += stock_move.get('quantity', 0.0)
                    move_ids_to_mark.append(stock_move.get('id'))
            
            if total_delivered > 0:
                delivery_moves.append({
                    'po_line': line,
                    'delivered_qty': total_delivered,
                    'enterprise_move_ids': move_ids_to_mark
                })
        
        return delivery_moves

    def _process_deliveries_standard(self, delivery_moves):
        """Process deliveries using existing receipts and standard Odoo backorder process"""
        
        # Get the first available receipt (created when PO was confirmed)
        available_receipt = self._get_first_available_receipt()
        
        if not available_receipt:
            # If no receipt exists, create one (shouldn't happen normally)
            available_receipt = self._create_initial_receipt()
        
        # Update receipt with delivered quantities
        self._update_receipt_with_deliveries(available_receipt, delivery_moves)
        
        # Validate the receipt - this will automatically create backorders if needed
        self._validate_receipt_standard(available_receipt, delivery_moves)

    def _get_first_available_receipt(self):
        """Get the first receipt that's ready for processing"""
        available_receipts = self.picking_ids.filtered(
            lambda p: p.state in ['draft', 'waiting', 'confirmed', 'assigned', 'partially_available'] and 
            p.picking_type_id.code == 'incoming'
        )
        
        # Return the earliest receipt
        return available_receipts.sorted('create_date')[0] if available_receipts else None

    def _create_initial_receipt(self):
        """Create initial receipt if none exists"""
        picking_vals = {
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'location_id': self.picking_type_id.default_location_src_id.id,
            'location_dest_id': self.picking_type_id.default_location_dest_id.id,
            'purchase_id': self.id,
        }
        
        receipt = self.env['stock.picking'].create(picking_vals)
        
        # Create stock moves for each PO line
        for line in self.order_line:
            if line.product_qty > 0:
                move_vals = {
                    'name': line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_qty,
                    'product_uom': line.product_uom.id,
                    'location_id': receipt.location_id.id,
                    'location_dest_id': receipt.location_dest_id.id,
                    'picking_id': receipt.id,
                    'purchase_line_id': line.id,
                    'state': 'draft',
                }
                self.env['stock.move'].create(move_vals)
        
        return receipt

    def _update_receipt_with_deliveries(self, receipt, delivery_moves):
        """Update receipt moves with delivered quantities"""
        
        # Ensure receipt is in correct state
        if receipt.state == 'draft':
            receipt.action_confirm()
        if receipt.state in ['waiting', 'confirmed']:
            receipt.action_assign()
        
        # Don't delete existing move lines - update them instead
        # receipt.move_line_ids.unlink()  # Remove this line
        
        # Update each move with delivered quantity
        for move in receipt.move_ids_without_package:
            delivered_qty = 0.0
            
            # Find delivered quantity for this move's PO line
            for delivery_data in delivery_moves:
                if delivery_data['po_line'] == move.purchase_line_id:
                    delivered_qty = delivery_data['delivered_qty']
                    break
            
            # Limit delivered quantity to ordered quantity
            actual_delivered = min(delivered_qty, move.product_uom_qty)
            
            # Update existing move lines or create new ones
            existing_move_lines = move.move_line_ids
            if existing_move_lines:
                # Update the first move line with delivered quantity
                existing_move_lines[0].write({
                    'quantity': actual_delivered,
                    'picked': actual_delivered > 0,
                })
                # Remove extra move lines if any
                if len(existing_move_lines) > 1:
                    existing_move_lines[1:].unlink()
            else:
                # Create new move line if none exists
                if actual_delivered > 0:
                    self.env['stock.move.line'].create({
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'quantity': actual_delivered,
                        'picked': True,
                    })
    def _validate_receipt_standard(self, receipt, delivery_moves):
        """Validate receipt using standard Odoo process"""
        try:
            # Check if this is a partial delivery
            has_partial_delivery = False
            for move in receipt.move_ids_without_package:
                delivered_qty = sum(move.move_line_ids.mapped('quantity'))
                if 0 < delivered_qty < move.product_uom_qty:
                    has_partial_delivery = True
                    break
            
            # Validate the receipt
            if has_partial_delivery:
                # For partial deliveries, use button_validate which will trigger backorder creation
                res = receipt.button_validate()
                
                # If Odoo returns a wizard for backorder confirmation, process it
                if isinstance(res, dict) and res.get('res_model') == 'stock.backorder.confirmation':
                    # Auto-confirm backorder creation
                    wizard = self.env[res['res_model']].browse(res['res_id'])
                    wizard.process()
            else:
                # For complete deliveries, direct validation
                receipt.button_validate()
            
            # Mark Enterprise moves as synced
            self._mark_enterprise_moves_synced(delivery_moves)
            
            # Note: qty_received is automatically updated by Odoo during move validation
            # No need to manually update PO line delivered quantities
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error validating receipt {receipt.name}: {str(e)}")
            # Try manual validation as fallback
            self._manual_validate_receipt(receipt, delivery_moves)

    def _manual_validate_receipt(self, receipt, delivery_moves):
        """Manual validation fallback"""
        try:
            # Process each move individually
            for move in receipt.move_ids_without_package:
                delivered_qty = sum(move.move_line_ids.mapped('quantity'))
                
                if delivered_qty > 0:
                    # Mark move as done with delivered quantity
                    move.write({
                        'quantity': delivered_qty,
                        'state': 'done'
                    })
                else:
                    # Cancel move if nothing delivered
                    move.write({'state': 'cancel'})
            
            # Update receipt state
            if any(move.state == 'done' for move in receipt.move_ids_without_package):
                receipt.write({
                    'state': 'done',
                    'date_done': fields.Datetime.now()
                })
                
                # Create backorder for remaining quantities if needed
                self._create_backorder_if_needed(receipt)
            else:
                receipt.write({'state': 'cancel'})
                
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Manual validation failed for receipt {receipt.name}: {str(e)}")

    def _create_backorder_if_needed(self, original_receipt):
        """Create backorder for remaining quantities following standard process"""
        
        backorder_moves = []
        
        for move in original_receipt.move_ids_without_package:
            delivered_qty = move.quantity if move.state == 'done' else 0
            remaining_qty = move.product_uom_qty - delivered_qty
            
            if remaining_qty > 0:
                backorder_moves.append({
                    'po_line': move.purchase_line_id,
                    'product_id': move.product_id.id,
                    'remaining_qty': remaining_qty,
                    'product_uom': move.product_uom.id,
                })
        
        if backorder_moves:
            # Create backorder receipt
            backorder_vals = {
                'picking_type_id': original_receipt.picking_type_id.id,
                'partner_id': original_receipt.partner_id.id,
                'origin': f"{original_receipt.origin} (Backorder)",
                'location_id': original_receipt.location_id.id,
                'location_dest_id': original_receipt.location_dest_id.id,
                'purchase_id': self.id,
                'backorder_id': original_receipt.id,
            }
            
            backorder = self.env['stock.picking'].create(backorder_vals)
            
            # Create moves for backorder
            for move_data in backorder_moves:
                move_vals = {
                    'name': move_data['po_line'].product_id.display_name,
                    'product_id': move_data['product_id'],
                    'product_uom_qty': move_data['remaining_qty'],
                    'product_uom': move_data['product_uom'],
                    'location_id': backorder.location_id.id,
                    'location_dest_id': backorder.location_dest_id.id,
                    'picking_id': backorder.id,
                    'purchase_line_id': move_data['po_line'].id,
                    'state': 'draft',
                }
                self.env['stock.move'].create(move_vals)
            
            # Confirm backorder
            backorder.action_confirm()

    def _mark_enterprise_moves_synced(self, delivery_moves):
        """Mark Enterprise stock moves as synced"""
        if not self.server_url:
            return
            
        try:
            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
            uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
            models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
            
            # Mark all enterprise moves as synced
            for delivery_data in delivery_moves:
                if delivery_data.get('enterprise_move_ids'):
                    models.execute_kw(
                        self.server_db, uid, self.server_password,
                        'stock.move', 'write',
                        [delivery_data['enterprise_move_ids'], {'is_quantity_updated': True}]
                    )
                    
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Could not mark Enterprise moves as synced: {str(e)}")

    def _update_po_line_delivered_qty(self, delivery_moves):
        """Update purchase order line delivered quantities - Remove this method call"""
        pass

    def accept_bill(self):
        for rec in self:
            rec.action_create_invoice()
            for invoice in rec.invoice_ids:
                invoice.write({'invoice_date':fields.Date.today()})
                invoice.action_post()

    def _compute_url(self):
        for l in self:
            res = self.env['res.company'].search([])
            for u in res:
                l.server_url = u.server_url

    def _compute_database(self):
        for l in self:
            res = self.env['res.company'].search([])
            for d in res:
                l.server_db = d.server_db

    def _compute_name(self):
        for l in self:
            res = self.env['res.company'].search([])
            for n in res:
                l.user_name = n.user_name

    def _compute_password(self):
        for l in self:
            res = self.env['res.company'].search([])
            for r in res:
                l.server_password = r.server_password

    def action_type(self):
        print("Starting synchronization...")
        if self.server_url:
            print("Connecting to Enterprise server...")
            common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.server_url))
            print("Connection established:", common)
            uid = common.authenticate(self.server_db, self.user_name, self.server_password, {})
            models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.server_url))
            order_lines = []

            for l in self.order_line:
                order_details = {
                    'product_id': 1,
                    'name':l.product_id.name,
                    'primary_item_code_key':l.product_id.default_code,
                    'is_community_enterprise':True,
                    'duplicate_sale_line_entry_id':l.id,
                    'product_uom_qty':l.product_uom_qty,
                    'price_unit':l.price_unit,
                }
                order_lines.append((0, 0,order_details))
            
            value = models.execute_kw(self.server_db, uid, self.server_password, 'sale.order', 'create', [
                {
                'partner_id': self.company_id.id,
                'partner_primary_key':self.company_id.company_primary_key,
                'duplicate_sale_entry_id':self.id,
                'client_order_ref':self.name,
                'order_line':order_lines,
                'is_community_enterprise':True
                }])
            if value:
                self.sale_order_no = value
                print(f"Sale order created in Enterprise with ID: {value}")


class StockPicking(models.Model):
    _inherit = "stock.picking"
    
    enterprise_picking_ref = fields.Char(
        'Enterprise Picking Reference',
        help="Reference to the corresponding picking in Enterprise system"
    )


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    sale_delivered_qty = fields.Float(
        'Delivered Quantity',
        help="Quantity delivered from Enterprise sale order"
    )

    
    






