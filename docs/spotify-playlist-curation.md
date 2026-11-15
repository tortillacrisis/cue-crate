# Themed Spotify playlist workflow

This guide covers standalone, theme-based playlists built from listening ideas rather
than Cue Crate's physical-record catalogue. Examples include era, genre, party, or mood
playlists. For playlists assembled from records in the local library, use the in-app
[Playlist manager](operations.md#playlist-manager-and-destinations) instead.

## Workflow

1. **Agree on the shape.** Establish a concise theme, audience/setting, energy, era, and
   any exclusions. Keep the scope open enough for adjacent styles when that improves the
   sequence.
2. **Review a seed.** Draft about 20 recognizable anchor tracks. The user reviews the
   musical direction before it is expanded.
3. **Check the seed in Spotify.** Search for the requested artist and title. Prefer the
   intended recording; distinguish remixes, edits, live versions, covers, and re-recordings
   when Spotify returns multiple plausible results. Report unresolved choices instead of
   silently calling them exact.
4. **Expand to the target length.** Build toward roughly 100 tracks while avoiding
   accidental duplicates and maintaining variety, pacing, and the agreed center of gravity.
   The user reviews the expanded selection before publishing.
5. **Resolve Spotify matches.** Use the exact or closest suitable catalog match. If the
   user has authorized best-judgment matching, note meaningful deviations for later review.
   Pace requests when needed and respect Spotify's `Retry-After` response on throttling.
6. **Publish only with explicit approval.** Confirm the destination account, playlist name,
   and visibility. Do not infer that a review of the track list authorizes a public or
   private playlist write. Never print or commit access tokens.
7. **Verify and hand off.** Confirm the playlist URL, visibility, and track count. Call out
   any meaningful alternate versions or title/artist discrepancies so the user can listen
   and edit directly in Spotify.

## Practical notes

- A useful iteration pattern is seed → Spotify availability check → expansion → user review
  → publish. Publishing is the external side effect and should remain a distinct,
  explicitly approved step.
- The seed and expansion are editorial drafts, not proof that a specific recording is the
  intended version. User listening feedback remains authoritative.
- Cue Crate's local Spotify connection can be reused when available, but this themed
  workflow does not require changing the record catalogue or local playlists.
- Keep playlist-specific choices and review notes outside committed personal data. The
  repository should document the process, not contain private playlist exports, tokens,
  or account-specific data.
