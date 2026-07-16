
{
    'name': "Community to Enterprise",
    'version': "18.0.2.0",
    'author': "Prixgen Tech Solutions Pvt. Ltd.",
    'category': "Integration",
    'data': [
        'security/ir.model.access.csv',
        'security/data.xml',
        'views/sale_order.xml',
        # 'views/product_tally_sync_views.xml',
        'views/tally_product_api.xml',
        'wizards/distributor_partner.xml',
        # 'views/res_config.xml',
        # 'wizards/reject_wizard.xml',
        'wizards/tallyPushWizard.xml',
        # 'views/menu.xml',
        'views/sale_register_report_inherit.xml'
        
        
    # 'views/crm_lead.xml',
    # 'views/res_partner.xml',
        ],
    'demo': [],
    'depends': ['base','sale_management','sale','mail','sale_stock','stock','purchase','purchase_stock','dms_custom_fileds','sale_register_report_18'],
    
    'installable': True,
    'application': False,
    'license': 'LGPL-3',

}

#dms_custom_fileds is added becuase of taluk and district master which is defined in dms_custom_fileds app
