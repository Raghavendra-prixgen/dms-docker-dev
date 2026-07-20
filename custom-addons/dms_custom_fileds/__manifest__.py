# -*- coding: utf-8 -*-
{
    'name': "DMS Custom Fields",

    'summary': """
        """,

    'description': """ """,
    'module_type':'official',
    'author': "Prixgen Tech Solutions Pvt. Ltd.",
    'company': "Prixgen Tech Solutions Pvt. Ltd.",
    'website': "https://www.prixgen.com",
    'category': 'Customization',
    'origin': 'base',
    'version': '18.0.0.2',
    'license': 'LGPL-3',

    'depends': ['base','stock','product',],

    'data': [
        'security/ir.model.access.csv',
        'views/product_groups.xml',
        'views/res_partner.xml',
    ],

    'installable': True,
    'auto_install': False,
}
