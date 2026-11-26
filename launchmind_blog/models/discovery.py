# -*- coding: utf-8 -*-
"""Publication evidence, discovery policy and IndexNow convergence.

One row per (source UUID, native URL) survives the post itself, so a
deleted, drafted or moved article can still be withdrawn. Current native
state decides what is due; a rendered anonymous response decides whether
an update may be promoted. Site-wide doubt holds everything instead of
sending anything.
"""

import json
import logging
import platform
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from odoo import api, fields, models, modules, release

from ..utils import outbound
from ..utils.destination import find_destination, parameter_id
from ..utils.enrollment import (
    PARAM_API_KEY,
    PARAM_CONNECTED,
    PARAM_SUBSCRIPTION,
    EnrollmentState,
    fresh_param,
    read_state,
)
from ..utils.signing import (
    ACK_HEADER,
    ack_signature,
    is_uuid,
    request_headers,
    runtime_supported,
)
from ..utils import site_policy, telemetry

_logger = logging.getLogger(__name__)

PARAM_DISCOVERY = 'launchmind_blog.discovery_enabled'
PARAM_INDEXNOW = 'launchmind_blog.indexnow_enabled'
PARAM_TELEMETRY = 'launchmind_blog.telemetry_enabled'
PARAM_PRODUCTION = 'launchmind_blog.production_origin'
# The database UUID that designated production; a copy no longer matches.
PARAM_PRODUCTION_BINDING = 'launchmind_blog.production_installation'
PARAM_INDEXNOW_KEY = 'launchmind_blog.indexnow_key'
PARAM_INDEXNOW_BINDING = 'launchmind_blog.indexnow_key_installation'
PARAM_DISCOVERY_HOLD = 'launchmind_blog.discovery_hold'
PARAM_INDEXNOW_HOLD = 'launchmind_blog.indexnow_hold'
PARAM_HEALTH_AT = 'launchmind_blog.health_accepted_at'
PARAM_HEALTH_CODE = 'launchmind_blog.health_code'
PARAM_INDEXNOW_PROOF_AT = 'launchmind_blog.indexnow_last_permit_at'

VERIFY_PER_RUN = 10
PAGE_TIMEOUT = 5.0


def enabled(value: str) -> bool:
    return (value or '').lower() == 'true'


@dataclass(frozen=True)
class Config:
    discovery: bool
    indexnow: bool
    telemetry: bool
    origin: str | None
    production_bound: bool
    indexnow_key: str | None
    neutralized: bool
    connected: bool
    api_key: str
    subscription_id: str | None
    api_base: str
    enrollment: EnrollmentState


def read_config(env) -> Config:
    """Cache-free reads; safe without the enrollment lock (no decision writes)."""
    state = read_state(env)
    database_uuid = state.database_uuid
    key = fresh_param(env, PARAM_INDEXNOW_KEY)
    subscription = fresh_param(env, PARAM_SUBSCRIPTION)
    return Config(
        discovery=enabled(fresh_param(env, PARAM_DISCOVERY)),
        indexnow=enabled(fresh_param(env, PARAM_INDEXNOW)),
        telemetry=enabled(fresh_param(env, PARAM_TELEMETRY)),
        origin=site_policy.production_origin(fresh_param(env, PARAM_PRODUCTION)),
        production_bound=bool(database_uuid)
        and fresh_param(env, PARAM_PRODUCTION_BINDING) == database_uuid,
        indexnow_key=(
            key
            if site_policy.is_indexnow_key(key)
            and fresh_param(env, PARAM_INDEXNOW_BINDING) == database_uuid
            else None
        ),
        neutralized=bool(fresh_param(env, 'database.is_neutralized')),
        connected=enabled(fresh_param(env, PARAM_CONNECTED)),
        api_key=fresh_param(env, PARAM_API_KEY).strip(),
        subscription_id=subscription if is_uuid(subscription) else None,
        api_base=(fresh_param(env, 'launchmind_blog.api_base') or 'https://launchmind.io').rstrip(
            '/'
        ),
        enrollment=state,
    )


def checkpoint(env) -> None:
    """Make evidence durable before an external effect (cron transactions only)."""
    if not modules.module.current_test:
        env.cr.commit()


def _now() -> datetime:
    return fields.Datetime.now()


