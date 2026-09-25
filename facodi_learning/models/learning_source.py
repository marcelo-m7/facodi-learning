import logging
import os

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services.youtube import build_youtube_slide_values


_logger = logging.getLogger(__name__)


class LearningSource(models.Model):
    _name = "facodi.learning.source"
    _description = "Learning content provenance"
    _order = "id desc"

    name = fields.Char(required=True)
    provider = fields.Char(required=True, default="manual")
    external_id = fields.Char(required=True)
    url = fields.Char(help="Provenance only; core never fetches this URL.")
    channel_id = fields.Many2one("slide.channel", required=True, ondelete="restrict")
    candidate_id = fields.Many2one(
        "facodi.learning.course.candidate",
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    slide_id = fields.Many2one("slide.slide", ondelete="restrict", readonly=True)
    state = fields.Selection(
        [("pending", "Pending"), ("imported", "Imported"), ("failed", "Failed")],
        default="pending",
        required=True,
        readonly=True,
    )
    imported_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    metadata = fields.Json()
    _identity_unique = models.Constraint(
        "unique(provider, external_id, channel_id)",
        "This source is already registered for this course.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (
                any(vals.get(key) for key in ("slide_id", "imported_at", "last_error"))
                or vals.get("state", "pending") != "pending"
            ):
                raise AccessError("Use ingestion to associate source content.")
            vals.update(
                state="pending", slide_id=False, imported_at=False, last_error=False
            )
        return super().create(vals_list)

    def write(self, vals):
        if {
            "slide_id",
            "state",
            "imported_at",
            "last_error",
            "provider",
            "external_id",
            "channel_id",
            "candidate_id",
        } & vals.keys():
            raise AccessError(
                "Source identity and ingestion evidence cannot be changed."
            )
        if any(source.state == "imported" for source in self):
            raise AccessError(
                "Imported provenance is immutable; register a new source version."
            )
        return super().write(vals)

    @api.constrains("external_id", "provider")
    def _check_identity(self):
        if any(
            not source.external_id.strip() or not source.provider.strip()
            for source in self
        ):
            raise ValidationError("Provider and external identity must not be blank.")

    @api.model
    def ingest(self, values, slide_id=None):
        """Idempotent ingestion; target-course lock serializes first registration."""
        self.check_access("create")
        provider = values.get("provider", "manual")
        channel = self.env["slide.channel"].browse(values.get("channel_id")).exists()
        if not channel:
            raise ValidationError("An existing target course is required.")
        channel.check_access("write")
        if not channel.try_lock_for_update():
            raise ValidationError("This course is being ingested; retry shortly.")
        source = self.search(
            [
                ("provider", "=", provider),
                ("external_id", "=", values.get("external_id")),
                ("channel_id", "=", channel.id),
            ],
            limit=1,
        )
        source = source or self.create(dict(values, provider=provider))
        source._ingest(slide_id)
        return source

    def _ingest(self, slide_id=None):
        self.check_access("write")
        for source in self.try_lock_for_update():
            source.invalidate_recordset()
            if source.slide_id:
                source._ensure_pending_publication_review()
                source._queue_supabase_analysis()
                continue
            source.channel_id.check_access("write")
            try:
                with self.env.cr.savepoint():
                    adapter = source._get_ingestion_registry().get(source.provider)
                    if not adapter:
                        raise ValidationError(
                            "No installed ingestion adapter for this provider."
                        )
                    if slide_id:
                        slide = self.env["slide.slide"].browse(slide_id).exists()
                        slide.check_access("write")
                        if not slide or slide.channel_id != source.channel_id:
                            raise ValidationError(
                                "Content must belong to the target course."
                            )
                    else:
                        values = dict(adapter(source))
                        values.update(
                            channel_id=source.channel_id.id,
                            is_published=False,
                            website_published=False,
                        )
                        slide = self.env["slide.slide"].create(values)
                    super(LearningSource, source).write(
                        {
                            "slide_id": slide.id,
                            "state": "imported",
                            "imported_at": fields.Datetime.now(),
                            "last_error": False,
                        }
                    )
                source._ensure_pending_publication_review()
                source._queue_supabase_analysis()
            except Exception as exc:
                super(LearningSource, source).write(
                    {
                        "state": "failed",
                        "last_error": f"{type(exc).__name__}: operation failed; inspect the provider configuration.",
                    }
                )
        return True

    def _ensure_pending_publication_review(self):
        """Make missing provenance explicit without inventing editorial evidence."""
        Review = self.env["facodi.learning.content.review"]
        for source in self.filtered("slide_id"):
            slide = source.slide_id
            if slide._facodi_has_approved_review():
                continue
            pending = Review.search(
                [("slide_id", "=", slide.id), ("state", "=", "pending")],
                limit=1,
            )
            if pending:
                if not pending.source_id:
                    pending.write(
                        {
                            "source_id": source.id,
                            "source_url": source.url or slide.url or False,
                        }
                    )
                continue
            Review.create(
                {
                    "slide_id": slide.id,
                    "source_id": source.id,
                    "origin": "source_ingestion",
                    "source_url": source.url or slide.url or False,
                }
            )
        return True

    def _queue_supabase_analysis(self):
        """Queue one production analysis job after canonical content exists.

        The queue is enabled only when the server-to-server Supabase credentials
        are present. Replaying ingestion does not create duplicate analysis jobs.
        """
        if not (
            (os.environ.get("SUPABASE_URL") or "").strip()
            and (os.environ.get("SUPABASE_SECRET_KEY") or "").strip()
        ):
            return self.env["facodi.learning.analysis.job"]

        jobs = self.env["facodi.learning.analysis.job"]
        for source in self.filtered("slide_id"):
            source_url = (source.slide_id.url or source.url or "").strip()
            if not source_url:
                continue
            existing = jobs.search(
                [
                    ("slide_id", "=", source.slide_id.id),
                    ("provider", "=", "supabase_edge"),
                ],
                order="id desc",
                limit=1,
            )
            if existing:
                if existing.state == "failed":
                    existing.action_retry()
                jobs |= existing
                continue
            try:
                with self.env.cr.savepoint():
                    jobs |= jobs.create(
                        {
                            "slide_id": source.slide_id.id,
                            "provider": "supabase_edge",
                        }
                    )
            except Exception as exc:
                _logger.warning(
                    "FACODI Supabase analysis queue failed for source %s (%s)",
                    source.id,
                    type(exc).__name__,
                )
        return jobs

    def action_ingest(self):
        return self._ingest()

    @api.model
    def ingest_manual(self, values, slide_id=None):
        if values.get("provider", "manual") != "manual":
            raise ValidationError("Use ingest for external provider adapters.")
        return self.ingest(values, slide_id=slide_id)

    def _get_ingestion_registry(self):
        """Trusted provider addons extend this mapping with normalized slide values."""
        return {
            "manual": lambda source: {"name": source.name, "slide_category": "article"},
            "youtube": build_youtube_slide_values,
        }
