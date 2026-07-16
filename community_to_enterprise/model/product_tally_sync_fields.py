# -*- coding: utf-8 -*-
from odoo import models, fields, api



# Middle ware model for product


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    # Tally Sync Fields
    last_tally_sync_date = fields.Datetime(
        string='Last Tally Sync',
        readonly=True,
        help='Last time this product was synced to Tally'
    )
    
    tally_sync_status = fields.Selection([
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('failed', 'Failed')
    ], string='Tally Sync Status', 
       default='pending',
       help='Current sync status with Tally')
    
    tally_sync_message = fields.Text(
        string='Sync Message',
        readonly=True,
        help='Last sync result message'
    )
    
    def action_reset_sync_status(self):
        """Reset sync status to retry sync"""
        self.write({
            'tally_sync_status': 'pending',
            'tally_sync_message': False
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Sync status reset to pending',
                'type': 'success',
            }
        }


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Add same fields to product template for easy access
    last_tally_sync_date = fields.Datetime(
        string='Last Tally Sync',
        related='product_variant_ids.last_tally_sync_date',
        readonly=True
    )
    
    tally_sync_status = fields.Selection([
        ('pending', 'Pending'),
        ('synced', 'Synced'),
        ('failed', 'Failed')
    ], string='Tally Sync Status',
       related='product_variant_ids.tally_sync_status',
       readonly=True)