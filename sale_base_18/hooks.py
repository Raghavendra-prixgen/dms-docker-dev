from odoo import models, fields, api, SUPERUSER_ID
import itertools

def sale_uninstall_hook(env):
    action = env.ref('sale.action_quotations_with_onboarding')
    if action:
        action.write({'domain': False})

    action_orders = env.ref('sale.action_orders')
    if action_orders:
        action_orders.write({'domain':[('state', 'not in', ('draft', 'sent', 'cancel'))]})

    