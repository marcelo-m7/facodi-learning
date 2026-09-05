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

    facodi_learning_course_selection_mode = fields.Selection(
        [("manual", "Manual"), ("assisted", "Assisted"), ("auto", "Auto Approve")],
        string="FACODI course selection mode",
        required=True,
        default="manual",
        config_parameter="facodi_learning.course_selection_mode",
        help="Manual requires Manager decisions, Assisted can shortlist, and Auto Approve resolves only candidates that pass every configured guardrail.",
    )
    facodi_learning_auto_approve_min_relevance = fields.Float(
        string="Minimum relevance",
        default=0.80,
        config_parameter="facodi_learning.auto_approve_min_relevance",
        help="Normalized 0..1 relevance threshold required for automatic approval.",
    )
    facodi_learning_auto_approve_min_metadata_quality = fields.Float(
        string="Minimum metadata quality",
        default=0.70,
        config_parameter="facodi_learning.auto_approve_min_metadata_quality",
        help="Normalized 0..1 metadata quality threshold required for automatic approval.",
    )
    facodi_learning_auto_approve_min_language_fit = fields.Float(
        string="Minimum language fit",
        default=0.90,
        config_parameter="facodi_learning.auto_approve_min_language_fit",
        help="Normalized 0..1 language-fit threshold required for automatic approval.",
    )
    facodi_learning_auto_approve_min_coverage = fields.Float(
        string="Minimum coverage",
        default=0.65,
        config_parameter="facodi_learning.auto_approve_min_coverage",
        help="Normalized 0..1 coverage threshold required for automatic approval.",
    )
    facodi_learning_auto_approve_max_duplication_risk = fields.Float(
        string="Maximum duplication risk",
        default=0.30,
        config_parameter="facodi_learning.auto_approve_max_duplication_risk",
        help="Normalized 0..1 duplication-risk ceiling allowed for automatic approval.",
    )
    facodi_learning_course_selection_languages = fields.Char(
        string="Accepted course languages",
        default="pt,en",
        config_parameter="facodi_learning.course_selection_languages",
        help="Comma-separated lower-case language identifiers used by deterministic course evaluation.",
    )
    facodi_learning_auto_approve_trusted_providers = fields.Char(
        string="Auto Approve trusted providers",
        default="manual",
        config_parameter="facodi_learning.auto_approve_trusted_providers",
        help="Comma-separated provider identifiers that are eligible for Auto Approve. Other providers always require review.",
    )
