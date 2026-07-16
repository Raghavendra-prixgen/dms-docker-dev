from odoo import models, fields, api, _
from odoo.tools.float_utils import float_round, float_is_zero
from odoo import tools

from odoo import models, api
from odoo.exceptions import AccessError


class PurchaseRegisterReport(models.Model):
    _name = "purchase.register.report"
    _auto = False
    _description =  " "
    
    y_move_id = fields.Many2one('account.move',string="Bill",readonly=True)
    y_move_line_id = fields.Many2one('account.move.line',string="Bill Line",readonly=True)
    y_bill_num = fields.Char('Bill Number',readonly=True)
    y_bill_date = fields.Date(string="Bill Date",readonly=True)
    y_accounting_date = fields.Date('Accounting Date',readonly=True)
    y_invoice_ref = fields.Char(string="Vendor Reference",readonly=True)
    y_purchase_order_id = fields.Many2one('purchase.order',string="PO No",readonly=True)
    y_purchase_line_id = fields.Many2one('purchase.order.line',string="PO line",readonly=True)
    y_purchase_order_date = fields.Datetime(string="PO Date",readonly=True)
    y_grn_ref = fields.Char(string="GRN Ref",compute="get_picking_names",readonly=True)

    # Partner relate fields
    y_partner_id = fields.Many2one('res.partner', 'Partner Name',readonly=True)
    y_partner_category_id = fields.Many2one('partner.category',related="y_partner_id.y_partner_category",string="Partner Category",readonly=True)
    y_partner_state_id = fields.Many2one('res.country.state',string="Partner State",readonly=True)
    y_partner_city = fields.Char(string="Partner City",readonly=True)
    y_partner_country_id = fields.Many2one('res.country',string="Partner Country",readonly=True)
    y_gst_name = fields.Char(string="GST No",readonly=True)
    y_analytic_account_ids = fields.Many2many('account.analytic.account',compute="get_analytic_distribution",string="Analytical Account",readonly=True)
    y_journal_id = fields.Many2one('account.journal', 'Journal',readonly=True)
    y_currency_id = fields.Many2one('res.currency', string="Currency",readonly=True)
    y_boe_rate = fields.Float(string='BOE Rate',readonly=True)

    # Product Details
    y_product_id = fields.Many2one('product.product', string="Product",readonly=True)
    y_product_tmpl_id = fields.Many2one('product.template',string="Product Template",readonly=True)
    y_label = fields.Char(string="Label") # invoice_line.name
    y_account_id = fields.Many2one('account.account','Account',readonly=True)
    y_product_category_id = fields.Many2one('product.category',string="Product Category",readonly=True)
    y_uom_id = fields.Many2one('uom.uom',string="Product UoM",readonly=True)
    y_quantity = fields.Float('Billed Quantity',readonly=True) #invoice_line.quantity
    y_price_unit = fields.Float('Unit Price',readonly=True)
    y_amount_exclusive_tax = fields.Float(string="Amount Exclusive Tax",readonly=True) 
    
    y_cgst_percent = fields.Char(compute="report_compute_tax", string="CGST Rate %",readonly=True)
    y_cgst_amount = fields.Float(compute="report_compute_tax", string="CGST Amount",readonly=True)
    y_sgst_percent = fields.Char(compute="report_compute_tax", string="SGST Rate %",readonly=True)
    y_sgst_amount = fields.Float(compute="report_compute_tax", string="SGST Amount",readonly=True)
    y_igst_percent = fields.Char(compute="report_compute_tax", string="IGST Rate %",readonly=True)
    y_igst_amount = fields.Float(compute="report_compute_tax", string="IGST Amount",readonly=True)    
    y_tds_percent = fields.Char(compute="report_compute_tax", string="TDS Rate %",readonly=True)
    y_tds_amount = fields.Float(compute="report_compute_tax", string="TDS Amount",readonly=True)
    y_rcm_percent = fields.Char(string="RCM Rate %",compute="report_compute_tax",readonly=True)
    y_rcm_amount = fields.Float(string="RCM Amount",compute="report_compute_tax",readonly=True)
    y_ocean_tax_percent = fields.Char(string="Ocean Tax Rate",compute="report_compute_tax",readonly=True)
    y_ocean_tax_amount = fields.Float(string="Ocean Tax Amount",compute="report_compute_tax",readonly=True)

    y_sgstrcm_percent = fields.Char(string="SGSTRCM Rate %",compute="report_compute_tax",readonly=True)
    y_sgstrcm_amount = fields.Float(string="SGSTRCM Amount",compute="report_compute_tax",readonly=True)
    y_cgstrcm_percent = fields.Char(string="CGSTRCM Rate %",compute="report_compute_tax",readonly=True)
    y_cgstrcm_amount = fields.Float(string="CGSTRCM Amount",compute="report_compute_tax",readonly=True)
    y_igstrcm_percent = fields.Char(string="IGSTRCM Rate %",compute="report_compute_tax",readonly=True)
    y_igstrcm_amount = fields.Float(string="IGSTRCM Amount",compute="report_compute_tax",readonly=True)


    y_company_id = fields.Many2one('res.company',string="Company",readonly=True)
    y_tax_amount = fields.Float(compute="total_tax", string="Total Tax Amount",readonly=True)
    y_amount_inclusive_tax = fields.Float(string="Amount Inclusive Tax",readonly=True)
    y_move_type_name = fields.Selection([
            ('entry','Journal Entry'),
            ('out_invoice', 'Customer Invoice'),    
            ('out_refund' , 'Customer Credit Note'),
            ('in_invoice' , 'Vendor Bill'),
            ('in_refund' ,'Vendor Credit Note'),  
            ('out_receipt' ,'Sales Receipt' ),  
            ('in_receipt'  ,'Purchase Receip'),],string='Invoice Type',readonly=True)    
    y_payment_state = fields.Selection(
        selection=[
            ('not_paid', 'Not Paid'),
            ('in_payment', 'In Payment'),
            ('paid', 'Paid'),
            ('partial', 'Partially Paid'),
            ('reversed', 'Reversed'),
            ('invoicing_legacy', 'Invoicing App Legacy'),
        ],
        string="Payment State",readonly=True)
    y_product_type = fields.Selection([
        ('product', 'Storable Product'),
        ('consu', 'Consumable'),
        ('service', 'Service'), 
        ('combo','Combo')],string='Product Type',readonly=True)

    y_bill_aging = fields.Char(string="Bill Aging",readonly=True)
    y_price_subtotal = fields.Float('Subtotal',readonly=True)
    y_invoice_payment_term_id = fields.Many2one('account.payment.term',readonly=True,string="Payment Terms")
    partner_ref = fields.Char('Partner Reference')
         
    
    # Computing the taxes
    def report_compute_tax(self):
        for record in self:
            cgst_percent = 0.0
            sgst_percent = 0.0
            igst_percent = 0.0
            tds_percent = 0.0
            
            igst_amount = 0.0
            cgst_amount = 0.0
            sgst_amount = 0.0
            tds_amount = 0.0
            
            ocean_tax_percent = 0.0
            ocean_tax_amount = 0.0
            rcm_amount = 0.0
            rcm_percent = 0.0

            sgstrcm_amount = 0.0
            sgstrcm_percent = 0.0
            cgstrcm_amount = 0.0
            cgstrcm_percent = 0.0
            igstrcm_percent = 0.0
            igstrcm_amount = 0.0


            tax_dict = record.sudo().y_move_line_id._get_tax_line_group_values()
            if tax_dict:

                igst_value = tax_dict.get('IGST') or 0
                igst_percent = tax_dict.get('IGST_RATE') if igst_value > 0 else 0

                cgst_value = tax_dict.get('CGST') or 0
                cgst_percent = tax_dict.get('CGST_RATE') if cgst_value > 0 else 0

                sgst_value = tax_dict.get('SGST') or 0
                sgst_percent = tax_dict.get('SGST_RATE') if sgst_value > 0 else 0

                tds_percent = tax_dict.get('TDS_RATE') or 0

                igst_amount = igst_value if igst_value > 0 else 0
                cgst_amount = cgst_value if cgst_value > 0 else 0
                sgst_amount = sgst_value if sgst_value > 0 else 0

                tds_amount = tax_dict.get('TDS') or 0
                

            for tax in record.sudo().y_move_line_id.tax_ids:
                if tax.amount_type == 'group':
                    for child_tax in tax.children_tax_ids:                
                        if child_tax.l10n_in_reverse_charge == True:
                            rcm_percent += abs(child_tax.amount) if child_tax.amount else 0.00
                            rcm_amount += (record.y_amount_exclusive_tax * child_tax.amount) /100
                            sgstrcm_percent = abs(child_tax.amount) if child_tax.amount else 0.00
                            sgstrcm_amount = (record.y_amount_exclusive_tax * child_tax.amount) /100
                            cgstrcm_percent = abs(child_tax.amount) if child_tax.amount else 0.00
                            cgstrcm_amount = (record.y_amount_exclusive_tax * child_tax.amount) /100
                else:
                    if tax.l10n_in_reverse_charge == True:
                        rcm_percent += abs(tax.amount) if tax.amount else 0.00
                        rcm_amount += (record.y_amount_exclusive_tax * tax.amount) /100  
                        igstrcm_percent = abs(tax.amount) if tax.amount else 0.00
                        igstrcm_amount = (record.y_amount_exclusive_tax * tax.amount) /100 


            if record.y_move_id.move_type == 'in_refund':
                record.y_sgstrcm_amount = -(sgstrcm_amount)
                record.y_sgstrcm_percent = sgstrcm_percent
                record.y_cgstrcm_amount = -(cgstrcm_amount)
                record.y_cgstrcm_percent = cgstrcm_percent
                record.y_igstrcm_percent = igstrcm_percent
                record.y_igstrcm_amount = -(igstrcm_amount)

                        
                record.y_tds_percent = tds_percent
                record.y_sgst_percent = sgst_percent
                record.y_cgst_percent = cgst_percent 
                record.y_igst_percent = igst_percent 
                record.y_sgst_amount = -(sgst_amount)
                record.y_cgst_amount = -(cgst_amount)
                record.y_igst_amount = -(igst_amount )
                record.y_tds_amount = -(tds_amount)
                record.y_rcm_percent = rcm_percent
                record.y_rcm_amount = -(rcm_amount)
                record.y_ocean_tax_percent = ocean_tax_percent
                record.y_ocean_tax_amount = -(ocean_tax_amount)
                
            else:
                record.y_sgstrcm_amount = sgstrcm_amount
                record.y_sgstrcm_percent = sgstrcm_percent
                record.y_cgstrcm_amount = cgstrcm_amount
                record.y_cgstrcm_percent = cgstrcm_percent
                record.y_igstrcm_percent = igstrcm_percent
                record.y_igstrcm_amount = igstrcm_amount

                        
                record.y_tds_percent = tds_percent
                record.y_sgst_percent = sgst_percent
                record.y_cgst_percent = cgst_percent 
                record.y_igst_percent = igst_percent 
                record.y_sgst_amount = sgst_amount
                record.y_cgst_amount = cgst_amount
                record.y_igst_amount = igst_amount 
                record.y_tds_amount = tds_amount
                record.y_rcm_percent = rcm_percent
                record.y_rcm_amount = rcm_amount
                record.y_ocean_tax_percent = ocean_tax_percent
                record.y_ocean_tax_amount = ocean_tax_amount
                
    # Total Tax
    def total_tax(self):
        for itm in self:
            itm.y_tax_amount = sum([itm.y_sgst_amount,itm.y_cgst_amount,itm.y_igst_amount])

    def get_picking_names(self):
        for rec in self:
            rec.y_grn_ref = ''
            if rec.sudo().y_move_line_id:
                picking_names = rec.sudo().y_move_line_id.y_stock_picking_ref.filtered(lambda x:x.state == 'done').mapped('name')
                rec.y_grn_ref = ",".join(picking_names)                

    def get_analytic_distribution(self):
        for rec in self:
            rec.y_analytic_account_ids = False
            if rec.sudo().y_move_line_id.analytic_distribution:
                analytic_ids = []
                for analytic_keys in rec.sudo().y_move_line_id.analytic_distribution.keys():
                    for analytic_key in analytic_keys.split(','):
                        int_analytic_key = int(analytic_key)
                        analytic_account_obj = rec.env['account.analytic.account'].browse(int_analytic_key)
                        if analytic_account_obj.active:
                            analytic_ids.append(analytic_account_obj.id)
                if analytic_ids:
                    rec.y_analytic_account_ids = analytic_ids     


    @api.model
    def init(self):
        company = self.env.company.id
        tools.drop_view_if_exists(self._cr, 'purchase_register_report')
        self._cr.execute("""
            CREATE OR REPLACE VIEW purchase_register_report AS (
                SELECT 
                    row_number() OVER () AS id,
                    move.move_type AS y_move_type_name,
                    move.id AS y_move_id,
                    move.company_id AS y_company_id,
                    move.name AS y_bill_num,
                    move.invoice_payment_term_id AS y_invoice_payment_term_id,
                    move.ref AS y_invoice_ref,
                    move.invoice_date AS y_bill_date,
                    CURRENT_DATE - DATE(move.invoice_date) AS y_bill_aging,
                    move.payment_state AS y_payment_state,
                    line.name AS y_label,
                    CASE 
                        WHEN res_curr.name != 'INR' AND line.price_subtotal != 0 THEN (line.debit / line.price_subtotal) 
                    END AS y_boe_rate,
                    pl.id AS y_purchase_line_id,
                    po.id AS y_purchase_order_id,
                    po.date_order AS y_purchase_order_date,
                    line.product_id AS y_product_id,
                    pt.id AS y_product_tmpl_id,
                    CASE 
                        WHEN pt.type = 'consu' AND pt.is_storable THEN 'product'
                        WHEN pt.type = 'consu' AND pt.is_storable = FALSE THEN 'consu'
                        WHEN pt.type = 'service' THEN 'service'
                        ELSE 'combo'
                    END AS y_product_type,
                    pt.uom_id AS y_uom_id,
                    pt.categ_id AS y_product_category_id,
                    line.id AS y_move_line_id,
                    CASE 
                        WHEN move.move_type = 'in_refund' THEN -(line.quantity)
                        ELSE line.quantity
                        END AS y_quantity,
                    CASE 
                        WHEN move.move_type = 'in_refund' THEN -(line.price_unit)
                        ELSE line.price_unit
                        END AS y_price_unit,
                    CASE 
                        WHEN company_curr.id = move.currency_id and move.move_type = 'in_refund' THEN -(line.price_subtotal)
                        WHEN company_curr.id = move.currency_id and move.move_type = 'in_invoice' THEN line.price_subtotal
                        WHEN move.move_type = 'in_refund' THEN -(line.credit)
                        WHEN move.move_type = 'in_invoice' THEN line.debit
                        ELSE 0
                    END AS y_amount_exclusive_tax,
                    line.price_subtotal AS y_price_subtotal,
                    CASE 
                        WHEN move.move_type = 'in_refund' THEN -(line.price_total)
                        ELSE line.price_total
                        END AS y_amount_inclusive_tax,
                    line.journal_id AS y_journal_id,
                    line.account_id AS y_account_id,
                    line.partner_id AS y_partner_id,
                    line.currency_id AS y_currency_id,
                    line.discount AS discount,
                    line.date AS y_accounting_date,
                    partner.ref AS partner_ref,
                    partner.vat AS y_gst_name,
                    partner.state_id AS y_partner_state_id,
                    partner.city AS y_partner_city,
                    partner.country_id AS y_partner_country_id,
                    product.default_code AS product_ref
                FROM 
                    account_move_line line
                LEFT JOIN 
                    account_move move ON move.id = line.move_id
                LEFT JOIN 
                    purchase_order_line pl ON pl.id = line.purchase_line_id
                LEFT JOIN 
                    purchase_order po ON po.id = pl.order_id
                LEFT JOIN 
                    res_partner partner ON partner.id = line.partner_id
                LEFT JOIN 
                    product_product product ON product.id = line.product_id
                LEFT JOIN 
                    product_template pt ON pt.id = product.product_tmpl_id
                LEFT JOIN 
                    res_currency res_curr ON res_curr.id = line.currency_id
                LEFT JOIN 
                    res_company company ON company.id = move.company_id
                LEFT JOIN 
                    res_currency company_curr ON company_curr.id = company.currency_id
                WHERE 
                    move.state = 'posted' 
                    AND line.display_type = 'product' 
                    AND line.product_id IS NOT NULL 
                    AND (move.move_type = 'in_invoice' OR move.move_type = 'in_refund')


                )""")

        

    @api.model
    def purchase_register_query(self,domain_clause,company_clause):    
        company = self.env.company.id
        tools.drop_view_if_exists(self._cr, 'purchase_register_report')
        self._cr.execute("""
            CREATE OR REPLACE VIEW purchase_register_report AS (
                SELECT 
                    row_number() OVER () AS id,
                    move.move_type AS y_move_type_name,
                    move.id AS y_move_id,
                    move.company_id AS y_company_id,
                    move.name AS y_bill_num,
                    move.invoice_payment_term_id AS y_invoice_payment_term_id,
                    move.ref AS y_invoice_ref,
                    move.invoice_date AS y_bill_date,
                    CURRENT_DATE - DATE(move.invoice_date) AS y_bill_aging,
                    move.payment_state AS y_payment_state,
                    line.name AS y_label,
                    CASE 
                        WHEN res_curr.name != 'INR' AND line.price_subtotal != 0 THEN (line.debit / line.price_subtotal) 
                    END AS y_boe_rate,
                    pl.id AS y_purchase_line_id,
                    po.id AS y_purchase_order_id,
                    po.date_order AS y_purchase_order_date,
                    line.product_id AS y_product_id,
                    pt.id AS y_product_tmpl_id,
                    CASE 
                        WHEN pt.type = 'consu' AND pt.is_storable THEN 'product'
                        WHEN pt.type = 'consu' AND pt.is_storable = FALSE THEN 'consu'
                        WHEN pt.type = 'service' THEN 'service'
                        ELSE 'combo'
                    END AS y_product_type,
                    pt.uom_id AS y_uom_id,
                    pt.categ_id AS y_product_category_id,
                    line.id AS y_move_line_id,
                    CASE 
                        WHEN move.move_type = 'in_refund' THEN -(line.quantity)
                        ELSE line.quantity
                        END AS y_quantity,
                    CASE 
                        WHEN move.move_type = 'in_refund' THEN -(line.price_unit)
                        ELSE line.price_unit
                        END AS y_price_unit,
                    CASE 
                        WHEN company_curr.id = move.currency_id and move.move_type = 'in_refund' THEN -(line.price_subtotal)
                        WHEN company_curr.id = move.currency_id and move.move_type = 'in_invoice' THEN line.price_subtotal
                        WHEN move.move_type = 'in_refund' THEN -(line.credit)
                        WHEN move.move_type = 'in_invoice' THEN line.debit
                        ELSE 0
                    END AS y_amount_exclusive_tax,
                    line.price_subtotal AS y_price_subtotal,
                    CASE 
                        WHEN move.move_type = 'in_refund' THEN -(line.price_total)
                        ELSE line.price_total
                        END AS y_amount_inclusive_tax,
                    line.journal_id AS y_journal_id,
                    line.account_id AS y_account_id,
                    line.partner_id AS y_partner_id,
                    line.currency_id AS y_currency_id,
                    line.discount AS discount,
                    line.date AS y_accounting_date,
                    partner.ref AS partner_ref,
                    partner.vat AS y_gst_name,
                    partner.state_id AS y_partner_state_id,
                    partner.city AS y_partner_city,
                    partner.country_id AS y_partner_country_id,
                    product.default_code AS product_ref
                FROM 
                    account_move_line line
                LEFT JOIN 
                    account_move move ON move.id = line.move_id
                LEFT JOIN 
                    purchase_order_line pl ON pl.id = line.purchase_line_id
                LEFT JOIN 
                    purchase_order po ON po.id = pl.order_id
                LEFT JOIN 
                    res_partner partner ON partner.id = line.partner_id
                LEFT JOIN 
                    product_product product ON product.id = line.product_id
                LEFT JOIN 
                    product_template pt ON pt.id = product.product_tmpl_id
                LEFT JOIN 
                    res_currency res_curr ON res_curr.id = line.currency_id
                LEFT JOIN 
                    res_company company ON company.id = move.company_id
                LEFT JOIN 
                    res_currency company_curr ON company_curr.id = company.currency_id
                WHERE 
                    move.state = 'posted' 
                    AND line.display_type = 'product' 
                    AND line.product_id IS NOT NULL 
                    AND (move.move_type = 'in_invoice' OR move.move_type = 'in_refund')
                    {} {}
                )""".format(domain_clause,company_clause))
        
        return {
            'name': _("Purchase Register Report List"),

            'type': 'ir.actions.act_window',

            'res_model': 'purchase.register.report',

            'view_mode': 'list,pivot',

            'views': [(self.env.ref('purchase_register_report_18.view_purchase_register_report_list').id, 'list'),(False, 'pivot')],

            'target': 'current'
        }

    
    
    
    
    

    