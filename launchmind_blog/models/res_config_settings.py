# -*- coding: utf-8 -*-
"""
Launchmind Blog — Settings

Extends ``res.config.settings`` so the merchant can paste their Launchmind
API key under Settings > Website > Launchmind Blog and click "Connect".
The Connect action POSTs to the Launchmind register endpoint with this
Odoo's own ``web.base.url`` so launchmind.io knows where to push articles.

Settings and signing key slots live in ``ir.config_parameter``; replay
receipts live in ``launchmind.blog.receipt``.
"""

import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from odoo import _, api, fields, models, release, tools
from odoo.exceptions import UserError

from ..utils.webhook_values import language_base
from ..utils.destination import (
    DESTINATION_MESSAGE,
    destination_default_language,
    parameter_id,
    validate_destination,
)
from ..utils.enrollment import (
    PARAM_API_KEY,
    PARAM_CONNECTED,
    PARAM_PENDING,
    PARAM_RATCHET,
    PARAM_SUBSCRIPTION,
    fresh_param,
    lock,
    read_state,
    write_param,
    write_slot,
)
from ..utils.signing import (
    MAX_REGISTER_RESPONSE_BYTES,
    MODULE_VERSION,
    REGISTER_EVENT,
    SUPPORTED_SERIES,
    base_url_allowed,
    is_uuid,
    parse_registration,
    request_headers,
    runtime_supported,
)

try:
    # ``requests`` ships with Odoo and is the standard way to call external
    # HTTP APIs from server code.
    import requests
except ImportError:  # pragma: no cover - defensive: should never happen on Odoo 18
    requests = None

_logger = logging.getLogger(__name__)


