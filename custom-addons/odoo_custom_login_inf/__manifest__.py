# -*- coding: utf-8 -*-
{
    "name": "DMS Login page ",
    "summary": "DMS Login Page",
    "description": """
    """,
    "version": "18.0.0.1",
    "category": "",
    "license": "LGPL-3",
    "author": "Prixgen Tech Solutions Pvt. Ltd.",
    "website": "https://www.prixgen.com",
    "orgin":'Product specific',
    # any module necessary for this one to work correctly
    "depends": ["base", "base_setup", "web", "auth_signup"],
    "data": [
        "views/right_login_template.xml",
    ],
    'images': ["static/description/walc.png"],

    'assets': {
        'web.assets_frontend': {
            '/odoo_custom_login_inf/static/src/css/web_login_style.css',
            '/odoo_custom_login_inf/static/src/css/style.scss',
        },
    },
}
