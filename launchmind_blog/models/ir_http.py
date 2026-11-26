# -*- coding: utf-8 -*-
"""Connector resources answer only where Odoo's own fallback answered nothing.

Routes, website pages, attachments and redirects keep precedence because
this runs after ``super()._serve_fallback()`` returned no response.
"""

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _serve_fallback(cls):
        response = super()._serve_fallback()
        if response:
            return response
        resource = (
            request.env['launchmind.blog.url'].sudo()._unclaimed_resource(request.httprequest)
        )
        if resource is None:
            return None
        body, content_type, extra = resource
        headers = [('Content-Type', content_type), ('Cache-Control', 'no-store')]
        headers.extend(extra.items())
        return request.make_response(body, headers=headers)
