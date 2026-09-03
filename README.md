# Cue Crate

Local-first assistant for vinyl DJs: catalogue physical records, prepare shared crates,
and build toward quicker, more confident selections at the decks. It uses Discogs for
verified release metadata and leaves DJ-specific notes open for later.

## View the crate

The shared list is available in `viewer.html`. Serve the folder locally, then open the address it prints:

```bash
cd ~/Nextcloud/repos/cue-crate
python3 -m http.server --bind 127.0.0.1 8000
```

Open `http://localhost:8000/viewer.html`. It has a quick search and will include your
local collection data after it is imported.

## Interface design

The local pages share the **After-Hours Index** design system: a warm, cover-led record
library with a responsive mobile navigation pattern, a focused review workspace, and room
for future BPM/key/transition metadata. The reusable tokens and component rules live in
[DESIGN.md](DESIGN.md); `app.css` and `app.js` are the shared implementation layer. The
Library is now the primary browse/detail view, with Quick Crate, Review, Playlists, and
Scout as persistent destinations.

## Principles

- The catalogue is local and portable: `data/library/catalog.json` is the source of truth.
- Each profile owns its own Discogs account; credentials never enter this repository.
- Photo analysis creates *candidates only*. It never adds a guessed pressing to Discogs.
- Adding to Discogs is a dry run unless `--apply` is explicitly supplied.
- One record is one physical copy; later each record can hold its track-level BPM and transition notes.

## Local data layout

The app code, static pages, and documentation are safe to commit. All personal collection data, Discogs API caches, order history, review decisions, and generated reports stay in local-only subdirectories under `data/` and are intentionally ignored by Git:

- `data/library/catalog.json` — combined physical-copy catalogue, retaining each record's owner profile.
- `data/library/quick-crates/<profile>.json` — one reviewed quick crate per profile; `quick-crate.json` is the combined browser export.
- `data/workspace/<profile>/` — that profile's photo candidates, review decisions, additions queue, purchase log, and YouTube review state.
- `data/cache/discogs/users/<profile>/` — profile-specific Wantlists; release metadata and seller inventories are shared caches.
- `data/reports/<profile>/` — generated taste profiles and Seller Scout reports.

See `data/README.md` for the complete map. Back up the local `data/` directory separately before moving to another computer; it is deliberately not part of the remote repository.

## Profiles and collectives

Use `--owner` with a local profile ID or display name at any time. For repeatable local
setup, copy `config/profiles.example.json` to the ignored
`config/profiles.local.json`, then add only display names and public Discogs usernames.
The old `people.local.json` format remains readable during migration.

Copy `config/collectives.example.json` to the ignored
`config/collectives.local.json` when the same physical records should participate in a
named collaboration. A profile may belong to several collectives; each physical copy
still has one owner and can be explicitly shared with any number of collectives.

```bash
python3 cue_crate.py profiles
python3 cue_crate.py collectives
python3 cue_crate.py analyse-photos --owner dj-one --photo-dir '/path/to/record-photos'
```

The main catalogue remains combined, with each physical copy retaining its owner. Use a
record location (for example `regular-bin`) for a physical crate, and a collective scope
for a collaboration; neither replaces ownership.

```bash
python3 cue_crate.py set-record-location \
  --owner dj-one --record-id 'dj-one-RELEASE-INSTANCE' --location regular-bin
python3 cue_crate.py set-record-collective \
  --owner dj-one --record-id 'dj-one-RELEASE-INSTANCE' --collective after-hours
```

Discogs credentials are deliberately per profile and stay outside this repository. A
profile-specific token can live in `~/.config/cue-crate/discogs-token-<profile-id>` or
a macOS Keychain item named `cue-crate.discogs-token.<profile-id>`; the existing
generic token locations remain supported for backward compatibility.

Cue Crate also reads credentials from the previous local installation namespace during
the transition. New credentials and OAuth refreshes are written only under Cue Crate.

If a collaborator runs the tool on another computer, they can send a credential-free
bundle of their Discogs-derived catalogue and reviewed quick crate. It intentionally
excludes tokens, raw photos, review-server state, and purchase history:

