# -*- coding: utf-8 -*-
from odoo import release
from odoo.exceptions import UserError

from . import controllers
from . import models
from .utils.signing import SUPPORTED_SERIES, runtime_supported


def pre_init_hook(env):
    # The actual server series decides, not the manifest's version string.
    if not runtime_supported(release.serie):
        raise UserError(
            'Launchmind Blog supports Odoo %s only; this server runs Odoo %s.'
            % (SUPPORTED_SERIES, release.serie)
        )
