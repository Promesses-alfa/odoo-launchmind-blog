# Pebble Odoo connector: customer launch and pstack workflow pilot

Status: in-build
Council: overridden (ronde 0, door eigenaar)

Workflow pilot: approved for product scoping.
Product specification: the current contract is the [parity gaps](../design/pebble-odoo-parity-gaps.md) document for slices 1-3, extended by the owner decisions below for the remaining delivery.
Test boundaries: approved.
Implementation: slices 1 and 2 passed their gates; slice 3 is built and in review (see the decision trail for the current round). Remaining implementation is approved under the 2026-11-20 decisions below. Branch: `feat/odoo-parity-slice-1`.
Owner: Jeffrey.
Recorded: 2026-11-19.

This is the canonical working specification in the authoritative monorepo.
The earlier standalone `docs/specs/` document is a provisional snapshot.

## Purpose and boundaries

Deliver a reliable Odoo blog integration for Pebble Green Systems first,
then extend it toward verified WordPress blog outcomes. Use this project
to pilot the supplied pstack workflow, adapted to Factory Droid.

This specification owns the product scope and this project's workflow
experiment. It does not establish a repository-wide workflow, modify
`WORKFLOW.md`, replace mandatory controls except the explicit pilot-only
council override recorded below, or authorize production access, merging,
or deployment. Repository publishing authorization is scoped below.
Resolve a conflict explicitly with the owner; do not silently override a
repo rule with this document. Platform changes remain governed by the
Launchmind repository's instructions.

The owner approved the remaining product scope and release-ready delivery
on 2026-11-20. Production operations remain excluded. Historical approvals
below describe their original checkpoints, not new implementation blockers.

## Owner decisions: remaining delivery (2026-11-20)

These AskUser decisions supersede earlier pending-design wording in this
plan. They do not revive the removed v2 architecture or change repo-wide
policy. The coordinator may choose reversible implementation details within
these outcomes without asking for each slice.

### Slice 4: native metadata and destination

- Create connector-owned authors per stable source-author identity; never
  identify or mutate customer contacts by matching their names. Missing
  source authors use a connector-owned Launchmind fallback. Update only
  owned author records from supplied source profile fields.
- Assign native tags from the source's visible tag set. Reuse exact-label
  tags or create them; never rename or delete shared customer tag records.
  Hidden/empty source tags clear assignments on owned posts.
- Require explicit, validated selection of an existing website/blog pair
  in Odoo settings. No guessed/hardcoded customer destination; missing or
  ambiguous selection prevents publication.
- Once owned posts exist, block destination changes. Moving posts, changing
  their URLs and adding migration redirects require separate migration work.
- Preserve the existing managed-field and recreation policies. Customer
  posts and unrelated fields remain outside connector authority.

### Slice 5: SEO, measurement and support

- Selected engineering design: [discovery and measurement](../design/odoo-discovery-measurement.md).
  Customer rollout remains separate from isolated implementation proof.
- Verify native canonical URLs, Open Graph, sitemap inclusion and crawlable
  article output. Add missing article-level outcomes, including Article
  structured data where absent, without duplicate SEO owners or replacing
  customer routing/templates.
- Include `llms.txt`, crawler rules and IndexNow in this release. Preserve
  customer-owned output and restrictive rules; add only non-conflicting
  connector output for eligible public articles. Never bypass staging
  restrictions or noindex. Surface configuration conflicts as actionable
  warnings rather than overwriting customer policy.
- IndexNow is authorized as a feature for verified production-domain
  Launchmind-owned public article URLs and their update/withdrawal
  notifications, with retry/deduplication. Never submit staging, drafts,
  private content or unrelated customer URLs. This feature approval does
  not authorize this delivery session to activate it on customer production.
- Measurement includes pageviews, link clicks, hosted lead attribution,
  origin-observed crawler visits and daily connection health. Match the
  audited WordPress telemetry contract, adapted to Odoo's platform/version
  fields and runtime, using existing Launchmind endpoints. The owner
  explicitly approved full referrer and clicked-target URLs, crawler
  user-agent/IP transmission for verification over HTTPS, and existing
  backend-derived IP hashes/location. Keys remain server-side.
- This approval is not a claim of legal compliance or customer consent.
  Customer telemetry approval/configuration belongs in the rollout handoff.
  Do not claim visibility into CDN-served requests that never reach Odoo,
  count bots as human views, or report unknown coverage as zero.
