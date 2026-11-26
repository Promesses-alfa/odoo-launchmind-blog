# Pebble Odoo: existing connector vs WordPress parity gaps

Status: in-build

The contracts below own slices 1-3. Owner-approved scope for slices 4-6,
the separately reviewed public slug-lookup fix, and single-PR delivery and
review controls is recorded in the [pilot plan](../plans/pebble-odoo-pilot.md),
under "Owner decisions: remaining delivery (2026-11-20)". Those decisions
are approved scope, not completed implementation or customer rollout proof.

Source: read-only inventories of the design worktree on 2026-11-19 (base
`c490e9298b`). File references are to that tree. The existing connector is the
starting point: `packages/blog-connectors/odoo-launchmind-blog/controllers/main.py`
(webhook), `apps/web/lib/odoo/odoo-push.ts` (push) and
`apps/web/app/api/cron/publish-to-odoo/route.ts` (cron, every minute).
WordPress parity is measured against executable plugin code, not its readme.

## Confirmed bugs in the existing path

| # | Bug | Evidence |
|---|---|---|
| B1 | The cron's article query selects six columns that do not exist (`language`, `title`, `meta_description`, `content`, `cover_image_url`, `tags`), so no article can be delivered against the real schema. | `route.ts` article select vs `launchmind_blog_posts` in the baseline migration |
| B2 | A failed tracking row excludes the article forever, so failures never retry. | `route.ts` loads all `odoo_published_articles` rows without a status filter |
| B3 | Any readable 2xx response counts as delivered, including a login page or `{"success":false}`. A test asserts this. | `odoo-push.ts` success branch; `odoo-push-ophaal-poort.test.ts` |
| B4 | No `show_on_website` filter; only `is_published`. (Archive stays eligible, as in the feed.) | `route.ts` article query |
| B5 | No update or unpublish after the first delivery; the receiver always sets `is_published = True`. | `route.ts` exclusion set; `main.py` post values |
| B6 | Registration writes the language hint to `language`, while publishing reads `site_language`. | `integrations/odoo/register/route.ts` vs cron |
| B7 | Identity is a substring match on `lm:<id>` inside SEO keywords (truncated to 255 chars), not a dedicated field. | `main.py` dedupe search |

## Parity gaps (existing Odoo vs WordPress)

| Area | WordPress today | Existing Odoo | Reuse from platform? |
|---|---|---|---|
| Body composition | Shared renderer plus lead CTA, sources, powered-by, `hide_tags` | Raw content, none of these | Yes: `renderConnectorArticleBody`, `buildConnectorArticleHtml`, `leadCaptureOptsFromPartnerContent` |
| Localized fields and slug | Per-language title/body/excerpt/meta/slug | Unlocalized, wrong columns; receiver ignores language | Platform columns; Odoo writes in the `nl_NL` context |
| Eligibility | Published and visible (`show_on_website` true or null) | Published only | Same rule as the customer feed |
| Updates | Delta cursor, hash-skip, metadata refresh | None | Platform `updated_at`/content hash |
| Takedown | Hidden/archived become draft, full reconcile | None | Unpublish event to the receiver |
| Excerpt, SEO title/description | Separate fields | Excerpt = meta description; SEO title = title | Platform values |
| Publication date | Set from source | Not written | Platform `published_at` |
| Cover image and alt | Downloaded into media library | Remote CSS URL only, never cleared | Platform URL/alt; Odoo stores an attachment |
| Inline images | Downloaded and rewritten, retried | Left remote | Odoo side |
| Tags and category | Native taxonomy | Keywords text only | Platform tags; Odoo `blog.tag` |
| Author | Native author with profile | Name match on `res.partner` (may rename/merge a customer contact) | Platform author profile |
| Canonical, OG, JSON-LD, sitemap | Plugin emits | Not handled | Mostly native Odoo website SEO; verify before adding |
| Blog/website selection | Configurable page | Hardcoded "Launchmind Blog", global settings | Odoo settings |
| Tracking (pageview, crawler, lead) | Beacon, signed crawler reports, CTA article ID | None except the CTA link once composed | Platform endpoints |
| Health and support | Daily health beacon, sync status, logs | Health reports only last receive time; platform status means "attempted" | `plugin-health` endpoint |
| Auth | HMAC wakeup with timestamp and replay window | Static bearer key in header or body | Reuse the WordPress HMAC scheme |

