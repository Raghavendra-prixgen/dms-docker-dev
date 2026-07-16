{
    'name': 'Attach Picking to Invoice/Bills - 18.0.3.0',
    'version': '18.0.0.1',
    'summary': 'Attach Picking to Invoice/Bills',
    'module_type':'official',
    'author': 'Prixgen Tech Solutions Pvt. Ltd.',
    'company': 'Prixgen Tech Solutions Pvt. Ltd.',
    'website': 'https://www.prixgen.com',
    'description':"""Attach Picking to Invoice/Bills""", 
    'App origin':'Base',
    'license': 'LGPL-3',
    'depends':['base','account','purchase','sale','stock','purchase_stock','sale_stock'],
    'data':[
        'security/security.xml',
        'views/picking_to_accounts.xml',
        ],
    'installable': True,
    'auto_install': False,
}

