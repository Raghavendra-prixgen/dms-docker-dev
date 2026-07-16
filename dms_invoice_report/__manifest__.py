{
    'name': "Distributor Invoice Report",

    'summary': """ """,
    'description': """ """,

    'author': "Prixgen Tech Solutions Pvt. Ltd.",
    'company': "Prixgen Tech Solutions Pvt. Ltd.",
    'website': "https://www.prixgen.com",
    'module_type':'official',

    'category': 'Sale',
    'origin': 'base',
    'version': '18.0.0.1',
    'license': 'LGPL-3',

    'depends': ['sale','account','community_to_enterprise'],

    'data': [
        'security/ir.model.access.csv',
        'wizard/distributor_invoice_report_wizard.xml',
        'wizard/tree_view_aml.xml'
        
    ],
}
