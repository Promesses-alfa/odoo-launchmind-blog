"""Stable Launchmind identity, independent of editable SEO metadata."""

from odoo import fields, models


class BlogPost(models.Model):
    _inherit = 'blog.post'

    launchmind_article_id = fields.Char(index=True, copy=False, readonly=True)

    _sql_constraints = [
        (
            'launchmind_article_id_unique',
            'unique(launchmind_article_id)',
            'A Launchmind article can only be linked to one blog post.',
        ),
    ]
