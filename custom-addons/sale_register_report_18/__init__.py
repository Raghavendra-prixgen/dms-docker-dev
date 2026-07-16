# -*- coding: utf-8 -*-

from . import models
# from . import wizard

def pre_init(cr):
	create_sale_register_data_sp(cr)



def create_sale_register_data_sp(cr):
	query = """
        CREATE OR REPLACE VIEW sales_register_report AS (
                SELECT 
                row_number() OVER () as id,
                move.move_type AS y_move_type_name,
                move.id AS y_move_id,
                move.invoice_date AS y_invoice_date,
                move.payment_state AS y_payment_state,
                move.name AS y_vendor_entry_ref,
                move.ref AS y_vendor_bill_ref,
		move.invoice_user_id AS y_sales_person_id,
		move.team_id AS y_sales_team_id,
                line.name AS y_label,
                (CASE WHEN res_curr.name != 'INR' THEN (line.price_subtotal) END) AS y_invoice_amount_fc
                sl.id AS y_sale_line_id,
                so.id AS y_sale_order_id,
                so.date_order AS y_sale_order_date,
                line.product_id AS y_product_id,
                pt.id AS product_tmpl_id,
                pt.detailed_type AS product_type,
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
                partner.ref AS y_partner_ref,
                partner.state_id AS y_partner_state_id,
                partner.city AS y_partner_city,
                partner.vat AS y_gst_name,
                partner.country_id AS y_partner_country_id,
                rp.name as y_partner_shipping_id,
		rp.state_id as y_partner_shipping_state_id,
		rp.vat as y_vat,
                product.default_code as y_product_ref 
                FROM account_move move
                LEFT JOIN account_move_line line ON move.id = line.move_id
	 	LEFT JOIN sale_order so on so.name = move.invoice_origin
                LEFT JOIN sale_order_line sl ON sl.order_id = so.id
                LEFT JOIN res_partner partner ON partner.id = move.partner_id
		LEFT JOIN res_partner rp on rp.id = move.partner_shipping_id
                LEFT JOIN product_product product ON product.id = line.product_id
                LEFT JOIN product_template pt ON pt.id = product.product_tmpl_id
                LEFT JOIN product_category pro_categ ON pro_categ.id = pt.categ_id
                LEFT JOIN uom_uom uom ON uom.id = pt.uom_id
                LEFT JOIN res_currency res_curr ON res_curr.id = line.currency_id
                LEFT JOIN account_move_line_account_tax_rel tax_rel ON line.id  = tax_rel.account_move_line_id
                where move.state = 'posted' AND line.product_id is Not null AND (move_type = 'out_invoice' OR move_type = 'out_refund') 
                group by res_curr.name,line.name,line.id,sl.id,so.id,partner.city,pro_categ.id,pt.id,pt.detailed_type,uom.id, move.move_type,move.id,line.quantity,line.price_unit,line.discount,
                rp.state_id ,rp.vat,rp.name,line.price_subtotal,line.journal_id,line.account_id,line.partner_id,line.currency_id,line.date,
                move.payment_state,move.move_type,move.ref,partner.ref,partner.vat,partner.state_id,partner.country_id,
                line.product_id,product.default_code,move.name"""
	cr.execute(query)