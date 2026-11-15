# Public release checklist

## Review locally

- [x] Select the MIT License and include its standard text and copyright notice in [LICENSE](../LICENSE).
- [ ] Run the tests, source/link checks, and value-redacting secret guard from
  [CONTRIBUTING.md](../CONTRIBUTING.md). Investigate results privately; never paste secrets into CI logs.
- [ ] Inspect the exact source/config/docs publication diff, including new files and media.
  Exclude `data/`, local configuration, credentials, and personal screenshots/QR links.
- [ ] Check documentation against implemented and piloted behavior. Database song matches
  are not proof of vinyl pressing/mix identity, measured tempo, or harmonic compatibility.
- [x] Confirm private vulnerability reporting on the public repository (15 November 2026).
- [ ] Verify the provider-independent CI workflow after publishing the reviewed snapshot.
- [ ] Validate a fresh dependency installation and plan a reviewed dependency snapshot/advisory check.

## Keep the clean public history

The private working history and existing public GitHub history are separate. Old private
commits contain person-specific examples removed from the current source. Do not merge
that history into the public branch, use `--allow-unrelated-histories`, or mirror-push it.

Use a separate checkout of the existing public branch. Transfer only the reviewed source
snapshot and approved new files, without `.git`, ignored data, or local configuration.
Review the diff there, rerun checks, and create a normal new commit on the existing public
history. Use a deliberate publish/PR step; do not change visibility, rewrite history, or
force-push as part of ordinary cleanup. Choose a privacy-appropriate public commit identity.

Some working checkouts use a private remote rather than the public project home. Verify the
destination before any push. Git synchronization is not a backup of ignored collection data;
back up personal working data separately.

## GetSongBPM registration

- [ ] Publish an anonymously accessible project page with a visible
  [GetSongBPM](https://getsongbpm.com/) backlink. The README includes attribution, but its
  acceptance as the website/backlink URL is not guaranteed by the provider's documentation.
- [ ] Verify the public URL and backlink without logging in. If needed, provide a small
  project website or ask the provider whether the README qualifies.
- [ ] Register using a valid email and follow the [API requirements](https://getsongbpm.com/api).
  Registration is separate from repository publishing; it has not been submitted by cleanup.
- [ ] Store the key outside Git using the [credential guide](credentials.md).
- [ ] Finish metadata-preserving, version-aware BPM matching and run the reviewed 20-track
  pilot before any full-catalogue batch. Report unavailable/uncertain matches honestly.

Do not claim production readiness or approval by any provider merely because the source is public.
