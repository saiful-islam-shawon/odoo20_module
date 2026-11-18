{
    'name': 'Zencore Sales Analysis Customization',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Segregate sold products and free products per customer in Sales Analysis',
    'description': """
Zencore Sales Analysis Customization
====================================
- Segregates commercial sold products and promotional free products per customer in Sales Analysis.
- Displays commercial sold products first, followed by a 'Total Free Product' summary row and individual free product lines.
- Recalculates customer group headers to include only commercial sold product quantities and totals.
- Hides the free product summary row if a customer has 0 free products.
- Preserves standard Odoo behavior for ungrouped views and the bottom Grand Total row.
    """,
    'author': 'Zencore / Antigravity',
    'license': 'LGPL-3',
    'depends': ['sale', 'sale_loyalty', 'web'],
    'data': [
        'views/sale_report_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'zencore_sales_analysis_customization/static/src/views/sales_analysis_list_renderer.scss',
            'zencore_sales_analysis_customization/static/src/views/sales_analysis_list_renderer.js',
            'zencore_sales_analysis_customization/static/src/views/sales_analysis_list_view.js',
            'zencore_sales_analysis_customization/static/src/views/sales_analysis_list_renderer.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
