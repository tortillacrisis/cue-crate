"""Collection imports must not overwrite deliberate local playlist curation."""

import copy
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cue_crate as app


class CollectionMetadataTests(unittest.TestCase):
    def test_refresh_preserves_local_sharing_and_annotations(self):
        local = {
            "id": "example-1", "owner": "Example DJ", "discogs_release_id": 10,
            "discogs_instance_id": 20, "title": "Old Title",
            "collective_ids": ["collective-one", "collective-two"],
            "crate_locations": ["gig-bin"], "quick_access": True,
            "quick_access_sources": ["review"], "dj_notes": {"energy": 4},
            "tracklist": [{"title": "Chosen Mix", "bpm": 118}],
        }
        catalog = {"records": [copy.deepcopy(local)]}
        incoming = {key: local[key] for key in ("id", "owner", "discogs_release_id", "discogs_instance_id")}
        incoming.update({"title": "Corrected Discogs Title", "collective_ids": []})
        self.assertEqual(app.merge_records(catalog, [incoming]), (0, 1))
        updated = catalog["records"][0]
        self.assertEqual(updated["title"], "Corrected Discogs Title")
        for field in ("collective_ids", "crate_locations", "quick_access", "quick_access_sources", "dj_notes", "tracklist"):
            self.assertEqual(updated[field], local[field])

    def test_reserved_workspace_is_not_inferred_as_a_profile(self):
        with tempfile.TemporaryDirectory() as root:
            workspaces = Path(root)
            for name in ("collectives", ".cache", "example-dj"):
                (workspaces / name).mkdir()
            with patch.object(app, "WORKSPACE_DIR", workspaces), \
                 patch.object(app, "load_profiles_config", return_value={}), \
                 patch.object(app, "load_json", return_value={"records": []}):
                self.assertEqual(app.available_profiles(), [{"id": "example-dj", "display_name": "example-dj"}])


class TracklistEnrichmentTests(unittest.TestCase):
    def test_missing_only_enrichment_preserves_existing_track_data(self):
        existing = {
            "id": "copy-one", "owner": "DJ One", "discogs_release_id": 10,
            "tracklist": [{
                "position": "A1", "title": "Chosen Mix", "bpm": 118,
                "bpm_user_override": True, "dj_notes": {"intro_bars": 8},
            }],
        }
        original = copy.deepcopy(existing)
        missing = {
            "id": "copy-two", "owner": "DJ Two", "discogs_release_id": 20,
            "artist": "Example Artist", "tracklist": [],
        }
        catalog = {"records": [existing, missing]}
        release = {"uri": "https://www.discogs.com/release/20", "tracklist": [
            {"type_": "track", "position": "A", "title": "Example Track", "duration": "6:00"},
        ]}
        with patch.object(app, "read_token", return_value="test-key"), \
             patch.object(app, "load_catalog", return_value=catalog), \
             patch.object(app, "discogs_request", return_value=release) as request, \
             patch.object(app, "save_catalog") as save, \
             patch.object(app.time, "sleep"):
            app.command_enrich(Namespace(owner=None, token_file=None, refresh=False))
        request.assert_called_once_with("/releases/20", "test-key")
        save.assert_called_once_with(catalog)
        self.assertEqual(existing, original)
        self.assertEqual(missing["tracklist"][0]["title"], "Example Track")
        self.assertEqual(missing["tracklist"][0]["artist"], "Example Artist")


class PlaylistRefreshTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"kind": "album", "id": "record-b", "mode": "full_album"},
            {"kind": "album", "id": "record-a", "mode": "spotify_skip"},
        ]
        self.spotify_review = {
            "items": [{"id": "record-b", "selected_spotify_id": "chosen-track"}],
            "ready": 1,
        }
        self.manager = {"playlists": [{
            "id": "local-set",
            "entries": copy.deepcopy(self.entries),
            "spotify_review": copy.deepcopy(self.spotify_review),
            "youtube": {"playlist_id": "remote-set"},
        }]}
        # Published order intentionally differs from the newer local edit.
        self.old_review = {"items": [
            {"id": "record-a", "selected_video_id": "video-a", "published_playlist_item_id": "receipt-a"},
            {"id": "record-b", "selected_video_id": "video-b", "published_playlist_item_id": "receipt-b"},
        ]}
        self.new_review = {
            "items": [{"id": "record-a"}, {"id": "record-b"}, {"id": "new-record"}],
            "playlist": {"id": "remote-set"},
        }

    def test_routine_refresh_preserves_local_order_modes_and_spotify_choices(self):
        result, _ = app.migrate_playlist_identities(
            "DJ One", self.manager, self.old_review, self.new_review,
            restore_published_membership=False,
        )
        playlist = result["playlists"][0]
        self.assertEqual(playlist["entries"], self.entries)
        self.assertEqual(playlist["spotify_review"], self.spotify_review)
        self.assertEqual(playlist["youtube"], {"playlist_id": "remote-set"})
        self.assertNotIn("new-record", playlist["track_ids"])

    def test_changed_identity_invalidates_only_derived_spotify_review(self):
        self.new_review["identity_aliases"] = {"record-b": "canonical-b"}
        self.new_review["items"].append({"id": "canonical-b"})
        result, _ = app.migrate_playlist_identities(
            "DJ One", self.manager, self.old_review, self.new_review,
            restore_published_membership=False,
        )
        playlist = result["playlists"][0]
        self.assertEqual(playlist["entries"][0]["id"], "canonical-b")
        self.assertNotIn("spotify_review", playlist)
        self.assertEqual(playlist["youtube"]["playlist_id"], "remote-set")

    def test_explicit_migration_can_still_recover_published_membership(self):
        result, _ = app.migrate_playlist_identities(
            "DJ One", self.manager, self.old_review, self.new_review,
        )
        playlist = result["playlists"][0]
        self.assertEqual([entry["id"] for entry in playlist["entries"]], ["record-a", "record-b"])
        self.assertEqual(playlist["membership_source"], "published_youtube_receipts")
        self.assertNotIn("spotify_review", playlist)

    def test_collection_refresh_opts_out_of_published_membership_recovery(self):
        with patch.object(app.Path, "exists", return_value=True), \
             patch.object(app, "load_profiles_config", return_value={}), \
             patch.object(app, "reconcile_photo_review_identities", return_value=({}, {"changed_items": 0})), \
             patch.object(app, "command_apply_review"), \
             patch.object(app, "export_quick_crate", return_value=([], None, None)), \
             patch.object(app, "load_json", side_effect=[self.old_review, self.manager]), \
             patch.object(app, "build_youtube_music_review", return_value=self.new_review), \
             patch.object(app, "migrate_playlist_identities", wraps=app.migrate_playlist_identities) as migrate, \
             patch.object(app, "write_json"):
            app.refresh_local_identity_views("DJ One")
        self.assertFalse(migrate.call_args.kwargs["restore_published_membership"])


if __name__ == "__main__":
    unittest.main()
