# -*- coding: utf-8 -*-

from . import model
from . import wizard

def pre_init(cr):
        create_purchase_register_data_sp(cr)

def create_purchase_register_data_sp(cr):
	query = """
        CREATE OR REPLACE VIEW purchase_register_report AS (
                SELECT 
                row_number() OVER () as id,
                move.move_type AS move_type_name,
                move.id AS y_move_id,
                move.name AS y_bill_num,
                move.ref AS y_invoice_ref,
                move.invoice_date AS y_bill_date,
                move.payment_state AS y_payment_state,
                line.name AS y_label,
                (CASE WHEN res_curr.name != 'INR' AND line.debit != 0 THEN (line.debit / line.price_subtotal) END) AS y_boe_rate,
                pl.id AS y_purchase_line_id,
                po.id AS y_purchase_order_id,
                po.date_order AS y_purchase_order_date,
                line.product_id AS y_product_id,
                pt.id AS y_product_tmpl_id,
                pt.detailed_type AS y_product_type,
                uom.id AS y_uom_id,
                pro_categ.id AS y_product_category_id,
                line.id AS y_move_line_id,
                line.quantity AS y_quantity,
                line.price_unit AS y_price_unit,
                line.price_subtotal AS y_price_subtotal,
                line.journal_id AS y_journal_id,
                line.account_id AS y_account_id,
                line.partner_id AS y_partner_id,
                line.currency_id AS y_currency_id,
                line.discount AS discount,
                line.date AS y_accounting_date,
                array_agg(tax_rel.account_tax_id) AS y_tax_id_list,
                partner.ref AS partner_ref,
                partner.vat AS y_gst_name,
                partner.state_id AS y_partner_state_id,
                partner.city AS y_partner_city,
                partner.country_id AS y_partner_country_id,
                product.default_code as product_ref
                FROM account_move move
                LEFT JOIN account_move_line line ON move.id = line.move_id
                LEFT JOIN purchase_order_line pl ON pl.id = line.purchase_line_id
                LEFT JOIN purchase_order po ON po.id = pl.order_id
                LEFT JOIN res_partner partner ON partner.id = line.partner_id
                LEFT JOIN product_product product ON product.id = line.product_id
                LEFT JOIN product_template pt ON pt.id = product.product_tmpl_id
                LEFT JOIN product_category pro_categ ON pro_categ.id = pt.categ_id
                LEFT JOIN uom_uom uom ON uom.id = pt.uom_id
                LEFT JOIN res_currency res_curr ON res_curr.id = line.currency_id
                LEFT JOIN account_move_line_account_tax_rel tax_rel ON line.id  = tax_rel.account_move_line_id
                where move.state = 'posted' AND line.product_id is Not null AND (move_type = 'in_invoice' OR move_type = 'in_refund') {}
                group by res_curr.name,line.name,line.id,pl.id,po.id,partner.city,pro_categ.id,pt.id,pt.detailed_type,uom.id, move.move_type,move.id,line.quantity,line.price_unit,line.discount,line.price_subtotal,line.journal_id,line.account_id,line.partner_id,line.currency_id,line.date,
                move.payment_state,move.move_type,move.ref,partner.ref,partner.vat,partner.state_id,partner.country_id,
                line.product_id,product.default_code,move.name,"""
	cr.execute(query)