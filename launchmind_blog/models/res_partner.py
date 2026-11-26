"""Connector-owned author identities never claim customer contacts."""

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    launchmind_author_key = fields.Char(index=True, copy=False)

    _sql_constraints = [
        (
            'launchmind_author_key_unique',
            'unique(launchmind_author_key)',
            'A Launchmind author key can only belong to one partner.',
        ),
    ]
