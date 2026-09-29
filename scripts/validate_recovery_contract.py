#!/usr/bin/env python3
"""Static contract for FACODI/Open2 recovery scripts."""

from pathlib import Path

SCRIPTS = (
    Path("scripts/recover_open2_lesti.py"),
    Path("scripts/recover_open2_public_catalog.py"),
)

for path in SCRIPTS:
    text = path.read_text(encoding="utf-8")
    compile(text, str(path), "exec")
    assert "def _recovery_title(" in text, f"{path}: recovery title guard missing"
    assert 'optimized.lower().startswith("monynha fun:")' in text, (
        f"{path}: synthetic Monynha title guard missing"
    )
    assert '"título otimizado" in optimized.lower()' in text, (
        f"{path}: synthetic optimized-title guard missing"
    )
    assert '"slide_category": "video"' in text, (
        f"{path}: recovered YouTube content must stay native Odoo video"
    )
    assert '"video_url": "https://www.youtube.com/watch?v=%s"' in text, (
        f"{path}: native Odoo video URL field missing"
    )
    assert "website_slides_skip_fetch_metadata=True" in text, (
        f"{path}: recovery must suppress provider HTTP metadata fetches"
    )

print("FACODI recovery contracts OK")
