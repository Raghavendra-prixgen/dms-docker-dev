{
    "name": "Contact Base - 18.0.1.9",
    "version": "18.0.0.1",
    'license': 'LGPL-3',
    'author': 'Prixgen Tech Solutions Pvt. Ltd.',
    'company': 'Prixgen Tech Solutions Pvt. Ltd.',
    'website': 'https://www.prixgen.com',
    "summary": """
    Automatically create the customer number from a sequence when a customer is being created.
    """,
    "description": """
        1. Automatically create the customer number from a sequence when a customer is being created.The customer number can be configured in the sequence "Customer Number".
        2. Instead of GST code, functionality is based on TIN Number which is same as GST Code
        3. customer approval while sale order confirmation
        4. vendor approval while purchase order confirmation
        5. contact reject reason functionality added
    """,
    'module_type':'official',
    "category": "Sales",
    "App Origin": "Base",
    "depends": [
        "base",
        "sale","contacts","product","account",'purchase','sales_team','delivery','crm','user_approval_code'
    ],
    #crm_base given for sales_report implementation
    "data": [
        "security/ir.model.access.csv",
        "security/contact_approval.xml",
        "views/partner.xml",
        "views/partner_approval.xml",
        
    ],
    "installable": True,
    "auto_install": False,
    'uninstall_hook':'test_uninstall_hook'
}
