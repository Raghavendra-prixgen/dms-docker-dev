{
    'name': 'Sale Register Report 18 - 18.0.2.5',
    'version': '18.0.0.1',
    'category': 'Sale',
    'summary': 'Sale Register Report 18',
    'App origin':'Base',
    'description': """
		This module get the Sale summary between the given dates .
    				""",
    'author': "Prixgen Tech Solutions Pvt. Ltd.",
    'company': 'Prixgen Tech Solutions Pvt. Ltd.',
    'website': 'https://www.prixgen.com',   
    'module_type':'official', 

    'depends': ['hr', 'sale','stock','product','account','base','tax_amount_addon','contact_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/sales_report.xml',
    ],


    'installable': True,
    'auto_install': False
}