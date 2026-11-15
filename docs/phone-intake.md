# Phone intake and image models

## Capture only what needs cataloging

An older multi-record photo does not by itself require a retake. Keep a reviewed,
exact Discogs selection unless you have found a real discrepancy. Concentrate on
new records and entries still marked ambiguous or manual-only in Crate Review.

Each new **physical copy** gets one phone bundle, not a six-cover grid. Start Cue
Crate on your trusted Wi-Fi network:

```bash
.venv/bin/python cue_crate.py serve --owner dj-one --lan
```

Open the printed **Phone connect screen** on the Mac and scan the QR code. Old
phone links stop working when the server restarts; scan the current QR again.

For each record:

1. Add a sharp **Primary label or back cover** photo. For a record in a generic
   sleeve, photograph the centre label (either side); no sleeve artwork is required.
2. Add the **Other-side label** if it supplies a different title, mix/version, label
   or catalog detail. Both sides still form one physical-record bundle.
3. Add a **Barcode** close-up when present, including both the bars and all digits
   directly underneath. A catalog number printed above it is a different identifier.
4. Use the optional **Front** view for artwork/title context. Upload the bundle, then
   move to the next record.

One readable label is enough to begin identification, though not necessarily to
prove an exact pressing. A catalog number is helpful, not mandatory: it may sit near
the spindle hole, track list, label logo, or perimeter text. Keep the full label in
focus rather than hunting for the code before every photo. Do not photograph a plain
sleeve just to fill a slot. If two similar pressings remain after label review, a
targeted identifier or runout close-up can be a later follow-up, not an intake minimum.

A barcode alone is not guaranteed to
identify the exact pressing: multiple editions can share identifiers, and OCR can
misread digits. No barcode is needed for records that never had one.

## Process the pending inbox

Upload a few records first, then run a small initial batch:

```bash
.venv/bin/python cue_crate.py analyse-intake --owner dj-one --all-pending --limit 3
```

This skips bundles with an existing intake analysis. It does not reprocess confirmed
records. If interrupted after a successful bundle, the next run resumes with the
remaining bundles. Remove `--limit` when ready to process the rest.

To select one specific new upload:

```bash
.venv/bin/python cue_crate.py analyse-intake --owner dj-one --upload-id UPLOAD_ID
```

`--refresh` explicitly reanalyses an already processed bundle. Do not use it merely
because the model changed. Legacy `analyse-photos` runs protect the existing draft
list; use `--resume` to append new grids. `--replace-candidates` deliberately replaces
that list and should not be part of an ordinary intake cycle.

Analysis is still a CLI operation, not automatic on upload. Open Crate Review on
the Mac after analysis. Check the visible identifiers and select an exact Discogs
release. Photo results remain **candidates**; adding them to Discogs requires the
separate reviewed additions workflow and explicit apply step.

## Inspect current models before using them

```bash
.venv/bin/python cue_crate.py photo-models --refresh
```

This reads OpenCode Go's public model metadata, without a key, photo upload, or
generation request. Results are cached locally for 24 hours. `cue_crate_supported`
means image input and the Go chat transport are advertised—not that recognition
accuracy has been benchmarked.

As checked on **1 November 2026**, the configured model aliases are:

| Alias | Model ID | Role |
| --- | --- | --- |
| `mimo` | `mimo-v2.6-flash` | Provisional latency-oriented default for routine records. |
| `kimi` | `kimi-k3.1-pro` | Explicit second opinion for difficult evidence; not an automatic fallback. |
| `minimax` | `minimax-m3.1-flash` | Current chat-compatible MiniMax image option. |
| `deepseek` | `deepseek-v4.1-flash` | Advertises image input; may need Global region access. |

The former `kimi-k2.6` is absent from the current catalog. Cue Crate checks model
availability, image capability, and the advertised transport before uploading. It
does not guess that every model from a family supports vision. Models needing a
different native transport are shown as unsupported by this adapter.

The defaults above have been checked against live **metadata**. A dedicated Keychain
key also enabled a small MiMo live check on one already-confirmed LP: artist/title and
catalog number were recovered from the label, and the three-photo bundle recovered
the barcode. The stylized record-label logo was misread. This is not a general accuracy
benchmark or a claim that all four models have been exercised end-to-end.

In that local check, MiMo took about 46 seconds for the label and 44 seconds for the
bundle. A same-label MiniMax M3.1 Flash check took about 25 seconds and read the label
logo correctly, but supplied an unsupported year. This makes MiniMax a useful next
pilot candidate, not an established accuracy winner. MiMo remains the configured
default until a more representative set of records is reviewed. Detailed output can
contain errors even when artist/title/catalog number and self-reported confidence
look convincing. Keep exact-pressing selection and the canonical release year under
Discogs/human review.

The speed preference is deliberate, not a claim of a local benchmark win. Once the
dedicated key is installed, compare MiMo and MiniMax on the same few label-only
records. Record end-to-end time plus exact artist/title/mix and identifier accuracy;
do not choose solely by the model's confidence score. Keep Kimi for a difficult
second pass when the extra time is worthwhile, and never silently escalate every
uncertain image to a slower model.

### Non-mutating provider check

Use an existing phone bundle to time image recognition without replacing any saved
identification:

```bash
.venv/bin/python scripts/check_photo_models.py --owner dj-one --provider mimo
```

The default makes **two inference requests**: one label view and the full bundle.
Use `--case label` for just one request, `--upload-id ID` to choose a bundle, or
`--single-view evidence` if its primary evidence photo is the centre label. The report
is written under the local profile's `data/reports/` directory. Catalog, review,
candidate, and playlist metadata are fingerprinted to check that they remain unchanged.
Do not infer broad accuracy or typical latency from a single record. Runtime varies
with provider load, output length, and the evidence; inspect identifier mistakes as
well as timing and self-reported confidence.

See the [official Go model list, endpoints, and limits](https://opencode.ai/v2/docs/console/go/).
Keep Extra Usage off to prevent service-side pay-as-you-go fallback. Go is described
as a coding-agent plan: confirm eligibility for this photo workflow with OpenCode
before planning a large batch. Cue Crate uses its own truthful identity and does not
masquerade as another client.

## Keep model settings out of application code

Copy the non-secret template if you want local defaults:

```bash
cp config/photo-analysis.example.json config/photo-analysis.local.json
```

The local file is ignored by Git. It controls the default alias, pinned model IDs,
image dimension, and output/reasoning allowance. Credentials stay in the separate
[credential store](credentials.md). Use `--photo-config PATH` for another settings
file. CLI options override local defaults:

```bash
.venv/bin/python cue_crate.py analyse-intake --owner dj-one --all-pending --limit 3 --provider mimo
.venv/bin/python cue_crate.py analyse-intake --owner dj-one --provider kimi --model kimi-k3.1-pro --max-tokens 12000
```

Selected photos are sent to OpenCode Go and its serving model provider. The model ID
and analysis time are recorded beside every saved analysis. Photos, model caches,
results, and review decisions remain local-only data files and are never committed.
No fallback to another model, host, or billing API occurs automatically. Authentication
or allowance errors stop the run; completed earlier bundles remain saved.
