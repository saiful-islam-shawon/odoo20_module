{
    "name": "Zencore Zaintagro Sales Portal",
    "version": "20.0.1.6.2",
    "summary": "Secure responsive website quotation creation using Odoo 20 sales logic",
    "category": "Website/Website",
    "author": "Saiful Islam Shawon",
    "license": "LGPL-3",
    "depends": [
        "website",
        "portal",
        "sale_management",
        "sale_stock",
        "sale_crm",
        "sale_margin",
        "utm",
    ],
    "data": [
        "security/sales_portal_groups.xml",
        "views/website_menu.xml",
        "views/sales_portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "zencore_zaintagro_sales_portal/static/src/scss/sales_portal.scss",
            "zencore_zaintagro_sales_portal/static/src/interactions/sales_portal.js",
        ],
    },
    "application": True,
    "installable": True,
}
