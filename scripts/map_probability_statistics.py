"""Run through `odoo shell` to apply the reviewed UAlg LESTI UC 19411018 mapping."""

from odoo.addons.facodi_learning.services.probability_statistics_mapping import (
    apply_probability_statistics_mapping,
)


unit = apply_probability_statistics_mapping(env)
env.cr.commit()
print("Mapped UAlg LESTI curricular unit %s: %s" % (unit.external_unit_code, unit.name))