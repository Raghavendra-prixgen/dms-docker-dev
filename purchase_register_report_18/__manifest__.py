{
    'name': 'Purchase Register Report 18 - 18.0.2.9',
    'version': '18.0.0.1',
    'category': 'Purchase',
    'summary': 'Purchase Register Report 18',
    'App origin':'Base',
    'description': """
		This module get the Purchase summary between the given dates .
    				""",
    'module_type':'official',
    'author': "Prixgen Tech Solutions Pvt. Ltd.",
    'company': 'Prixgen Tech Solutions Pvt. Ltd.',
    'website': 'https://www.prixgen.com',    

    'depends': ['purchase','stock','product','account','base','tax_amount_addon','contact_base','picking_to_accounts'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/purchase_report_wizard.xml',
        'views/purchase_report.xml',
        'views/purchase_report_view.xml',
    ],
    'installable': True,
    'auto_install': False
}
