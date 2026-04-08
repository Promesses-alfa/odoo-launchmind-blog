================
Launchmind Blog
================

AI-generated, GEO-optimized blog articles published automatically to your
Odoo Website.

Connect your Odoo Website to Launchmind.io and let the platform push
SEO + GEO optimized articles directly into your native ``website_blog``.

Features
========

* One-click connect with your Launchmind API key
* Articles arrive as native ``blog.post`` records, fully editable in Odoo
* Real-time push via webhook — no cron job needed on the Odoo side
* Optimized for Google AND AI search engines (ChatGPT, Perplexity, Claude)
* 8 languages supported (EN, NL, DE, FR, ES, IT, PL, HI)
* Cover images, tags, author and meta descriptions all preserved
* Idempotent webhook receiver (re-deliveries update, never duplicate)
* Works with Odoo's built-in SEO (canonical, sitemap.xml, schema.org)

Requirements
============

* Odoo 18.0 (Community or Enterprise)
* Active `Launchmind.io <https://launchmind.io>`_ subscription
* Public HTTPS URL on your Odoo Website (required so launchmind.io can
  deliver webhooks to ``/launchmind-blog/webhook``)
* The standard ``website_blog`` module installed (Odoo includes it by
  default)

Installation
============

1. Install **Launchmind Blog** from the Odoo Apps store, or upload the
   module ZIP via *Apps > Update Apps List > Search > Install*.
2. Go to *Settings > Website > Launchmind Blog*.
3. Paste your Launchmind API key (find it in your Launchmind dashboard
   at *Settings > API*).
4. Click **Connect**.

Once connected, your most recent published articles will start arriving
in your Odoo blog within one minute. From then on, every new article you
generate at launchmind.io will appear automatically.

How it works
============

The module exposes one public webhook endpoint:

  ``POST /launchmind-blog/webhook``

  ``Authorization: Bearer <your_launchmind_api_key>``

Launchmind's publish-to-odoo cron POSTs each new article to that endpoint.
The receiver verifies the bearer token against the API key you configured
locally, then upserts a ``blog.post`` record under a "Launchmind Blog"
``blog.blog`` (auto-created on first push).

Each article carries a unique Launchmind id which the receiver stores in
``website_meta_keywords`` as a marker (``lm:<id>``). Re-deliveries of the
same id update the existing post instead of creating a duplicate, which
makes the endpoint safe to retry.

Security
========

* The webhook endpoint requires a valid bearer token matching the API
  key configured locally. Without it, every request returns 401.
* Image fetches from launchmind.io are capped at 5 MB to prevent
  oversized payloads from blowing up Odoo.
* No data is sent to launchmind.io beyond the initial register call
  (which carries your Odoo base URL, version and company name).

License
=======

LGPL-3.0 — see ``LICENSE``.

Support
=======

* Email: support@launchmind.io
* Documentation: https://launchmind.io/docs/odoo
