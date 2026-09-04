from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    facodi_learning_analysis_provider = fields.Selection(
        [("local_metadata", "Local Odoo metadata")],
        string="FACODI analysis provider",
        required=True,
        default="local_metadata",
        config_parameter="facodi_learning.analysis_provider",
        help="Provider used for new FACODI analysis jobs. Provider addons may extend this selection.",
    )
    facodi_learning_analysis_batch_size = fields.Integer(
        string="FACODI analysis batch size",
        required=True,
        default=10,
        config_parameter="facodi_learning.analysis_batch_size",
        help="Maximum number of pending FACODI analysis jobs processed by one scheduled-action batch.",
    )
