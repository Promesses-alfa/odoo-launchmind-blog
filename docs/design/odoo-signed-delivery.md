# Design Memo: Odoo Signed Delivery

Status: implemented candidate for slice 6, 2026-11-20; isolated SQL and native
boundary proofs passed, whole-PR review and CI remain pending. This records
the implementation shape, not permission to apply migrations, install a
customer module, or activate a customer rollout.

## Problem

Move Odoo webhooks from bearer-only delivery to timestamped, replay-protected
HMAC without breaking installations that have not upgraded. Once an
installation enters the signed transition, neither side may fall back to
bearer delivery after a signature failure. The receiver must enforce Odoo 18
from its actual runtime, not from the module version string.

## First-principles derivation

- **Latency floor:** enrollment needs one Odoo-to-Launchmind registration
  round trip and one Launchmind-to-Odoo confirmation round trip, followed
  by one local database commit. Thus enrollment time is at least
  `2 * RTT + T_database`. A normal signed delivery keeps the existing
  single HTTP round trip; it adds a body hash, an HMAC, and one unique
  receipt insert. No network or runtime latency has been measured.
- **Consistency floor:** key activation and subscription destination
  changes must commit atomically. Replay admission must be unique across
  Odoo workers and restarts. PostgreSQL row locks and unique indexes are
  the minimum consistency that satisfies these invariants.
- **Storage floor:** the current cron sends at most 10 article actions per
  subscription per minute. A 10-minute freshness window therefore retains
  about 100 receipt rows per active subscription, plus occasional
  reconciliation requests. At a conservative 256 bytes per row including
  index overhead, 1,000 active installations retain about 25.6 MB before
  cleanup. This is an estimate, not a measurement.
- **Idiot Index:** signed delivery adds one constant-size HMAC and one
  durable receipt write per request, with no new service or queue. That
  cost is justified by mixed-version compatibility and replay protection.
  HMAC work is linear in the already bounded request body; its CPU cost
  remains unmeasured.

## Invariants

### Safety

1. A subscription with no enrollment history retains the existing legacy
   bearer contract.
2. Once any HMAC enrollment starts, absence, expiry, or corruption of an
   active key never restores legacy mode. Pending or broken enrollment
   blocks article delivery until it is repaired.
3. A confirmed installation sends only HMAC-signed publish, withdrawal,
   reconciliation, and registration requests. A failed or malformed
   signature never causes a bearer retry.
4. HMAC secrets are per installation, service-role-only in Launchmind,
   absent from portal responses and logs, and never sent in signed
   delivery bodies or authorization headers.
5. Each signed request ID is admitted at most once across Odoo workers and
   restarts. A retry uses a new request ID.
6. Only an Odoo 18 runtime can install, connect, or confirm an enrollment.
   The module-reported version and the actual runtime version are distinct.
7. A confirmed installation can be replaced only with proof from its
   active HMAC key. API-key-only recovery is not allowed; loss of the
   active database/key goes through support.
8. Existing redirect checks, cross-origin credential isolation, strict
   acknowledgements, the 64 KiB response cap, and the bounded media-413
   retry remain in force.

### Liveness

An eligible delivery eventually resumes after a valid pending enrollment is
confirmed and Odoo is reachable. A failed confirmation leaves work pending
and visible; it does not silently switch to a weaker credential.

## Requirements audit

| Requirement | Owner/date | Disposition |
|---|---|---|
| Timestamped replay-protected HMAC | Jeffrey, 2026-11-20 plan | Kept; shared web/Python test vectors and a durable Odoo receipt table |
| Explicit per-installation transition | Jeffrey, 2026-11-20 plan | Kept; key generations and state live in `odoo_enrollments` |
| Legacy compatibility before upgrade | Jeffrey, 2026-11-20 plan | Kept; legacy mode exists only before enrollment history |
| No fallback after signed failure | Jeffrey, 2026-11-20 plan | Kept; pending state holds delivery, confirmed state has no bearer credential |
| Odoo 18 support and incompatible-version block | Jeffrey, 2026-11-20 plan | Kept; pre-init, Connect, registration, and confirmation check actual runtime |
| Replacement requires the active HMAC proof | Jeffrey, AskUser, 2026-11-20 | Kept; lost-key recovery is support-led |
| No customer install, production migration, live publication, or rollout | Jeffrey, 2026-11-20 plan | Kept; local isolated proof only |

## State and wire protocol

`odoo_enrollments` is the single owner of installation keys. It stores one
row per key generation with `kid`, subscription, stable installation ID,
requested Odoo URL, signing secret, runtime/module versions, timestamps, and
state (`pending`, `confirmed`, or `superseded`). Partial unique indexes
allow at most one pending and one confirmed row per subscription. State
transitions are forward-only. Rows are not deleted to reset a subscription
to legacy.

Delivery mode is derived from enrollment history:

| State | Delivery behavior |
|---|---|
| No enrollment row | Existing legacy bearer contract |
| Pending enrollment | Hold publish/withdraw/check work; send only the signed confirmation challenge |
| Confirmed enrollment | Send HMAC only, with the confirmed installation key |
| Only expired/superseded rows or invalid key state | Hold and report an actionable enrollment error, never legacy |

