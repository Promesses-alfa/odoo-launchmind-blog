# -*- coding: utf-8 -*-
"""Native robots.txt stays authoritative; the connector may only add a comment.

A comment carries no crawler semantics, so customer rules (including
restrictive ones) keep exactly their meaning. Nothing is added when the
file already mentions llms.txt or when no verified listing exists.
"""

from odoo import http
from odoo.addons.website.controllers.main import Website
from odoo.http import request

from ..models.discovery import PARAM_DISCOVERY_HOLD, read_config
from ..utils.enrollment import fresh_param


class LaunchmindRobots(Website):
    @http.route()
    def robots(self, **kwargs):
        response = super().robots(**kwargs)
        try:
            urls = request.env['launchmind.blog.url'].sudo()
            config = read_config(request.env)
            if (
                response.status_code != 200
                or not config.discovery
                or config.neutralized
                or not config.production_bound
                or not urls._host_matches(request.httprequest, config.origin)
                or urls._site_hold(config)
                or fresh_param(request.env, PARAM_DISCOVERY_HOLD)
                or not urls._llms_entries(config)
            ):
                return response
            body = response.get_data(as_text=True)
            if 'llms.txt' in body.lower():
                return response
            separator = '' if body.endswith('\n') else '\n'
            response.set_data(
                body
                + separator
                + '# Launchmind article list (informational): %s/llms.txt\n' % config.origin
            )
        except Exception:  # pragma: no cover - never break the customer's robots.txt
            return response
        return response
