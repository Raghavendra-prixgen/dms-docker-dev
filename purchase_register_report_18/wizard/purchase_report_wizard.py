from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
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
class PurchaseRegisterReportWizard(models.TransientModel):
    _name = "purchase.register.wizard"
    _description = ""

    y_date_start = fields.Date(string="Start Date", required=True, default=fields.Date.today)
    y_date_end = fields.Date(string="End Date", required=True, default=fields.Date.today)
    y_choose_from = fields.Selection([       
        ('partner_id','Vendor'),
        ('categ_id','Product Category'),
        ],string="Choose")
    y_report_date = fields.Selection([('accounting','Accounting Date'),('invoice','Invoice Date')],default='accounting',string="Report On")
    y_categ_id = fields.Many2many('product.category', string="Product Category")
    y_partner_id = fields.Many2many('res.partner', string="Vendor")
    y_company_id = fields.Many2one('res.company',string="Company")

    # Calling report method
    def retrieve_purchase_register(self):
        arg_list = []
        if self.y_report_date == 'accounting':
            date_clause = " AND move.date >= '{}' AND move.date <= '{}'".format(self.y_date_start,self.y_date_end)
        if self.y_report_date == 'invoice':
            date_clause = " AND move.invoice_date >= '{}' AND move.invoice_date <= '{}'".format(self.y_date_start,self.y_date_end)
        if self.y_choose_from:
            if self.y_partner_id and self.y_choose_from == 'partner_id':
                if len(self.y_partner_id.ids) > 1:
                    domain_clause = " AND move.partner_id in {}".format(tuple(self.y_partner_id.ids))
                else:
                    domain_clause = " AND move.partner_id = {}".format(self.y_partner_id.ids[0])
                date_clause+=domain_clause
            if self.y_categ_id and self.y_choose_from == 'categ_id':
                if len(self.y_categ_id.ids) > 1:
                    domain_clause = " AND pt.categ_id in {}".format(tuple(self.y_categ_id.ids))
                else:
                    domain_clause = " AND pt.categ_id = {}".format(self.y_categ_id.ids[0])
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
        return self.env['purchase.register.report'].sudo().purchase_register_query(date_clause,company_clause)
        
    @api.constrains('y_date_start')
    def _code_constrains(self):
        if self.y_date_start > self.y_date_end:
            raise ValidationError(_("'Start Date' must be before 'End Date'"))


    def get_headers(self):
        headers = [
            "Bill Number",
            "Bill Date",
            "Vendor Code",
            "Vendor",
            "Vendor GST No",
            "Partner Category",
            "Company",
            "Bill Amount FC",
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
            "Purchase Order Number",
            "Purchase Order Date",
            "Quantity",
            "Price",
            "Weight Per Unit",
            "Total Weight",
            "Amount Exclusive Tax",
            "Taxes",
            "IGST Rate %",
            "IGST Amount",
            "CGST Rate %",
            "CGST Amount",
            "SGST Rate %",
            "SGST Amount",
            "TDS Rate %",
            "TDS Amount",

            "RCM Tax",
            "RCM Amount",
            "SGSTRCM Rate",
            "SGSTRCM Amount",
            "CGSTRCM Rate",
            "CGSTRCM Amount",
            "IGSTRCM Rate",
            "IGSTRCM Amount",

            "Total Tax Amount",
            "Amount Inclusive Tax",
            "Analytic Account",
            "Vendor City",
            "Vendor State",
            "Vendor Country",
            "Bill Type",
            "Bill Ageing",
            "Accounting Date",
            "Bill Reference",
            "GRN Reference",
            "BOE Rate",
            "Payment Terms",
        ]
        return headers

    def get_purchase_register_domain(self):
        domain = [('state','=','posted'),
                  ('move_type','in',('in_invoice','in_refund'))]

        # Date filters
        if self.y_report_date == 'accounting':
            domain += [
                ('date', '>=', self.y_date_start),
                ('date', '<=', self.y_date_end),
            ]

        if self.y_report_date == 'invoice':
            domain += [
                ('invoice_date', '>=', self.y_date_start),
                ('invoice_date', '<=', self.y_date_end),
            ]

        # Partner / Category filters
        if self.y_choose_from == 'partner_id' and self.y_partner_id:
            domain.append(('partner_id', 'in', self.y_partner_id.ids))

        if self.y_choose_from == 'categ_id' and self.y_categ_id:
            domain.append(('invoice_line_ids.product_id.categ_id', 'in', self.y_categ_id.ids))


        # Company filter (parent + children)
        if not self.sudo().y_company_id.child_ids:
            domain.append(('company_id', '=', self.y_company_id.id))
        else:
            access_company_ids = (
                self.env.user.company_ids.filtered(
                    lambda c: c.parent_id == self.y_company_id
                ) | self.y_company_id
            )
            domain.append(('company_id', 'in', access_company_ids.ids))


        return domain


    def update_worksheet(self,row,worksheet,line,invoice,styles):
        worksheet.write(row, 0, invoice.name ,styles['left_alignment']) # Invoice Number
        worksheet.write(row, 1, invoice.invoice_date or '' ,styles['date_style']) # Invoice Date
        partner_id = line.partner_id if line.partner_id else invoice.partner_id 
        worksheet.write(row, 2, partner_id.ref or '' ,styles['left_alignment']) # Vendor Code
        worksheet.write(row, 3, partner_id.name or '' ,styles['left_alignment']) # Vendor
        worksheet.write(row, 4, partner_id.vat or '' ,styles['left_alignment']) # Vendor GST No
        worksheet.write(row, 5, invoice.y_partner_category_id.y_name or '' ,styles['left_alignment']) # Partner Category
        worksheet.write(row, 6, invoice.company_id.name or '',styles['left_alignment']) # Company
        # Invoice Amount FC
        invoice_amount_fc = 0
        if invoice.company_id.currency_id != invoice.currency_id:
            invoice_amount_fc = line.price_subtotal 
        worksheet.write(row, 7, invoice_amount_fc or '' ,styles['center_alignment']) # Company


        # worksheet.write(row, 8, invoice.invoice_user_id.name or '' ,styles['left_alignment']) # Salesperson
        # worksheet.write(row, 9, invoice.team_id.name or '' ,styles['left_alignment']) # Sales Team



        worksheet.write(row, 8, line.product_id.default_code or '' ,styles['center_alignment']) # Product Code
        worksheet.write(row, 9, line.product_id.name or '' ,styles['left_alignment']) # Product
        worksheet.write(row, 10, line.name or '' ,styles['left_alignment']) # Label

        worksheet.write(row, 11, line.product_category_id.name or '' ,styles['center_alignment']) # Product Category
        product_type = ''
        if line.product_id.product_tmpl_id.type == 'consu' and line.product_id.product_tmpl_id.is_storable:
            product_type = 'Storable Product'
        elif line.product_id.product_tmpl_id.type == 'consu' and line.product_id.product_tmpl_id.is_storable == False:
            product_type = 'Consumable'
        elif line.product_id.product_tmpl_id.type == 'service':
            product_type = 'Service'
        else:
            product_type = 'Combo'
        worksheet.write(row, 12, product_type ,styles['left_alignment']) # Product Type
        worksheet.write(row, 13, line.product_uom_id.name or '' ,styles['center_alignment']) # Product UOM
        payment_state = get_selection_label(self,'account.move','payment_state',invoice.payment_state)  
        worksheet.write(row, 14, payment_state ,styles['center_alignment']) # Payment State
        worksheet.write(row, 15, line.account_id.display_name or '',styles['left_alignment']) # Account Name
        worksheet.write(row, 16, line.journal_id.name or '' ,styles['left_alignment']) # Journal Name
        worksheet.write(row, 17, invoice.currency_id.name or '' ,styles['center_alignment']) # Currency
        worksheet.write(row, 18, ",".join(line.purchase_line_id.order_id.mapped('name')) or '' ,styles['left_alignment']) # Purchase Order Number
        purchase_order_date = ''
        purchase_order_ids = line.purchase_line_id.mapped('order_id')
        if purchase_order_ids:
            purchase_order_date = purchase_order_ids[0].date_order
        worksheet.write(row, 19, purchase_order_date or '' ,styles['date_style']) # Purchase Order Date

        worksheet.write(row, 20, line.quantity if invoice.move_type != 'in_refund' else -(line.quantity) ,styles['center_alignment']) # Quantity
        worksheet.write(row, 21, line.price_unit if invoice.move_type != 'in_refund' else -(line.price_unit) ,styles['style_number_float']) # Price
        worksheet.write(row, 22, line.product_id.weight ,styles['style_number_float']) # Weight Per Unit
        worksheet.write(row, 23, (line.quantity * line.product_id.weight) ,styles['center_alignment']) # Total Weight
        amount_exclusive_tax = ''
        if invoice.company_id.currency_id == invoice.currency_id and invoice.move_type == 'in_refund':
            amount_exclusive_tax = -(line.price_subtotal)
        elif invoice.company_id.currency_id == invoice.currency_id and invoice.move_type == 'in_invoice':
            amount_exclusive_tax = line.price_subtotal
        elif invoice.move_type == 'in_refund':
            amount_exclusive_tax = -(line.credit)
        elif invoice.move_type == 'in_invoice':
            amount_exclusive_tax = line.debit
        worksheet.write(row, 24, amount_exclusive_tax or '' ,styles['center_alignment']) # Amount Exclusive Tax
        tmp_name = ''
        if line.tax_ids:
            tmp_name = ",".join(line.tax_ids.mapped('name'))
        worksheet.write(row, 25, tmp_name or '',styles['left_alignment']) # Taxes
        cgst_percent = 0.0
        sgst_percent = 0.0
        igst_percent = 0.0
        tds_percent = 0.0
        
        igst_amount = 0.0
        cgst_amount = 0.0
        sgst_amount = 0.0
        tds_amount = 0.0
    
        tax_dict = line.sudo()._get_tax_line_group_values()
        if tax_dict:
            igst_percent = tax_dict.get('IGST_RATE') if tax_dict.get('IGST') > 0 else 0 or 0
            cgst_percent = tax_dict.get('CGST_RATE') if tax_dict.get('CGST') > 0 else 0 or 0
            sgst_percent = tax_dict.get('SGST_RATE') if tax_dict.get('SGST') > 0 else 0 or 0
            tds_percent = tax_dict.get('TDS_RATE') or 0
            igst_amount = tax_dict.get('IGST') if tax_dict.get('IGST') > 0 else 0 or 0
            cgst_amount = tax_dict.get('CGST') if tax_dict.get('CGST') > 0 else 0 or 0
            sgst_amount = tax_dict.get('SGST') if tax_dict.get('SGST') > 0 else 0 or 0
            tds_amount = tax_dict.get('TDS') or 0

        if invoice.move_type == 'in_refund':
            igst_amount = -(igst_amount)
            cgst_amount = -(cgst_amount)
            sgst_amount = -(sgst_amount)
            tds_amount = -(tds_amount)

        worksheet.write(row, 26, igst_percent ,styles['center_alignment']) # IGST Rate % 
        worksheet.write(row, 27, igst_amount ,styles['style_number_float']) # IGST Amount
        worksheet.write(row, 28, cgst_percent ,styles['center_alignment']) # CGST Rate %
        worksheet.write(row, 29, cgst_amount ,styles['style_number_float']) # CGST Amount
        worksheet.write(row, 30, sgst_percent ,styles['center_alignment']) # SGST Rate %
        worksheet.write(row, 31, sgst_amount ,styles['style_number_float']) # SGST Amount
        worksheet.write(row, 32, tds_percent ,styles['center_alignment']) # TDS Rate %
        worksheet.write(row, 33, tds_amount ,styles['style_number_float']) # TDS Amount



        rcm_amount = 0.0
        rcm_percent = 0.0
        sgstrcm_amount = 0.0
        sgstrcm_percent = 0.0
        cgstrcm_amount = 0.0
        cgstrcm_percent = 0.0
        igstrcm_percent = 0.0
        igstrcm_amount = 0.0



        for tax in line.tax_ids:
            if tax.amount_type == 'group':
                for child_tax in tax.children_tax_ids:                
                    if child_tax.l10n_in_reverse_charge == True:
                        rcm_percent += abs(child_tax.amount) if child_tax.amount else 0.00
                        rcm_amount += (amount_exclusive_tax * child_tax.amount) /100
                        sgstrcm_percent = abs(child_tax.amount) if child_tax.amount else 0.00
                        sgstrcm_amount = (amount_exclusive_tax * child_tax.amount) /100
                        cgstrcm_percent = abs(child_tax.amount) if child_tax.amount else 0.00
                        cgstrcm_amount = (amount_exclusive_tax * child_tax.amount) /100


            else:
                if tax.l10n_in_reverse_charge == True:
                    rcm_percent += abs(tax.amount) if tax.amount else 0.00
                    rcm_amount += (amount_exclusive_tax * tax.amount) /100  
                    igstrcm_percent = abs(tax.amount) if tax.amount else 0.00
                    igstrcm_amount = (amount_exclusive_tax * tax.amount) /100  

        if invoice.move_type == 'in_refund':
            rcm_amount = -(rcm_amount)
            sgstrcm_amount = -(sgstrcm_amount)
            cgstrcm_amount = -(cgstrcm_amount)
            igstrcm_amount = -(igstrcm_amount)



        worksheet.write(row, 34,rcm_percent  ,styles['left_alignment']) # rcm percent
          
        worksheet.write(row, 35,rcm_amount  ,styles['left_alignment']) # rcm amount

        worksheet.write(row, 36,sgstrcm_percent  ,styles['left_alignment']) # sgstrcm percent
        worksheet.write(row, 37,sgstrcm_amount  ,styles['left_alignment']) # sgstrcm amount
        worksheet.write(row, 38,cgstrcm_percent  ,styles['left_alignment']) # cgstrcm percent
        worksheet.write(row, 39,cgstrcm_amount  ,styles['left_alignment']) # cgstrcm amount
        worksheet.write(row, 40,igstrcm_percent  ,styles['left_alignment']) # igstrcm percent
        worksheet.write(row, 41,igstrcm_amount  ,styles['left_alignment']) # igstrcm amount



        tot_tax_amount = igst_amount + cgst_amount + sgst_amount 
        worksheet.write(row, 42, tot_tax_amount ,styles['style_number_float']) # Total Tax Amount


        amount_inclusive_tax = ''
        if invoice.company_id.currency_id == invoice.currency_id and invoice.move_type == 'in_refund':
            amount_inclusive_tax = -(line.price_total)
        elif invoice.company_id.currency_id == invoice.currency_id and invoice.move_type == 'in_invoice':
            amount_inclusive_tax = line.price_total
        elif invoice.move_type == 'in_refund':
            amount_inclusive_tax = -(line.credit)
        elif invoice.move_type == 'in_invoice':
            amount_inclusive_tax = line.debit

        worksheet.write(row, 43, amount_inclusive_tax ,styles['style_number_float']) # Amount Inclusive Tax
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
        worksheet.write(row, 44, analytic_accounts or '' ,styles['left_alignment']) # Analytic Account

        worksheet.write(row, 45, partner_id.city or '' ,styles['left_alignment']) # Vendor City
        worksheet.write(row, 46, partner_id.state_id.name or '' ,styles['left_alignment']) # Vendor State
        worksheet.write(row, 47, partner_id.country_id.name or '' ,styles['left_alignment']) # Vendor Country
        move_type = get_selection_label(self,'account.move','move_type',line.move_type)        
        worksheet.write(row, 48, move_type ,styles['left_alignment']) # Invoice Type
        bill_aging = (fields.date.today() - invoice.invoice_date).days
        worksheet.write(row, 49,bill_aging  ,styles['left_alignment']) # Bill ageing

        worksheet.write(row, 50,invoice.date  ,styles['date_style']) # accounting date
        worksheet.write(row, 51,invoice.ref  ,styles['left_alignment']) # bill ref

        y_grn_ref = ''
        if line.sudo().y_stock_picking_ref:
            picking_names = line.sudo().y_stock_picking_ref.filtered(lambda x:x.state == 'done').mapped('name')
            y_grn_ref = ",".join(picking_names)   
        worksheet.write(row, 52,y_grn_ref  ,styles['left_alignment']) # grn ref


        boe_rate = 0
        if invoice.currency_id.name != 'INR' and line.price_subtotal != 0:
            boe_rate = line.debit/line.price_subtotal
        worksheet.write(row, 53,boe_rate  ,styles['left_alignment']) # boe rate ref
        worksheet.write(row, 54,invoice.invoice_payment_term_id.name  ,styles['left_alignment']) # Payment Terms
                
        return 54

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




    def button_download_xlsx_report(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        report_name = "Purchase Register Report"
        worksheet = workbook.add_worksheet(report_name)
        worksheet.freeze_panes(2,5)
        worksheet.set_column('A:C', 15)
        worksheet.set_column('D:D', 20)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 15)
        worksheet.set_column('G:AR', 15)
        styles = self.get_report_styles(workbook)
        worksheet.merge_range('U1:V1', report_name,styles['main_heading_style'])
        
        headers = self.get_headers()
        row = 1
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, styles['column_heading_style'])
        row +=1
        domain = self.get_purchase_register_domain()
        invoice_ids = self.env['account.move'].search(domain)
        
        for invoice in invoice_ids:
            for line in invoice.invoice_line_ids.filtered(lambda x:x.product_id):
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

