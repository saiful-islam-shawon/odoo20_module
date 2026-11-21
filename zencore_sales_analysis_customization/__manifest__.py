{
    'name': 'Zencore Sales Analysis Customization',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Segregate sold products and free products per customer in Sales Analysis, editable free quantity on Sale Orders, and Stock In/Out/Closing in Inventory Stock Report',
    'description': """
Zencore Sales Analysis Customization
====================================
- Segregates commercial sold products and promotional free products per customer and per product in Sales Analysis.
- Displays commercial sold products first, followed by a 'Total Free Product' summary row and individual free product lines.
- Recalculates customer/product group headers to include only commercial sold product quantities, total free quantities, and totals.
- Displays commercial valuation in the Total column of the 'Total Free Product' row with blank quantity cells.
- Mirrors the exact layout in Excel export (.xlsx) and isolates selected records/groups.
- Allows sales users to directly edit the Quantity on promotional free product lines in Quotations / Sale Orders with 100% free pricing and auto-reset protection.
- Adds Stock In, Stock Out, and Closing Stock columns in the Inventory Stock Report list view.
    """,
    'author': 'Zencore / Antigravity',
    'license': 'LGPL-3',
    'depends': ['sale', 'sale_loyalty', 'web', 'stock', 'purchase', 'stock_account'],
    'data': [
        'views/product_views.xml',
        'views/sale_order_views.xml',
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