Pending takes precedence over confirmed when both rows exist: replacement
holds article sends until its challenge completes. Expiration never deletes
history or restores legacy delivery.

The module stores current and pending key slots in `ir.config_parameter`.
When a current key exists, Connect signs enrollment changes with it. An
initial legacy installation may use the API key to request its first pending
key. Registration is idempotent for the same installation ID and returns
the same unexpired pending key. A legacy registration cannot overwrite or
reset any enrollment history. An API-key-authenticated retry may retrieve an
initial unexpired pending grant only for the same installation and exact
requested URL, while no confirmed generation has ever existed. After expiry,
that same initial installation may obtain a fresh pending generation. A
different installation or URL requires the active confirmed HMAC key, or
support if no such key is available. Every signed registration consumes a
durable platform receipt before returning key material; a captured signed
registration cannot be replayed to retrieve a pending secret. The transition
RPC rechecks the proof's key ID under the subscription row lock, so a key
superseded between route verification and mutation cannot authorize a change.

The transition has two committed steps:

1. Connect validates actual Odoo 18 runtime, identifies the installation,
   and requests a pending key. Launchmind persists it before returning the
   key to Odoo over HTTPS.
2. The cron sends a signed `installation.confirm` challenge. Odoo validates
   it, admits the request ID, promotes the pending key, and returns a signed
   acknowledgement containing the installation ID, key ID, challenge,
   runtime, and module version. Launchmind verifies the exact response and
   atomically confirms the enrollment and destination.

Connect and webhook admission serialize on an Odoo transaction advisory lock.
Connect holds it while requesting/storing the pending grant, so a stale
legacy sender cannot pass admission after the local transition commits.
Native Odoo uses REPEATABLE READ: a transaction may already have a snapshot
before waiting for that advisory lock. Therefore state writes also bump a
dedicated signing-epoch parameter row, which admission locks. A stale
snapshot receives a serialization failure and Odoo retries the request on
a fresh snapshot. Independent real database sessions exercised this case;
an advisory lock without the epoch fence is insufficient.
Disconnect clears neither key slots nor enrollment history: it disables
delivery locally, and reconnect still requires the active key. Configuration
reads for authentication must bypass Odoo's per-worker parameter cache.

While pending, the cron sends no article work for that subscription. If Odoo
promotes the key but Launchmind cannot confirm the database transition, the
next challenge is re-acknowledged by the current Odoo key. No legacy delivery
can race the ratchet. URL conflicts are reported and leave the enrollment
pending; they do not redirect or downgrade delivery.

Wire format v2:

```text
X-Launchmind-Signature: v2=<hex HMAC-SHA256>
X-Launchmind-Key-Id: <key UUID>
X-Launchmind-Installation: <installation UUID>
X-Launchmind-Request-Id: <fresh UUID>
X-Launchmind-Timestamp: <Unix seconds>

canonical =
  "lm-odoo-v2\n" + installation_id + "\n" + key_id + "\n" +
  request_id + "\n" + timestamp + "\n" + hex(SHA256(raw_body))
```

The accepted skew is 300 seconds. Receipt expiry is anchored to
`timestamp + 600 seconds`, so cleanup cannot reopen a valid replay window.
Signed event bodies omit `api_key`; signed requests omit `Authorization`.
If any signature header is present, the receiver follows only the HMAC path.
Registration bodies have `event: "installation.register"` and confirmation
bodies have `event: "installation.confirm"`; each route admits only its
own event. This prevents reuse of a valid signature for a different operation.
Confirmation acknowledgement signatures use a distinct domain:
`"lm-odoo-ack-v2\n" + request_id + "\n" + hex(SHA256(raw_response_body))`.
The acknowledgement body echoes the fresh challenge and installation/key
IDs. The sender verifies both the exact bytes and all echoed fields.

## Architecture

```text
Odoo Connect
  -> authenticated register / pending key
  -> Launchmind enrollment ledger (service role only)
  -> cron confirmation challenge
  -> Odoo durable receipt + key promotion
  <- signed acknowledgement
  -> atomic Launchmind confirmation + destination update
  -> signed-only event sender
  -> Odoo HMAC verification + receipt + native write
```

PostgreSQL owns enrollment transitions and URL serialization. Odoo owns
receiver-side replay admission and local key slots. The web sender owns
credential construction and never changes credential type after a response.
The existing Odoo article identity remains idempotent by Launchmind article
UUID.

## Door classification

| Decision | Door | Rationale |
|---|---|---|
| Append-only enrollment schema and HMAC wire format | One-way | Existing installed modules and requests must coexist across releases |
| Separate HMAC key per Odoo installation | One-way | It separates signed transport from the legacy API-key bearer |
| 300-second skew and 600-second receipt expiry | Two-way | Adjustable without changing the protocol version |
| Support-led lost-key recovery | Two-way | Keeps production reset capability out of the public Connect flow |

## Pre-mortem

1. **Lost Connect response:** Launchmind has a pending row but Odoo has not
   stored its key. Registration for the same installation returns the same
   pending key; the sender holds article work until confirmation.
