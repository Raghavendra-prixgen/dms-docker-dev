{
    "name": "DMS Community UI Enhancements",
    "summary": "DMS Community UI enterprise theme",
    "description": """
    """,
    "version": "18.0.0.1",
    "category": "",
    "license": "LGPL-3",
    "author": "Prixgen Tech Solutions Pvt. Ltd.",
    "website": "https://www.prixgen.com",
    "orgin":'Product specific',
    "depends": ["web"],
    "data": [
        'views/webclient_templates.xml',
        'views/remove_module.xml',
    ],

    "assets": {
        "web.assets_frontend": [
            'odoo_community_ui/static/src/scss/login.scss'
        ],
        "web.assets_backend": [   
            'odoo_community_ui/static/src/xml/WebClient.xml',
            'odoo_community_ui/static/src/xml/navbar/sidebar.xml', 
            'odoo_community_ui/static/src/xml/systray_items/user_menu.xml',
            'odoo_community_ui/static/src/js/SidebarBottom.js',  
            'odoo_community_ui/static/src/js/WebClient.js', 
            'odoo_community_ui/static/src/scss/layout.scss',
            'odoo_community_ui/static/src/scss/navbar.scss', 
            'odoo_community_ui/static/src/js/navbar.js',
        ],
    },
    
    "installable": True,
    "application": True,
    "auto_install": False,
}