Owner decision that differs from WordPress: Launchmind overwrites managed fields
on owned posts (WordPress protects local edits). Recreation after local delete
is also owner-confirmed.

## Proposed slices on the existing path

1. **Deliver correctly.** Fix B1-B4, B6, B7: localized Dutch columns, feed
   visibility rule, retry failed rows, strict acknowledgement (`success:true`
   plus `post_id`), shared composition, dedicated identity field on
   `blog.post`, `nl_NL` write context, publication date, excerpt and SEO title.
2. **Keep in sync.** Updates by content hash, unpublish/withdraw to draft,
   recreate a deleted owned post (B5).
3. **Media.** Cover and inline images as Odoo attachments with alt text,
   replacement and removal, with measured limits.
4. **Native metadata.** `blog.tag`, author without contact name-matching,
   configurable website/blog.
5. **SEO and measurement.** Verify native Odoo canonical/OG/sitemap, add
   JSON-LD only where missing, pageview/crawler tracking, health beacon.
6. **Rollout.** HMAC auth, version/hosting confirmation on Pebble staging,
   canary, backlog.

Each slice is proved with the Docker harness against real Odoo 18 and isolated
Postgres, at the approved test boundaries.

## Slice 1 webhook contract (existing endpoint, additive)

`POST {odoo_url}/launchmind-blog/webhook`, `Authorization: Bearer <api_key>`,
JSON. Keys used by the current module keep their names so an un-upgraded
module still works; new keys are additive.

```json
{
  "event": "article.published",
  "api_key": "<same as bearer, legacy fallback>",
  "source": "launchmind.io",
  "delivered_at": "<ISO>",
  "article": {
    "id": "<uuid>",
    "slug": "<slug_{lang} or slug>",
    "language": "<lang, e.g. nl>",
    "title": "<title_{lang}>",
    "excerpt": "<excerpt_{lang} or ''>",
    "seo_title": "<title_{lang}>",
    "meta_description": "<meta_description_{lang} or ''>",
    "content": "<platform-composed HTML: renderConnectorArticleBody + buildConnectorArticleHtml>",
    "cover_image_url": "<featured_image_url or ''>",
    "cover_image_alt": "<featured_image_alt or ''>",
    "tags": ["<meta_keywords, else keywords; [] when hide_tags>"],
    "author": "<author_profile.name or author or 'Launchmind'>",
    "published_at": "<ISO>"
  }
}
```

Platform rules:
- Connect fills `site_language` only when it is still empty, with the
  Odoo website's default language (never the admin's interface language),
  because `site_language` also drives mails and the portal.
- Language `lang` = subscription `site_language` when it is a supported
  article column language, else `en`. An article is eligible only when
  `title_{lang}` and `content_{lang}` are non-empty; English is never sent
  as another language.
- Eligible: the customer feed's own rule, shared in
  `apps/web/lib/blog/connector-query.ts`: `is_published = true`,
  `show_on_website` true or null. Archived articles stay eligible in every
  channel (owner decision); scheduled articles are held by
  `is_published = false`. Composition is shared with the feed through
  `apps/web/lib/blog/connector-article.ts`; the date is
  `published_at`, else `created_at`.
- Candidates are paged server-side until the per-run budget is filled, so
  the size of the delivery ledger never hides an older article. A legacy
  success row without `odoo_post_id` does not count as delivered.
- Only `push_status = 'success'` rows exclude an article; failed rows retry.
  (Slice 2 below replaces this with change detection, takedown and backoff.)
- Delivered means: HTTP 2xx, JSON object, `success === true`, `post_id` a
  positive integer, and `article_id` equal to the sent id when present.
  Anything else, including a 200 login page, is a failure.

Receiver rules:
- Identity: a `launchmind_article_id` field on `blog.post` (indexed,
  `copy=False`). Lookup by that field first; else the legacy `lm:<id>`
  keyword marker in the Launchmind blog, and then backfill the field.
- Translatable fields are written in the active Odoo language matching
  `language` (e.g. `nl` to `nl_NL`); if none is active, the default context.
- `post_date` from `published_at`; `subtitle` from `excerpt` (fallback
  `meta_description`); `website_meta_title` from `seo_title` (fallback
  title); `website_meta_description` from `meta_description`;
  `website_meta_keywords` from tags only.
