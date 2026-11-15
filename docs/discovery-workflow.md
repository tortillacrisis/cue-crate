# Record discovery: reusable workflow draft

This captures the research process for a future Cue Crate Scout feature and, if
useful, an agent skill. It is not yet an installed skill, an autonomous buying agent,
or a new recommendation UI. Keep the reusable method separate from each listener's
private taste, ownership, and shopping context.

## Two connected loops

**Musical discovery:** references → a small, varied audition set → user feedback →
a more precise brief. Do not begin with a seller's available stock and rationalize
whatever happens to be cheap.

**Purchasing:** chosen track/version → qualifying physical releases → current copies
and sellers → delivered-cost comparison. Keep a wanted recording visible even if no
qualifying copy is available today. Do not silently substitute a later remix.

## What a research brief needs

- Selected profile or collective, and the purchase-ownership scope. Owning an MP3,
  streaming a track, hearing a collaborator's copy, and owning a physical pressing
  are different facts.
- Positive and negative listening references, including **why** they fit or miss:
  production, bass character, drum feel, vocals, repetition, texture, energy, or
  familiarity. Treat an assistant's musical interpretation as a hypothesis until
  user feedback supports it.
- Separate modes or lanes for distinct jobs: core sound, crossover/recognition,
  adjacent exploration, and later-night progression. Do not collapse everything into
  a single genre tag or a hard historical cutoff.
- Shopping context: destination/currency, item ceiling, minimum media grade, acceptable
  sleeve trade-offs, and whether the goal is one seller or the best musical selection.
  Recheck these when travel or the intended set changes.

## Track and exact version first

Find the song and mix that matches the brief before choosing an album or pressing.
A low average album rating can coexist with a compelling track; a high release
rating does not establish musical fit. Keep rating **and vote count** visible, and
flag sparse votes without treating obscurity as either proof of quality or a reason
for automatic rejection. Do not invent per-song Discogs ratings from release scores.

Check version names, track listings, durations, artist aliases, and catalogue details.
Original, edit, instrumental, dub, club remix, and later re-recording are not freely
interchangeable. Reissue year and original recording year answer different questions.
Map artist/title aliases for ownership checks without collapsing genuinely different
recordings. A possible owned copy belongs in an ownership-review bucket, not quietly
in a buying recommendation.

## Feedback should be useful data

Retain clear yes/no/maybe feedback plus its reason and provenance. Separate:

- user-confirmed preferences;
- user-supplied references not yet auditioned in this workflow;
- machine-inferred similarities;
- seller/live-listing facts.

Do not automatically equate liked previews with purchase approval, an ordered record
with a received/played record, or a style experiment with a permanent change of taste.
Existing local choices and deliberate exclusions should survive future collection
refreshes.

## Make purchase recommendations auditable

For a useful candidate, retain the exact song/mix, musical rationale, relevant role
in the set, ownership status, release/listing link, price/currency, seller location,
media and sleeve grades separately, seller comments, release rating and vote count,
and the time/source of verification.

Validate current listings rather than trust search snippets. Distinguish a confirmed
exact pressing from a catalogue-matched reference pressing. Seller grades are not a
play test. Treat shipping tiers and free-shipping thresholds as unknown unless the
seller's policy or a non-purchasing quote actually supports them. Compare delivered
cost, not simply the number of records from one seller.

Show what was excluded and why, and describe bounded searches honestly. “No qualifying
copy in the checked stock” is not “unavailable everywhere.” A programming arc is not
proof of beat/key compatibility unless separately analyzed or rehearsed.

## Proposed application boundaries

Keep preference snapshots and feedback under the selected local workspace, e.g.
`data/workspace/<profile-id>/discovery-preferences.json`. These are private and ignored
by Git. A generic method, schema examples without real users, and future skill
instructions can be public.

A future Scout session can load that profile, ask for the current search mode, offer
audition cards, record version-specific feedback, then run purchasing checks only on
the chosen targets. Updating Wantlists, publishing playlists, contacting sellers,
adding to carts, and buying are separate actions needing explicit user direction.

Next step: validate the private preference snapshot with the listener, then specify
the smallest Scout audition/feedback loop. Avoid building a full autonomous shopping
system before that loop is useful.