```bash
# On a collaborator's computer
python3 cue_crate.py export-profile-bundle --owner dj-two \
  --output ~/Downloads/dj-two-cue-crate.json

# In the combined local crate, after inspecting the file
python3 cue_crate.py import-profile-bundle --owner dj-two \
  --input ~/Downloads/dj-two-cue-crate.json
```

The first import creates that profile's quick crate; later imports require
`--replace-quick-crate` so a current shared view cannot be overwritten accidentally.

## Current workflow

### 1. Import existing Discogs data

For a CSV export from either profile:

```bash
python3 cue_crate.py import-csv --owner dj-one --input ~/Downloads/discogs-collection.csv
```

Or read a collection directly. The personal token stays in a local temporary/config file and is never committed:

```bash
python3 cue_crate.py fetch-collection \
  --owner dj-one --token-file /tmp/discogs-token
```

Normal imports add or update the local snapshot. If you remove items in
Discogs and want the local catalogue to mirror that change, opt into a
reconciliation pass:

```bash
python3 cue_crate.py fetch-collection --owner dj-one --reconcile
```

This removes stale Discogs API rows for that profile. It does not discard a
record that has local photo-review evidence, a quick-crate marker, DJ notes,
or a crate location; those records remain locally catalogued instead.

### Local phone companion

The mobile MVP runs only on your local network. Install dependencies, then
start it on the Mac:

```bash
python3 -m pip install -r requirements.txt
python3 cue_crate.py serve-mobile --owner dj-one
```

Open the printed `connect.html` address on the Mac. It displays a one-time QR
code that opens the phone companion over Wi-Fi. The phone can browse the chosen
profile's catalogue and upload front, back, label, and optional barcode close-up photos into
`data/inbox/<profile-id>/<upload-id>/`. A primary evidence photo is the minimum;
label, front-cover, and barcode close-up views are optional fallbacks. A barcode close-up should include both the bars and the complete number printed directly below them. Keep the service on a trusted network: this MVP
uses a short-lived link token rather than a full account system. The token remains in
the URL fragment and is sent only as a request header; static serving is allowlisted so
the server will not expose the local `data/` directory. Treat it as a trusted-LAN tool,
not an Internet service.

To analyse the most recent phone bundle as one physical record, use the
bundle-aware command:

```bash
python3 cue_crate.py analyse-intake --owner dj-one
python3 cue_crate.py serve-review --owner dj-one
```

The command sends all available views together to Kimi K2.6 by default, saves
the evidence in `data/workspace/<profile-id>/intake-review.json`, and adds one item
to the existing review queue. It never writes to Discogs automatically. Use
`--upload-id <id>` to select an older bundle, or `--refresh` to analyse an
already processed bundle again.

Supply `--username` only when fetching a public collection owned by someone else.
If you keep it under `/tmp`, recreate the file after a restart or cleanup removes temporary files.

### Recommended token storage on macOS

Do not keep a long-lived personal access token in `/tmp` or in this repository. The commands look for a token in this order: an explicit `--token-file`, `DISCOGS_TOKEN`, `~/.config/cue-crate/discogs-token`, then a **Keychain Access** Password item named `cue-crate.discogs-token`. Older local credential locations remain readable during the product rename. The newer macOS **Passwords** app may not expose a generic secret to the command-line Keychain interface, so use the per-user config file or duplicate the item in Keychain Access for dependable local automation. If using the config file, create its parent directory with mode `700` and the token file with mode `600`.

To install a token file into the local macOS Keychain without putting it in shell history, run this once (the command does not print the token):

```bash
read -r token < /tmp/discogs-token
security add-generic-password -U \
  -s cue-crate.discogs-token -a "$USER" -w "$token"
unset token
```

Verify that the item exists without displaying its secret:

```bash
security find-generic-password -s cue-crate.discogs-token >/dev/null
```

