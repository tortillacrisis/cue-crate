# Local data (not committed)

This directory separates personal collection state and external API responses from the application code. Everything here except this guide is ignored by Git.

## Layout

- `library/` — canonical combined catalogue; `quick-crates/<profile-id>.json` and CSV exports; `quick-crate.json` is the aggregate browser export.
- `workspace/<profile-id>/` — photo-analysis candidates, review decisions, owned-title overrides, purchase records, pending Discogs additions, playlist manager state (including ordered album/track `entries`), and YouTube playlist review state for one profile.
- `workspace/collectives/<collective-id>/` — future shared setlist or live-session state for a configured collaboration. It does not replace the per-profile workspace.
- `cache/discogs/users/<profile-id>/` — each profile's Wantlist; `cache/discogs/release-features.json` is shared because Discogs release metadata is not profile-specific.
- `cache/sellers/` — fetched seller inventories; potentially large and safe to regenerate.
- `reports/` — generated taste profiles and seller-scoring reports.

## Backup and sharing

This is personal working data. Back it up separately from the Git remote, and share only deliberately exported files such as `library/quick-crates/<profile-id>.csv`. OAuth client secrets and access tokens belong outside the project in your system configuration or password manager, never here. Provider OAuth tokens are scoped to `~/.config/cue-crate/profiles/<profile-id>/`; Discogs tokens can use a profile-specific local file or Keychain item.

For collaborator handoff, use `export-profile-bundle` rather than copying this directory. A bundle includes only one profile's catalogue records and reviewed quick-crate entries; it omits credentials, raw photos, review state, collective memberships, and purchase history.
