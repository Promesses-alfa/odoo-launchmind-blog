# Odoo release handoff

Status: in preparation. This is not a customer installation or rollout record.

## Authority and artifacts

The Launchmind monorepo is authoritative. The public `18.0` repository is a
generated release mirror, never an independent place to change the product.
`scripts/export-odoo-public.mjs` exports only the native installation files
and explicitly named public documentation. Its `.launchmind-source.json`
records the full source commit and each exported file's SHA-256.

`node packages/blog-connectors/scripts/build-odoo.js` produces a versioned
`dist/odoo-launchmind-blog-<manifest-version>.zip` and the byte-identical
`dist/odoo-launchmind-blog.zip` compatibility alias. Both contain the
`launchmind_blog/` addon directory. Test harnesses, local configuration and
the public documentation snapshots are not part of the installation ZIP.

The ZIP and mirror use the same allowlist. Reproducibility and source
deletion propagation run through:

```sh
node --test scripts/export-odoo-public.test.mjs scripts/odoo-release-zip.test.mjs
```

The mirror workflow waits for successful push CI on the current main commit.
Manual dispatch has the same current-main/green-CI gate. A superseded source
cannot overwrite a newer mirror, and an unrelated main commit does not churn
only the provenance SHA. The no-op check compares actual tracked bytes and
inventory, not just the stored marker. These checks are exercised with local
fixtures; the revised GitHub workflow has not been dispatched in this session.

No manual mirror publication or customer artifact upload was performed.

## Supported environment

- Odoo **18.0**, Community or Enterprise, with `website_blog` installed.
- Hosting must allow custom Python addons and their upgrade hooks. Standard
  Odoo Online without custom addon installation is not a supported target.
  Odoo.sh or self-hosting still needs explicit customer installation access.
- A public HTTPS destination, with correct clock synchronization and
  certificate verification. The local HTTP exception belongs only to the
  isolated proof harness, not a customer configuration.
- Explicit selection of an existing website/blog pair. No customer
  destination is guessed. Once owned posts exist, changing that pair needs
  a separately approved content/URL migration.
- Database and filestore backup before module installation or upgrade.

Customer version, hosting and privileges have not been verified.

## Migration order and verification

Do not apply production migrations from this document. Use the repository's
normal migration plan, owner approval, apply and companion-verification flow.
The release adds these migrations in version order:

1. `20261119192833_odoo_sync_ledger.sql`, lifecycle retry/reconciliation.
2. `20261119204057_odoo_media_pending.sql`, deferred media state.
3. `20261120065353_odoo_crawler_source.sql`, explicit Odoo crawler source.
4. `20261120081413_odoo_signed_enrollments.sql`, private enrollment keys,
   replay receipts and forward-only enrollment transitions.
5. `20261120082602_odoo_python_health.sql`, Python runtime health evidence.

Each has a companion under `supabase/migration-verifications/`. The isolated
SQL proofs are:

```sh
node --test scripts/odoo-crawler-source.test.mjs scripts/odoo-enrollments.test.mjs
```

The platform deployment itself requires this schema first, including for
legacy installations: cron reads the enrollment ledger before scanning
subscriptions, and legacy registration calls its new RPC. Missing schema
fails closed and holds all Odoo delivery, not just upgraded installations.
Coordinate schema approval/apply with the web deployment; do not merge into
an automatically deploying main branch until that ordering is arranged.
This document does not authorize either operation.

Signed enrollment requires the schema before an upgraded module connects.
Publish/withdraw/check work is held whenever enrollment is pending, expired
or broken. An unavailable enrollment lookup must not select legacy mode.
Only installations with no enrollment history retain the old bearer path.

The native addon upgrade must run its versioned migration hooks before
backlog activation. The release candidate is `18.0.1.6.0`. The isolated
proof installs the pinned `18.0.1.0.1` addon from `c490e9298`, then replaces
it with the candidate ZIP and runs the real module upgrade. It verifies
ownership-gated migration, unchanged existing content and a customer
control post, explicit legacy adoption, and reconnect without
signature-ratchet downgrade. A fresh ZIP installation and native database
duplication are also exercised.

On 20 November 2026, `node scripts/odoo-connector-proof.mjs` passed 83 native
tests, 15 platform/runtime tests and four Chromium HTTPS beacons. This is
isolated Odoo 18 evidence, not customer-template or production proof.

## Connection and recovery

1. Verify staging first with a synthetic source article and the actual
   selected website/blog. Review the managed-field overwrite policy.
2. Enter the Launchmind API key only in server-side Odoo settings, then
   Connect. New enrollment returns a pending per-installation key.
3. The next platform confirmation challenge proves signed support. Confirm
   the connection status and native URL before allowing article delivery.
4. If confirmation acknowledgment is lost, retry the challenge with a fresh
   request ID. Do not reset credentials or create another publication path.
5. Fix clock, HTTPS, runtime or destination errors as reported. A signature
   failure never permits a bearer retry.

An active HMAC key is required to replace a confirmed installation.
Disconnect does not erase enrollment history. If the confirmed database or
key is lost, stop delivery and contact support. There is deliberately no
API-key-only public reset. Support must verify account ownership and the
intended installation, revoke the old generation through separately approved
maintenance, and re-prove the replacement before resuming. No support reset
or production maintenance was performed in this session.

Use Odoo's native duplicate-database flow for staging and disconnect the copy
before using it. A raw PostgreSQL/filestore clone may copy installation
credentials and is not covered by the native clone-isolation claim.

## SEO and measurement prerequisites

Customer templates, robots policy and existing structured-data owners must
remain authoritative. Validate the actual rendered canonical, social tags,
sitemap, public body and customer routing. Restrictive policy and staging
must never be bypassed for discovery or notifications.

Customer telemetry approval is required separately. Approved engineering
scope includes full referrer and clicked-target URLs, crawler UA/IP over
HTTPS for verification, and existing backend-derived IP hash/location. This
does not establish consent or legal compliance. Keys remain server-side.
Crawler coverage is origin-observed; CDN-only requests remain unknown.

IndexNow must remain disabled in this delivery session. A later activation
requires verified control of the exact production origin, explicit
production designation, and eligible owned-public URL proof. A successful
notification means accepted, not indexed.

## Still required before customer rollout

- Verify customer Odoo version, hosting, custom-addon privileges and backup.
- Agree on the exact destination, telemetry configuration and deployment
  schedule. Inventory legacy and customer-written posts.
- Run the customer-template and real-browser journey on representative
  staging, including images, lead capture, pageview/click/crawler evidence,
  health, and restrictive crawl policy.
- Exercise update, withdrawal, lost acknowledgment, retry/backoff, local
  deletion/recreation and rollback/recovery procedures.
- Obtain an explicit owner-approved canary and verify its actual public URL.
- Obtain separate backlog/IndexNow activation authorization only after the
  canary and production-domain checks pass.

No production migration, customer install, live publication, canary,
backlog activation or live IndexNow submission is claimed here.
