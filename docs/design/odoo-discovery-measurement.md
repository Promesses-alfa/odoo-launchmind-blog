# Odoo discovery and measurement

Status: implemented candidate; isolated native and browser proofs passed,
whole-PR review and CI remain pending.
Scope is the remaining slice 5 in the canonical pilot plan. No customer
installation, telemetry activation or live IndexNow submission is authorized.

## Candidate comparison and decision

Two independent candidates inspected the current module and pinned Odoo 18:
`d72d3a50-159b-4a7e-bfc7-01c599bc6da7` and
`94175d69-9e5e-4cfb-aa10-d200bbf64592`. Their complete reports are the
candidate artifacts; neither session could write its requested scratch files.

Choose A's existing native article-response adapter and fallback-only
discovery ownership. Do not relocate the already proven JSON-LD behavior
into B's broader, unproven `ir.http._post_dispatch` hook. Retain B's useful
idea that current publication state, not a second publication event stream,
determines notification intent. Keep one policy authority for native facts,
anonymous rendered restrictions and notification eligibility.

Do not cache a seven-day production authorization or add a second grant
table. Instead, each notification batch obtains a fresh, short-lived permit
from the platform. The platform externally verifies both a fresh
installation-bound signed challenge and the public IndexNow key resource.
This avoids stale grant renewal and cannot mistake possession of a public
IndexNow key for installation control.

## Caller and ownership

```python
# Existing native article route, after super() and normal rendering:
response = publication.observe_and_decorate(post, response)

# Native fallback, only after Odoo's normal fallback returns no response:
response = super()._serve_fallback()
return response or publication.unclaimed_resource()

# Native scheduled work, bounded independently of article delivery:
publication.refresh_and_notify()
telemetry.send_daily_health()
```

These signatures describe ownership, not an additional generic pipeline.
The response adapter reads real native responses. The publication owner
derives eligibility and owns URL evidence/notification retries. Telemetry
owns wire payloads, server-only credentials and best-effort transmission.
The platform remains the sole owner of crawler recognition/IP verification
and stored analytics. Existing enrollment remains the sole key/binding owner.

Suggested native boundaries are `models/discovery.py` for publication
evidence/notifications, `models/ir_http.py` for the fallback adapter,
`utils/site_policy.py` for pure restriction decisions, and
`utils/telemetry.py` for beacon transport. Existing `controllers/article.py`
remains the article adapter. Additive settings inheritance avoids creating a
second connection implementation.

## Eligibility and customer policy

Promotion requires all of:

- An owned, active, currently published post whose publication date is due.
- The explicitly selected website/blog pair and exact configured HTTPS
  origin. No default guessed destination.
- No neutralized database, staging/other-host request, native noindex,
  rendered robots noindex, `X-Robots-Tag: noindex`, private/login response,
  non-200 response or unresolved restriction.
- A canonical belonging to that owned post, consistent with the native
  computed public URL and selected origin. Do not guess an unrelated path
  when custom routing cannot be proved.
- Effective customer robots rules permit the URL. Restrictive rules must
  not be relaxed by an added bot-specific `Allow` group.

Current request evidence is anonymous, not an administrator's preview.
Background promotion obtains a fresh anonymous HTTPS response, without
cookies or redirects, before sending. Observe rendered restrictions from
the response, rather than assuming database publication flags prove the
customer theme emits no noindex. Unknown evidence suppresses promotion and
shows a warning. Bounded scheduled refresh can discover eligible posts
without depending on a human visit.

The native robots controller/template remains authoritative. Reuse its
crawler rules, preserve customer bytes and restrictive semantics, and add
only a non-semantic connector discovery comment when non-conflicting.
Never generate an unconditional crawler-specific allow group. A policy
parser may conservatively withhold a URL on a matching restrictive rule;
it must not silently interpret an unsupported restriction as permission.

`/llms.txt` is served only from the native fallback after existing routes,
attachments, pages and redirects have had their normal chance to answer.
Customer output wins structurally. The connector lists only verified
eligible owned URLs, with escaped text and a bounded, explicitly described
listing. No draft, private or staging listing.

## Measurement

Telemetry is off until explicitly configured for the customer. Public
browser configuration contains only the subscription/source article UUID,
module version and HTTPS intake URL, never an API or enrollment key.

Human pageviews and HTTP(S) link clicks use browser beacons. This preserves
the backend's visitor IP hash/location semantics. Do not emit a parallel
Odoo-server human-view beacon: the current intake would hash the Odoo
server IP and merge unrelated visitors in its dedup window. Browser-only
coverage excludes no-JavaScript visitors; it is not reported as complete.

