===============
Launchmind Blog
===============

Publish Launchmind articles into an explicitly selected native Odoo blog.
The Launchmind monorepo owns the module; the public repository is a generated
release mirror. See ``CHANGELOG.md`` for release changes.

Requirements
============

* Odoo **18.0**, Community or Enterprise, with ``website_blog``.
* Hosting that allows custom Python addons, such as Odoo.sh or self-hosting.
  Standard Odoo Online without custom addons is not supported.
* An active Launchmind subscription, public HTTPS, synchronized clocks,
  and an existing website/blog pair.
* A database and filestore backup, plus installation/upgrade privileges.

Installation and connection
===========================

1. Extract the versioned ZIP. Put its ``launchmind_blog`` directory on your
   server's addons path, restart Odoo, update the Apps list, and install
   **Launchmind Blog** using your hosting provider's addon procedure.
2. In *Settings > Website > Launchmind Blog*, select the existing website
   and its blog. Enter the Launchmind API key server-side.
3. Click **Connect**. Registration starts a pending installation-specific
   signing key. Launchmind confirms it with a signed challenge before
   article delivery can resume. Pending or failed confirmation holds work.
4. Check the connection diagnostics and an explicitly approved staging
   article before allowing customer publication or backlog activation.

The destination cannot change once connector-owned posts exist. Moving
those posts and their URLs needs a separately approved migration.
No website or blog is guessed or automatically created.

Content ownership
=================

Articles are native ``blog.post`` records identified by a dedicated
Launchmind source ID, not a metadata-keyword marker. Repeated delivery
updates the same owned record. Source changes replace managed title, body,
SEO metadata, cover, author and tags. Native edits to those fields can be
overwritten. Unrelated customer posts and unmanaged fields are not owned.

Hidden or unpublished source articles become drafts. While a source stays
eligible, reconciliation can restore a locally drafted, archived or deleted
post. Local deletion is therefore not a permanent opt-out. Arrange source
withdrawal through Launchmind instead.

Authors use connector-owned identities, never name-matched customer
contacts. Tags reuse exact labels or are created; shared tags are never
renamed or deleted. Valid delivered cover/inline images are stored locally.
Unavailable media can stay remote while retryable media remains pending.
Payloads and image admission are bounded.

SEO, discovery and measurement
==============================

Native routing, canonical URLs, social metadata and sitemap remain Odoo's
responsibility. Eligible owned articles receive Article JSON-LD only when
no Article/BlogPosting structured-data owner already exists.

Discovery preserves customer resources and restrictive robots/noindex
policy. The ``llms.txt`` fallback lists only verified eligible owned URLs.
Staging, private/draft posts and unresolved policy are not promoted.

Telemetry is off until explicitly configured. When enabled, browser
pageview/click beacons include full referrer and HTTP(S) target URLs.
Origin-observed crawler telemetry sends user-agent and IP over HTTPS for
backend verification; it cannot observe CDN-only requests. Backend visitor
hash/location and hosted-lead attribution use the existing Launchmind
intake. Daily health reports actual Odoo/Python/module versions. Missing
coverage is unknown, not zero. Obtain customer telemetry approval separately;
this module does not establish consent or legal compliance.

IndexNow is disabled by default. Enabling it requires an explicitly
designated production origin and a fresh platform-verified installation
and public-key proof. Only eligible owned public URLs and their retained
withdrawal evidence may be notified. Acceptance is not proof of indexing.
Do not enable IndexNow on staging or as part of an unapproved rollout.

Authentication and recovery
===========================

``POST /launchmind-blog/webhook`` accepts timestamped HMAC requests after
enrollment. Signatures bind the exact body, installation, key, request ID
and timestamp. The skew window is 300 seconds; durable receipts reject
replays. Any signature header selects signed authentication exclusively.
Signed failure never retries bearer authentication.

Only installations with no enrollment history retain legacy bearer
compatibility. Pending, expired or broken enrollment never restores it.
Replacing a confirmed installation requires the active signing key.
Disconnect preserves keys and the authentication ratchet. If the confirmed
database/key is lost, stop delivery and contact support: there is no
API-key-only reset. Repair clocks and HTTPS rather than weakening checks.

Use Odoo's native database duplication flow for staging, and disconnect
the copy before use. Its changed database UUID invalidates the copied
installation binding. Raw database/filestore copies can retain credentials
and must not share the production subscription.

Upgrade and rollback
====================

Apply the reviewed platform migrations through the normal approval flow
before connecting an upgraded module. Back up the Odoo database/filestore,
replace the addon, restart and run the module upgrade (``-u launchmind_blog``)
using your hosting procedure. Upgrade hooks can preset a destination only
when existing owned posts prove one unambiguous website/blog pair.
Otherwise an administrator must select it.

Inspect connection, pending work, last successful delivery and safe error
codes in existing Odoo settings and Launchmind support surfaces. Test
update, withdrawal, media retry, local deletion recovery and lost
acknowledgments on representative staging. Do not assume installing the
module authorizes publication.

After signed enrollment begins, rolling back to an old bearer-only addon
is not a recovery strategy. Hold delivery and use a reviewed restore or
forward fix with support; never erase enrollment history to bypass signing.
Customer staging, canary, backlog and IndexNow activation require separate
authorization. The release handoff in the source repository records
migration order, verification commands and customer checks not run.

License and support
===================

LGPL-3.0, see ``LICENSE``.

* Email: support@launchmind.io
* Website: https://launchmind.io
