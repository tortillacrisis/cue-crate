# Cue Crate roadmap

This is a deliberately small, local-first project. Keep the catalogue useful for the
next gig while leaving room for richer DJ assistance later.

## Deferred integrations

- [ ] Spotify destination: have the app owner create a Development Mode app, add the
  intended Spotify users to its allowlist, and test playlist creation with separate
  OAuth accounts. Implement Authorization Code with PKCE, refresh-token storage, track
  search, and private/public playlist publishing. Treat Spotify as a showcase and
  listening companion, never as the audio source for the bar or a live DJ mix.
- [ ] GetSongBPM enrichment: run a small pilot, review match confidence, and retain
  manual BPM/key overrides. Keep provider metadata separate from the canonical record
  and track identities.
- [ ] Public-repository readiness: complete the secret/data audit, document local
  setup, provide safe configuration examples, and keep private catalogue/photos out of
  version control.
- [ ] Remove real names, account labels, and person-specific defaults from code,
  examples, documentation, and reachable Git history before making a remote public.
  Replace them with neutral sample profiles and require local configuration at runtime.
- [ ] Harden the LAN phone server before wider use: issue the QR link only to the local
  connect screen, require its token for every data-bearing route, and serve an explicit
  static-file allowlist instead of the project directory.
- [ ] Model collaboration separately from ownership: local profiles have their own
  provider handles and Keychain credential references; collectives have stable IDs,
  members, roles, shared record scopes, bins, and setlists. A physical copy remains
  owned by one profile while it may be shared with multiple collectives.
- [ ] Move every provider credential to a profile-specific local reference. Discogs
  already has this pattern; YouTube and the future Spotify integration must stop using
  one machine-wide token file.

## Live-gig helper (post-MVP)

- [ ] Ship the smallest useful live workflow first: type the current track into a
  **Now playing** field, resolve it against the local catalogue, and immediately show
  explainable next-record suggestions. Keep this manual path as the reliable fallback
  when automatic recognition is unavailable.
- [ ] Add an AudD recognition adapter after the manual flow is useful: capture a short
  phone clip, send it through the local service without exposing its API token, retain
  only the normalized match, and pass that match into the same suggestion workflow.
- [ ] Add a normalized track identity layer linking Discogs tracks to YouTube and
  Spotify matches without replacing the physical-copy and owner model.
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
- [ ] Investigate one-tap song recognition from a phone microphone (Shazam-style or
  another permitted recognition provider), including API cost, latency, privacy, and
  offline/failure behavior. Recognition should feed the same fit workflow rather than
  become a separate catalogue.
- [ ] Improve live ergonomics: mobile-first layout, large type, keyboard shortcuts,
  cached metadata, and a graceful manual fallback when recognition or network access
  is unavailable.