- Content and excerpt-derived fields keep the existing sanitizer barrier.
- A cover URL is used only when it is an absolute http(s) URL without
  quotes, parentheses, backslashes or whitespace.
- Success response: `{"success": true, "action", "post_id", "post_url",
  "article_id"}` where `post_url` is the absolute `website_url` Odoo computes.
- Blog selection, author mapping, media download and unpublish are unchanged
  in this slice (slices 2-4).

## Slice 2 contract: keep in sync (existing endpoint, additive)

Owner decisions (2026-11-19): an additive migration on
`odoo_published_articles` is allowed (applied only through the normal
post-merge plan and approval); a deleted Odoo post is found by a daily check
event; a Launchmind post that an Odoo admin archived or unpublished while the
article is still eligible is restored on the next sync; a takedown moves the
Odoo post to draft and keeps it.

Ledger, per `(subscription_id, launchmind_article_id)`. New columns:
`source_updated_at` (the article's `updated_at` at the last delivered
publish), `composition_key` (hash of the subscription's composition inputs:
language, `hide_tags`, `hide_powered_by` and the lead-capture options),
`attempt_count` (failed attempts since the last success, default 0) and
`next_attempt_at` (null means due now). `backlink_subscriptions` gets
`odoo_last_reconciled_at` and `odoo_last_check_attempt_at`. `push_status` is `success` (live in Odoo),
`withdrawn` (draft in Odoo) or `failed` (the last attempt failed).
`odoo_post_id` is kept on failure, so a known Odoo post is never forgotten.

Per subscription and run, from the shared visible-article rule (archived stays
eligible) and the ledger, in this priority within the existing budgets:
1. Withdraw: a row with an `odoo_post_id` and status `success` or `failed`
   whose article is no longer eligible (unpublished, hidden, missing its
   localized title or content, or deleted on the platform) gets
   `article.unpublished`. Success sets `withdrawn`.
2. Publish: an eligible article without a delivered row, or with status
   `withdrawn` or `failed`, gets `article.published`.
3. Update: an eligible `success` row whose article `updated_at` is newer than
   `source_updated_at`, or whose `composition_key` differs, or whose
   `source_updated_at` is null, gets `article.published` again.
