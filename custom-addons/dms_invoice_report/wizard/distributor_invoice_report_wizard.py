from odoo import models, fields, api, _
from datetime import datetime, timedelta,date
import calendar
from xlwt import easyxf
import xlwt
import io
import base64
import datetime
import math
import pdb
from odoo.tools.misc import file_path, xlsxwriter
import json
from odoo.exceptions import AccessError, UserError, ValidationError



class AccountMoveLineCustomization(models.Model):
    _inherit = 'account.move.line'
    
    tally_invoice_number = fields.Char(string="Tally Invoice Number",related='move_id.tally_invoice_number')
    product_reference = fields.Char(related='product_id.default_code')
    product_display_name = fields.Char(related='product_id.name')

    
class DistributorInvoiceReportWizard(models.TransientModel):
    _name = "distributor.invoice.report.wizard"
    _description = " "
        
    y_start_date = fields.Date(string="Start Date")
    y_end_date = fields.Date(string="End Date")
    y_project_report = fields.Binary('Report')
    y_file_name = fields.Char('File Name')
    y_project_report_printed = fields.Boolean('Invoice Report Printed')
    y_company_ids = fields.Many2many('res.company')
    y_move_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Credit Note'),
        ('in_refund', 'Vendor Credit Note'),
        ])
    y_invoice_status = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
        ], string='Invoice Status')
    
    @api.constrains('start_date','end_date')
    def _check_dates(self):
        for rec in self:
            if rec.y_end_date < rec.y_start_date:
                raise ValidationError(_("""End Date Can not be less than Start Date"""))
            
    # def _convert_to_tax_base_line_dict(self,line,price_unit):
    #     """ Convert the current record to a dictionary in order to use the generic taxes computation method
    #     defined on account.tax.
    #     :return: A python dictionary.
    #     """
    #     self.ensure_one()
    #     is_invoice = line.move_id.is_invoice(include_receipts=True)
    #     sign = -1 if line.move_id.is_inbound(include_receipts=True) else 1

    #     return self.env['account.tax']._convert_to_tax_base_line_dict(
    #         line,
    #         partner=line.partner_id,
    #         currency=line.currency_id,
    #         product=line.product_id,
    #         taxes=line.tax_ids,
    #         price_unit= price_unit if is_invoice else line.amount_currency,
    #         quantity=line.quantity if is_invoice else 1.0,
    #         discount=line.discount if is_invoice else 0.0,
    #         account=line.account_id,
    #         analytic_distribution=line.analytic_distribution,
    #         price_subtotal=sign * line.amount_currency,
    #         is_refund=line.is_refund,
    #         rate=(abs(line.amount_currency) / abs(line.balance)) if line.balance else 1.0
    #     )


    def get_distributor_invoice_report(self):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Invoice Report')

        amount_tot = 0.0
        column_heading_style = workbook.add_format({'bold': True, 'align': 'center'})
        left_alignment = workbook.add_format({'align': 'left'})
        center_alignment = workbook.add_format({'align': 'center'})

        column_headers = [
            "Accounting Date", "Distributor Name", "Invoice Type", "Invoice Number", "Tally Invoice Number", 
            "Customer Name", "Sales Person", "Sales Team", "GST Number", "State", 
            "District", "Taluk", "Product Category", "Item Group", "Product Group 1", 
            "Internal Reference", "Product", "Label", "Product wt", "Total weight", "Qty", 
            "UOM", "Sales MRP", "Basic Price", "Trade Disc. %", "Trade Disc. Amount", 
            "Total Trade Disc. Amount", "Cash Disc. %", "Cash Disc. Amount", "Total Cash Disc. Amount", 
            "Total Basic Amount", "Total Tax Amount", "Net Total", "Status", "Delivery Address"
        ]

        for col_num, header in enumerate(column_headers):
            worksheet.write(0, col_num, header, column_heading_style)

        state_info = self.y_invoice_status if self.y_invoice_status else 'posted'
        row = 1

        domain = [('invoice_date', '>=', self.y_start_date), 
                ('invoice_date', '<=', self.y_end_date), 
                ('state', '=', state_info)]

        if len(self.y_company_ids) > 1:
            domain.append(('company_id', 'in', self.y_company_ids.ids))
            domain.append(('move_type', '=', self.y_move_type))
        else:
            domain.append(('company_id', '=', self.y_company_ids.ids[0]))
            domain.append(('move_type', '=', self.y_move_type))

        format2 = workbook.add_format({'num_format': 'dd/mm/yyyy', 'align': 'left'})
        account_move_ids = self.env['account.move'].search(domain)

        for invoice in account_move_ids:
            partner_id = invoice.partner_id
            # Process each invoice line
            for line in invoice.invoice_line_ids:
                product_id = line.product_id
                # Calculate move type
                move_type_mapping = {
                    'entry': "Journal Entry",
                    'out_invoice': "Customer Invoice",
                    'out_refund': "Customer Credit Note",
                    'in_invoice': "Vendor Bill",
                    'in_refund': "Vendor Credit Note",
                    'out_receipt': "Sales Receipt",
                    'in_receipt': "Purchase Receipt"
                }
                move_type = move_type_mapping.get(invoice.move_type, "")
                # Calculate discounts and prices
                unit_base_price = line.price_unit
                unit_discount_amount = (line.price_unit * line.discount / 100) if line.discount > 0 else 0
                unit_base_price -= unit_discount_amount

                unit_cash_discount = (unit_base_price * line.cash_discount / 100) if line.cash_discount > 0 else 0
                unit_base_price -= unit_cash_discount

                discount_amount = (line.price_unit * line.quantity * line.discount / 100)
                cash_discount = line.price_subtotal - line.tally_amount
                base_price = (line.price_unit * line.quantity) - (discount_amount + cash_discount)

                # Calculate tax
                tax_amount = line.tax_ids[:1].amount if line.tax_ids else 0.0
                total_tax_amount = (base_price * tax_amount) / 100
                net_total = base_price + total_tax_amount

                worksheet.write(row, 0, invoice.invoice_date, format2)
                worksheet.write(row, 1, invoice.company_id.name, left_alignment)
                worksheet.write(row, 2, move_type, left_alignment)
                worksheet.write(row, 3, invoice.name, left_alignment)
                worksheet.write(row, 4, invoice.tally_invoice_number, left_alignment)
                worksheet.write(row, 5, partner_id.name, left_alignment)
                worksheet.write(row, 6, invoice.invoice_user_id.name, left_alignment)
                worksheet.write(row, 7, invoice.team_id.name, left_alignment)
                worksheet.write(row, 8, partner_id.vat, left_alignment)
                worksheet.write(row, 9, partner_id.state_id.name, left_alignment)
                worksheet.write(row, 10, partner_id.district_id.name, left_alignment)
                worksheet.write(row, 11, partner_id.taluk_id.name, left_alignment)
                worksheet.write(row, 12, product_id.categ_id.name, left_alignment)
                worksheet.write(row, 13, product_id.y_item_group.y_name, left_alignment)
                worksheet.write(row, 14, product_id.y_product_group_1.y_name, left_alignment)
                worksheet.write(row, 15, product_id.default_code, left_alignment)
                worksheet.write(row, 16, product_id.name, left_alignment)
                worksheet.write(row, 17, line.name, left_alignment)  
                worksheet.write(row, 18, product_id.weight, center_alignment)
                worksheet.write(row, 19, product_id.weight * line.quantity, center_alignment)
                worksheet.write(row, 20, line.quantity, center_alignment)
                worksheet.write(row, 21, line.product_uom_id.name, left_alignment)
                worksheet.write(row, 22, line.price_unit, center_alignment)
                worksheet.write(row, 23, round(unit_base_price, 2), center_alignment)
                worksheet.write(row, 24, line.discount, center_alignment)
                worksheet.write(row, 25, round(unit_discount_amount * line.quantity, 2), center_alignment)
                worksheet.write(row, 26, round(discount_amount, 2), center_alignment)
                worksheet.write(row, 27, line.cash_discount, center_alignment)
                worksheet.write(row, 28, round(unit_cash_discount, 2), center_alignment)
                worksheet.write(row, 29, round(cash_discount, 2), center_alignment)
                worksheet.write(row, 30, round(base_price, 2), center_alignment)
                worksheet.write(row, 31, round(total_tax_amount, 2), center_alignment)
                worksheet.write(row, 32, round(net_total, 2), center_alignment)
                worksheet.write(row, 33, invoice.state, center_alignment)
                worksheet.write(row, 34, invoice.delivery_address, left_alignment)
                
                row += 1
            special_discount_diff = round(sum(invoice.invoice_line_ids.mapped('tally_amount')), 2) - invoice.tally_taxable_amount
            if special_discount_diff > 0:
                print("Special Discount Difference:", special_discount_diff)
                worksheet.write(row, 0, invoice.invoice_date, format2)
                worksheet.write(row, 1, invoice.company_id.name, left_alignment)
                worksheet.write(row, 2, move_type, left_alignment)
                worksheet.write(row, 3, invoice.name, left_alignment)
                worksheet.write(row, 4, invoice.tally_invoice_number, left_alignment)
                worksheet.write(row, 5, partner_id.name, left_alignment)
                worksheet.write(row, 6, invoice.invoice_user_id.name, left_alignment)
                worksheet.write(row, 7, invoice.team_id.name, left_alignment)
                worksheet.write(row, 8, partner_id.vat, left_alignment)
                worksheet.write(row, 9, partner_id.state_id.name, left_alignment)
                worksheet.write(row, 10, partner_id.district_id.name, left_alignment)
                worksheet.write(row, 11, partner_id.taluk_id.name, left_alignment)
                worksheet.write(row, 17, "Special Discount", left_alignment)  
                worksheet.write(row, 25, invoice.special_disc_on_sales, center_alignment)
                worksheet.write(row, 26, special_discount_diff, center_alignment)
                worksheet.write(row, 34, invoice.delivery_address, left_alignment)
                
                row += 1

        workbook.close()
        xlsx_data = output.getvalue()

        self.y_project_report = base64.encodebytes(xlsx_data)
        self.y_file_name = 'Invoice Report.xlsx'
        self.y_project_report_printed = True

        return {
            'name': "Invoice Report",
            'view_mode': 'form',
            'res_id': self.id,
            'res_model': 'distributor.invoice.report.wizard',
            'view_type': 'form',
            'type': 'ir.actions.act_window',
            'context': self.env.context,
            'target': 'new',
        }