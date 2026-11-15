"""Run the real local UI with fictional, temporary data and provider access disabled."""
import argparse
from contextlib import contextmanager, ExitStack
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cue_crate as app


def provider_disabled(*args, **kwargs):
    raise ValueError("Provider access is disabled in the fictional demo.")


@contextmanager
def demo_workspace():
    """Redirect every app data/config path before creating any demo records."""
    with ExitStack() as stack:
        root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="cue-crate-demo-")))
        old_data, old_config = app.DATA_DIR, app.CONFIG_DIR
        for name, value in list(vars(app).items()):
            if isinstance(value, Path) and value.is_relative_to(old_data):
                stack.enter_context(patch.object(app, name, root / "data" / value.relative_to(old_data)))
            elif isinstance(value, Path) and value.is_relative_to(old_config):
                stack.enter_context(patch.object(app, name, root / "config" / value.relative_to(old_config)))
        stack.enter_context(patch.object(app, "LOCAL_CONFIG_DIR", root / "credentials"))
        stack.enter_context(patch.object(app, "LEGACY_LOCAL_CONFIG_DIR", root / "legacy-credentials"))
        for name in ("read_token", "read_spotify_client_id", "read_opencode_go_key", "read_getsongbpm_key"):
            stack.enter_context(patch.object(app, name, return_value=None))
        for name in ("discogs_request", "spotify_api_request", "youtube_service", "getsongbpm_request"):
            stack.enter_context(patch.object(app, name, side_effect=provider_disabled))
        app.write_json(app.PROFILES_CONFIG_PATH, {"profiles": {
            "dj-one": {"display_name": "DJ One"}, "dj-two": {"display_name": "DJ Two"},
        }})
        records = []
        specs = [
            ("Demo Artist One", "Midnight Practice", "DJ One", "Boogie", 1984),
            ("Demo Artist Two", "After Hours", "DJ Two", "Disco", 1982),
            ("Demo Artist Three", "Warm-Up Signals", "DJ One", "Electro", 1985),
        ]
        features = {}
        for index, (artist, title, owner, style, year) in enumerate(specs, 1):
            release_id = 900000000 + index
            tracks = [{"position": "A1", "artist": artist, "title": "Example Mix", "duration": "6:12", "dj_notes": {}}]
            records.append({
                "id": f"demo-copy-{index}", "owner": owner, "owner_id": app.profile_context(owner)["id"],
                "discogs_release_id": release_id, "artist": artist, "title": title,
                "year": year, "format": "Vinyl, 12\"", "label": "Example Records",
                "catalog_number": f"DEMO-{index:03}", "source": "fictional_demo",
                "quick_access": True, "tracklist": tracks,
            })
            features[str(release_id)] = {
                "release_id": release_id, "artist": artist, "title": title,
                "genres": ["Funk / Soul"], "styles": [style], "formats": ["Vinyl", '12"'],
                "year": year, "videos": [], "videos_known": True,
            }
        app.save_catalog({"schema_version": 1, "records": records})
        app.write_json(app.RELEASE_FEATURES_PATH, {"features": features})
        for owner in ("DJ One", "DJ Two"):
            app.write_json(app.person_workspace_path(owner, "review.json"), {"owner": owner, "items": []})
            app.build_youtube_music_review(owner)
        yield root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    args = parser.parse_args()
    with demo_workspace():
        print("Fictional demo: data is temporary; API credentials and provider calls are disabled.", flush=True)
        app.command_serve(argparse.Namespace(owner="DJ One", port=args.port, lan=False, advertise=None, token_file=None))


if __name__ == "__main__":
    main()