4. Check (runs first in a subscription's turn, outside the article budget,
   bounded by the run's time budget): once per 24 hours per subscription, `articles.check` sends the ids
   of `success` rows (at most 500 per request). The ids Odoo reports as
   stale get `source_updated_at` cleared, so rule 3 re-sends them.

Only rows whose `next_attempt_at` is null or due are attempted. A failure
increments `attempt_count` and sets `next_attempt_at` to now plus 1 minute,
5 minutes, 30 minutes, 2 hours, 6 hours, then 24 hours for every later
attempt; it never gives up. Success resets both. A failed or unfinished check does not
change article rows or `odoo_last_reconciled_at`; `odoo_last_check_attempt_at`
holds the next check back for an hour.
An article that passes the shared rule but does not compose for Odoo (for
example a whitespace-only localized title) counts as ineligible for Odoo:
it is withdrawn, never published. The shared feed rule is unchanged.

Events, all on `POST {odoo_url}/launchmind-blog/webhook` with the slice 1
auth and the `X-Launchmind-Event` header:
- `article.published`: the slice 1 body and acknowledgement.
- `article.unpublished`: `{"event", "article": {"id"}}`. Acknowledgement:
  `success === true` and `article_id` equal to the sent id; `post_id` is the
  drafted post or null when Odoo has no such post. Both count as withdrawn.
- `articles.check`: `{"event", "article_ids": [...]}`. Acknowledgement:
  `success === true` and `stale` an array of strings, each one of the sent
  ids.

Receiver rules:
- Identity lookups include archived posts (`active_test=False`).
- `article.published` on an archived or unpublished owned post sets
  `active = True` and publishes it; a missing post is recreated. The response
  `action` is `created`, `updated`, `restored` or `recreated` where Odoo can
  tell.
- `article.unpublished` sets `is_published = False` on the owned post and
  keeps it; it never deletes or archives.
- `articles.check` reports an id as stale when Odoo has no owned post for it,
  or the post is archived or unpublished.
- An un-upgraded module rejects the new events with a 4xx; the platform
  treats that as a failure with backoff, never as success.

## Slice 3 contract: media (existing endpoint, additive)

Owner decisions (2026-11-19): the platform fetches every image and sends the
bytes; Odoo needs no outbound access. A post is published even when an image
fails; transient image failures are retried, and so is an image that the
receiver could not store (owner decision, round 3 of the slice 3 review).
After a successful update,
Launchmind-owned attachments the post no longer uses are deleted; an empty
cover clears the cover; customer-uploaded attachments are never touched. Any
public https image that passes the platform's guarded fetch may be stored.
A second additive migration adds `odoo_published_articles.media_pending`
(boolean, not null, default false).

Platform, per `article.published`:
- Images: the cover (`cover_image_url`) and every `<img src>` in the
  composed content with an absolute https URL, de-duplicated by URL, in
  document order, at most 10 per article (the cover first). Images beyond
  that stay remote and are not pending.
- Each image is fetched with `guardedFetchResponseBytes` (8 s, at most 5 MiB, the
  guarded fetch's hop and public-address rules). The type comes from the
  bytes: JPEG, PNG, GIF or WebP by their fixed signatures. There is no
  runtime declaration: platform (`sniffOdooImage`) and receiver
  (`sniff_image`) each check the bytes directly, and the module's
  `test/image_sniff_cases.json` is the one set of byte samples both test
  suites must classify identically. SVG and anything else is rejected. The
  request carries at most 15 MiB of decoded image bytes; images that would
  exceed it stay remote and are pending.
- A permanent image failure (unsafe or non-https URL, too large, not an
  accepted image type, 4xx) leaves the image remote and is not pending. A
  transient failure (timeout, network error, 5xx, 429) leaves it remote and
  sets `media_pending`. HTTP error status decides even when its body exceeds
  the cap. Empty, malformed, private or mixed DNS answers are permanent and
  never fetched; resolver exceptions (including EAI_AGAIN) are transient for
  Odoo media, including redirect targets. Other guarded-fetch callers retain
  their existing DNS diagnostics.
- A delivered publish with `media_pending` true keeps `push_status
  'success'` and is re-sent by the update rule under the slice 2 backoff
  (`attempt_count`, `next_attempt_at`); a publish with no pending media
  resets `media_pending` and the backoff.
- A publish that carries image bytes gets a 25 s push deadline; the cron
  starts no new image work after 25 s of its run, so every push still ends
  inside the route's 60 s.
  If a reverse proxy returns 413, the sender retries without media within
  the same deadline. A successful text-only fallback sets `media_pending`.
- A success reply with `media_deferred: true` is still a delivery: it
  sets `media_pending` like the text-only fallback.
- Successful delivery has a required internal `mediaPending` boolean.
  The ledger consumes it once after combining downloaded and receiver-pending
  media. Decoded-byte overflow stays pending across repeated successful updates.
- Each two-item batch settles all started items and persists its ledger rows
  before the next batch starts. A thrown media/push/withdraw operation becomes
  a failed row with backoff and retains prior post identity. A failed upsert
  stops later sends, preserves prior batch commits, and reports interrupted
  delivery diagnostics rather than full success.
- The daily check's stale-id ledger write is split into chunks of 100 ids;
  the webhook check request keeps 500.

Payload, additive to slice 1 and 2:

```json
"media": [
  {
    "sha256": "<hex of the bytes>",
    "mime": "image/jpeg | image/png | image/gif | image/webp",
    "source_url": "<the URL as it appears in content or cover_image_url>",
    "role": "cover | inline",
    "alt": "<cover_image_alt for the cover; the img alt for inline>",
    "data": "<base64 bytes>"
  }
]
```

Receiver rules:
- `media` is optional; an un-upgraded platform sends none and the slice 1
  behavior holds. Each entry is validated before any write: a known role,
  an accepted mime, `sha256` matching the decoded bytes, the bytes
  sniffing as exactly the claimed mime, at most 10 entries and 15 MiB decoded. An
  invalid entry is ignored (its image stays remote), never stored.
- Each image becomes an `ir.attachment` owned by Launchmind (a
  `launchmind_sha256` field on the attachment), linked to the post
  (`res_model = 'blog.post'`, `res_id`), `public = True`. The same post and
  `sha256` reuse the existing attachment.
- The cover becomes `cover_properties` with `url(/web/image/<id>)` and the
  cover alt is stored with it. The receiver resolves the cover once: a
  delivered `cover` entry whose `source_url` equals `cover_image_url` wins;
  otherwise the remote URL is kept; inline `<img>` elements whose `src` equals a
  delivered `source_url` get `/web/image/<id>` and the delivered alt. An
  empty `cover_image_url` clears the cover.
- After a successful write, Launchmind-owned attachments of that post that
  the new cover and content no longer reference are deleted. Attachments
  without `launchmind_sha256` are never deleted.
- Image storage runs in a savepoint after the text write. If it fails,
  only the image work rolls back: the post keeps its new text and
  publication state, no partial Launchmind attachments remain, and the
  reply is the slice 1 acknowledgement plus `"media_deferred": true`.
  Otherwise the reply adds nothing. Old platforms ignore the field.

## Slice 4 contract: native metadata and destination (existing endpoint, additive)

Owner decisions (2026-11-20, plan section "Owner decisions: remaining
delivery"): connector-owned authors per source author, exact-label native
tags, explicit website/blog selection, destination locked once owned posts
exist. Module version 18.0.1.5.0.

Payload, additive to slices 1-3 (`article.*`):

```json
"author_key": "client_author:<uuid> | name:<normalized name> | launchmind",
"author_profile": { "name": "", "role": "", "bio": "", "linkedin_url": "" }
```

Platform rules:
- `author_key` is `client_author:<launchmind_blog_posts.author_id>` when the
  article has an author id; otherwise `name:` plus the display author name
  (the same `author` value already sent) trimmed, lowercased, inner
  whitespace collapsed; `launchmind` when there is no name.
- `author_profile` carries the article's `author_profile` name, role, bio and
  `linkedin_url` when present (strings, `''` when absent). `author` keeps its
  slice 1 meaning.
- `tags` keeps its slice 1 meaning: the visible tag set, `[]` when the
  subscription hides tags.
- The composition key includes a payload version (2 for this slice), so
  every delivered article is re-sent once and existing posts get native
  authors and tags (a data fix for existing rows, not only for new ones).
- A receiver reply `409` with `"error": "destination_not_configured"` is a
  failure under the slice 2 backoff; its message is the diagnostic.

Receiver rules:
- Destination: `launchmind_blog.website_id` and `launchmind_blog.blog_id`
  (Settings > Website > Launchmind Blog, two required selections). Valid only
  when both exist and the blog's website is empty or equals the selected
  website. `article.published` without a valid destination replies 409
  `destination_not_configured` before any write; `article.unpublished` and
  `articles.check` work on existing owned posts without a destination.
- New owned posts are created in the selected blog. Updates never write
  `blog_id`, so an existing post never moves and its URL stays.
- Lock: saving a different blog or website is refused (UserError) while any
  owned post (`launchmind_article_id` set, archived included) exists.
  Clearing or moving requires a separate migration.
- Upgrade: a post-migration to 18.0.1.5.0 sets the destination once when it
  is empty and exactly one blog holds owned or legacy-marker posts (the
  connector's own former `Launchmind Blog`). Otherwise it stays empty and
  publication waits for the operator; nothing is guessed.
- Authors: `res.partner.launchmind_author_key` (unique, copy=False) is the
  only identity. The receiver finds the partner by key (archived included),
  creates it when missing (`company_type` person, `name`, `function` from
  role, `website` from `linkedin_url`, `comment` from bio) and on later
  deliveries writes only those fields on that owned partner. A partner
  without the key is never selected, renamed or merged, even when its name
  matches. Missing `author_key` (old platform) uses `name:` of the author
  name, else `launchmind`, the same derivation. The fallback partner is
  named `Launchmind`.
- Tags: for each label in `tags` (trimmed, non-empty, de-duplicated by exact
  value, document order, at most 20), an existing `blog.tag` whose name
  equals the label exactly in the write language is reused read-only;
  otherwise a tag is created. The post's `tag_ids` is replaced with exactly
  that set, so an empty `tags` clears the post's assignments. Tag records
  are never renamed, deleted or rewritten. `website_meta_keywords` keeps its
  slice 1 value.
