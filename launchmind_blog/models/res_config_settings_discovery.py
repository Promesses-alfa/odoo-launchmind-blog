# -*- coding: utf-8 -*-
"""Discovery and measurement settings in the existing Launchmind Website block.

Every feature is off until the customer turns it on. Production is an
explicit, exact HTTPS origin bound to this database; a copy keeps the value
but loses the binding, so it holds until someone designates it again.
"""

from collections import Counter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..utils import site_policy
from ..utils.enrollment import PARAM_SUBSCRIPTION, fresh_param
from ..utils.signing import is_uuid
from .discovery import (
    PARAM_DISCOVERY,
    PARAM_DISCOVERY_HOLD,
    PARAM_HEALTH_AT,
    PARAM_HEALTH_CODE,
    PARAM_INDEXNOW,
    PARAM_INDEXNOW_BINDING,
    PARAM_INDEXNOW_HOLD,
    PARAM_INDEXNOW_KEY,
    PARAM_PRODUCTION,
    PARAM_PRODUCTION_BINDING,
    PARAM_TELEMETRY,
)

# Safe, actionable text per code; remote error text is never shown.
WARNINGS = {
    'database_neutralized': 'This database is neutralized (staging); discovery is held.',
    'production_not_designated': 'Enter the exact production address to enable discovery.',
    'clone_detected': 'This database is a copy. Clear and re-enter the production address '
    'on the real production database.',
    'destination_not_configured': 'Select a publication website and blog.',
    'production_origin_mismatch': 'The production address differs from the website domain.',
    'robots_unavailable': 'robots.txt could not be read anonymously; discovery is held.',
    'robots_restrictive': 'robots.txt blocks crawlers site-wide; discovery is held.',
    'robots_unsupported': 'robots.txt has rules the connector cannot evaluate; held.',
    'robots_disallowed': 'robots.txt blocks some articles; they are not submitted.',
    'meta_noindex': 'Some articles render noindex; they are not submitted.',
    'x_robots_noindex': 'Some articles send X-Robots-Tag noindex; they are not submitted.',
    'login_page': 'Some articles render a login page for visitors.',
    'canonical_mismatch': 'Some articles have a canonical URL elsewhere.',
    'canonical_missing': 'Some articles render without a canonical URL.',
    'redirected': 'Some articles redirect anonymous visitors.',
    'not_connected': 'Connect to Launchmind first.',
    'enrollment_required': 'Reconnect to Launchmind to finish the signed connection.',
    'enrollment_pending': 'The signed connection is waiting for confirmation.',
    'indexnow_key_missing': 'Save the settings again to create the IndexNow key.',
    'api_base_not_https': 'The Launchmind API address must use HTTPS.',
    'api_key_missing': 'Measurement needs the Launchmind API key.',
    'subscription_unknown': 'Reconnect to Launchmind so views can be attributed.',
    'health_not_recorded': 'Launchmind did not record the last health report.',
    'retry_exhausted': 'Some IndexNow submissions failed repeatedly.',
    'indexnow_400': 'IndexNow rejected a submission (400).',
    'indexnow_403': 'IndexNow rejected the key (403); check /<key>.txt is public.',
    'indexnow_422': 'IndexNow rejected URLs for this host (422).',
    'key_pending': 'IndexNow received URLs; key validation is pending.',
}


