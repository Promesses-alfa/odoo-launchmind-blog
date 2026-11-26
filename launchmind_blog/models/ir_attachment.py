"""Ownership marker for attachments managed by the connector."""

from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    launchmind_sha256 = fields.Char(index=True, copy=False, readonly=True)
