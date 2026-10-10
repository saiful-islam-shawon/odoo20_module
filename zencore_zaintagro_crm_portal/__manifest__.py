{
    "name": "Zencore Zaintagro CRM Portal",
    "version": "20.0.1.8.0",
    "summary": "Secure website CRM opportunity creation for selected users",
    "category": "Website/Website",
    "author": "Saiful Islam Shawon",
    "license": "LGPL-3",
    "depends": [
        "website",
        "portal",
        "crm",
        "base_geolocalize",
        "utm",
        "website_crm_partner_assign",
    ],
    "data": [
        "security/crm_portal_groups.xml",
        "views/website_menu.xml",
        "views/crm_opportunity_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "zencore_zaintagro_crm_portal/static/src/scss/crm_portal.scss",
            "zencore_zaintagro_crm_portal/static/src/interactions/crm_portal.js",
        ],
    },
    "application": True,
    "installable": True,
}
