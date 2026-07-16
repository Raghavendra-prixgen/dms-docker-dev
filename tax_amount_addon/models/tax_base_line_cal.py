from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import pdb
from datetime import datetime
import json

class AccountMove(models.Model):
    _inherit = 'account.move'

    y_tds_amount = fields.Float(string="TDS Amount",compute="_compute_total_tax_amount_totals",store=True)
    y_tcs_amount = fields.Float(string="TCS Amount",compute="_compute_total_tax_amount_totals",store=True)
    y_sgst_amount = fields.Float(string="SGST Amount",compute="_compute_total_tax_amount_totals",store=True)
    y_cgst_amount = fields.Float(string="CGST Amount",compute="_compute_total_tax_amount_totals",store=True)
    y_igst_amount = fields.Float(string="IGST Amount",compute="_compute_total_tax_amount_totals",store=True)

    @api.depends('invoice_line_ids.y_line_tax_totals')
    def _compute_total_tax_amount_totals(self):
        for move in self:
            tot_tds_amount = 0
            tot_tcs_amount = 0
            tot_sgst_amount = 0
            tot_cgst_amount = 0
            tot_igst_amount = 0
            for line in move.invoice_line_ids:
                tax_dict = line._get_tax_line_group_values()
                if tax_dict:
                    tot_igst_amount += tax_dict.get('IGST') or 0
                    tot_cgst_amount += tax_dict.get('CGST') or 0
                    tot_sgst_amount += tax_dict.get('SGST') or 0
                    tot_tcs_amount += tax_dict.get('TCS') or 0
                    tot_tds_amount += tax_dict.get('TDS') or 0

            move.y_tds_amount = tot_tds_amount
            move.y_tcs_amount = tot_tcs_amount
            move.y_sgst_amount = tot_sgst_amount
            move.y_cgst_amount = tot_cgst_amount
            move.y_igst_amount = tot_igst_amount


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    y_line_tax_totals = fields.Json(string="Invoice Line Tax Totals",compute='_compute_y_line_tax_totals',exportable=False,store=True)
    
    @api.depends_context('lang')
    @api.depends('price_unit', 'price_subtotal', 'price_total', 'currency_id','tax_ids')
    def _compute_y_line_tax_totals(self):
        for line in self:
            line.y_line_tax_totals = ''
            if line.tax_ids:
                if line.display_type not in ('product', 'cogs'):
                    continue
                base_lines = line.move_id._prepare_product_base_line_for_taxes_computation(line)
                self.env['account.tax']._add_tax_details_in_base_line(base_lines,line.company_id)
                tax_dict = {}
                if base_lines.get('tax_details'):
                    tax_values = base_lines.get('tax_details').get('taxes_data')
                    if tax_values:
                        for tax in tax_values:
                            tax_id = tax['tax']['id']
                            tax_dict.update({tax_id:tax.get('tax_amount')})
                        json_object = json.dumps(tax_dict,indent=4, sort_keys=True, default=str)                
                        line.y_line_tax_totals = json_object
                                       

    def _get_tax_line_group_values(self):
        # return : {} ==> dictionary contain list of tax groups and tax rates and amount
        tax_group_dict = {}
        for val in self.env['account.tax.group'].search([]):
            tax_group_dict.update({val.name:0.0,"{}_RATE".format(val.name):''})
        if self.y_line_tax_totals:
            line_tax_dict = json.loads(self.y_line_tax_totals)
            for tax in line_tax_dict:
                tax_amount = line_tax_dict.get(tax)
                tax_value = self._get_tax_line_dict_values(int(tax),tax_amount,tax_group_dict)
        return tax_group_dict

    def _get_tax_line_dict_values(self,tax_id,tax_amount,tax_group_dict):
        tax_id = self.env['account.tax'].search([('id','=',tax_id)])
        residue = tax_id.amount - int(tax_id.amount)
        tax_rate = round(tax_id.amount,1) if residue > 0 else int(tax_id.amount)
        tax_group_dict.update({tax_id.tax_group_id.name:tax_amount,"{}_RATE".format(tax_id.tax_group_id.name):"{}".format(tax_rate)})


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    y_line_tax_totals = fields.Json(string="Purchase Line Tax Totals",compute='_compute_y_line_tax_totals',exportable=False,store=True)

    @api.depends('price_unit','product_qty', 'currency_id','taxes_id','discount')
    def _compute_y_line_tax_totals(self):
        for line in self:
            AccountTax = self.env['account.tax']
            line.y_line_tax_totals = ''
            if line.taxes_id and line.display_type not in ('line_section','line_note'):
                base_lines = line._prepare_base_line_for_taxes_computation()
                self.env['account.tax']._add_tax_details_in_base_line(base_lines, line.company_id)
                tax_dict = {}
                if base_lines.get('tax_details'):
                    tax_values = base_lines.get('tax_details').get('taxes_data')
                    if tax_values:
                        for tax in tax_values:
                            tax_id = tax['tax']['id']
                            tax_dict.update({tax_id:tax.get('tax_amount')})
                        json_object = json.dumps(tax_dict,indent=4, sort_keys=True, default=str)                
                        line.y_line_tax_totals = json_object
            # dd = line._get_tax_line_group_values()

    def _get_tax_line_group_values(self):
        # return : {} ==> dictionary contain list of tax groups and tax rates and amount
        tax_group_dict = {}
        for val in self.env['account.tax.group'].search([]):
            tax_group_dict.update({val.name:0.0,"{}_RATE".format(val.name):''})
        if self.y_line_tax_totals:
            line_tax_dict = json.loads(self.y_line_tax_totals)
            for tax in line_tax_dict:
                tax_amount = line_tax_dict.get(tax)
                tax_value = self._get_tax_line_dict_values(int(tax),tax_amount,tax_group_dict)
        return tax_group_dict

    def _get_tax_line_dict_values(self,tax_id,tax_amount,tax_group_dict):
        tax_id = self.env['account.tax'].search([('id','=',tax_id)])
        residue = tax_id.amount - int(tax_id.amount)
        tax_rate = round(tax_id.amount,1) if residue > 0 else int(tax_id.amount)
        tax_group_dict.update({tax_id.tax_group_id.name:tax_amount,"{}_RATE".format(tax_id.tax_group_id.name):"{} %".format(tax_rate)})


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    y_line_tax_totals = fields.Json(string="Sale Line Tax Totals",compute='_compute_y_line_tax_totals',exportable=False,store=True)

    @api.depends_context('lang')
    @api.depends('product_uom_qty','discount','price_unit', 'currency_id','tax_id')
    def _compute_y_line_tax_totals(self):
        for line in self:
            line.y_line_tax_totals = ''
            if line.tax_id and line.display_type not in ('line_section','line_note'):
                base_lines = line._prepare_base_line_for_taxes_computation()
                self.env['account.tax']._add_tax_details_in_base_line(base_lines,line.company_id)
                tax_dict = {}
                if base_lines.get('tax_details'):
                    tax_values = base_lines.get('tax_details').get('taxes_data')
                    if tax_values:
                        for tax in tax_values:
                            tax_id = tax['tax']['id']
                            tax_dict.update({tax_id:tax.get('tax_amount')})
                        json_object = json.dumps(tax_dict,indent=4, sort_keys=True, default=str)                
                        line.y_line_tax_totals = json_object        

    def _get_tax_line_group_values(self):
        # return : {} ==> dictionary contain list of tax groups and tax rates and amount
        tax_group_dict = {}
        for val in self.env['account.tax.group'].search([]):
            tax_group_dict.update({val.name:0.0,"{}_RATE".format(val.name):''})

        if self.y_line_tax_totals:
            line_tax_dict = json.loads(self.y_line_tax_totals)
            for tax in line_tax_dict:
                tax_amount = line_tax_dict.get(tax)
                tax_value = self._get_tax_line_dict_values(int(tax),tax_amount,tax_group_dict)
        return tax_group_dict

    def _get_tax_line_dict_values(self,tax_id,tax_amount,tax_group_dict):
        tax_id = self.env['account.tax'].search([('id','=',tax_id)])
        residue = tax_id.amount - int(tax_id.amount)
        tax_rate = round(tax_id.amount,1) if residue > 0 else int(tax_id.amount)
        tax_group_dict.update({tax_id.tax_group_id.name:tax_amount,"{}_RATE".format(tax_id.tax_group_id.name):"{} %".format(tax_rate)})