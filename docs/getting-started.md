# Getting started

Cue Crate has one normal runtime command. It starts the complete local app—Library,
Review, Playlists, and Scout—on one port.

```bash
.venv/bin/python cue_crate.py serve --owner dj-one
```

Open the Library at <http://127.0.0.1:8765/viewer.html>. The active `--owner` profile is
used for Review, YouTube playlist state, and phone intake; the Library still shows the
combined collection.

## First profile

Copy the example configuration and make it local to your machine:

```bash
cp config/profiles.example.json config/profiles.local.json
```

Set a stable profile ID, a display name, and the public Discogs username. The local file
is ignored by Git. For a shared project, add a collective in the same way:

```bash
cp config/collectives.example.json config/collectives.local.json
```

## Import a collection

Import a Discogs collection export:

```bash
.venv/bin/python cue_crate.py import-csv --owner dj-one --input ~/Downloads/discogs-collection.csv
```

Or fetch from Discogs once a local token is configured:

```bash
.venv/bin/python cue_crate.py fetch-collection --owner dj-one
```

Then restart `serve` if it is not already running and open the Library.

## Phone intake

Use the LAN option only on a trusted home or studio network:

```bash
.venv/bin/python cue_crate.py serve --owner dj-one --lan
```

The command prints a **Phone connect screen** URL for the serving computer. It creates a
one-time QR link to the phone companion. The phone can browse only the active profile's
catalogue and upload intake photos; Library, Review, Playlists, and Scout APIs remain
loopback-only.

For detailed import, photo-review, and provider workflows, see the
[operations reference](operations.md).
