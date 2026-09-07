from unittest import TestCase
from unittest.mock import patch

from ..services.youtube import _validated_youtube_url, discover_youtube_items


class TestYouTubeDiscoverySafety(TestCase):
    def test_rejects_non_https_seed_before_network_access(self):
        with patch(
            "odoo.addons.facodi_learning.services.youtube.fetch_url"
        ) as fetch_url:
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                discover_youtube_items("http://www.youtube.com/@Odoo", limit=1)
            fetch_url.assert_not_called()

    def test_rejects_non_youtube_host_before_network_access(self):
        with patch(
            "odoo.addons.facodi_learning.services.youtube.fetch_url"
        ) as fetch_url:
            with self.assertRaisesRegex(ValueError, "official YouTube hosts"):
                discover_youtube_items(
                    "https://www.youtube.com.evil.example/@Odoo", limit=1
                )
            fetch_url.assert_not_called()

    def test_rejects_non_channel_path(self):
        with self.assertRaisesRegex(ValueError, "channel URL"):
            _validated_youtube_url(
                "https://www.youtube.com/redirect?q=http://127.0.0.1/",
                kind="channel",
            )

    def test_rejects_userinfo_and_nonstandard_port(self):
        with self.assertRaisesRegex(ValueError, "user credentials"):
            _validated_youtube_url(
                "https://user@www.youtube.com/@Odoo",
                kind="channel",
            )
        with self.assertRaisesRegex(ValueError, "standard HTTPS port"):
            _validated_youtube_url(
                "https://www.youtube.com:444/@Odoo",
                kind="channel",
            )

    def test_accepts_official_channel_url(self):
        self.assertEqual(
            _validated_youtube_url(
                "https://www.youtube.com/@Odoo",
                kind="channel",
            ),
            "https://www.youtube.com/@Odoo",
        )
