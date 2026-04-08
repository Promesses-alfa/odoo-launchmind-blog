# -*- coding: utf-8 -*-
"""
Launchmind Blog — Settings

Extends ``res.config.settings`` so the merchant can paste their Launchmind
API key under Settings > Website > Launchmind Blog and click "Connect".
The Connect action POSTs to the Launchmind register endpoint with this
Odoo's own ``web.base.url`` so launchmind.io knows where to push articles.

All persisted values live in ``ir.config_parameter`` (Odoo's standard
key/value config store) — there is no custom database table.
"""

import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

try:
    # ``requests`` ships with Odoo and is the standard way to call external
    # HTTP APIs from server code.
    import requests
except ImportError:  # pragma: no cover - defensive: should never happen on Odoo 18
    requests = None

_logger = logging.getLogger(__name__)


# We declare a single major version constant so the settings page and the
# header sent to launchmind.io stay in lockstep with __manifest__.py.
LAUNCHMIND_MODULE_VERSION = '18.0.1.0.1'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

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

    def action_launchmind_connect(self):
        """Register this Odoo with launchmind.io.

        Sends a single POST containing the Odoo base URL + Odoo version to
        the Launchmind register endpoint, authenticated with the API key
        the user just entered. On success we flip ``launchmind_connected``
        to True; on failure we surface the API error to the user.
        """
        self.ensure_one()

        # Always re-read the latest values from settings so the admin's
        # most recent input is what we use, even if they haven't clicked
        # "Save" yet.
        ICP = self.env['ir.config_parameter'].sudo()
        api_base = (self.launchmind_api_base or ICP.get_param('launchmind_blog.api_base') or 'https://launchmind.io').rstrip('/')
        api_key = (self.launchmind_api_key or ICP.get_param('launchmind_blog.api_key') or '').strip()

        if not api_key:
            raise UserError(_('Please enter your Launchmind API key first.'))

        if requests is None:
            raise UserError(_('The Python `requests` library is not available; cannot contact Launchmind.'))

        # The Odoo Website base URL the merchant has configured. This is
        # what launchmind.io will push articles to.
        base_url = ICP.get_param('web.base.url')
        if not base_url:
            raise UserError(_('Could not determine your Odoo base URL. Please set web.base.url in System Parameters first.'))

        base_url = base_url.rstrip('/')

        if not base_url.startswith('https://') and 'localhost' not in base_url and '127.0.0.1' not in base_url:
            raise UserError(_(
                'Your Odoo base URL must use HTTPS for the Launchmind webhook to work. '
                'Update web.base.url under Settings > Technical > System Parameters.'
            ))

        register_url = api_base + '/api/integrations/odoo/register'

        # Pull a couple of metadata fields from the company so the
        # Launchmind admin can identify the install at a glance.
        company = self.env.company
        payload = {
            'odoo_url': base_url,
            'odoo_version': LAUNCHMIND_MODULE_VERSION,
            'company_name': company.name or '',
            'contact_email': company.email or '',
            'language': (self.env.user.lang or 'en')[:2],
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_key,
            'User-Agent': 'Launchmind-Odoo-Module/' + LAUNCHMIND_MODULE_VERSION,
        }

        try:
            response = requests.post(register_url, json=payload, headers=headers, timeout=15)
        except requests.exceptions.RequestException as exc:
            ICP.set_param('launchmind_blog.last_status', 'network_error')
            raise UserError(_('Could not reach Launchmind: %s') % exc) from exc

        if response.status_code == 401:
            ICP.set_param('launchmind_blog.last_status', 'invalid_key')
            raise UserError(_('Launchmind rejected the API key. Please double-check it in your Launchmind dashboard.'))

        if response.status_code == 403:
            ICP.set_param('launchmind_blog.last_status', 'subscription_inactive')
            raise UserError(_('Your Launchmind subscription is not active. Please reactivate it and try again.'))

        if response.status_code == 409:
            ICP.set_param('launchmind_blog.last_status', 'url_in_use')
            raise UserError(_('This Odoo URL is already connected to a different Launchmind account.'))

        if response.status_code >= 400:
            ICP.set_param('launchmind_blog.last_status', 'http_%s' % response.status_code)
            try:
                error_message = response.json().get('error') or response.text
            except (ValueError, json.JSONDecodeError):
                error_message = response.text or 'Unknown error'
            raise UserError(_('Launchmind returned an error: %s') % error_message)

        # Success
        ICP.set_param('launchmind_blog.connected', 'True')
        ICP.set_param('launchmind_blog.connected_at', fields.Datetime.now().isoformat())
        ICP.set_param('launchmind_blog.last_status', 'connected')

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
        """Local-only disconnect: clears the API key and connected flag.

        We deliberately do NOT call back to launchmind.io here — the
        Launchmind admin can revoke the link from their side independently.
        Clearing the local key is enough to stop the webhook receiver from
        accepting incoming pushes.
        """
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('launchmind_blog.api_key', '')
        ICP.set_param('launchmind_blog.connected', 'False')
        ICP.set_param('launchmind_blog.connected_at', '')
        ICP.set_param('launchmind_blog.last_status', 'disconnected')

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
