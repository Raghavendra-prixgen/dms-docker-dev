from odoo import models, fields, api, _
from odoo.tools.float_utils import float_round, float_is_zero
from odoo import tools
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta,date
import calendar
from xlwt import easyxf
import xlwt
import io
import base64
import datetime
import math
import pdb
import json
import xlsxwriter

def get_selection_label(self, object, field_name, field_value):
    return (dict(self.env[object].fields_get(allfields=[field_name])[field_name]['selection'])[field_value])

class SaleRegisterReportWizard(models.TransientModel):
    _name = "sale.register.wizard"
    _description = "Sale Register Report"

    y_name  = fields.Char(string="Name")
    y_start_date = fields.Date('Start Date', default=fields.Date.today)
    y_end_date = fields.Date('End Date', default=fields.Date.today)
    y_company_id = fields.Many2one('res.company', string="Company")
    y_choose_from = fields.Selection([('partner_id','Customer'),
                                      ('sale_person','Sale Person'),],string="Choose")
    
    y_sale_person_id = fields.Many2many('res.users', string="Sale Person")
    y_partner_id = fields.Many2many('res.partner', string="Customer")

    # Calling report method
    def retrieve_register(self):
        date_clause = " AND move.date >= '{}' AND move.date <= '{}'".format(self.y_start_date,self.y_end_date)    
        
        if self.y_choose_from:
            if self.y_partner_id and self.y_choose_from == 'partner_id':
                if len(self.y_partner_id.ids) > 1:
                    domain_clause = " AND move.partner_id in {}".format(tuple(self.y_partner_id.ids))
                else:
                    domain_clause = " AND move.partner_id = {}".format(self.y_partner_id.ids[0])
                date_clause+=domain_clause
            if self.y_sale_person_id and self.y_choose_from == 'sale_person':
                if len(self.y_sale_person_id.ids) > 1:
                    domain_clause = " AND move.invoice_user_id in {}".format(tuple(self.y_sale_person_id.ids))
                else:
                    domain_clause = " AND move.invoice_user_id = {}".format(self.y_sale_person_id.ids[0])
                date_clause+=domain_clause

        if not self.sudo().y_company_id.child_ids:
            company_clause = " AND move.company_id = {}".format(self.y_company_id.id)
            date_clause+=company_clause
        else:
            company_ids = self.env.user.company_ids
            access_company_ids = (company_ids.filtered(lambda x:x.parent_id == self.y_company_id) + self.y_company_id).ids
            if len(access_company_ids) == 1:
                company_clause = " AND move.company_id = {}".format(access_company_ids[0])
            else:
                company_clause = " AND move.company_id in {}".format(tuple(access_company_ids))
            date_clause+=company_clause
        return self.env['sales.register.report'].sudo().sale_register_query(date_clause)

    def get_headers(self):
        headers = [
            "Invoice Number",
            "Invoice Date",
            "Customer Code",
            "Customer",
            "VAT",
            "Partner Category",
            "Company",
            "Invoice Amount FC",
            "Salesperson",
            "Sales Team",
            "Product Code",
            "Product",
            "Label",
            "Product Category",
            "Product Type",
            "Product UOM",
            "Payment State",
            "Account Name",
            "Journal Name",
            "Currency",
            "Sale Order Number",
            "Sale Order Date",
            "Quantity",
            "Price",
            "Weight Per Unit",
            "Total Weight",
            "Amount Exclusive Tax",
            "Tax",
            "Amount",
            "Amount Inclusive Tax",
            "Analytic Account",
            "Customer City",
            "Customer State",
            "Customer Country",
            "Invoice Type",
        ]
        return headers

    def get_sale_register_domain(self):
        domain = [('state','=','posted'),
                  ('date','>=',self.y_start_date),
                  ('date','<=',self.y_end_date),
                  ('move_type','in',('out_invoice','out_refund'))]

        if self.y_choose_from:
            if self.y_partner_id and self.y_choose_from == 'partner_id':
                if len(self.y_partner_id.ids) > 1:
                    domain+=[('partner_id','in',self.y_partner_id.ids)]
                else:
                    domain+=[('partner_id','=',self.y_partner_id.id)]
            if self.y_sale_person_id and self.y_choose_from == 'sale_person':
                if len(self.y_sale_person_id.ids) > 1:
                    domain+=[('invoice_user_id','in',self.y_sale_person_id.ids)]
                else:
                    domain+=[('invoice_user_id','in',self.y_sale_person_id.id)]


        company_ids = self.env['res.company']
        if not self.sudo().y_company_id.child_ids:
            domain+= [('company_id','=',self.y_company_id.id)]
        else:
            company_ids = self.env.user.company_ids
            access_company_ids = (company_ids.filtered(lambda x:x.parent_id == self.y_company_id) + self.y_company_id)
            if len(access_company_ids) == 1:
                domain+=[('company_id','=',access_company_ids[0].id)]
            else:
                domain+=[('company_id','in',access_company_ids.ids)]
                
        return domain


    def update_worksheet(self,row,worksheet,line,invoice,styles):
        worksheet.write(row, 0, invoice.name ,styles['left_alignment']) # Invoice Number
        worksheet.write(row, 1, invoice.invoice_date or '' ,styles['date_style']) # Invoice Date
        partner_id = line.partner_id if line.partner_id else invoice.partner_id 
        worksheet.write(row, 2, partner_id.ref or '' ,styles['left_alignment']) # Customer Code
        worksheet.write(row, 3, partner_id.name or '' ,styles['left_alignment']) # Customer
        worksheet.write(row, 4, partner_id.vat or '' ,styles['left_alignment']) # Customer GST No
        worksheet.write(row, 5, invoice.y_partner_category_id.y_name or '' ,styles['left_alignment']) # Partner Category
        worksheet.write(row, 6, invoice.company_id.name or '',styles['left_alignment']) # Company
        # Invoice Amount FC
        invoice_amount_fc = 0
        if invoice.company_id.currency_id != invoice.currency_id:
            invoice_amount_fc = line.price_subtotal 
        worksheet.write(row, 7, invoice_amount_fc or '' ,styles['center_alignment']) # Company
        worksheet.write(row, 8, invoice.invoice_user_id.name or '' ,styles['left_alignment']) # Salesperson
        worksheet.write(row, 9, invoice.team_id.name or '' ,styles['left_alignment']) # Sales Team
        worksheet.write(row, 10, line.product_id.default_code or '' ,styles['center_alignment']) # Product Code
        worksheet.write(row, 11, line.product_id.name or '' ,styles['left_alignment']) # Product
        worksheet.write(row, 12, line.name or '' ,styles['left_alignment']) # Label

        worksheet.write(row, 13, line.product_category_id.name or '' ,styles['center_alignment']) # Product Category
        product_type = ''
        if line.product_id.product_tmpl_id.type == 'consu' and line.product_id.product_tmpl_id.is_storable:
            product_type = 'Storable Product'
        elif line.product_id.product_tmpl_id.type == 'consu' and line.product_id.product_tmpl_id.is_storable == False:
            product_type = 'Consumable'
        elif line.product_id.product_tmpl_id.type == 'service':
            product_type = 'Service'
        else:
            product_type = 'Combo'
        worksheet.write(row, 14, product_type ,styles['left_alignment']) # Product Type
        worksheet.write(row, 15, line.product_uom_id.name or '' ,styles['center_alignment']) # Product UOM
        payment_state = get_selection_label(self,'account.move','payment_state',invoice.payment_state)  
        worksheet.write(row, 16, payment_state ,styles['center_alignment']) # Payment State
        worksheet.write(row, 17, line.account_id.display_name or '',styles['left_alignment']) # Account Name
        worksheet.write(row, 28, line.journal_id.name or '' ,styles['left_alignment']) # Journal Name
        worksheet.write(row, 19, invoice.currency_id.name or '' ,styles['center_alignment']) # Currency
        worksheet.write(row, 20, ",".join(line.sale_line_ids.order_id.mapped('name')) or '' ,styles['left_alignment']) # Sale Order Number
        sale_order_date = ''
        sale_order_ids = line.sale_line_ids.mapped('order_id')
        if sale_order_ids:
            sale_order_date = sale_order_ids[0].date_order
        worksheet.write(row, 21, sale_order_date or '' ,styles['date_style']) # Sale Order Date

        worksheet.write(row, 22, line.quantity if invoice.move_type != 'out_refund' else -(line.quantity) ,styles['center_alignment']) # Quantity
        worksheet.write(row, 23, line.price_unit if invoice.move_type != 'out_refund' else -(line.price_unit) ,styles['style_number_float']) # Price
        worksheet.write(row, 24, line.product_id.weight ,styles['style_number_float']) # Weight Per Unit
        worksheet.write(row, 25, (line.quantity * line.product_id.weight) ,styles['center_alignment']) # Total Weight
        amount_exclusive_tax = ''
        if invoice.company_id.currency_id == invoice.currency_id and invoice.move_type == 'out_refund':
            amount_exclusive_tax = -(line.price_subtotal)
        elif invoice.company_id.currency_id == invoice.currency_id and invoice.move_type == 'out_invoice':
            amount_exclusive_tax = line.price_subtotal
        elif invoice.move_type == 'out_refund':
            amount_exclusive_tax = -(line.debit)
        elif invoice.move_type == 'out_invoice':
            amount_exclusive_tax = line.credit
        worksheet.write(row, 26, amount_exclusive_tax or '' ,styles['center_alignment']) # Amount Exclusive Tax
        tmp_name = ''
        if line.tax_ids:
            tmp_name = ",".join(line.tax_ids.mapped('name'))
        worksheet.write(row, 27, tmp_name or '',styles['left_alignment']) # Taxes
        tax_amount = 0.0
        tax_dict = line.sudo()._get_tax_line_group_values()
        if tax_dict:
            total_tax = sum(
                    value for key, value in tax_dict.items()
                    if not key.endswith('_RATE') and isinstance(value, (int, float))
                )
            
            tax_amount = total_tax or 0

        if invoice.move_type == 'out_refund':
            tax_amount = -(tax_amount)


        worksheet.write(row, 28, tax_amount ,styles['center_alignment']) # Tax
        amount_inclusive_tax = line.price_total
        if invoice.move_type == 'out_refund':
            amount_inclusive_tax =-(line.price_total)
        worksheet.write(row, 29, amount_inclusive_tax ,styles['style_number_float']) # Amount Inclusive Tax
        analytic_accounts = ''
        if line.analytic_distribution:
            analytic_ids = []
            for analytic_keys in line.analytic_distribution.keys():
                for analytic_key in analytic_keys.split(','):
                    int_analytic_key = int(analytic_key)
                    analytic_account_obj = line.env['account.analytic.account'].browse(int_analytic_key)
                    if analytic_account_obj.active:
                        analytic_ids.append(analytic_account_obj)
            if analytic_ids:
                analytic_accounts = ",".join([analytic.name for analytic in analytic_ids])
        worksheet.write(row, 30, analytic_accounts or '' ,styles['left_alignment']) # Analytic Account

        worksheet.write(row, 31, partner_id.city or '' ,styles['left_alignment']) # Customer City
        worksheet.write(row, 32, partner_id.state_id.name or '' ,styles['left_alignment']) # Customer State
        worksheet.write(row, 33, partner_id.country_id.name or '' ,styles['left_alignment']) # Customer Country
        move_type = get_selection_label(self,'account.move','move_type',line.move_type)        
        worksheet.write(row, 34, move_type ,styles['left_alignment']) # Invoice Type

        return 34

        
    def get_report_styles(self,workbook):
        styles = {
                    'column_heading_style': workbook.add_format({'bold': True,'font_color': 'black','bg_color': 'deebf7','font_name':'Arial','font_size': 10,'align': 'center','valign': 'vcenter'}),
                    'main_heading_style' : workbook.add_format({'bold': True,'font_color': 'black','font_name':'Arial','font_size': 15,'align': 'center','valign': 'vcenter'}),
                    'left_alignment' : workbook.add_format({'font_color': 'black','font_name':'Arial','font_size': 10,'border':1,'border_color':'black','align': 'left','valign': 'vcenter'}),
                    'center_alignment' : workbook.add_format({'font_color': 'black','font_name':'Arial','font_size': 10,'border':1,'border_color':'black','align': 'center','valign': 'vcenter'}),
                    'right_alignment' : workbook.add_format({'font_color': 'black','font_size': 10,'font_name':'Arial','border':1,'border_color':'black','align': 'right','valign': 'vcenter'}),
                    'style_number_float' : workbook.add_format({'border':1,'font_color': 'black','font_name':'Arial','font_size': 10,'align':'center', 'num_format':'###0.000;-###0.000;""'}),
                    'style_num_float' : workbook.add_format({'border':1,'font_color': 'black','font_name':'Arial','font_size': 10,'align':'center', 'num_format':'###0.00;-###0.00;""'}),
                    'date_style' : workbook.add_format({'border': 1, 'num_format': 'dd/mm/yyyy','font_size': 10,'font_name':'Arial','align': 'center'}),

                }
        return styles




    def get_report_hedding(self,worksheet,report_name,styles):
        headers = self.get_headers()
        def colnum_to_excel_col(n):
            result = ''
            while n > 0:
                n, remainder = divmod(n - 1, 26)
                result = chr(65 + remainder) + result
            return result

        header_len = len(headers)
        # Calculate center of header columns (merge 2 columns)
        middle_col = header_len // 2
        start_col_num = middle_col
        end_col_num = middle_col + 1

        # Convert column numbers to Excel letters
        start_col_letter = colnum_to_excel_col(start_col_num)
        end_col_letter = colnum_to_excel_col(end_col_num)

        # Define heading merge range
        heading_range = f'{start_col_letter}1:{end_col_letter}1'

        # Use in your merge
        worksheet.merge_range(heading_range, report_name, styles['main_heading_style'])
        row = 1
        return row

    def button_download_xlsx_report(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        report_name = "Sale Register Report"
        worksheet = workbook.add_worksheet(report_name)
        worksheet.freeze_panes(2,5)
        worksheet.set_column('A:C', 15)
        worksheet.set_column('D:D', 20)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 15)
        worksheet.set_column('G:AS', 15)
        styles = self.get_report_styles(workbook)
        row = self.get_report_hedding(worksheet,report_name,styles)
        headers = self.get_headers()
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, styles['column_heading_style'])
        row +=1
        domain = self.get_sale_register_domain()
        invoice_ids = self.env['account.move'].search(domain)
        
        for invoice in invoice_ids:
            for line in invoice.invoice_line_ids.filtered(lambda x:x.product_id or x.account_id):
                col = self.update_worksheet(row,worksheet,line,invoice,styles)
                row +=1
                
        workbook.close()
        output.seek(0)
        file_name = "{}.xlsx".format(report_name)
        attachment_id = self.env['ir.attachment'].create({
            'name': file_name,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'store_fname': file_name,
            'res_model': self._name,
            'res_id': self.id,
        })
        # Return the action to download the report
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/{}'.format(attachment_id.id),
            'target': 'self',
        }

    # Validation for start date and end date
    @api.onchange('y_start_date','y_end_date')
    def date_validation(self):
        if self.y_start_date and self.y_end_date:
            if self.y_start_date > self.y_end_date:
                raise ValidationError(_("'Start Date' must be before 'End Date'"))