# One module version constant (utils/signing.py), in lockstep with __manifest__.py.
LAUNCHMIND_MODULE_VERSION = MODULE_VERSION


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    launchmind_website_id = fields.Many2one(
        'website',
        string='Publication website',
        config_parameter='launchmind_blog.website_id',
    )
    launchmind_blog_id = fields.Many2one(
        'blog.blog',
        string='Publication blog',
        config_parameter='launchmind_blog.blog_id',
    )

    def set_values(self):
        self.ensure_one()
        website, blog = self.launchmind_website_id, self.launchmind_blog_id
        params = self.env['ir.config_parameter'].sudo()
        previous = (
            parameter_id(params.get_param('launchmind_blog.website_id')),
            parameter_id(params.get_param('launchmind_blog.blog_id')),
        )
        selected = (website.id or 0, blog.id or 0)
        if previous != selected and self.env['blog.post'].sudo().with_context(
            active_test=False
        ).search_count([('launchmind_article_id', '!=', False)], limit=1):
            raise UserError(
                _(
                    'The Launchmind destination is locked while owned posts exist. '
                    'Use a separate migration to clear or move it.'
                )
            )
        if (website or blog) and not validate_destination(
            website.id, blog.id, blog.website_id.id if blog else 0
        ):
            raise UserError(_(DESTINATION_MESSAGE))
        return super().set_values()

    launchmind_api_base = fields.Char(
        string='Launchmind API Base URL',
        config_parameter='launchmind_blog.api_base',
        default='https://launchmind.io',
        help='Leave at the default unless you are pointing this Odoo at a '
        'staging environment of Launchmind.',
    )

    launchmind_api_key = fields.Char(
        string='Launchmind API Key',
        config_parameter='launchmind_blog.api_key',
        help='Your personal Launchmind API key. Find it in your Launchmind '
        'dashboard under Settings > API. The webhook receiver also uses '
        'this key to authenticate incoming pushes from launchmind.io.',
    )

    launchmind_connected = fields.Boolean(
        string='Connected',
        config_parameter='launchmind_blog.connected',
        default=False,
        readonly=True,
    )

    launchmind_connected_at = fields.Char(
        string='Connected since',
        config_parameter='launchmind_blog.connected_at',
        readonly=True,
    )

    launchmind_last_status = fields.Char(
        string='Last status',
        config_parameter='launchmind_blog.last_status',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _launchmind_publication_language(self):
        # The blog's language is the destination website's default (falling back
        # to the current website), not the connecting admin's interface language.
        return language_base(destination_default_language(self.env, self.launchmind_website_id))

    def _launchmind_loopback_allowed(self):
        # Only an explicit server option, set by a controlled local test,
        # admits a loopback Launchmind origin.
        return bool(tools.config.get('launchmind_blog_allow_loopback'))

    def action_launchmind_connect(self):
        """Register this Odoo installation with launchmind.io.

        Before any enrollment, the API key authenticates the request (bearer).
        Once this database holds a current signing key, the request is signed
        with it instead and carries no API key at all. The response is
        validated in full before any key material is stored.
        """
        self.ensure_one()
        if not runtime_supported(release.serie):
            raise UserError(
                _(
                    'Launchmind Blog supports Odoo %(supported)s only; this server runs Odoo %(actual)s.'
                )
                % {'supported': SUPPORTED_SERIES, 'actual': release.serie}
            )
        if requests is None:
            raise UserError(
                _('The Python `requests` library is not available; cannot contact Launchmind.')
            )
        env = self.env
        api_base = base_url_allowed(
            self.launchmind_api_base
            or fresh_param(env, 'launchmind_blog.api_base')
            or 'https://launchmind.io',
            self._launchmind_loopback_allowed(),
        )
        if not api_base:
            raise UserError(_('The Launchmind API Base URL must be a public HTTPS address.'))
        configured_base = fresh_param(env, 'web.base.url')
        if not configured_base:
            raise UserError(
                _(
                    'Could not determine your Odoo base URL. Please set web.base.url in System Parameters first.'
                )
            )
        base_url = base_url_allowed(configured_base, allow_loopback=True)
        if not base_url:
            raise UserError(
                _(
                    'Your Odoo base URL must use HTTPS for the Launchmind webhook to work. '
                    'Update web.base.url under Settings > Technical > System Parameters.'
                )
            )

        # Held until this transaction commits, so no webhook is admitted
        # against the state this Connect is replacing.
        lock(env)
        state = read_state(env)
        if state.corrupt:
            raise UserError(
                _('The Launchmind signing state is unreadable. Contact Launchmind support.')
            )
        installation_id = state.database_uuid
        if not is_uuid(installation_id) or not state.bound:
            raise UserError(
                _(
                    'This database is a copy of another Launchmind installation. '
                    'Contact Launchmind support to connect it.'
                )
            )
        company = env.company
        raw = json.dumps(
            {
                'event': REGISTER_EVENT,
                'installation_id': installation_id,
                'odoo_url': base_url,
                'runtime_series': release.serie,
                'runtime_version': release.version,
                'module_version': MODULE_VERSION,
                'company_name': company.name or '',
                'contact_email': company.email or '',
                'language': self._launchmind_publication_language(),
            },
            separators=(',', ':'),
        ).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Launchmind-Odoo-Module/' + MODULE_VERSION,
        }
        current = state.current
        if current is not None:
            headers.update(
                request_headers(
                    current.secret,
                    installation_id,
                    current.kid,
                    str(uuid.uuid4()),
                    int(time.time()),
                    raw,
                )
            )
        else:
            api_key = (self.launchmind_api_key or fresh_param(env, PARAM_API_KEY)).strip()
            if not api_key:
                raise UserError(_('Please enter your Launchmind API key first.'))
            headers['Authorization'] = 'Bearer ' + api_key

        try:
            response = requests.post(
                api_base + '/api/integrations/odoo/register',
                data=raw,
                headers=headers,
                timeout=15,
                allow_redirects=False,
                stream=True,
            )
            try:
                body = _read_capped(response, MAX_REGISTER_RESPONSE_BYTES)
            finally:
                response.close()
        except requests.exceptions.RequestException as exc:
            raise UserError(_('Could not reach Launchmind (%s).') % type(exc).__name__) from exc
        except ValueError as exc:
            raise UserError(_('Launchmind returned an unexpected response.')) from exc
        status = response.status_code
        if 300 <= status < 400:
            raise UserError(_('Launchmind answered with a redirect; it was not followed.'))
        if status == 401:
            raise UserError(
                _(
                    'Launchmind rejected the API key. Please double-check it in your Launchmind dashboard.'
                )
                if current is None
                else _('Launchmind rejected the signed request. Contact Launchmind support.')
            )
        if status == 403:
            raise UserError(
                _('Your Launchmind subscription is not active. Please reactivate it and try again.')
            )
        if status >= 400 or status < 200:
            code = _error_code(body) or 'http_%s' % status
            if code == 'url_in_use':
                raise UserError(
                    _('This Odoo URL is already connected to a different Launchmind account.')
                )
            raise UserError(_('Launchmind returned an error: %s') % code)
        try:
            registration = parse_registration(
                body,
                installation_id,
                current.kid if current is not None else None,
                datetime.now(timezone.utc),
            )
        except ValueError as exc:
            raise UserError(_('Launchmind returned an unexpected response.')) from exc

        if registration.pending is not None:
            write_slot(env, PARAM_PENDING, registration.pending)
            write_param(env, PARAM_RATCHET, 'True')
        else:
            # Confirmed for the current key means the platform holds no
            # pending grant; a local one can never be confirmed any more.
            write_slot(env, PARAM_PENDING, None)
        write_param(env, PARAM_SUBSCRIPTION, registration.subscription_id)
        write_param(env, PARAM_CONNECTED, 'True')
        write_param(env, 'launchmind_blog.connected_at', fields.Datetime.now().isoformat())
        write_param(
            env,
            'launchmind_blog.last_status',
            'pending_confirmation' if registration.pending is not None else 'connected',
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Launchmind Connected'),
                'message': _(
                    'Your Odoo Website is now connected to Launchmind. New '
                    'articles will appear in Website > Blog within 1 minute '
                    'of being published.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_launchmind_disconnect(self):
        """Local-only disconnect: stops this receiver from accepting pushes.

        We deliberately do NOT call back to launchmind.io; the Launchmind
        admin can revoke the link independently. Signing keys and the
        enrollment ratchet stay: a reconnect still needs the active key, and
        bearer delivery never returns.
        """
        self.ensure_one()
        env = self.env
        lock(env)
        write_param(env, PARAM_API_KEY, '')
        write_param(env, PARAM_CONNECTED, 'False')
        write_param(env, 'launchmind_blog.connected_at', '')
        write_param(env, 'launchmind_blog.last_status', 'disconnected')

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }


def _read_capped(response, limit):
    chunks, size = [], 0
    for chunk in response.iter_content(8192):
        size += len(chunk)
        if size > limit:
            raise ValueError('Response too large')
        chunks.append(chunk)
    return b''.join(chunks)


def _error_code(body):
    try:
        code = json.loads(body).get('error')
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, str) and re.fullmatch(r'[a-z0-9_]{1,64}', code) else None
