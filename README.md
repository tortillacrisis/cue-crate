# Cue Crate

Cue Crate is a local-first assistant for vinyl DJs. It brings together a physical-record
catalogue, shared crates, photo-assisted identification, playlists, scouting, and the
foundation for live next-record suggestions.

It is deliberately a companion to a record collection—not a streaming player or a tool
for supplying music at a venue. Your collection data, photos, credentials, and purchase
history stay on your own computer.

## Quick start

```bash
git clone https://github.com/tortillacrisis/cue-crate.git
cd cue-crate
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python cue_crate.py serve --owner dj-one
```

Open <http://127.0.0.1:8765/viewer.html>. The single `serve` command runs the Library,
Review, Playlists, and Scout screens on one local port. Replace `dj-one` with your local
profile ID or display name.

To use the phone intake companion on a trusted Wi-Fi network, add `--lan`:

```bash
.venv/bin/python cue_crate.py serve --owner dj-one --lan
```

Open the printed **Phone connect screen** on the serving computer, then scan its QR
code. Desktop data APIs remain available only on that computer; the phone link is a
short-lived, token-protected capability.

## What is local

```text
Cue Crate server (one port)
├── Library, Review, Playlists, and Scout — browser UI + local API
├── Phone companion — optional QR flow, protected by a one-time session token
├── data/ — local catalogue, photos, caches, review state, and reports (never committed)
└── Optional providers — Discogs, YouTube, GetSongBPM, and future Spotify/AudD adapters
```

Profiles own physical copies and provider credentials. Collectives can share selected
copies, bins, and future setlists without losing individual ownership.

## Documentation

- [Getting started](docs/getting-started.md) — profiles, imports, and the normal app flow.
- [Architecture and local-network security](docs/architecture.md) — one-server design and data boundaries.
- [Credentials](docs/credentials.md) — Discogs, OpenCode Go, YouTube, and GetSongBPM setup.
- [Operations reference](docs/operations.md) — photo review, Discogs workflows, scouting, playlists, and advanced commands.
- [Roadmap](TODO.md) — BPM/key enrichment, Spotify, and the live-gig assistant.

## Development status

Cue Crate is an early local application. Before connecting a provider or adding a record
to Discogs, it makes review and explicit confirmation the default. Contributions and
experiments are welcome, but keep real collection data and credentials out of Git.