- Extend existing Odoo settings and Launchmind integration/support surfaces
  for connection health, last successful delivery, pending/retrying work
  and actionable per-article errors. No new standalone dashboard or secrets
  in diagnostics.

### Slice 6: authentication and release readiness

- Release preparation and unrun customer checks:
  [Odoo release handoff](../design/odoo-release-handoff.md).
- Implement timestamped, replay-protected HMAC with an explicit
  per-installation capability transition. Preserve compatibility for
  modules not yet upgraded; confirmed upgraded installations require HMAC.
  Never fall back to weaker authentication after a signed request fails.
- Ship verified Odoo 18 support. Detect/block incompatible installations
  clearly and document hosting/custom-module prerequisites. Other major
  versions or hosting migrations are not part of this delivery.
- Deliver a tested versioned installable ZIP, changelog, configuration and
  upgrade notes, migration ordering and verification instructions, and an
  honest list of customer checks not run. Complete/prove the existing
  allowlisted deterministic release export into the standalone mirror.
- Customer-specific deployment scheduling, credentials, selected target,
  staging, canary choice, telemetry approval and backlog activation remain
  TBD in the handoff. They do not block release-ready code, but must never
  be reported as verified or silently bypassed.
- Migration files and local proofs are in scope; production migration apply,
  customer installation, live publication and backlog activation are not.
  Preserve the normal plan/approval/apply workflow.
- Implementation design: [Odoo signed delivery](../design/odoo-signed-delivery.md).
  Legacy mode exists only before enrollment history; pending enrollment holds
  article sends; confirmed enrollment is signed-only. A confirmed installation
  can be replaced only with proof from its active HMAC key. The owner chose
  support-led recovery if that key is lost, not API-key-only replacement.

### Cross-connector fix and delivery controls

- Public customer-feed slug lookups must require both published and visible,
  rather than exposing unpublished content. Keep this cross-connector fix's
  compatibility tests and review evidence distinct, but include it in the
  same final PR.
- Deliver all six slices and that fix in **one PR**, targeting main.
  Local commits, branch pushes, opening/updating that PR and fixing its
  CI/review/conflicts are authorized. Do not publish to the standalone
  mirror manually as a second product source; use the reviewed export path.
- Finish the slice-3 finding; reuse valid slice-1/2 evidence, but test the
  integrated result. The final thermos gate reviews the **entire PR diff**.
  Both independent reviewers must report zero findings in the same frozen
  round; do not substitute a last-slice review or self-approval.
- Continue to double zero without the previous six-round pause. After
  every two consecutive review rounds, before further repairs, use
  separately prompted independent `design-candidate` droids to challenge
  the design, especially recurring classes; synthesize the invariant and
  record the disposition. The recorded slice-3 round-4 checkpoint already
  reaches this trigger, so perform the challenge before its next repair.
  Candidate feedback is not a replacement for mandatory thermos reviewers.
- Make reversible engineering decisions within scope. Do not silently
  drop features, accept unresolved findings, weaken proof/review/CI, change
  customer policy or expand production permissions. Material contradictions,
  missing required capabilities or unsafe actions remain explicit blockers.
- Present the PR with required CI green, closed final double-zero evidence,
  package and remaining customer prerequisites. **Do not merge.** The owner
  will command merge; contributor permissions and repo approval rules remain.

### Recorded source evidence

WordPress telemetry was inspected in
`packages/blog-connectors/wordpress-launchmind-blog/launchmind-blog.php`
(`send_health_beacon`, `maybe_record_server_pageview`,
`dispatch_ai_crawler_hit`, `inject_tracking_script`) and
`apps/web/app/api/tracking/plugin-view/route.ts`. These are source findings,
not executed Odoo measurement proof. Implementation must verify the actual
end-to-end Odoo behavior and storage contract.

## Evidence and current state

- Customer: <https://pebblegreensystems.nl/>.
- Public pages confirm native Odoo blogs: `/onze-blog` (blog 1),
  `/referenties` (blog 8), and `/grootverbruik` (blog 16). These observed
  IDs are evidence, not values to hardcode.
- The owner explicitly selected Dutch for Pebble's first release.
  Multilingual parity remains follow-up scope, not an inferred omission
  based solely on the public website.
- Existing articles have root-level canonical URLs. Preserve customer
  content and use Odoo's actual computed URLs, including their existing
  routing configuration.
- Customer Odoo version, hosting, installation permissions, staging,
  credentials, approved destination blog and rollout date are unknown.
  Do not require or infer a live eight-language rollout for the Dutch
  first release.
