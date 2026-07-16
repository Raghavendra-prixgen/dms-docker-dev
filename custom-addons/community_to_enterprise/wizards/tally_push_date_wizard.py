from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta

class TallyPushDateWizard(models.TransientModel):
    _name = 'tally.push.date.wizard'
    _description = 'Push Products to Tally by Date'
    
    push_type = fields.Selection([
        ('by_date', 'Products Created Between Dates'),
        ('today', 'Products Created Today'),
        ('last_7_days', 'Products Created in Last 7 Days'),
        ('last_30_days', 'Products Created in Last 30 Days'),
        ('not_synced', 'All Not Synced Products'),
        ('failed', 'All Failed Products')
    ], string='Push Type', default='not_synced', required=True)
    
    date_from = fields.Date('From Date')
    date_to = fields.Date('To Date', default=fields.Date.today)
    
    company_ids = fields.Many2many(
        'res.company',
        string='Target Companies',
        domain=[('tally_url', '!=', False)]
    )
    
    push_mode = fields.Selection([
        ('all', 'All Companies with Tally'),
        ('selected', 'Selected Companies Only'),
        ('current', 'Current Company Only')
    ], string='Company Mode', default='current', required=True)
    
    update_existing = fields.Boolean(
        'Update Existing Products in Tally',
        default=True,
        help='If checked, will update products that already exist in Tally'
    )
    
    product_count = fields.Integer('Products to Push', compute='_compute_product_count')
    
    @api.depends('push_type', 'date_from', 'date_to')
    def _compute_product_count(self):
        for wizard in self:
            domain = wizard._get_product_domain()
            wizard.product_count = self.env['product.template'].search_count(domain)
    
    @api.onchange('push_type')
    def _onchange_push_type(self):
        """Set date range based on push type"""
        if self.push_type == 'today':
            self.date_from = fields.Date.today()
            self.date_to = fields.Date.today()
        elif self.push_type == 'last_7_days':
            self.date_from = fields.Date.today() - timedelta(days=7)
            self.date_to = fields.Date.today()
        elif self.push_type == 'last_30_days':
            self.date_from = fields.Date.today() - timedelta(days=30)
            self.date_to = fields.Date.today()
        elif self.push_type in ['not_synced', 'failed']:
            self.date_from = False
            self.date_to = False
    
    def _get_product_domain(self):
        """Build domain based on wizard settings"""
        domain = []
        
        if self.push_type == 'by_date':
            if self.date_from:
                domain.append(('create_date', '>=', self.date_from))
            if self.date_to:
                domain.append(('create_date', '<=', self.date_to))
        elif self.push_type in ['today', 'last_7_days', 'last_30_days']:
            domain.append(('create_date', '>=', self.date_from))
            domain.append(('create_date', '<=', self.date_to))
        elif self.push_type == 'not_synced':
            domain.append(('tally_sync_status', '=', 'not_synced'))
        elif self.push_type == 'failed':
            domain.append(('tally_sync_status', '=', 'failed'))
        
        return domain
    
    def action_push_to_tally(self):
        """Execute the push to Tally"""
        self.ensure_one()
        
        # Get products based on criteria
        domain = self._get_product_domain()
        products = self.env['product.template'].search(domain)
        
        if not products:
            raise UserError(_('No products found matching the criteria.'))
        
        # Determine companies
        if self.push_mode == 'all':
            company_ids = None
        elif self.push_mode == 'current':
            company_ids = [self.env.company.id]
        else:
            if not self.company_ids:
                raise UserError(_('Please select at least one company.'))
            company_ids = self.company_ids.ids
        
        # Call API
        try:
            result = products.call_tally_push_api(
                company_ids=company_ids,
                update_existing=self.update_existing
            )
            return self._show_results(result)
        except Exception as e:
            raise UserError(_(f'Failed to push to Tally: {str(e)}'))
    
    def _show_results(self, result):
        """Show results"""
        summary = result.get('summary', {})
        
        message = f"""
        <h4>Tally Push Completed</h4>
        <ul>
            <li>Total Products: {summary.get('total_products', 0)}</li>
            <li>✅ Successful: {summary.get('successful', 0)}</li>
            <li>🔄 Updated: {summary.get('updated', 0)}</li>
            <li>❌ Failed: {summary.get('failed', 0)}</li>
        </ul>
        """
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tally Push Results'),
                'message': message,
                'type': 'success' if summary.get('failed', 0) == 0 else 'warning',
                'sticky': True,
            }
        }