Known bot requests receive no human beacon. The platform independently
filters bot UAs on Odoo client events as well as server events. Stable source
UUID resolution occurs within the subscription before the existing tracking
RPC, whose master-slug contract remains unchanged. Full valid referrer and
clicked-target URLs follow the existing bounded intake contract.

Origin-observed crawler requests use the existing `bot_hit` contract and v1
tracking signature keyed with the server-held API key, not the delivery key.
The backend owns classification and IP verification. Use the connection
peer unless trusted proxy configuration is actually established. Raw crawler
IP is transmitted only over HTTPS, never logged or durably queued. Delivery
is bounded best effort; failure must not break the native page response.
Verify the chosen after-response callback on the real pinned HTTP runtime
before relying on it.

Daily health uses `/api/plugin-health`: actual Odoo runtime and Python
versions, module version, owned-public count and an explicit origin-observed
coverage label. Only `recorded: true` advances the native accepted-health
timestamp. Missing health/coverage remains unknown, not zero.

Hosted leads use the successful tenant/source-bound native URL in the
delivery ledger, not a reconstructed localized slug.

## Fresh production proof

The native operator explicitly designates production and enables IndexNow,
which is off by default. The platform additionally requires:

1. A valid signed `installation.indexnow.verify` request from the currently
   confirmed enrollment, active subscription and no pending replacement.
2. The exact HTTPS origin matches both the configured company website and
   the confirmed Odoo destination origin. No inferred subdomain/`www`
   equivalence or staging hostname fallback. An alternative production
   origin requires correcting the existing customer configuration first.
3. Durable replay admission under the subscription row lock through
   `odoo_admit_enrollment_request`; failed signed proof never tries bearer.
4. An externally generated fresh challenge fetched through the public
   guarded-fetch boundary, without redirects:
   `/launchmind-blog/production-proof?challenge=<uuid>&request_id=<uuid>`.
   The native fallback responds only for the currently bound installation,
   selected production host, enabled feature and non-neutralized database.
   Its body echoes the IDs/challenge, real runtime and public IndexNow key;
   the existing confirmation-ack HMAC signs the exact response bytes.
5. An independent public GET of `/<indexnow_key>.txt` returns exactly that
   key, with bounded bytes and no redirect.
6. A final current enrollment/binding check before issuing the 60-second
   permit. Network, runtime, signature, key-resource, origin and state errors
   all fail closed.

The native dispatcher uses a permit only for the immediately following
bounded batch on the bound origin. Stored last-proof time is diagnostic
evidence, not offline authorization. A clone's changed database UUID
invalidates the enrollment binding before it can request or use a permit.

## Notification convergence

Retain durable evidence per `(source UUID, native URL)`, independently of the
post's eventual deletion. A foreign key to the post must use `SET NULL`,
not delete the evidence. Per-URL evidence records its last verified
eligible fingerprint, intended update/withdrawal, attempts/backoff, safe
error code and last acceptance. A fingerprint excludes view counters and
connector diagnostic timestamps.

Current native state determines what is due:

- Current eligible URL/revision differs from the accepted one: update.
- Previously eligible URL is no longer the current owned-public URL:
  withdrawal, including deletion and URL changes.
- Current site-wide staging/noindex/restrictive policy or missing production
  proof: hold, never bypass the restriction to send either operation.
- Feature disabled/disconnected: hold, not mass withdrawal.

Do not require a prior successful acknowledgment for withdrawal. A timed-out
update may have been accepted remotely. Keep eligible-URL evidence durable
before external notification so crashes cannot erase that uncertainty.

Use unique URL evidence and row-locked bounded scheduled batches. Validate
policy and binding at dispatch and never let an old acknowledgment erase a
newer desired revision. Commit acceptance only after the response. A crash
may repeat a notification, so the claim is at-least-once convergence, not
external exactly-once delivery.

The [IndexNow protocol](https://www.indexnow.org/documentation), retrieved
successfully during design, defines 200 as received and 202 as received with
key validation pending. Neither means indexed. Retry timeout/429/5xx with
bounded exponential backoff; 400/403/422 are actionable blocked states.
Redirects and unexpected responses are not success. Native tests use a
controlled receiver, never the live IndexNow service.

## Proof and support

Required native proof includes customer resource precedence, noindex and
staging suppression, JSON-LD preservation, actual browser pageview/click
beacons, crawler transmission/privacy, recorded-health semantics, fresh
domain proof, update/withdraw/deletion/uncertain-ACK recovery, dedup/backoff
and disabled-feature zero outbound requests.

Existing settings and customer-detail support show health, last successful
delivery, pending/retrying/held work and safe per-article diagnoses. They do
not expose secrets or raw remote error text. No standalone dashboard.

Customer version/hosting/template/proxy behavior, telemetry approval,
production designation, staging, canary and activation remain unrun
customer prerequisites, not permissions inferred from local tests.