Once verified, remove the temporary token file yourself. For a collaborator's private account token, use a separate Keychain item named `cue-crate.discogs-token-<profile-id>`; public collection imports do not require another person's token.

### 2. Identify your six-record photos

Keep the originals wherever they are. The command only reads the given folder and writes review candidates to `data/workspace/<profile-id>/photo-candidates.json`. JPEG, PNG, WebP, HEIC, and HEIF are accepted; HEIC is converted only to a temporary JPEG while it is analysed:

```bash
python3 -m pip install -r requirements.txt
python3 cue_crate.py analyse-photos --owner dj-one --photo-dir '/path/to/record-photos'
```

The photo commands use the OpenCode Go gateway.  They look for a credential in
this order: `--api-key-file PATH`, `OPENCODE_GO_API_KEY`,
`~/.config/cue-crate/opencode-go-api-key`, then the OpenCode login file at
`~/.local/share/opencode/auth.json`.  The last location is where OpenCode
stores the provider key after `/connect` or `opencode auth login`, so a normal
OpenCode login is enough for a local run; the key is never copied into this
repository.

If OpenCode has not been connected yet, run `opencode auth login`, select
OpenCode Go, and complete the browser sign-in.  To use a separate credential
file instead, create it outside the repository with one key on one line and
restrict it to your user account:

```bash
mkdir -p ~/.config/cue-crate
umask 077
printf '%s\n' 'YOUR_OPENCODE_GO_KEY' > ~/.config/cue-crate/opencode-go-api-key
python3 cue_crate.py analyse-photos --owner dj-one --api-key-file ~/.config/cue-crate/opencode-go-api-key --photo-dir '/path/to/record-photos'
```

An environment variable remains useful for temporary shells or automation:

```bash
export OPENCODE_GO_API_KEY='…'
```

The single-record phone-intake analyzer uses the same credential lookup:

```bash
python3 cue_crate.py analyse-intake --owner dj-one
```

Kimi K2.6 is the default provider. If it is temporarily unavailable, MiniMax M3 can use the same OpenCode Go key:

```bash
python3 cue_crate.py analyse-photos --provider minimax --owner dj-one --photo-dir '/path/to/record-photos'
```

The MiniMax fallback is experimental: its OpenCode Go text endpoint is confirmed, but the current gateway may reject image bodies. The command will stop with an explicit message rather than produce partial or guessed results.

MiMo V2.5 is an OpenAI-compatible alternative with documented base64 image input:

```bash
python3 cue_crate.py analyse-photos --provider mimo --owner dj-one --photo-dir '/path/to/record-photos'
```

If a long batch is interrupted, resume without repeating already-saved grids:

```bash
python3 cue_crate.py analyse-photos --provider mimo --resume --owner dj-one --photo-dir '/path/to/record-photos'
```

The image model must only transcribe visible evidence. After review, the next feature will search Discogs candidates and let you confirm the exact pressing.

For the current phone export, the script makes a temporary 2048px preview for each upload, then removes it. HEIC uses macOS Quick Look because `sips` can render some HDR iPhone photos as black. This keeps the originals untouched and makes six-record grids practical to transmit.

## How photo overlap is handled

Discogs is the canonical list of owned physical copies. Photos identify the quick-access crate, not a second collection:

1. A photo produces a review candidate only.
2. After a human confirms its exact Discogs release, the candidate is matched to the same owner's existing release.
3. A match will gain a `quick_access` marker and the source photo path; it will not create a duplicate record.
4. A no-match remains an explicit unmatched candidate until it is added to Discogs or deliberately kept local.

This lets new Discogs purchases be imported at any time before or after the photo pass.

### 3. Review the suggested local matches

Build the review queue after importing or refreshing your Discogs collection:

```bash
python3 cue_crate.py build-review --owner dj-one
python3 cue_crate.py serve-review --owner dj-one --token-file /tmp/discogs-token
```

