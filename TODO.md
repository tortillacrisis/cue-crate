# Cue Crate roadmap

This is a deliberately small, local-first project. Keep the catalogue useful for the
next gig while leaving room for richer DJ assistance later.

Reviewed against the implementation on **15 November 2026**. Checked items describe
implemented foundations, not a claim that every provider or deployment is fully tested.

## Implemented foundations

- [x] One local `serve` command for Library, Review, Playlists, and Scout; focused
  getting-started, operations, architecture, and credential documentation.
- [x] Local profiles and collectives with stable IDs, membership roles, explicit copy
  ownership, and shared-copy/location metadata. Shared setlist permissions remain future work.
- [x] Profile-specific YouTube/Spotify OAuth storage and Discogs credential lookup;
  dedicated local photo-analysis credentials without changing the OpenCode login.
- [x] Canonical catalogue/listening identities and migration of photo evidence and
  playlist membership away from provisional artist/title strings.
- [x] Phone QR intake with label-only capture, optional additional views, pending-bundle
  analysis, and human exact-pressing review before any Discogs write.
- [x] Trusted-LAN access boundary: loopback-only connect/desktop APIs, capability-token
  mobile APIs, and an explicit static-file allowlist. This is not Internet authentication.
- [x] Shared Host/Origin/Fetch Metadata checks, bounded JSON writes, and separate desktop
  CSRF capabilities across unified/legacy servers; legitimate OAuth callbacks retain state/PKCE checks.
- [x] Preserve collective assignments on collection refresh and exclude reserved workspace
  directories from inferred user profiles.
- [x] Configurable Go image models, model-capability checks, protected review state,
  isolated Keychain credentials, and an opt-in non-mutating model comparison script.
  MiMo/MiniMax have a small live check; representative-record validation is still needed.
- [x] Library ownership indicators and artist/year/genre/style/format filtering,
  including neutral/include/exclude facet controls.
- [x] Local playlist manager with ordered album/track entries and YouTube selection,
  review, and publishing workflows.
- [x] Spotify destination MVP: PKCE, renewable profile-specific tokens, confidence-gated
  matching/review, Web Playback SDK listening, and public/private playlist publishing.
  Streaming remains a listening/showcase companion, never the audio source for a gig.
- [x] Shared After-Hours Index styling and a first cross-screen responsive alignment pass.
- [x] Current-tree credential scan, ignored personal data/configuration, and neutral
  configuration examples; broader accidental-secret ignore rules and repeatable redacting checks.
- [x] Prepare read-only, SHA-pinned CI, contributor/security/release guides, an isolated
  fictional demo, privacy-safe screenshot, and explicit Python/macOS support notes.
  Hosted CI results remain pending publication.
- [x] Seller Scout baseline with ownership exclusions, price/grade/rating filters, and
  local taste reports; reusable discovery/taste-feedback method documented as a draft.

## Next: track-level BPM and key

- [x] Refresh the owning profile's Discogs collection and complete missing tracklists
  for the current imported catalogue (15 November 2026). Repeat for future additions;
  keep purchased/ordered items distinct from confirmed physical ownership.
- [ ] Complete GetSongBPM registration, required public attribution/backlink, and secure
  key setup. Confirm the provider accepts the project page before relying on access.
- [ ] Harden enrichment before a live batch: separate provider observations from canonical
  track identities and manual overrides; preserve both through tracklist refreshes.
- [ ] Match the exact recording/mix where possible; expose ambiguity rather than treating
  an artist/title similarity score as proof of an extended, dub, or instrumental version.
- [ ] Run a roughly 20-track pilot across albums and singles; report coverage, unmatched
  tracks, version uncertainty, and manual spot-checks before expanding to both catalogues.
- [ ] Add Library BPM/key/source/confidence display and a practical correction/review flow;
  then add tempo/key filters. The current CLI/display prototype is not the finished workflow.
- [ ] Catalogue remaining physical records through the phone intake/review flow and
  compare image models on several representative labels, not just one known LP.

## Validation, public release, and collaboration

