{
    'name': "Sale Base Odoo 18 --version 18.0.1.4",
    'summary': """ """,
    'description': """
        Included Functionalities - 
        1. Document Type 
        2. Sequence on Document Type
        3. Short Close For Sale Order
        4. Blanket sale order
        """,
    'module_type':'official',
    'author': "Prixgen Tech Solutions Pvt. Ltd.",
    'website': "https://www.prixgen.com",
    'company': "Prixgen Tech Solutions Pvt. Ltd.",
    'category': 'Sale',
    'version': '18.0.0.1',
    'license': 'LGPL-3',
    'App origin':"Base",
    'depends': ['base','mail','product','sale_management','sale','crm','stock','account'],
    'data': [
        'data/data.xml',
        'security/sales_team_security.xml',
        'security/ir.model.access.csv',
        'views/res_partner.xml',
        'views/views.xml',
        'views/sale_restriction.xml',
        'views/blanket_order_view.xml',
        'views/customer_view.xml',
        'views/sale_short_close.xml',
        'wizard/create_sale_quotation_view.xml',
        'wizard/saleorder_short_close_wizard.xml',
    ],
}
