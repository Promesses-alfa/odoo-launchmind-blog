# -*- coding: utf-8 -*-
"""Durable replay receipts for signed Launchmind requests.

The unique (key_id, request_id) constraint is the admission: a second
insert of the same pair, from any worker or after a restart, finds the
committed row (or waits for the competing transaction) and is refused.
"""

from datetime import datetime, timezone

from odoo import api, fields, models

from ..utils.signing import receipt_expiry


class LaunchmindBlogReceipt(models.Model):
    _name = 'launchmind.blog.receipt'
    _description = 'Launchmind signed request receipt'
    _log_access = False

    key_id = fields.Char(required=True, size=36, readonly=True)
    request_id = fields.Char(required=True, size=36, readonly=True)
    expires_at = fields.Datetime(required=True, readonly=True, index=True)

    _sql_constraints = [
        (
            'key_request_unique',
            'unique(key_id, request_id)',
            'A signed request is admitted once.',
        ),
    ]

    @api.model
    def _admit(self, key_id: str, request_id: str, timestamp: int) -> bool:
        expires_at = datetime.fromtimestamp(receipt_expiry(timestamp), timezone.utc).replace(
            tzinfo=None
        )
        self.env.cr.execute(
            'INSERT INTO launchmind_blog_receipt (key_id, request_id, expires_at) '
            'VALUES (%s, %s, %s) ON CONFLICT (key_id, request_id) DO NOTHING RETURNING id',
            (key_id, request_id, expires_at),
        )
        return self.env.cr.fetchone() is not None

    @api.autovacuum
    def _gc_expired_receipts(self):
        self.env.cr.execute(
            'DELETE FROM launchmind_blog_receipt WHERE expires_at < %s',
            (fields.Datetime.now(),),
        )
