# -*- coding: utf-8 -*-
{
    'name': 'Launchmind Blog',
    'version': '18.0.1.0.1',
    'category': 'Website/Blog',
    'summary': 'AI-generated, GEO-optimized blog articles published automatically to your Odoo Website',
    'description': """
Launchmind Blog Connector
=========================

Connect your Odoo Website to Launchmind.io and let AI-generated, GEO and SEO
optimized blog articles flow into your native Odoo blog automatically — no
copy-paste, no scheduling, no extra dashboards.

Features
--------
* One-click connect with your Launchmind API key
* Articles arrive as native ``blog.post`` records, fully editable in Odoo
* Optimized for Google AND AI search engines (ChatGPT, Perplexity, Claude)
* 8 languages supported (EN, NL, DE, FR, ES, IT, PL, HI)
* Pushed in real-time via webhook — no cron job needed on your side
* Cover images, tags, author and meta descriptions all preserved
* Works with Odoo's built-in SEO (canonical, sitemap.xml, schema.org)

Requirements
------------
* An active Launchmind.io subscription (https://launchmind.io)
* Odoo 18.0 Community or Enterprise
* Public HTTPS URL (your Odoo Website must be reachable from launchmind.io)
""",
    'author': 'Launchmind',
    'website': 'https://launchmind.io',
    'support': 'support@launchmind.io',
    'license': 'LGPL-3',
    'depends': [
        'website_blog',
        'website',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': [
        'static/description/images/main_screenshot.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
