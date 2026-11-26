# -*- coding: utf-8 -*-
{
    'name': 'Launchmind Blog',
    'version': '18.0.1.6.0',
    'category': 'Website/Blog',
    'summary': 'AI-generated, GEO-optimized blog articles published automatically to your Odoo Website',
    'description': """
Launchmind Blog Connector
=========================

Connect your Odoo Website to Launchmind.io and let AI-generated, GEO and SEO
optimized blog articles flow into your native Odoo blog automatically, with no
copy-paste, no scheduling, no extra dashboards.

Features
--------
* Explicit website/blog selection and signed installation confirmation
* Articles arrive as native ``blog.post`` records; sync overwrites managed fields
* Source changes update posts; hidden or unpublished source articles become drafts
* Daily checks restore archived, drafted or deleted posts while the source stays live
* Optimized for Google AND AI search engines (ChatGPT, Perplexity, Claude)
* Dutch-first pilot; other languages require separate native validation
* Webhook delivery with scheduled discovery, notifications and daily health
* Cover and inline images stored locally when delivered, with remote fallback
* Native exact-label tags, connector-owned authors and meta descriptions
* Native SEO plus Article JSON-LD only when no article owner exists
* Customer-first discovery and opt-in telemetry; IndexNow disabled by default
* Timestamped HMAC with durable replay protection after enrollment

Requirements
------------
* An active Launchmind.io subscription (https://launchmind.io)
* Odoo 18.0 Community or Enterprise
* Hosting that permits custom Python addons (not standard Odoo Online)
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
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/media_cover.xml',
    ],
    'images': [
        'static/description/images/main_screenshot.png',
    ],
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
