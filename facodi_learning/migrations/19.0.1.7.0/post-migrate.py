from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.facodi_learning.services.curriculum_bootstrap import (
        ensure_lesti_2026_27,
    )

    ensure_lesti_2026_27(env)
