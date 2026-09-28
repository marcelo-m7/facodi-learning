from odoo import SUPERUSER_ID, api

from odoo.addons.facodi_learning.services.curriculum_bootstrap import (
    ensure_design_curricula_2026_27,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ensure_design_curricula_2026_27(env)