- [ ] Test Spotify matching against more vintage LPs and 7/12-inch singles, then verify a
  separately allowlisted collaborator account.
- [x] Audit current files and reachable private/public history for likely credentials and
  personal content. Keep the clean public history separate from older private examples.
- [x] License the project under MIT, with the standard license text and matching documentation.
- [x] Confirm GitHub private vulnerability reporting is enabled (15 November 2026).
- [ ] Publish only the
  reviewed snapshot onto the existing clean public branch. Do not merge private history.
- [ ] Verify hosted CI and a fresh dependency installation; establish a reviewed dependency
  snapshot and advisory-checking/update process.
- [x] Add regression coverage so a collection refresh preserves saved playlist order,
  album modes, and Spotify review choices when their identities have not changed;
  missing-only tracklist enrichment also preserves existing track metadata.
- [x] Cover local/LAN route authorization, foreign-origin and missing-session rejection,
  legacy entry points, OAuth callback routing, and credential-redacting BPM transport.
- [ ] Expand automated coverage for explicit tracklist refresh, identity migration, and provider matching.
- [ ] Finish mobile-friendly artist selection, consistent profile/scope controls,
  unsaved-change feedback, keyboard/screen-reader review, and visual regression fixtures.
- [ ] If hosting becomes a goal, add real authentication, invitations, collaboration
  authorization, and server-side managed secrets with rotation/deletion. Keep the present
  trusted-LAN/local-profile model clearly distinct from multi-user security.
- [ ] Extend collectives into permission-aware shared setlists/bins and live sessions;
  a copy can participate in several collaborations without acquiring multiple owners.

## Live-gig helper (post-MVP)

- [ ] Ship the smallest useful live workflow first: type the current track into a
  **Now playing** field, resolve it against the local catalogue, and immediately show
  explainable next-record suggestions. Keep this manual path as the reliable fallback
  when automatic recognition is unavailable.
- [ ] Add an AudD recognition adapter after the manual flow is useful: capture a short
  phone clip, send it through the local service without exposing its API token, retain
  only the normalized match, and pass that match into the same suggestion workflow.
- [ ] Extend the existing canonical record/listening layer into durable recording/mix-level
  identities for DJ metadata and cross-provider matches without losing physical-copy ownership.
- [ ] Store track-level DJ metadata: BPM, musical key/Camelot or Open Key, BPM/key
  confidence, playable RPM, intro/outro bars, energy, cue clues, and transition notes.
- [ ] Build a glanceable live view for a laptop or phone: current track, quick lookup,
  and the next few suggestions with an explainable fit meter.
- [ ] Define the fit score: compatible BPM (including half/double-time), harmonic-key
  distance, energy/style continuity, and available intro/outro information. Show the
  reasons and confidence instead of presenting a black-box ranking.
- [ ] Add collection scope controls: shared bin, my records, a collaborator's records,
  or the other DJ's collection. Preserve ownership and physical-copy availability in
  every suggestion.
- [ ] Validate recognition cost, latency, privacy, and failure behavior. Revisit native
  ShazamKit only if a native companion is justified; keep AudD/manual lookup on the web path.
- [ ] Improve live ergonomics: mobile-first layout, large type, keyboard shortcuts,
  cached metadata, and a graceful manual fallback when recognition or network access
  is unavailable.

## Discovery and taste feedback

- [ ] Build on [the reusable discovery workflow](docs/discovery-workflow.md): keep
  musical discovery separate from live purchasing checks, with profile-private taste
  snapshots and explicit search modes.
- [ ] Add track/mix-specific audition feedback to Scout; retain user-confirmed likes,
  reasons for misses, and uncertain ownership separately from inferred similarities.
- [ ] Validate exact versions and pressing-level rating/vote evidence before showing
  live buying options; do not optimize one seller's basket at the expense of fit.
- [ ] Add an interactive Scout search/feedback flow and destination-aware delivered-cost
  comparisons, including verified combined/free-shipping terms where sellers provide them.
- [ ] Package the validated research method as a reusable agent skill if useful; keep
  individual taste, shopping context, and collection data outside the shared skill.