Open `http://127.0.0.1:8765/review.html`. For each photographed sleeve, the page shows its source grid, visible text, and up to three suggestions from your own collection. The percentage is only a text-similarity hint, not a Discogs verification. You can also type the actual artist, title, catalogue number, or barcode: it searches the complete imported collection as you type, and debounced Discogs results refresh automatically from those four fields. If it is not in the imported collection yet, choose **Save identification — not in collection**; the typed name is retained for the later Discogs-lookup step. Decisions are saved locally in `data/workspace/<profile-id>/review.json`; this stage does not modify `data/library/catalog.json` or Discogs.

### 4. Apply confirmed quick-access copies locally

After the review is at a good stopping point, copy confirmed matches into the catalogue as `quick_access` markers:

```bash
python3 cue_crate.py apply-review --owner dj-one
```

This is local and idempotent: it marks only confirmed records, retains the source photo and review note, and removes stale markers if a later review decision is reopened. It does not write to Discogs. The main browser view displays the resulting records with a **Quick crate** badge.

### 5. Export the reviewed quick crate

When the priority is sharing titles rather than verifying every pressing, export every photo position as a simple list:

```bash
python3 cue_crate.py export-quick-crate --owner dj-one
```

This writes `data/library/quick-crates/<profile-id>.csv` and `.json` for sharing, then rebuilds `data/library/quick-crate.json` for the combined browser view at `quick-crate.html`. The export includes confirmed catalogue matches, named local identifications, and any future selected Discogs release, without requiring further Discogs work.

### 6. Choose Discogs releases for records not yet imported

Start the reviewer with your local Discogs token. Discogs candidates refresh automatically as the four identification fields change; the search keeps artist/title context with barcode or catalogue-number evidence, then falls back to a broader artist/title search when an identifier is uncertain. Use **Broad search on Discogs** for the wider web view, compare format, label, catalogue number, year, country, barcode, and cover, then paste or copy the verified release URL into **Use exact URL**. Selecting a release only saves it locally in `data/workspace/<profile-id>/review.json`; it does not add it to Discogs.

In the reviewer, use **Resolution → manual only** to find identifications that have a local artist/title (and possibly corrected evidence) but no exact Discogs pressing yet. Confirm an exact collection match, use a candidate’s **Use release URL** shortcut, or paste a specific Discogs release URL when search misses it. The final **Use exact URL** action verifies and saves the pressing locally.

When you have made selections, prepare an editable local queue:

```bash
python3 cue_crate.py prepare-additions --owner dj-one
```

This writes `data/workspace/<profile-id>/discogs-additions.local.json` (ignored by git). Inspect or edit it, then send it to that profile's owner if they will perform the final Discogs write. Duplicate release IDs are intentionally retained when they represent separate physical copies.

### 7. Enrich confirmed records with tracklists

```bash
python3 cue_crate.py enrich --owner dj-one --token-file /tmp/discogs-token
```

### 7a. Add BPM and key metadata

