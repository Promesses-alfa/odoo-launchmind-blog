"""Preset only a destination proven by existing connector posts."""

from odoo import SUPERUSER_ID, api
from odoo.addons.launchmind_blog.utils.destination import preset_destination


def migrate(cr, version):
    preset_destination(api.Environment(cr, SUPERUSER_ID, {}))