- Standalone module baseline: `18.0.1.0.1`, last synced module commit
  [d973cc3](https://github.com/Promesses-alfa/odoo-launchmind-blog/commit/d973cc32638412e8f77609b86a1a7b634635af9a).
- WordPress comparison baseline: version 6.13.0, inspected at Launchmind
  main `c490e9298b238d88f8d02af418fd1dc19f64bfef`.
- Framer's existing-collection publisher is the architectural precedent:
  explicit target selection, owned-item identity, recovery of uncertain
  writes, source versions, takedowns, a reviewed canary and activation.
  Reuse shared article rendering/composition directly; adapt publishing
  semantics rather than copying the Framer SDK or its schema wholesale.

The analysis found a platform query incompatible with the checked-in
article schema, failed tracking rows suppressing retries, permissive
HTTP-200 acknowledgement, missing website-visibility filtering, and no
routine update/unpublish delivery. The inspected standalone baseline lacked
the monorepo sanitizer changes, a release-mirror drift issue: the current
authoritative module already calls `sanitize_article_html`. Its installed
native behavior is unproven; mocked-import sanitizer checks do not prove it.
These are analysis findings to reproduce in durable regression tests,
not already-fixed behavior or production-state claims.

The owner confirmed that the monorepo remains authoritative for the Python
module as well as the publishing platform. The standalone repository stays
a release mirror; product module changes must originate in an authorized
monorepo worktree, not be developed only in this mirror.

The existing public-sync workflow can replace the standalone repository's
tracked contents on `18.0`. Design must provide an authoritative home and
release/preservation path for these spec/pilot artifacts before relying on
them across releases. Do not disable or reverse the source mirror on the
assumption that standalone has become authoritative.

## Product outcome

An authorized operator connects an installable, supported Pebble Odoo
environment to a selected existing blog. Launchmind publishes only eligible
articles into that target, with faithful content, safe updates and
unpublishing, visible failures, and no changes to unrelated customer posts.

### Customer launch acceptance criteria

| ID | Required observable outcome |
|---|---|
| P01 | An operator can select and verify the existing Odoo website/blog. Wrong-target or unsupported-version configuration fails clearly. |
| P02 | A published, visible Dutch article arrives with the correct title, body, publication date, excerpt, SEO title/description and canonical public URL. Unsupported language input is handled explicitly rather than silently relabeled. The platform query matches the authoritative schema. |
| P03 | Shared article composition preserves enabled lead capture, sources, attribution/branding preferences and tag visibility. External HTML is sanitized before native storage. |
| P04 | A replay and concurrent delivery of the same identity create one owned post. An uncertain write can be reconciled without blindly creating another. |
| P05 | Transient delivery failures retry within an agreed bounded policy. A 200 login page or a negative application response is not delivery success. |
| P06 | A changed source article updates its owned Odoo post; offline/hidden/removed sources cease to be public through explicit, tested lifecycle rules. |
| P07 | Existing customer-written posts are not adopted, deleted or overwritten. On Launchmind-owned posts, Launchmind is authoritative for the closed set of managed fields: direct Odoo edits to those fields are overwritten on synchronization. Non-managed fields remain untouched. The managed-field set and publication-state behavior must be explicit and tested. |
| P08 | Cover and inline media, alt text, author and native tags meet the agreed mapping. Media failure, replacement and removal have explicit behavior, not silent stale values. |
| P09 | Rendered articles use Pebble's existing templates and routing. Canonical, sitemap, crawlable body, social metadata and required structured data pass checks on the actual target. Reuse native Odoo output before adding a second owner. |
| P10 | Support can see connection health, last successful delivery, pending/blocked work and actionable per-article errors without exposing secrets. |
| P11 | Required article/lead/crawler measurement is verified for the customer subscription. No measurement is claimed merely because content was stored. |
| P12 | One customer-approved canary is verified before backlog activation. Retry, update, unpublish and rollback/recovery procedures are exercised before broad rollout. |

The customer-edit policy, first-release language, slice-1/2/3 contracts and
remaining delivery decisions above are settled. Implementation must prove
them rather than treating acceptance criteria as discretionary.

### Confirmed owner decisions

- **Local deletion:** recreate and report a deleted Launchmind-owned post
  while its source remains eligible. Preserve its durable identity and
  reverify the possibly changed URL. This does not authorize adopting a
  same-title customer post.
- **Managed content ownership:** Launchmind overwrites managed article
  fields. Do not implement a customer-edit conflict queue or manual reset
  workflow as the default. Do not extend that authority to unrelated posts
  or fields outside the managed contract.
- **First-release language:** Dutch for Pebble; multilingual parity follows.
- **Source ownership:** the monorepo is authoritative; standalone remains
  the release mirror. Both Python module and platform product work follow
  the monorepo's workflow and review controls.
- **Verification:** all three public-boundary tests below are approved.
  Approval of the boundaries is not approval to access customer staging or
  production, install dependencies, or deploy.

### Scope after Pebble launch

Broader supported-language behavior, richer operator tools and the remaining
verified WordPress blog outcomes follow as separate slices. Careers,
vacancies and service-page products are not part of the first blog release.
Do not copy WordPress-specific editors, cache adapters or rendering modes
when Odoo-native behavior provides the intended outcome.

## Approved test boundaries

1. **Platform publication entry point:** real eligibility selection,
   payload composition and delivery outcome transitions against isolated
   Postgres and a controlled HTTP receiver. Verify the real database query,
   not an ORM mock that invents nonexistent columns.
2. **Odoo installation and HTTP/ORM boundary:** a real supported Odoo
   instance with its real database and module installed. Exercise connection,
   authenticated delivery, replay/concurrency, sanitized writes and lifecycle
   operations, observing native records and public responses.
3. **Rendered customer journey:** publish a controlled article and inspect
   its listing, actual public URL, HTML, images, metadata, enabled lead
   capture and measurement on representative staging, then the approved
   customer canary.

Existing isolated tests support these proofs but do not substitute for them.
The owner approved these boundaries. Specific journeys and environment
commands will be derived during design; unavailable customer access remains
an explicit rollout blocker.

The current publishing contract, per slice, is the
[parity gaps](../design/pebble-odoo-parity-gaps.md) document. It fixes and
extends the existing connector in place: the Odoo webhook, the push in
`apps/web/lib/odoo/odoo-push.ts` and the publish-to-odoo cron. Each slice's
proof runs at the boundaries above through `scripts/odoo-connector-proof.mjs`
(real Odoo 18 module tests plus the end-to-end cron suite). Neither claims
completion of the full customer-launch criteria.

History, not a contract: the [publishing design](../design/pebble-odoo-publishing.md),
the [proof plan](../design/pebble-odoo-proof-plan.md), the
[architecture review](../design/pebble-odoo-architecture-review.md) and
[the local proof record](../evidence/pebble-odoo-local-proof.md) describe the
parallel v2 path (revision fence, writer modes, v2 activation) that the owner
removed. Their findings feed the gap list; their protocol, tables and
v2-only scenarios are not obligations. The owner-confirmed recreation policy
after local deletion carries over to slice 2 of the gap list.

## Pilot-only council override

On 2026-11-19 Jeffrey explicitly requested: "I don't want the council this
pilot - let's do the architecture review on what we have so far and then
continue".

Use `WORKFLOW.md`'s explicit owner-override path for this Pebble Odoo pilot
only. No council round has run (round 0); do not dispatch the three-member
panel or label an architecture-only review `Council: clean`.

Run one independent architecture review of the current plan, publishing
design and proof plan. Record its reviewed inputs, findings and disposition,
then continue the pilot's planning on the resulting design. Focus on state
ownership, interface depth, repository fit and the smallest complete
architecture preserving P01-P12. This is not a new repository-wide gate or
a renamed council loop.

The [architecture review/disposition](../design/pebble-odoo-architecture-review.md)
ran against the removed v2 design and is history; its writer selector and
continuation slice do not apply to the in-place fixes. The review did not
run product tests or approve implementation/customer compatibility.

`WORKFLOW.md`, global skills, code-review/CI/merge controls and production
authorization remain unchanged. The override removes the council blocker;
it does not approve unreviewed technical details or authorize installation,
customer access, deployment, migration apply or backlog activation.

## Canonical artifacts and release mirror

The authoritative plan lives under `docs/plans/`, the publishing design
under `docs/design/`, and this project uses the reusable `.factory/skills/pstack-pilot`
and `.factory/skills/decision-trail` skills. Project-specific scope and
approval remain in this plan. The decision trail has one writable home at
`docs/evidence/pebble-decisions.tsv`.

The standalone repository can expose generated snapshots for working
context, but never becomes an independent product source or a second
writable decision log. Historical trail rows pointing to the provisional
`docs/specs/pebble-odoo-pilot.md` are preserved; a superseding row records
the canonical relocation instead of rewriting the trail.

The release change must publish an explicitly allowlisted public package:
the native module plus the selected pilot/spec artifacts. Never export the
entire monorepo, private working notes, arbitrary `.factory` configuration
or credentials. Preserve the source-SHA marker, deterministic output and
deletion propagation. Test two successive exports, including removal of
an authoritative file. The current exporter is unchanged by this design
work and does not yet protect the provisional standalone artifacts.

No `WORKFLOW.md` changes are needed. A project entry point selects this
pilot only for its named Odoo work. This plan uses the monorepo's recorded
owner-override path for council; all other applicable implementation,
review and merge controls remain authoritative.

## Eerdere reviewlessen

| Klasse | Hoe dit plan hem kan herhalen | Ontwerpkeuze | Bewijs |
|---|---|---|---|
| Platform-markup heeft één compositie-eigenaar | Odoo builds its own article/CTA sandwich and omits the next shared block. | Feed and Odoo push share `apps/web/lib/blog/connector-article.ts`; Python owns native storage/sanitization, not another content composer. | `apps/web/__tests__/content/connector-article.test.ts` and the end-to-end cron suite compare the delivered article with the feed composition. |
| Onbetrouwbare content wordt aan de datagrens gesaneerd | A native Html field is incorrectly assumed to sanitize or a media URL reaches an unrestricted fetch. | Sanitize before native writes and validate media acquisition at its real outbound boundary. | The installed-module HTTP tests send hostile content and an unsafe cover URL, not a sanitizer mock. |
| Opgeslagen data en oude contracten overleven de code | An older module or legacy marker post bypasses the new identity after an upgrade. | Keep the existing endpoint and payload additive; adopt legacy `lm:` posts into `launchmind_article_id` once. | The installed-module tests cover legacy marker adoption; the strict acknowledgement accepts the old module's response. |
| Een bewijs is gedrag, geen tekst | Tests mock the nonexistent article columns or only inspect source for a safety check. | Exercise real schema/HTTP/native transaction behavior at the approved boundaries. | The cron tests reject columns missing from the baseline DDL; the end-to-end suite runs the real cron against PostgREST and Odoo, including a lost acknowledgement. |
| Een poort is bereikbare code die het verzoek afwijst | Authentication or target checks occur after a blog/author/media write. | Parse and authorize before native side effects and test both positive and denial paths. | The installed-module tests prove a wrong key and a malformed article id write nothing. |

## Project-local workflow pilot

### Source and scope

The supplied [workflow diagram](../references/pstack-workflow.png) is the
operator's intended stage map. The upstream reference is pinned to
[pstack e58dd04](https://github.com/cursor/plugins/tree/e58dd043600587dbaf58ba315e7f2b38373eeb43/pstack).
The [skill audit](../research/pstack-skill-audit.md) records exact ports,
equivalents, missing pieces and runtime constraints.

This is a named adaptation, not an unmodified pstack installation. Factory
skills are instructions; custom droids provide worker/tool boundaries.
Cursor model names, tools and autonomous actions are not assumed available.
Any future update to the pinned upstream is an explicit pilot change.

### Stages, artifacts and exits

| Stage | Method and concrete output | Exit condition |
|---|---|---|
| Plan | Trace the real Odoo/platform/Framer paths and history. Write falsifiable customer outcomes, scope, dependencies and decision trail. Use the present analysis instead of restarting discovery. | Approved product scope, test boundaries and workflow pilot; customer access blockers recorded. The pilot approach and boundaries are approved; detailed product design remains pending. |
| Design | Use `architect`; compare materially different shapes only where the choice is genuinely open. Use `prototype`/`explore-options` as the local arena equivalent when evidence can settle it. Define identity, ownership, lifecycle and content contract. | One chosen design with a named state owner per concern; applicable repo design/spec gates satisfied. |
| Build | Use `tdd` at approved public boundaries: one failing behavior, smallest complete implementation, then the next slice. Python work uses the bounded Odoo worker; platform TypeScript uses its discipline skills. Cleanup checks preserve useful comments and avoid unrelated churn. | Slice requirements proven; regressions, type/lint checks and applicable guards pass. |
| Test | Build and actually execute a project verification skill once the environment starts successfully. Validate real Odoo, rendered pages and the integrated publisher. Run blast-radius analysis; use benchmark checks only for measured resource/performance claims. | Evidence at the agreed boundaries, including failure/replay/concurrent and partly completed states. No mocked result presented as customer proof. |
| Review | Product changes originate in the monorepo and use its repo-local gate. Any separately changed mirror-only preparation artifacts retain their applicable personal thermos default. This occupies the diagram's adversarial-diff-review role, without pretending it is the upstream cross-vendor panel. | Required independent verdicts and spec-fidelity checks close on the actual reviewed commit. |
| Deliver | Prepare a reviewable PR and resolve conflicts, review comments and CI using available Factory equivalents. Keep customer rollout separate from merge readiness. | Required CI/review green; authorized owner decides merge and rollout. |
| Maintain | Evaluate the pilot and update verified journeys when behavior changes. Propose durable lessons through `retro`/`correct`. | Customer behavior remains healthy; workflow changes are explicit proposals, not automatic global policy edits. |

Not every skill is a compulsory ceremony on every small change. A skipped
conditional step records its applicability reason. A mandatory gate is not
skipped because a task is small.

### Roles and coordination

- The main session owns scope, decisions, the dependency frontier, shared
  state, the decision trail and integration. It does not delegate the whole
  playbook and then treat a worker's report as verification.
- Bounded workers receive the approved specification, slice acceptance
  criteria, test boundary, absolute worktree, permitted paths and checks.
  They do not ask the customer questions, invent scope or deploy.
- Use parallelism only for genuinely independent sizeable work. Writes use
  separate worktrees and disjoint ownership; one coordinator writes the
  decision trail. Never let parallel workers share a database or customer
  instance unless the test explicitly owns and verifies that concurrency.
- Review is independent of implementation. A model/vendored panel is only
  reported when those actual model identities and tools were available and
  used. Independent same-model sessions are not called cross-vendor review.

### Slice sequence

The slices are the six in the
[parity gaps](../design/pebble-odoo-parity-gaps.md#proposed-slices-on-the-existing-path),
all on the existing connector: deliver correctly, keep in sync, media,
native metadata, SEO and measurement, and rollout. The owner approved
continuation through release-ready delivery on 2026-11-20; no routine
per-slice approval is required. Every slice is proven through `scripts/odoo-connector-proof.mjs`
against isolated Postgres and a pinned Odoo 18 (not a Pebble compatibility
claim). No production credentials, customer access, public canary or backlog
without separate approval. Never add a second create path.

Each slice ends with evidence before dependent work starts. Slice numbers
do not authorize scope or bypass design decisions still marked pending.

### Pilot evidence and evaluation

Keep one append-only decision trail at `docs/evidence/pebble-decisions.tsv`,
using the `decision-trail` skill. Log public engineering decisions and
evidence, not private reasoning, secrets or customer data.

For each slice record its start/end, frozen revision where applicable,
acceptance result, test/evidence pointers, review rounds and rework. Report
an unmeasured baseline honestly: no invented speedup or causal productivity
claim. Evaluate:

- Traceability: every completed criterion has evidence at its agreed boundary.
- Correctness: failed, missing or inconclusive evidence never counts as a pass.
- Rework: review findings and repeated classes, including anything found after
  a claimed completion.
- Cost: elapsed work and review/rework per slice, and tool/token cost only
  when measured by an available source.
- Isolation: no unapproved global skill, repo workflow or production changes.
- Customer outcome: canary and enabled lifecycle/measurement behavior work.

Pause and reframe when the same invariant fails repeatedly, a worker exceeds
scope, the verification environment is not representative, or the design
requires a new owner/contract. Return material product choices to Jeffrey.
Evidence of a recurring mistake should become structure or a check before
another instruction is added.

### Approval and external-action boundaries

The 2026-11-20 decisions authorize remaining implementation, isolated
verification, packaging, local commits, branch push and opening/updating
one PR, including CI and review repairs. No customer installation has been
changed by this decision session. Customer access, production writes,
customer credential setup, migration apply, publication/backfill and merge
remain outside that authorization. A routing skill or upstream unattended
playbook never provides additional permission.

### Remaining external dependencies, not code-scope questions

- Customer version/hosting/custom-module privileges, representative staging
  and credentials, exact existing website/blog selection and legacy-content
  inventory.
- Customer telemetry approval, deployment schedule, canary and backlog
  authorization, and required migration/merge approvals.
- These remain explicit rollout prerequisites. No routine product question
  remains open for the agreed release-ready PR; unexpected material blockers
  follow the escalation boundary above.
