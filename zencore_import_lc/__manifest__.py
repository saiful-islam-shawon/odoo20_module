{
    'name': 'Import LC',
    'version': '20.0.3.0.7',
    'summary': 'Import Letter of Credit workflow for Purchase Orders',
    'description': """
        Enterprise Import Letter of Credit workflow for Odoo 20.
        ========================================================

        Features:
        - RFQ/PO as the source for PI commercial and logistics information
        - Configurable ports and container types
        - One approved Proforma Invoice per Import LC
        - Manual bank-issued LC number (mandatory; never auto-generated)
        - Single-PI Commercial Invoice, Vendor Bill and Receipt/GRN flow
        - LC amendments, landed costs, other charges and document traceability
    """,
    'category': 'bd_calling',
    'author': 'Mehedi Hasan',
    'website': 'https://www.zencoreltd.com',
    'license': 'LGPL-3',
    
    'depends': ['base', 'web', 'mail', 'purchase', 'purchase_stock', 'account', 'accountant', 'mrp', 'stock_landed_costs'],
    
    'data': [
        'security/lc_security.xml',
        'security/ir.access.csv',
        'data/lc_sequence.xml',
        'data/container_type_data.xml',
        'data/import_lc_default_data.xml',
        'views/purchase_views.xml',
        'views/lc_views.xml',
        'views/configuration_views.xml',
        'views/import_lc_views.xml',
        'views/payment_terms_views.xml',
        'views/import_ci_views.xml',
        'views/stock_picking_views.xml',
        # 'views/account_move.xml',
        'views/account_views.xml',
        'views/stock_landed_cost_views.xml',
        'views/amendment_views.xml',
        'views/res_user_views.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            'zencore_import_lc/static/src/scss/lc_management.scss',
        ],
    },

    'installable': True,
    'application': True,
    'auto_install': False,
    
    
    
    
   
}
