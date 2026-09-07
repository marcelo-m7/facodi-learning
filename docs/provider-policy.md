# FACODI Learning provider policy

FACODI Learning keeps the core discovery pipeline provider-neutral and offline-capable.

## Network-provider boundary

- `facodi_learning` does not ship a YouTube API client, YouTube API credential, Google/YouTube SDK, or provider that depends on that API.
- Future discovery integrations must be separately reviewed before they introduce any network client, credential or quota dependency.
- The existing `manual` discovery workflow remains the baseline and requires no network service.
- Generic provider adapters must return normalized candidate metadata through the existing discovery registry; they may never create or publish `slide.channel` directly.

## Video URLs are not API integration

Odoo eLearning may store ordinary public video/source URLs as standard content or provenance. A manually supplied YouTube URL is treated only as a URL handled by Odoo's existing mechanisms; it does not authorize FACODI to call a YouTube API, enumerate channels/playlists, fetch transcripts, or store an API credential.

## CI invariant

Repository CI rejects known YouTube API integration markers before running Odoo tests. The full Odoo 19 clean-install and upgrade gates continue to verify that this policy change does not alter the provider-neutral discovery, curriculum, mapping, or content-analysis behavior.
