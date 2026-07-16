from odoo import models, fields, api, SUPERUSER_ID
import itertools

def test_uninstall_hook(env):
    # env = api.Environment(env, SUPERUSER_ID, {})
    
    action = env.ref('contacts.action_contacts')
    if action:
        action.write({'domain': False})

    supplier_action = env.ref('account.res_partner_action_supplier')
    if supplier_action:
        supplier_action.write({'domain':False})

    customer_action = env.ref('account.res_partner_action_customer')
    if customer_action:
        customer_action.write({'domain':False})


    partner_action = env.ref('base.action_partner_form')
    if partner_action:
        partner_action.write({'domain':False})