Track-level BPM/key enrichment uses the GetSongBPM API. Create a free API key at
[getsongbpm.com/api](https://getsongbpm.com/api), then keep it outside the repository.
The API requires a backlink to GetSongBPM in the application and currently documents a
3,000-request-per-hour limit. A local cache prevents duplicate album copies and repeated
runs from making the same search again.

For a one-off test, save the key in a local file and pass it explicitly:

```bash
python3 cue_crate.py enrich-bpm --owner dj-one --api-key-file /tmp/getsongbpm-key --limit 20
python3 cue_crate.py enrich-bpm --owner dj-two --api-key-file /tmp/getsongbpm-key
```

Use `--limit 20` for the first live test; omit it to process the full profile catalogue.

The command can also read `GETSONGBPM_API_KEY`,
`~/.config/cue-crate/getsongbpm-api-key`, or the macOS Keychain item
`cue-crate.getsongbpm-api-key`. It writes provider data into each Discogs track in
`data/library/catalog.json`: `bpm`, `key`, `open_key`, `bpm_source`,
`bpm_match_confidence`, `bpm_match`, and `bpm_checked_at`. Manual corrections can set
`bpm_user_override: true`; later runs preserve them. Use `--refresh` to query the
provider again for non-overridden tracks.

### 8. Optional: add only approved records to Discogs

First inspect the queue created by `prepare-additions` (or make an equivalent local JSON array), then see the plan:

```bash
python3 cue_crate.py add-to-discogs \
  --owner dj-one --username YOUR_DISCOGS_USERNAME --folder-id 1 \
  --input data/workspace/dj-one/discogs-additions.local.json --token-file /tmp/discogs-token \
  --skip-existing
```

`--skip-existing` performs a read-only collection check and avoids adding release IDs already present in the target account. Only after checking every ID, add `--apply`. The write step verifies that the supplied token's Discogs identity matches the target username, so another profile owner can safely apply a queue prepared on your machine with their own token.

## Crate Scout: discovery without buying automation

The scout starts from your verified catalogue, quick-crate titles, and existing Wantlist. It creates local profile files only; it never adds items to the Wantlist or Discogs collection.

```bash
python3 cue_crate.py fetch-release-features --owner dj-one --token-file /tmp/discogs-token
python3 cue_crate.py fetch-wantlist --owner dj-one --token-file /tmp/discogs-token
python3 cue_crate.py build-taste-profile --owner dj-one
```

This produces `data/reports/<profile-id>/taste-profile.json` and `.md`. The Discogs calls are read-only and cached in `data/cache/discogs/release-features.json`; subsequent runs fetch only releases missing from the cache. The profile keeps early-80s boogie as the core but includes complementary Afro-boogie, South African bubblegum, Brazilian boogie/MPB-funk, and an intentionally open exploration lane. Candidate generation and live-shopping guidance come after reviewing this profile.

### Seller Scout: one-order recommendations

For a seller whose inventory looks promising, create a local top-ten that starts with Vinyl in VG+ / NM / M condition, excludes your owned releases, favours Wantlist and crate-profile matches, and enriches only the strongest prospects with Discogs community ratings:

```bash
python3 cue_crate.py scan-seller \
  --owner dj-one --seller EXAMPLE_SELLER \
  --token-file /tmp/discogs-token
```

The inventory is cached as `data/cache/sellers/seller-<seller>.json`; the recommendations are written to `data/reports/<profile-id>/sellers/`. Exact artist/title matches in the reviewed quick crate are excluded even when their pressing has not been added to the Discogs collection. For a release you know you own but have not fully catalogued, add an explicit local exclusion:

```bash
python3 cue_crate.py add-owned-title --owner dj-one \
  --artist 'Dunn & Bruce Street' --title 'Shout For Joy'
```

Every recommendation is from that one seller, so it can be combined into one order. The report flags whether the seller's public shipping text mentions combined orders or free shipping, but exact shipping, destination availability, and any seller-specific item limit remain a final Discogs-cart check. Use `--max-price` only when you know the seller's listing currency and have a real per-record ceiling. `--min-rating 4` requires the Discogs release-level community average; Discogs does not provide a parallel rating for individual tracks, so a record with one exceptional song remains a manual listening exception.

After placing an order, record its listing IDs locally. This does not add anything to your Discogs collection; it prevents the same releases from appearing in later Seller Scout reports while the order is in transit:

```bash
python3 cue_crate.py record-order --owner dj-one --seller EXAMPLE_SELLER \
  --listing-id 2975680208 --listing-id 3982794238 \
  --token-file /tmp/discogs-token
```

## Playlist manager and destinations

The profile-aware service now includes a playlist manager at `playlists.html`. It keeps
saved playlist names, descriptions, visibility, and provider destinations in
`data/workspace/<profile-id>/playlists.json`. YouTube Music and Spotify are separate
destinations, so a playlist can be shown for either provider or both. The manager never
returns credential contents to the browser; it only reports whether a local provider
credential is available.

Start the service and open the manager:

```bash
python3 cue_crate.py serve-youtube-review --owner dj-one --port 8766
```

Open `http://127.0.0.1:8766/playlists.html`. Use the **Profile** selector to
switch between profiles represented in the local catalogue; playlist settings and
track-review state stay in that profile's workspace. Use **Build this playlist from the
library** to select records and arrange their order; the YouTube-backed representative
track still gets curated in **Open track selector**. Existing YouTube publishing remains
an explicit command so an
OAuth browser sign-in and the final track list are always deliberate. Spotify is exposed
as a destination slot and reports **Not connected** until a local Spotify credential is
configured. For the current status check, use `SPOTIFY_ACCESS_TOKEN` or place the token
in `~/.config/cue-crate/profiles/<profile-id>/spotify-oauth.json` with owner-only
permissions; its publishing adapter is the next provider-specific increment.

Playlist membership is stored as an ordered `entries` list in each profile's
`data/workspace/<profile-id>/playlists.json`; an entry can represent a whole album or an
individual Discogs track. Older playlists without that field continue to mean “all
approved, YouTube Music-verified album selections” until they are saved from the manager.
The local setlist can contain individual tracks immediately, while provider publishing
currently includes only selected albums with a verified provider track; per-track YouTube
matching is the next provider-specific increment.

The existing YouTube review page remains available at
`http://127.0.0.1:8766/youtube-review.html`.

## YouTube Music crate playlist

This is a review-first shared-listening companion, not a place for personal audio uploads. It starts with every named record in the reviewed quick crate plus any catalogue-only title, deduplicated by artist/title. Pending purchases are excluded until they arrive.

```bash
python3 cue_crate.py build-youtube-review --owner dj-one
python3 cue_crate.py serve-youtube-review --owner dj-one
```

Open `http://127.0.0.1:8766/youtube-review.html`. For each title, use the provided YouTube and YouTube Music searches, paste the selected video URL, and only mark it **Approved** after opening that exact video in YouTube Music. The public API does not expose a reliable “available in YouTube Music” flag, so this is deliberately a human check. Only approved, checked items can be published.

After the one-time OAuth setup below, the practical default is automatic discovery rather than manually searching every title. It searches music-category videos, scores exact artist/title and official/album signals, then uses view count as a tiebreaker. It saves high-confidence results as **Auto-selected** and leaves only weak matches as exceptions:

```bash
python3 cue_crate.py discover-youtube-matches --owner dj-one \
  --client-secrets ~/Downloads/client_secret_....json
```

Spot-check the auto-selected results in YouTube Music before changing them to **Approved**. This keeps the human work bounded while retaining the Music-availability safeguard.

### One-time Google setup, only when ready to publish

1. In Google Cloud Console, create a personal project, enable **YouTube Data API v3**, and create an **OAuth client ID** of type **Desktop app**.
2. Download its JSON file somewhere outside this repository (for example `~/Downloads/`). Never commit it or share its contents.
3. Install the optional local publishing dependencies and dry-run the intended payload:

```bash
python3 -m pip install -r requirements.txt
python3 cue_crate.py publish-youtube-playlist \
  --owner dj-one \
  --client-secrets ~/Downloads/client_secret_....json
```

4. When the dry run looks correct, publish the unlisted playlist. A browser window will open: sign in to the profile owner's YouTube account and approve the requested YouTube playlist permission.

```bash
python3 cue_crate.py publish-youtube-playlist \
  --owner dj-one \
  --client-secrets ~/Downloads/client_secret_....json --apply
```

The OAuth token is stored locally at `~/.config/cue-crate/profiles/<profile-id>/youtube-oauth.json` with owner-only permissions. Run `python3 cue_crate.py migrate-provider-token --owner <profile-id> --provider youtube` once to move an older global token into that location. Publishing is resumable: the created playlist ID and each inserted playlist item are saved to `data/workspace/<profile-id>/youtube-music-review.json`, so a retry will not add duplicates.

## Next increments

1. Track-level DJ fields: BPM, playable RPM, intro/outro bars, energy, cue clues, and transition notes.
2. Additional collaborators can import a CSV or run the same command locally with their own token; no token needs to be shared.

The deferred Spotify work, public-repository checklist, and the longer-term live-gig
assistant idea are tracked in [`TODO.md`](TODO.md).