class LaunchmindBlogUrl(models.Model):
    _name = 'launchmind.blog.url'
    _description = 'Launchmind published URL evidence'
    _order = 'id'

    source_uuid = fields.Char(required=True, size=36, index=True, readonly=True)
    url = fields.Char(required=True, size=2048, readonly=True)
    origin = fields.Char(required=True, size=255, readonly=True)
    post_id = fields.Many2one('blog.post', ondelete='set null', index=True, readonly=True)
    title = fields.Char(readonly=True)
    eligible = fields.Boolean(readonly=True)
    ever_eligible = fields.Boolean(readonly=True)
    fingerprint = fields.Char(size=64, readonly=True)
    desired = fields.Selection(
        [('none', 'Nothing'), ('update', 'Update'), ('withdraw', 'Withdraw')],
        default='none',
        required=True,
        readonly=True,
    )
    desired_revision = fields.Integer(default=0, readonly=True)
    desired_fingerprint = fields.Char(size=64, readonly=True)
    accepted_revision = fields.Integer(default=0, readonly=True)
    accepted_operation = fields.Selection(
        [('update', 'Update'), ('withdraw', 'Withdraw')], readonly=True
    )
    accepted_fingerprint = fields.Char(size=64, readonly=True)
    accepted_at = fields.Datetime(readonly=True)
    state = fields.Selection(
        [
            ('idle', 'Up to date'),
            ('pending', 'Pending'),
            ('retrying', 'Retrying'),
            ('blocked', 'Blocked'),
            ('held', 'Held'),
        ],
        default='idle',
        required=True,
        readonly=True,
        index=True,
    )
    attempts = fields.Integer(default=0, readonly=True)
    next_attempt_at = fields.Datetime(readonly=True)
    last_code = fields.Char(size=64, readonly=True)
    checked_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        ('source_url_unique', 'unique(source_uuid, url)', 'One evidence row per source and URL.'),
    ]

    # ------------------------------------------------------------------
    # Native facts
    # ------------------------------------------------------------------

    @api.model
    def _destination(self):
        return find_destination(self.env) or (None, None)

    @api.model
    def _site_hold(self, config: Config) -> str | None:
        """Holds that apply to every URL: nothing is promoted or withdrawn."""
        if config.neutralized:
            return 'database_neutralized'
        if not config.origin:
            return 'production_not_designated'
        if not config.production_bound or not config.enrollment.bound:
            return 'clone_detected'
        website, _blog = self._destination()
        if not website:
            return 'destination_not_configured'
        if site_policy.production_origin(website.domain or None) != config.origin:
            return 'production_origin_mismatch'
        return None

    @api.model
    def _owned_posts(self, blog):
        return self._scan_batch(
            self.env['blog.post'].sudo().with_context(active_test=False),
            [('launchmind_article_id', '!=', False), ('blog_id', '=', blog.id)],
            'posts',
        )

    @api.model
    def _scan_batch(self, model, domain, name):
        """Keyset sweep under a frozen ceiling: new rows cannot starve old ones.

        The cursor commits with the evidence, so a rollback repeats work."""
        key = 'launchmind_blog.discovery_scan_' + name
        after = parameter_id(fresh_param(self.env, key))
        ceiling = parameter_id(fresh_param(self.env, key + '_ceiling'))
        bounds = [('id', '>', after), ('id', '<=', ceiling)]
        batch = model.search(domain + bounds, order='id', limit=VERIFY_PER_RUN)
        params = self.env['ir.config_parameter'].sudo()
        if not batch:
            last = model.search(domain, order='id desc', limit=1)
            ceiling = last.id or 0
            params.set_param(key + '_ceiling', ceiling)
            batch = model.search(domain + [('id', '<=', ceiling)], order='id', limit=VERIFY_PER_RUN)
        params.set_param(key, batch[-1].id if batch else 0)
        return batch

    @api.model
    def _natively_public(self, post) -> bool:
        return bool(
            post.active
            and post.is_published
            and post.post_date
            and post.post_date <= _now()
            and is_uuid(post.launchmind_article_id)
        )

    @api.model
    def _native_url(self, post, website, origin: str) -> str:
        lang = website.default_lang_id.code
        return origin + post.with_context(lang=lang).website_url

    @api.model
    def _post_fingerprint(self, post, website, url: str) -> str:
        post = post.with_context(lang=website.default_lang_id.code)
        return site_policy.fingerprint(
            {
                'url': url,
                'name': post.name,
                'subtitle': post.subtitle,
                'content': post.content,
                'meta_title': post.website_meta_title,
                'meta_description': post.website_meta_description,
                'meta_keywords': post.website_meta_keywords,
                'post_date': post.post_date,
                'cover': post.cover_properties,
                'author': post.author_name,
                'tags': sorted(post.tag_ids.mapped('name')),
            }
        )

    @api.model
    def _public_count(self) -> int:
        _website, blog = self._destination()
        if not blog:
            return 0
        self.env['blog.post'].flush_model()
        self.env.cr.execute(
            """SELECT count(*) FROM blog_post
                WHERE blog_id = %s AND active AND is_published AND post_date <= %s
                  AND launchmind_article_id ~ %s""",
            (blog.id, _now(), '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
        )
        return self.env.cr.fetchone()[0]

    # ------------------------------------------------------------------
    # Refresh: native intent plus anonymous rendered evidence
    # ------------------------------------------------------------------

    @api.model
    def _fetch(self, url: str, limit: int) -> outbound.Reply:
        return outbound.send(
            'GET',
            url,
            headers={
                'User-Agent': 'Launchmind-Odoo-Module/policy-check',
                'Accept': 'text/html,text/plain',
            },
            timeout=PAGE_TIMEOUT,
            limit=limit,
        )

    @api.model
    def _robots(self, origin: str):
        try:
            reply = self._fetch(origin + '/robots.txt', site_policy.MAX_ROBOTS_BYTES)
        except outbound.OutboundError:
            return None, 'robots_unavailable'
        if reply.status in (404, 410):
            return [], None
        if reply.status != 200:
            return None, 'robots_unavailable'
        groups = site_policy.parse_robots(reply.body.decode('utf-8', errors='replace'))
        return groups, site_policy.robots_site_hold(groups)

    @api.model
    def _hold_all(self, code: str) -> None:
        self.env['ir.config_parameter'].sudo().set_param(PARAM_DISCOVERY_HOLD, code)
        self.sudo().search([('eligible', '=', True)]).write({'eligible': False})

    @api.model
    def _refresh(self) -> str:
        config = read_config(self.env)
        if not (config.discovery or config.indexnow):
            return 'disabled'
        hold = self._site_hold(config)
        robots = None
        if hold is None:
            robots, hold = self._robots(config.origin)
        if hold is not None:
            self._hold_all(hold)
            return hold
        self.env['ir.config_parameter'].sudo().set_param(PARAM_DISCOVERY_HOLD, False)
        website, blog = self._destination()
        origin = config.origin
        rows = self.sudo()
        now = _now()
        for post in self._owned_posts(blog).filtered(self._natively_public):
            url = self._native_url(post, website, origin)
            row = rows.search(
                [('source_uuid', '=', post.launchmind_article_id), ('url', '=', url)], limit=1
            )
            if not row:
                row = rows.create(
                    {
                        'source_uuid': post.launchmind_article_id,
                        'url': url,
                        'origin': origin,
                        'post_id': post.id,
                    }
                )
            elif row.post_id != post:
                row.post_id = post
            self._verify(row, post, website, robots)
        # Reconcile evidence independently of the post batch. Absence from a
        # bounded scan is NOT evidence of withdrawal. Inspect native identity
        # and URL, including deleted, moved, archived or drafted posts.
        for row in self._scan_batch(rows, [('ever_eligible', '=', True)], 'urls'):
            post = row.post_id.with_context(active_test=False)
            if (
                post
                and post.blog_id == blog
                and post.launchmind_article_id == row.source_uuid
                and self._natively_public(post)
                and self._native_url(post, website, origin) == row.url
            ):
                continue
            values: dict[str, object] = {'eligible': False}
            if row.desired != 'withdraw':
                values.update(
                    desired='withdraw',
                    desired_revision=row.desired_revision + 1,
                    desired_fingerprint=False,
                    state='pending',
                    attempts=0,
                    next_attempt_at=now,
                    last_code=False,
                )
            row.write(values)
        return 'refreshed'

    @api.model
    def _verify(self, row, post, website, robots) -> None:
        now = _now()
        try:
            reply = self._fetch(row.url, site_policy.MAX_PAGE_BYTES)
            restriction = site_policy.rendered_restriction(
                reply.status, reply.headers, reply.body, row.url
            )
        except outbound.OutboundError as exc:
            restriction = exc.code
        if restriction is None and not site_policy.robots_allows(robots, row.url):
            restriction = 'robots_disallowed'
        if restriction is not None:
            row.write(
                {
                    'eligible': False,
                    'checked_at': now,
                    'last_code': restriction,
                    'state': (
                        'held'
                        if row.desired == 'update' and row.desired_revision > row.accepted_revision
                        else row.state
                    ),
                }
            )
            return
        digest = self._post_fingerprint(post, website, row.url)
        values = {
            'eligible': True,
            'ever_eligible': True,
            'fingerprint': digest,
            'title': post.with_context(lang=website.default_lang_id.code).name,
            'checked_at': now,
        }
        current_intent = row.desired == 'update' and row.desired_fingerprint == digest
        accepted = row.accepted_operation == 'update' and row.accepted_fingerprint == digest
        if accepted and row.desired != 'withdraw':
            values.update(state='idle', last_code=False, desired_fingerprint=digest)
        elif not current_intent:
            values.update(
                desired='update',
                desired_revision=row.desired_revision + 1,
                desired_fingerprint=digest,
                state='pending',
                attempts=0,
                next_attempt_at=now,
                last_code=False,
            )
        elif row.state == 'held':
            values.update(state='pending', last_code=False, next_attempt_at=now)
        row.write(values)

    # ------------------------------------------------------------------
    # IndexNow dispatch with a fresh production permit
    # ------------------------------------------------------------------

    @api.model
    def _indexnow_hold(self, config: Config) -> str | None:
        if not config.indexnow:
            return 'indexnow_disabled'
        hold = self._site_hold(config)
        if hold:
            return hold
        if fresh_param(self.env, PARAM_DISCOVERY_HOLD):
            return fresh_param(self.env, PARAM_DISCOVERY_HOLD)
        state = config.enrollment
        if not config.connected:
            return 'not_connected'
        if state.corrupt or state.current is None:
            return 'enrollment_required'
        if state.pending is not None:
            return 'enrollment_pending'
        if not runtime_supported(release.serie):
            return 'incompatible_runtime'
        if not config.indexnow_key:
            return 'indexnow_key_missing'
        if not outbound.https_url_allowed(config.api_base + '/'):
            return 'api_base_not_https'
        return None

    @api.model
    def _due_rows(self, origin: str) -> list[int]:
        self.env.flush_all()
        self.env.cr.execute(
            """
            SELECT id FROM launchmind_blog_url
             WHERE desired <> 'none' AND desired_revision > accepted_revision
               AND origin = %s
               AND state IN ('pending', 'retrying')
               AND (next_attempt_at IS NULL OR next_attempt_at <= %s)
               AND (desired = 'withdraw' OR eligible)
             ORDER BY next_attempt_at NULLS FIRST, id
             LIMIT %s
             FOR UPDATE SKIP LOCKED
            """,
            (origin, _now(), site_policy.INDEXNOW_BATCH),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def _permit(self, config: Config) -> str | None:
        """Return None when a fresh permit for exactly this binding was issued."""
        current = config.enrollment.current
        raw = site_policy.permit_request_body(config.origin, config.indexnow_key)
        headers = request_headers(
            current.secret,
            current.installation_id,
            current.kid,
            str(uuid.uuid4()),
            int(time.time()),
            raw,
        )
        headers['Content-Type'] = 'application/json'
        try:
            reply = outbound.send(
                'POST',
                config.api_base + '/api/integrations/odoo/indexnow',
                data=raw,
                headers=headers,
                timeout=15.0,
                limit=8192,
            )
        except outbound.OutboundError as exc:
            return 'permit_' + exc.code
        if reply.status != 200:
            return 'permit_' + (site_policy.safe_error(reply.body) or 'http_%d' % reply.status)
        try:
            site_policy.parse_permit(
                reply.body,
                config.origin,
                current.installation_id,
                current.kid,
                config.indexnow_key,
                datetime.now(timezone.utc),
            )
        except (ValueError, TypeError):
            return 'permit_invalid'
        return None

    @api.model
    def _notify(self) -> str:
        config = read_config(self.env)
        params = self.env['ir.config_parameter'].sudo()
        hold = self._indexnow_hold(config)
        if hold:
            params.set_param(PARAM_INDEXNOW_HOLD, hold)
            return hold
        ids = self._due_rows(config.origin)
        if not ids:
            params.set_param(PARAM_INDEXNOW_HOLD, False)
            return 'idle'
        rows = self.sudo().browse(ids)
        claims = [
            (row.id, row.desired_revision, row.desired, row.desired_fingerprint, row.url)
            for row in rows
        ]
        now = _now()
        for row in rows:
            attempts = row.attempts + 1
            # Written before the effect: a crash leaves a bounded retry, not a loss.
            row.write(
                {
                    'attempts': attempts,
                    'next_attempt_at': now + site_policy.backoff(attempts),
                    'last_code': 'in_flight',
                }
            )
        checkpoint(self.env)
        problem = self._permit(config)
        if problem is None:
            # The permit is for this batch only; recheck that nothing moved meanwhile.
            fresh = read_config(self.env)
            if (
                fresh.enrollment.current != config.enrollment.current
                or fresh.origin != config.origin
                or fresh.indexnow_key != config.indexnow_key
                or fresh.enrollment.pending is not None
            ):
                problem = 'binding_changed'
        if problem:
            self._settle(claims, 'held', problem)
            params.set_param(PARAM_INDEXNOW_HOLD, problem)
            checkpoint(self.env)
            return problem
        params.set_param(PARAM_INDEXNOW_PROOF_AT, fields.Datetime.now().isoformat())
        body = site_policy.indexnow_body(config.origin, config.indexnow_key, [c[4] for c in claims])
        try:
            reply = outbound.send(
                'POST',
                site_policy.INDEXNOW_ENDPOINT,
                data=body,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=15.0,
                limit=8192,
            )
            outcome, code = site_policy.classify_indexnow(reply.status)
        except outbound.OutboundError as exc:
            outcome, code = 'retry', exc.code
        self._settle(claims, outcome, code)
        params.set_param(PARAM_INDEXNOW_HOLD, False)
        checkpoint(self.env)
        return outcome

    @api.model
    def _settle(self, claims, outcome: str, code: str | None) -> None:
        """Apply one response under row locks, fenced on the claimed revision."""
        now = _now()
        for row_id, revision, operation, digest, _url in claims:
            self.env.cr.execute(
                'SELECT desired_revision, accepted_revision, attempts FROM launchmind_blog_url '
                'WHERE id = %s FOR UPDATE',
                (row_id,),
            )
            found = self.env.cr.fetchone()
            if not found:
                continue
            desired_revision, accepted_revision, attempts = found
            row = self.sudo().browse(row_id)
            if outcome == 'accepted':
                values: dict[str, object] = {}
                if revision > accepted_revision:
                    values.update(
                        accepted_revision=revision,
                        accepted_operation=operation,
                        accepted_fingerprint=digest,
                        accepted_at=now,
                    )
                if desired_revision == revision:
                    values.update(state='idle', attempts=0, last_code=code or False)
                if values:
                    row.write(values)
                continue
            if desired_revision != revision:
                # A newer intent superseded this attempt; it keeps its own state.
                continue
            if outcome == 'retry' and attempts >= site_policy.MAX_ATTEMPTS:
                outcome_state, outcome_code = 'blocked', 'retry_exhausted'
            else:
                outcome_state = {'retry': 'retrying', 'blocked': 'blocked', 'held': 'pending'}[
                    outcome
                ]
                outcome_code = code
            values = {'state': outcome_state, 'last_code': outcome_code}
            if outcome == 'held':
                # A missing permit is not an attempt against IndexNow.
                values.update(attempts=max(attempts - 1, 0))
            row.write(values)

    # ------------------------------------------------------------------
    # Daily health
    # ------------------------------------------------------------------

    @api.model
    def _send_health(self) -> str:
        config = read_config(self.env)
        params = self.env['ir.config_parameter'].sudo()
        if not config.telemetry:
            return 'telemetry_disabled'
        if config.neutralized:
            code = 'database_neutralized'
        elif not config.api_key:
            code = 'api_key_missing'
        else:
            body = telemetry.health_body(
                config.api_key,
                site_policy.MODULE_VERSION,
                release.version,
                platform.python_version(),
                self._public_count(),
            )
            try:
                reply = outbound.send(
                    'POST',
                    config.api_base + telemetry.HEALTH_PATH,
                    data=body,
                    headers={'Content-Type': 'application/json'},
                    timeout=10.0,
                )
                if reply.status == 200 and telemetry.health_recorded(reply.body):
                    params.set_param(PARAM_HEALTH_AT, fields.Datetime.now().isoformat())
                    code = None
                else:
                    code = 'health_not_recorded'
            except outbound.OutboundError as exc:
                code = 'health_' + exc.code
        params.set_param(PARAM_HEALTH_CODE, code or False)
        return code or 'recorded'

    # ------------------------------------------------------------------
    # Cron entry points
    # ------------------------------------------------------------------

    @api.model
    def _cron_refresh_and_notify(self):
        for step in (self._refresh, self._notify):
            try:
                step()
            except Exception:
                if modules.module.current_test:
                    raise
                # A failing step leaves durable evidence for the next run.
                _logger.exception('[Launchmind] discovery step failed')
                self.env.cr.rollback()
            else:
                checkpoint(self.env)

    @api.model
    def _cron_send_daily_health(self):
        self._send_health()

    @api.model
    def _queue_counts(self) -> dict[str, int]:
        groups = self.sudo().read_group(
            [('state', 'in', ('pending', 'retrying', 'blocked', 'held'))], ['state'], ['state']
        )
        counts = {'pending': 0, 'retrying': 0, 'blocked': 0, 'held': 0}
        for group in groups:
            counts[group['state']] = group['state_count']
        return counts

    @api.model
    def _retry_blocked(self) -> None:
        self.sudo().search([('state', '=', 'blocked')]).write(
            {'state': 'pending', 'attempts': 0, 'next_attempt_at': _now(), 'last_code': False}
        )

    @api.model
    def _new_indexnow_key(self) -> str:
        return secrets.token_hex(16)

    # ------------------------------------------------------------------
    # Public resources served only when nothing else claimed the path
    # ------------------------------------------------------------------

    @api.model
    def _host_matches(self, httprequest, origin: str | None) -> bool:
        return bool(origin) and httprequest.host.lower() == urlsplit(origin).netloc

    @api.model
    def _llms_entries(self, config: Config):
        website, blog = self._destination()
        if not blog:
            return []
        rows = self.sudo().search([('eligible', '=', True), ('origin', '=', config.origin)])
        entries = []
        for row in rows:
            post = row.post_id
            # Re-check native state at serve time; a draft never stays listed.
            if (
                post
                and post.blog_id == blog
                and self._natively_public(post)
                and self._native_url(post, website, config.origin) == row.url
            ):
                entries.append((post.post_date, row.title or post.name, row.url))
        entries.sort(key=lambda entry: entry[0], reverse=True)
        return [(title, url) for _date, title, url in entries[: site_policy.LLMS_LIMIT]]

    @api.model
    def _unclaimed_resource(self, httprequest):
        """(body, content type, extra headers) for a connector-owned path, else None.

        Called only after Odoo's own fallback (attachments, pages, redirects)
        found nothing. Reads are cache-free and take no enrollment lock: the
        platform fetches the proof while a dispatcher may be mid-transaction.
        """
        if httprequest.method not in ('GET', 'HEAD'):
            return None
        path = httprequest.path
        config = read_config(self.env)
        if config.neutralized or not self._host_matches(httprequest, config.origin):
            return None
        if not config.production_bound:
            return None
        if path == '/llms.txt' and config.discovery:
            if self._site_hold(config) or fresh_param(self.env, PARAM_DISCOVERY_HOLD):
                return None
            entries = self._llms_entries(config)
            if not entries:
                return None
            website, _blog = self._destination()
            body = site_policy.llms_text(website.name or '', entries).encode('utf-8')
            return body, 'text/plain; charset=utf-8', {}
        if not config.indexnow or not config.indexnow_key:
            return None
        if path == '/%s.txt' % config.indexnow_key:
            return config.indexnow_key.encode('ascii'), 'text/plain; charset=utf-8', {}
        if path == '/launchmind-blog/production-proof':
            return self._production_proof(httprequest, config)
        return None

    @api.model
    def _production_proof(self, httprequest, config: Config):
        state = config.enrollment
        current = state.current
        challenge = httprequest.args.get('challenge')
        request_id = httprequest.args.get('request_id')
        if (
            set(httprequest.args) != {'challenge', 'request_id'}
            or not is_uuid(challenge)
            or not is_uuid(request_id)
            or not config.connected
            or state.corrupt
            or current is None
            or not state.bound
            or current.installation_id != state.database_uuid
            or not runtime_supported(release.serie)
        ):
            return None
        body = site_policy.proof_body(
            current.installation_id, current.kid, challenge, release.version, config.indexnow_key
        )
        return (
            body,
            'application/json',
            {ACK_HEADER: ack_signature(current.secret, request_id, body)},
        )