def _message(code):
    if code.startswith('permit_'):
        return _('Launchmind did not issue an IndexNow permit (%s).') % code[7:]
    return _(WARNINGS[code]) if code in WARNINGS else _('Check required (%s).') % code


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    launchmind_telemetry_enabled = fields.Boolean(
        string='Measure views, clicks and crawlers',
        config_parameter=PARAM_TELEMETRY,
        help='Only after the customer approved measurement. Visitors send their own '
        'view and click beacons; known crawlers are reported by this server.',
    )
    launchmind_discovery_enabled = fields.Boolean(
        string='Publish /llms.txt',
        config_parameter=PARAM_DISCOVERY,
    )
    launchmind_indexnow_enabled = fields.Boolean(
        string='Notify IndexNow',
        config_parameter=PARAM_INDEXNOW,
    )
    launchmind_production_origin = fields.Char(
        string='Production address',
        config_parameter=PARAM_PRODUCTION,
        help='Exact public HTTPS origin of this production website, for example '
        'https://www.example.com. Leave empty on staging.',
    )
    launchmind_health_accepted_at = fields.Char(
        string='Last accepted health report', compute='_compute_launchmind_status'
    )
    launchmind_last_delivery_at = fields.Char(
        string='Last delivery received', compute='_compute_launchmind_status'
    )
    launchmind_queue_pending = fields.Integer(compute='_compute_launchmind_status')
    launchmind_queue_retrying = fields.Integer(compute='_compute_launchmind_status')
    launchmind_queue_blocked = fields.Integer(compute='_compute_launchmind_status')
    launchmind_queue_held = fields.Integer(compute='_compute_launchmind_status')
    launchmind_warnings = fields.Text(compute='_compute_launchmind_status')

    @api.depends('launchmind_production_origin')
    def _compute_launchmind_status(self):
        env = self.env
        urls = env['launchmind.blog.url'].sudo()
        counts = urls._queue_counts()
        codes = []
        for key in (PARAM_DISCOVERY_HOLD, PARAM_INDEXNOW_HOLD, PARAM_HEALTH_CODE):
            code = fresh_param(env, key)
            if code and code != 'indexnow_disabled' and code not in codes:
                codes.append(code)
        if fresh_param(env, PARAM_TELEMETRY).lower() == 'true' and not is_uuid(
            fresh_param(env, PARAM_SUBSCRIPTION)
        ):
            codes.append('subscription_unknown')
        diagnoses = Counter(
            urls.search([('last_code', 'not in', (False, 'in_flight'))]).mapped('last_code')
        )
        lines = [_message(code) for code in codes]
        lines += [
            '%s (%d)' % (_message(code), count)
            for code, count in sorted(diagnoses.items())
            if code not in codes
        ]
        for record in self:
            record.launchmind_health_accepted_at = fresh_param(env, PARAM_HEALTH_AT) or ''
            record.launchmind_last_delivery_at = (
                fresh_param(env, 'launchmind_blog.last_received_at') or ''
            )
            record.launchmind_queue_pending = counts['pending']
            record.launchmind_queue_retrying = counts['retrying']
            record.launchmind_queue_blocked = counts['blocked']
            record.launchmind_queue_held = counts['held']
            record.launchmind_warnings = '\n'.join(lines)

    def set_values(self):
        self.ensure_one()
        typed = (self.launchmind_production_origin or '').strip()
        if typed and site_policy.production_origin(typed) is None:
            raise UserError(
                _(
                    'The production address must be an exact public HTTPS origin, '
                    'for example https://www.example.com (no path).'
                )
            )
        if self.launchmind_indexnow_enabled and not typed:
            raise UserError(_('IndexNow needs the production address.'))
        self.launchmind_production_origin = typed or False
        env = self.env
        previous = fresh_param(env, PARAM_PRODUCTION)
        result = super().set_values()
        params = env['ir.config_parameter'].sudo()
        database_uuid = fresh_param(env, 'database.uuid')
        if not typed:
            params.set_param(PARAM_PRODUCTION_BINDING, False)
        elif typed != previous:
            # Only an explicit (re)designation binds this database; saving other
            # settings on a copy keeps the stale binding and therefore holds.
            params.set_param(PARAM_PRODUCTION_BINDING, database_uuid)
        bound = typed and fresh_param(env, PARAM_PRODUCTION_BINDING) == database_uuid
        key = fresh_param(env, PARAM_INDEXNOW_KEY)
        if (
            self.launchmind_indexnow_enabled
            and bound
            and (
                typed != previous
                or not site_policy.is_indexnow_key(key)
                or fresh_param(env, PARAM_INDEXNOW_BINDING) != database_uuid
            )
        ):
            params.set_param(PARAM_INDEXNOW_KEY, env['launchmind.blog.url']._new_indexnow_key())
            params.set_param(PARAM_INDEXNOW_BINDING, database_uuid)
        return result

    def action_launchmind_retry_blocked(self):
        self.ensure_one()
        self.env['launchmind.blog.url'].sudo()._retry_blocked()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