2. **Lost confirmation acknowledgement:** Odoo has promoted the key but the
   platform remains pending. The cron replays confirmation with a fresh
   request ID; Odoo re-acknowledges the active key. Article work remains
   held, not unsigned.
3. **Odoo clock skew exceeds five minutes:** signed requests fail closed.
   Record a secret-free clock-skew diagnosis and require clock repair; never
   retry with bearer.
4. **Confirmed database/key is lost:** API-key-only replacement is rejected.
   Support performs the documented recovery; no customer request silently
   weakens authentication.
5. **A staging database is cloned:** Odoo's pinned 18.0 duplicate path calls
   `ir.config_parameter.init(force=True)` after the database copy, which
   regenerates `database.uuid`. The module detects the changed binding and
   refuses the copied enrollment. Raw PostgreSQL copies that bypass Odoo's
   duplicate path remain outside this proof and must not share a production
   subscription.

## Steelman of the rejected design

A URL-derived mode with a signing secret on `backlink_subscriptions` is
smaller and avoids the enrollment table. It does not identify an Odoo
database independently of its URL, risks exposing the secret through broad
subscription reads, and changes the destination before a new installation
proves HMAC support. A receipt-based ratchet is useful, but it does not fix
those ownership and retargeting problems. The explicit enrollment ledger
costs more schema and handshake code to keep installation identity, URL,
and key state auditable and atomic.

## Failure modes and defenses

| Failure mode | Tolerance and recovery |
|---|---|
| Bad signature, wrong key/installation, malformed body | Reject before native writes; do not read bearer when signature headers exist |
| Duplicate request ID, including concurrent workers/restart | Unique receipt admission; duplicate is rejected without a second native effect |
| Request older/newer than 300-second skew window | Reject; clock diagnosis only |
| Pending enrollment expires or URL conflicts | Keep the subscription held; same installation retries or operator repairs; no legacy fallback |
| Odoo 17/19 or malformed runtime report | Block install/connect/confirm before enrollment or article writes |
| Cross-origin redirect | Existing redirect policy drops credentials/signature and fails closed |
| API key alone attempts to replace confirmed key | Reject; require active HMAC proof or support-led recovery |
| Old module registers after HMAC enrollment began | Return `upgrade_required`; do not delete enrollment history |

Out-of-order distinct signed article events are not prevented by the request
replay table. The existing per-minute sync planner retries current eligible
state and reconciles deleted posts; convergence is eventual, not an
instantaneous ordering guarantee. Do not claim otherwise.

## Worst-case design

- **Overload:** do not mint an unbounded challenge batch. Process a bounded
  number of pending enrollments before article work, obey the route deadline,
  and keep unconfirmed subscriptions held for the next tick.
- **Degraded mode:** legacy installations without enrollment history retain
  their existing path. Pending/confirmed installations fail closed when the
  key or database is unavailable.
- **Recovery:** retry the same enrollment ID or confirmation state, inspect
  secret-free diagnostics, repair the Odoo clock/runtime/destination, or use
  support-led lost-key recovery. Never reset to legacy as a routine retry.

## SLOs, fitness functions, and falsifiability

No production latency/availability SLO was approved for this pilot; none is
invented here. The security fitness function is zero cases where a failed
signed request triggers bearer fallback. Required automated proof includes:

- identical TypeScript/Python HMAC test vectors for accepted, expired,
  future, tampered, malformed, wrong-key, wrong-installation, and replayed
  requests;
- pinned Odoo 18 HTTP tests for legacy compatibility, pending confirmation,
  current-key promotion, replay across workers/restarts, and no writes on
  invalid signatures;
- a networkless PostgreSQL proof for partial unique indexes, forward-only
  transitions, URL conflicts, legacy downgrade rejection, RLS/grants, and
  companion verification before/after migration;
- sender tests proving signed requests omit bearer/body key, each attempt
  uses a fresh request ID, and 401/403 never triggers another credential;
- an Odoo duplicate-database proof that the native duplicate operation
  changes the bound `database.uuid`.

Current native evidence exercises the exact `init(force=True)` reset used by
the pinned duplicate implementation and checks its source, but does not
duplicate a full database. The full duplicate-operation proof remains open;
do not describe the reset-only test as that proof.

Load-bearing assumptions: HMAC keys remain private in Odoo settings and the
service-role enrollment table; the pinned Odoo 18 runtime reports its actual
series; the native duplicate API regenerates `database.uuid`; pending
challenge work fits inside the cron deadline. Tests and support diagnostics
must make violations visible.

## Recursive cost and open questions

The design adds one append-only enrollment table, one platform registration
receipt table, one Odoo replay-receipt model,
one Connect response carrying a pending secret, one cron challenge step,
and shared wire vectors. It adds no service, queue, or dashboard. Secret
storage has the same database-at-rest posture as the current Odoo API key;
the new key must never be included in portal queries, logs, diagnostics, or
signed webhook bodies.

The support runbook must state how to recover a lost confirmed key without
allowing API-key-only reset. The native duplicate test must exercise the
pinned Odoo API. Customer installation, production schema apply, version
inventory, canary, and activation remain rollout prerequisites.
