from odoo import models, fields, api, _
from odoo.exceptions import UserError

class TallyPushWizard(models.TransientModel):
    _name = 'tally.push.wizard'
    _description = 'Push Products to Tally Wizard'
    
    product_tmpl_ids = fields.Many2many('product.template', string='Products', required=True)
    company_ids = fields.Many2many(
        'res.company',
        string='Target Companies',
        domain=[('tally_url', '!=', False)],
        help='Select which companies Tally servers to push to'
    )
    push_mode = fields.Selection([
        ('all', 'All Companies with Tally Configured'),
        ('selected', 'Selected Companies Only'),
        ('current', 'Current Company Only')
    ], string='Push Mode', default='current', required=True)
    
    product_count = fields.Integer(compute='_compute_counts', string='Products')
    company_count = fields.Integer(compute='_compute_counts', string='Companies')
    available_company_count = fields.Integer(compute='_compute_available_companies', string='Available Companies')
    
    @api.depends('product_tmpl_ids')
    def _compute_counts(self):
        for wizard in self:
            wizard.product_count = len(wizard.product_tmpl_ids)
            wizard.company_count = len(wizard.company_ids)
    
    @api.depends('push_mode')
    def _compute_available_companies(self):
        for wizard in self:
            wizard.available_company_count = self.env['res.company'].search_count([
                ('tally_url', '!=', False)
            ])
    
    @api.onchange('push_mode')
    def _onchange_push_mode(self):
        """Clear company selection when mode changes"""
        if self.push_mode != 'selected':
            self.company_ids = [(5, 0, 0)]
    
    def action_push_to_tally(self):
        """Execute the push to Tally via REST API"""
        self.ensure_one()
        
        if not self.product_tmpl_ids:
            raise UserError(_('Please select at least one product.'))
        
        # Determine which companies to push to
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
            result = self.product_tmpl_ids.call_tally_push_api(company_ids)
            return self._show_results(result)
        except Exception as e:
            raise UserError(_(f'Failed to push to Tally: {str(e)}'))
    
    def _show_results(self, result):
        """Display push results to user"""
        summary = result.get('summary', {})
        details = result.get('details', {})
        
        success_count = summary.get('successful', 0)
        failed_count = summary.get('failed', 0)
        
        # Build detailed message
        message_lines = []
        message_lines.append(f"<h4>Push to Tally Completed</h4>")
        message_lines.append(f"<p><b>Summary:</b></p>")
        message_lines.append(f"<ul>")
        message_lines.append(f"<li>Total Products: {summary.get('total_products', 0)}</li>")
        message_lines.append(f"<li>Target Companies: {summary.get('total_companies', 0)}</li>")
        message_lines.append(f"<li>✅ Successful: {success_count}</li>")
        message_lines.append(f"<li>❌ Failed: {failed_count}</li>")
        message_lines.append(f"</ul>")
        
        # Add success details
        if details.get('success'):
            message_lines.append(f"<p><b>Successfully Synced:</b></p>")
            message_lines.append(f"<ul>")
            for item in details['success'][:10]:
                message_lines.append(
                    f"<li>{item['product_name']} → {item['company_name']}</li>"
                )
            if len(details['success']) > 10:
                message_lines.append(f"<li>... and {len(details['success']) - 10} more</li>")
            message_lines.append(f"</ul>")
        
        # Add failure details
        if details.get('failed'):
            message_lines.append(f"<p><b>Failed Items:</b></p>")
            message_lines.append(f"<ul>")
            for item in details['failed'][:10]:
                message_lines.append(
                    f"<li>{item['product_name']} → {item['company_name']}: "
                    f"<span style='color: red;'>{item['error']}</span></li>"
                )
            if len(details['failed']) > 10:
                message_lines.append(f"<li>... and {len(details['failed']) - 10} more</li>")
            message_lines.append(f"</ul>")
        
        message = ''.join(message_lines)
        
        # Return a message wizard
        return {
            'name': _('Tally Push Results'),
            'type': 'ir.actions.act_window',
            'res_model': 'tally.result.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_message': message,
                'default_success_count': success_count,
                'default_failed_count': failed_count,
            }
        }


class TallyResultWizard(models.TransientModel):
    _name = 'tally.result.wizard'
    _description = 'Tally Push Results'
    
    message = fields.Html('Results', readonly=True)
    success_count = fields.Integer('Successful', readonly=True)
    failed_count = fields.Integer('Failed', readonly=True)