class SalesRegisterReport(models.Model):
    _name = "sales.register.report"
    _auto = False
    _description =  " "
    
    y_journal_id = fields.Many2one('account.journal', 'Journal Name',readonly=True)
    y_account_id = fields.Many2one('account.account','Account Name',readonly=True)
    y_move_id = fields.Many2one('account.move',string='Invoice',readonly=True)
    y_move_name = fields.Char(string="Invoice Number")
    y_move_line_id = fields.Many2one('account.move.line',string="Invoice Line",readonly=True)
    y_invoice_date = fields.Date(string='Invoice Date',readonly=True)
    y_currency_id = fields.Many2one('res.currency', string="Currency",readonly=True)

    y_sale_order_id = fields.Many2one('sale.order',string="Sale Order Number",readonly=True)
    y_sale_order_date = fields.Datetime(string="Sale Order Date",readonly=True)
    y_move_type_name = fields.Selection([
            ('entry','Journal Entry'),
            ('out_invoice', 'Customer Invoice'),    
            ('out_refund' , 'Customer Credit Note'),
            ('in_invoice' , 'Vendor Bill'),
            ('in_refund' ,'Vendor Credit Note'),  
            ('out_receipt' ,'Sales Receipt' ),  
            ('in_receipt'  ,'Purchase Receip'),],string='Invoice Type',readonly=True)    
    y_customer_invoice_ref = fields.Char(string="Customer Reference",readonly=True)

    # Partner relate fields
    y_partner_id = fields.Many2one('res.partner',string="Partner",readonly=True)
    y_partner_category_id = fields.Many2one('partner.category',string="Partner Category",readonly=True)
    y_partner_city = fields.Char(string="Customer City",readonly=True)
    y_partner_state_id = fields.Many2one('res.country.state',string="Customer State",readonly=True)
    y_partner_country_id = fields.Many2one('res.country',string="Customer Country",readonly=True)
    y_gst_name = fields.Char(string="VAT",readonly=True)
    y_partner_ref = fields.Char(string="Customer Code",readonly=True)
    y_sales_person_id = fields.Many2one('res.users',string="Sales person",readonly=True)
    y_sales_team_id = fields.Many2one('crm.team',string="Sales Team",readonly=True)
    
    # Product relate fields
    y_product_id = fields.Many2one('product.product', string="Product",readonly=True)
    y_label = fields.Char(string="Label",readonly=True) # invoice_line.name
    y_uom_id = fields.Many2one('uom.uom',string="Product Uom",readonly=True)
    y_product_category_id = fields.Many2one('product.category',string="Product Category",readonly=True)
    y_product_ref = fields.Char(string="Product Code",readonly=True)
    y_product_type = fields.Selection([('product', 'Storable Product'),
                                     ('consu', 'Consumable'),
                                     ('service', 'Service'),
                                     ('combo','Combo')], string='Product Type',readonly=True)
    y_invoice_amount_fc = fields.Float(string='Invoice Amount FC',readonly=True)
    y_quantity = fields.Float('Quantity',readonly=True)
    y_price_unit = fields.Float('Unit Price',readonly=True)
    y_price_subtotal = fields.Float('Subtotal',readonly=True)

    y_analytic_account_ids = fields.Many2many('account.analytic.account',compute="get_analytic_distribution",string="Analytical Account",readonly=True)
    y_amount_exclusive_tax = fields.Float(string="Amount Exclusive Tax",readonly=True) 
    y_amount_inclusive_tax = fields.Float(string="Amount Inclusive Tax",readonly=True)

    y_tax = fields.Char(string="Tax",compute="report_compute_tax",readonly=True)
    y_tax_amount = fields.Float(compute="report_compute_tax", string="Amount",readonly=True)
    y_company_id = fields.Many2one('res.company',string="Company",readonly=True)
    y_weight = fields.Float(string="Weight Per Unit",readonly=True)
    y_total_weight = fields.Float(string="Total Weight",readonly=True)
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

    # Computing the taxes
    def report_compute_tax(self):
        for record in self:
            tmp_name = ''
            if record.sudo().y_move_line_id.tax_ids:
                tmp_name = ",".join(record.sudo().y_move_line_id.tax_ids.mapped('name'))
            record.y_tax = tmp_name
            tax_amount = 0.0
            tax_dict = record.sudo().y_move_line_id.sudo()._get_tax_line_group_values()
            if tax_dict:
                total_tax = sum(
                        value for key, value in tax_dict.items()
                        if not key.endswith('_RATE') and isinstance(value, (int, float))
                    )
                
                tax_amount = total_tax or 0

            if record.sudo().y_move_line_id.move_id.move_type == 'out_refund':
                tax_amount = -(tax_amount)

            record.y_tax_amount = tax_amount

    # Amount Analytical Account
    def get_analytic_distribution(self):
        for rec in self:
            rec.y_analytic_account_ids = False
            if rec.sudo().y_move_line_id.analytic_distribution:
                analytic_ids = []
                for analytic_keys in rec.sudo().y_move_line_id.analytic_distribution.keys():
                    for analytic_key in analytic_keys.split(','):
                        # print(type(analytic_key),"DDD")
                        int_analytic_key = int(analytic_key)
                        analytic_account_obj = rec.env['account.analytic.account'].sudo().browse(int_analytic_key)
                        if analytic_account_obj.active:
                            analytic_ids.append(analytic_account_obj.id)
                if analytic_ids:
                    rec.y_analytic_account_ids = analytic_ids   

    def _select_query(self):
        return """  ac_move_line.id AS y_move_line_id,
                    move.move_type AS y_move_type_name,
                    move.id AS y_move_id,
                    move.name AS y_move_name,
                    move.company_id AS y_company_id,
                    move.invoice_date AS y_invoice_date,
                    move.payment_state AS y_payment_state,
                    move.ref AS y_customer_invoice_ref,
                    move.invoice_user_id AS y_sales_person_id,
                    move.team_id AS y_sales_team_id,
                    ac_move_line.name AS y_label,
                    CASE 
                        WHEN company.currency_id != move.currency_id THEN ac_move_line.price_subtotal 
                    END AS y_invoice_amount_fc,
                    so.id AS y_sale_order_id,
                    so.date_order AS y_sale_order_date,
                    product.id AS y_product_id,
                    pt.id AS product_tmpl_id,
                    CASE 
                        WHEN pt.type = 'consu' AND pt.is_storable THEN 'product'
                        WHEN pt.type = 'consu' AND pt.is_storable = FALSE THEN 'consu'
                        WHEN pt.type = 'service' THEN 'service'
                        ELSE 'combo'
                    END AS y_product_type,
                    pt.uom_id AS y_uom_id,
                    pt.categ_id AS y_product_category_id,
                    CASE 
                        WHEN move.move_type = 'out_refund' THEN -(ac_move_line.quantity)
                        ELSE ac_move_line.quantity
                        END AS y_quantity,
                    CASE 
                        WHEN move.move_type = 'out_refund' THEN -(ac_move_line.price_unit)
                        ELSE ac_move_line.price_unit
                        END AS y_price_unit,
                    CASE 
                        WHEN company.currency_id = move.currency_id and move.move_type = 'out_refund' THEN -(ac_move_line.price_subtotal)
                        WHEN company.currency_id = move.currency_id and move.move_type = 'out_invoice' THEN ac_move_line.price_subtotal
                        WHEN move.move_type = 'out_refund' THEN -(ac_move_line.debit)
                        WHEN move.move_type = 'out_invoice' THEN ac_move_line.credit
                        ELSE 0
                    END AS y_amount_exclusive_tax,
                    ac_move_line.price_subtotal AS y_price_subtotal,
                    CASE 
                        WHEN move.move_type = 'out_refund' THEN -(ac_move_line.price_total)
                        ELSE ac_move_line.price_total
                        END AS y_amount_inclusive_tax,
                    ac_move_line.journal_id AS y_journal_id,
                    ac_move_line.account_id AS y_account_id,
                    partner.id AS y_partner_id,
                    move.currency_id AS y_currency_id,
                    ac_move_line.discount AS discount,
                    partner.ref AS y_partner_ref,
                    partner.y_partner_category AS y_partner_category_id,
                    partner.state_id AS y_partner_state_id,
                    partner.city AS y_partner_city,
                    partner.vat AS y_gst_name,
                    partner.country_id AS y_partner_country_id,
                    product.default_code AS y_product_ref,
                    pt.weight AS y_weight,
                    (pt.weight * ac_move_line.quantity) AS y_total_weight

               """

    def _from_query(self):
        return """
                FROM
                    account_move_line ac_move_line
                LEFT JOIN 
                    account_move move ON move.id = ac_move_line.move_id
                LEFT JOIN
                    sale_order_line_invoice_rel inv_sale_line ON inv_sale_line.invoice_line_id = ac_move_line.id
                LEFT JOIN 
                    sale_order_line sale_line ON sale_line.id = inv_sale_line.order_line_id
                LEFT JOIN 
                    sale_order so ON so.id = sale_line.order_id
                LEFT JOIN 
                    res_partner partner ON partner.id = move.partner_id
                LEFT JOIN 
                    product_product product ON product.id = ac_move_line.product_id
                LEFT JOIN 
                    product_template pt ON pt.id = product.product_tmpl_id
                LEFT JOIN 
                    res_company company ON company.id = move.company_id
                """

    def _where_query(self):
        return """WHERE 
                    move.state = 'posted' 
                    AND ac_move_line.display_type = 'product'
                    AND ac_move_line.product_id IS NOT NULL 
                    AND (move.move_type = 'out_invoice' OR move.move_type = 'out_refund')
                """

    @api.model
    def init(self):
        company = self.env.company.id
        select_query = self._select_query()
        from_query = self._from_query()
        where_query = self._where_query()
        tools.drop_view_if_exists(self._cr, 'sales_register_report')
        self._cr.execute("""
            CREATE OR REPLACE VIEW sales_register_report AS (
                SELECT 
                    row_number() OVER () AS id,
                    {select_query}
                    {from_query}
                    {where_query}
                    
                )""".format(select_query=select_query,from_query=from_query,where_query=where_query))
        

    
    @api.model
    def sale_register_query(self,date_clause):
        company = self.env.company.id
        select_query = self._select_query()
        from_query = self._from_query()
        where_query = self._where_query()
        tools.drop_view_if_exists(self._cr, 'sales_register_report')
        query = """
            CREATE OR REPLACE VIEW sales_register_report AS (
                SELECT 
                    row_number() OVER () AS id,
                    {select_query}
                    {from_query}
                    {where_query}
                    {date_clause}
                )""".format(select_query=select_query,from_query=from_query,where_query=where_query,date_clause=date_clause)

        # print('\n'*3)
        # print(query)
        # print('\n'*3)
           
        self._cr.execute(query)

        return {
            'name': _("Sale Register Report List"),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.register.report',
            'view_mode': 'list,pivot',
            'views': [(self.env.ref('sale_register_report_18.view_sale_register_report_list').id, 'list'),(False, 'pivot')],
            'target': 'current',
        }
