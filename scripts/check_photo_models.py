#!/usr/bin/env python3
"""Small, opt-in Go photo check that never updates catalog/review/playlist state."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cue_crate as app
from photo_analysis import PhotoProviderError, complete_photo


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--upload-id", help="Existing phone bundle; omitted uses the latest")
    parser.add_argument("--provider", choices=list(app.DEFAULT_MODELS), default="mimo")
    parser.add_argument("--case", choices=["label", "bundle"], action="append", help="Repeat to select cases; default tests label and full bundle (two requests)")
    parser.add_argument("--single-view", default="label", help="Role used for the label case; set evidence if that photo is a label")
    args = parser.parse_args()
    cases = list(dict.fromkeys(args.case or ["label", "bundle"]))
    owner = app.owner_label(args.owner)
    bundle, metadata = app.intake_bundle_for(owner, args.upload_id)
    upload_id = str(metadata.get("upload_id") or bundle.name)
    files = metadata.get("files", {})
    views = {}
    for role in ("evidence", "back", "label", "barcode", "front", "other"):
        filename = files.get(role, {}).get("filename")
        path = bundle / str(filename or "")
        if filename and path.is_file():
            views[role] = path
    if not views:
        parser.error("This bundle has no readable image files.")
    if "label" in cases and args.single_view not in views:
        parser.error(f"No {args.single_view!r} view in this bundle; choose --single-view or use only --case bundle.")
    protected = [app.CATALOG_PATH, app.AGGREGATE_QUICK_CRATE_PATH, app.person_quick_crate_path(owner), app.person_youtube_review_path(owner), app.person_playlists_path(owner)]
    protected += [app.person_workspace_path(owner, name) for name in ("review.json", "intake-review.json", "photo-candidates.json")]
    before = {path: fingerprint(path) for path in protected}
    review = app.load_json(app.person_workspace_path(owner, "review.json"), {"items": []})
    known = next((item for item in review.get("items", []) if item.get("intake_id") == upload_id), {})
    selected = known.get("discogs_selection") or {}
    expected = {key: selected.get(key) for key in ("release_id", "artist", "title", "catalog_number", "barcode")}
    settings = app.photo_model_settings(app.load_model_catalog(app.PHOTO_MODELS_CACHE_PATH), app.load_photo_config(app.PHOTO_CONFIG_PATH), provider=args.provider)
    key = app.read_opencode_go_key()
    if not key:
        parser.error("No Go credential found. Install the dedicated Cue Crate key first.")
    report = {"tested_at": app.utc_now(), "owner": owner, "upload_id": upload_id, "model": settings["model"], "max_image_dimension": settings["max_image_dimension"], "reference_selection": expected, "cases": [], "review_updated": False}
    for case in cases:
        roles = [args.single_view] if case == "label" else list(views)
        print(f"Testing {settings['model']} / {case}: {', '.join(roles)}", flush=True)
        started = time.monotonic()
        content = [{"type": "text", "text": "These photographs show one physical record. Transcribe visible evidence only; return JSON."}]
        for role in roles:
            content += [{"type": "text", "text": f"VIEW: {role}"}, {"type": "image_url", "image_url": {"url": app.image_data_url(views[role], max_dimension=settings["max_image_dimension"]), "detail": "high"}}]
        request_started = time.monotonic()
        result = {"case": case, "views": roles}
        try:
            observed = app.parse_model_json(complete_photo(key, settings, app.INTAKE_PROMPT, content), f"{case} provider check")
            result["observed"] = observed
            if expected.get("artist") and expected.get("title"):
                result["artist_title_match_reference"] = all(app.normalise_match_text(observed.get(field)) == app.normalise_match_text(expected[field]) for field in ("artist", "title"))
            result["status"] = "ok"
        except (PhotoProviderError, SystemExit) as exc:
            result.update({"status": "error", "error": str(exc)})
        result["request_seconds"] = round(time.monotonic() - request_started, 2)
        result["total_seconds"] = round(time.monotonic() - started, 2)
        report["cases"].append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        if result["status"] == "error":
            break  # Do not repeatedly send photos after an auth/allowance/transport error.
    report["protected_metadata_unchanged"] = all(fingerprint(path) == previous for path, previous in before.items())
    stamp = app.datetime.now(app.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = app.person_reports_dir(owner) / "photo-checks" / f"{stamp}-{args.provider}-{uuid.uuid4().hex[:6]}.json"
    app.write_json(destination, report)
    print(f"Report: {destination}")
    print(f"Catalog/review/playlist metadata unchanged: {report['protected_metadata_unchanged']}")
    if any(case["status"] == "error" for case in report["cases"]) or not report["protected_metadata_unchanged"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
