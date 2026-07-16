import uuid

from odoo import api, fields, models, _
from odoo.fields import Date
from odoo.exceptions import ValidationError

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


class PublishDistributorWizard(models.TransientModel):
    _name = 'publish.distributor.wizard'

    distributor_ids = fields.Many2many('res.partner',string="Distributor",domain="[('y_is_distributor', '=', True)]")
    

    def publish_record(self):
        product_obj = self.env['product.template'].browse(self._context.get('active_id')).exists()
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(product_obj.server_url))
        uid = common.authenticate(product_obj.server_db, product_obj.user_name, product_obj.server_password, {})
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(product_obj.server_url))
        
        value = models.execute_kw(product_obj.server_db, uid, product_obj.server_password, 'product.template', 'create', [
            {
            'name': product_obj.name,
            'categ_id':1,
            'category_primary_key':product_obj.categ_id.category_primary_key,
            'company_names':self.distributor_ids.mapped('customer_primary_key'),
            'is_enterprise_community':True,
            'default_code':product_obj.default_code
            }])
        if value:
            product_obj.community_product_template = value
            
            
