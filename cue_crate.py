#!/usr/bin/env python3
"""A local-first assistant for vinyl DJs: catalogue, prepare, and play physical records."""

import argparse
import base64
import csv
import difflib
import ipaddress
import io
import mimetypes
import http.server
import json
import math
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default as email_default_policy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
PROFILES_CONFIG_PATH = CONFIG_DIR / "profiles.local.json"
LEGACY_PEOPLE_CONFIG_PATH = CONFIG_DIR / "people.local.json"
COLLECTIVES_CONFIG_PATH = CONFIG_DIR / "collectives.local.json"
LIBRARY_DIR = DATA_DIR / "library"
WORKSPACE_DIR = DATA_DIR / "workspace"
INBOX_DIR = DATA_DIR / "inbox"
CACHE_DIR = DATA_DIR / "cache"
DISCOGS_CACHE_DIR = CACHE_DIR / "discogs"
SELLER_CACHE_DIR = CACHE_DIR / "sellers"
GETSONGBPM_CACHE_PATH = CACHE_DIR / "getsongbpm-search.json"
REPORTS_DIR = DATA_DIR / "reports"
CATALOG_PATH = LIBRARY_DIR / "catalog.json"
RELEASE_FEATURES_PATH = DISCOGS_CACHE_DIR / "release-features.json"
QUICK_CRATES_DIR = LIBRARY_DIR / "quick-crates"
AGGREGATE_QUICK_CRATE_PATH = LIBRARY_DIR / "quick-crate.json"
API_ROOT = "https://api.discogs.com"
GETSONGBPM_API_ROOT = "https://api.getsong.co"
APP_NAME = "Cue Crate"
APP_SLUG = "cue-crate"
LEGACY_APP_SLUG = "vinyl-crate"
USER_AGENT = "cue-crate/0.1 (local vinyl DJ assistant)"
CONFIG_HOME = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))
LOCAL_CONFIG_DIR = CONFIG_HOME / APP_SLUG
LEGACY_LOCAL_CONFIG_DIR = CONFIG_HOME / LEGACY_APP_SLUG
KEYCHAIN_SERVICE = "cue-crate.discogs-token"
LEGACY_KEYCHAIN_SERVICE = "vinyl-crate.discogs-token"
CONFIG_TOKEN_PATH = LOCAL_CONFIG_DIR / "discogs-token"
LEGACY_CONFIG_TOKEN_PATH = LEGACY_LOCAL_CONFIG_DIR / "discogs-token"
GETSONGBPM_KEYCHAIN_SERVICE = "cue-crate.getsongbpm-api-key"
LEGACY_GETSONGBPM_KEYCHAIN_SERVICE = "vinyl-crate.getsongbpm-api-key"
GETSONGBPM_CONFIG_PATH = LOCAL_CONFIG_DIR / "getsongbpm-api-key"
LEGACY_GETSONGBPM_CONFIG_PATH = LEGACY_LOCAL_CONFIG_DIR / "getsongbpm-api-key"
OPENCODE_GO_CONFIG_PATH = LOCAL_CONFIG_DIR / "opencode-go-api-key"
LEGACY_OPENCODE_GO_CONFIG_PATH = LEGACY_LOCAL_CONFIG_DIR / "opencode-go-api-key"
OPENCODE_AUTH_PATH = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "opencode" / "auth.json"
LEGACY_YOUTUBE_TOKEN_PATH = LOCAL_CONFIG_DIR / "youtube-oauth.json"
LEGACY_SPOTIFY_TOKEN_PATH = LOCAL_CONFIG_DIR / "spotify-oauth.json"
OLDER_YOUTUBE_TOKEN_PATH = LEGACY_LOCAL_CONFIG_DIR / "youtube-oauth.json"
OLDER_SPOTIFY_TOKEN_PATH = LEGACY_LOCAL_CONFIG_DIR / "spotify-oauth.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dir() -> None:
    for directory in (
        LIBRARY_DIR,
        WORKSPACE_DIR,
        WORKSPACE_DIR / "collectives",
        INBOX_DIR,
        DISCOGS_CACHE_DIR,
        SELLER_CACHE_DIR,
        REPORTS_DIR,
        QUICK_CRATES_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def slugify_person(value: str) -> str:
    """Return a safe stable directory key for a configured person."""
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    slug = "".join(char if char.isalnum() else "-" for char in normalised).strip("-")
    return slug or "person"


def load_profiles_config() -> Dict[str, Any]:
    """Load local profile metadata, accepting the former people config during migration."""
    profiles: Dict[str, Any] = {}
    legacy = load_json(LEGACY_PEOPLE_CONFIG_PATH, {"people": {}})
    legacy_people = legacy.get("people", {}) if isinstance(legacy, dict) else {}
    if isinstance(legacy_people, dict):
        profiles.update(legacy_people)
    payload = load_json(PROFILES_CONFIG_PATH, {"profiles": {}})
    configured = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    if isinstance(configured, dict):
        profiles.update(configured)
    return profiles


def load_people_config() -> Dict[str, Any]:
    """Backward-compatible alias for older commands and local configurations."""
    return load_profiles_config()


def profile_discogs_username(details: Dict[str, Any]) -> str:
    """Read the Discogs handle from either the current or legacy profile shape."""
    providers = details.get("providers", {}) if isinstance(details, dict) else {}
    discogs = providers.get("discogs", {}) if isinstance(providers, dict) else {}
    if isinstance(discogs, dict) and str(discogs.get("username") or "").strip():
        return str(discogs.get("username") or "").strip()
    return str(details.get("discogs_username") or "").strip()


def profile_context(value: str) -> Dict[str, str]:
    """Resolve a stable profile ID or display name without requiring local setup."""
    requested = str(value).strip()
    if not requested:
        raise SystemExit("A profile is required. Configure one locally or supply --owner.")
    for profile_id, details in load_profiles_config().items():
        if not isinstance(details, dict):
            continue
        display_name = str(details.get("display_name") or profile_id).strip()
        if requested.casefold() in {str(profile_id).casefold(), display_name.casefold()}:
            return {
                "id": slugify_person(str(profile_id)),
                "display_name": display_name,
                "discogs_username": profile_discogs_username(details),
            }
    return {"id": slugify_person(requested), "display_name": requested, "discogs_username": ""}


def person_context(value: str) -> Dict[str, str]:
    """Backward-compatible name for the profile resolver used by existing commands."""
    return profile_context(value)


def available_profiles(default_owner: str = "") -> List[Dict[str, str]]:
    """Return known local profiles for owner-aware browser selectors.

    Profiles can be declared in ``config/profiles.local.json``. The legacy
    ``people.local.json`` remains readable so existing local workspaces keep working.
    Catalogue records and workspace directories are also included before setup.
    """
    candidates: List[str] = []
    if str(default_owner).strip():
        candidates.append(str(default_owner).strip())
    for person_id, details in load_profiles_config().items():
        if isinstance(details, dict):
            candidates.append(str(details.get("display_name") or person_id).strip())
        else:
            candidates.append(str(person_id).strip())
    catalogue = load_json(CATALOG_PATH, {"records": []})
    for record in catalogue.get("records", []) if isinstance(catalogue, dict) else []:
        if isinstance(record, dict) and str(record.get("owner") or "").strip():
            candidates.append(str(record["owner"]).strip())
    if WORKSPACE_DIR.exists():
        candidates.extend(path.name for path in WORKSPACE_DIR.iterdir() if path.is_dir())

    people: List[Dict[str, str]] = []
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        context = person_context(candidate)
        if context["id"] in seen:
            continue
        seen.add(context["id"])
        people.append({"id": context["id"], "display_name": context["display_name"]})
    return sorted(people, key=lambda person: person["display_name"].casefold())


def available_people(default_owner: str = "") -> List[Dict[str, str]]:
    """Backward-compatible alias for profile-aware browser selectors."""
    return available_profiles(default_owner)


def owner_label(value: str) -> str:
    return profile_context(value)["display_name"]


def load_collectives_config() -> Dict[str, Any]:
    """Load optional local collaboration metadata without credentials."""
    payload = load_json(COLLECTIVES_CONFIG_PATH, {"collectives": {}})
    collectives = payload.get("collectives", {}) if isinstance(payload, dict) else {}
    return collectives if isinstance(collectives, dict) else {}


def collective_member_ids(details: Dict[str, Any]) -> List[str]:
    members = details.get("members", []) if isinstance(details, dict) else []
    result: List[str] = []
    if not isinstance(members, list):
        return result
    for member in members:
        value = member.get("profile_id") if isinstance(member, dict) else member
        if str(value or "").strip():
            result.append(slugify_person(str(value)))
    return list(dict.fromkeys(result))


def collective_context(value: str) -> Dict[str, Any]:
    requested = str(value).strip()
    if not requested:
        raise SystemExit("A collective is required.")
    for collective_id, details in load_collectives_config().items():
        if not isinstance(details, dict):
            continue
        display_name = str(details.get("display_name") or collective_id).strip()
        if requested.casefold() in {str(collective_id).casefold(), display_name.casefold()}:
            return {
                "id": slugify_person(str(collective_id)),
                "display_name": display_name,
                "members": collective_member_ids(details),
            }
    raise SystemExit(f"Collective {requested!r} is not configured in {COLLECTIVES_CONFIG_PATH}.")


def available_collectives(profile: str = "") -> List[Dict[str, Any]]:
    profile_id = profile_context(profile)["id"] if str(profile).strip() else ""
    entries: List[Dict[str, Any]] = []
    for collective_id, details in load_collectives_config().items():
        if not isinstance(details, dict):
            continue
        members = collective_member_ids(details)
        if profile_id and profile_id not in members:
            continue
        entries.append({
            "id": slugify_person(str(collective_id)),
            "display_name": str(details.get("display_name") or collective_id).strip(),
            "members": members,
        })
    return sorted(entries, key=lambda entry: entry["display_name"].casefold())


def collective_workspace_dir(collective: str) -> Path:
    return WORKSPACE_DIR / "collectives" / collective_context(collective)["id"]


def collective_workspace_path(collective: str, filename: str) -> Path:
    return collective_workspace_dir(collective) / filename


def record_collective_ids(record: Dict[str, Any]) -> List[str]:
    values = record.get("collective_ids", []) if isinstance(record, dict) else []
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(slugify_person(str(value)) for value in values if str(value).strip()))


def record_is_shared_with(record: Dict[str, Any], collective: str) -> bool:
    return collective_context(collective)["id"] in record_collective_ids(record)


def profile_provider_token_path(owner: str, provider: str) -> Path:
    """Return an owner-specific local OAuth path; credentials never live in the repo."""
    provider_id = slugify_person(provider)
    return LOCAL_CONFIG_DIR / "profiles" / profile_context(owner)["id"] / f"{provider_id}-oauth.json"


def profile_provider_token_paths(owner: str, provider: str) -> List[Path]:
    """Return the current credential path plus the previous product namespace."""
    provider_id = slugify_person(provider)
    profile_id = profile_context(owner)["id"]
    return [
        profile_provider_token_path(owner, provider),
        LEGACY_LOCAL_CONFIG_DIR / "profiles" / profile_id / f"{provider_id}-oauth.json",
    ]


def legacy_provider_token_paths(provider: str) -> List[Path]:
    """Find pre-profile OAuth files from both supported configuration namespaces."""
    provider_id = slugify_person(provider)
    if provider_id == "youtube":
        return [LEGACY_YOUTUBE_TOKEN_PATH, OLDER_YOUTUBE_TOKEN_PATH]
    if provider_id == "spotify":
        return [LEGACY_SPOTIFY_TOKEN_PATH, OLDER_SPOTIFY_TOKEN_PATH]
    raise SystemExit(f"Unsupported provider {provider!r}.")


def person_workspace_dir(owner: str) -> Path:
    return WORKSPACE_DIR / person_context(owner)["id"]


def person_inbox_dir(owner: str) -> Path:
    return INBOX_DIR / person_context(owner)["id"]


def person_workspace_path(owner: str, filename: str) -> Path:
    return person_workspace_dir(owner) / filename


def person_wantlist_path(owner: str) -> Path:
    return DISCOGS_CACHE_DIR / "users" / person_context(owner)["id"] / "wantlist.json"


def person_reports_dir(owner: str) -> Path:
    return REPORTS_DIR / person_context(owner)["id"]


def person_taste_profile_path(owner: str) -> Path:
    return person_reports_dir(owner) / "taste-profile.json"


def person_taste_profile_markdown_path(owner: str) -> Path:
    return person_reports_dir(owner) / "taste-profile.md"


def person_seller_reports_dir(owner: str) -> Path:
    return person_reports_dir(owner) / "sellers"


def person_quick_crate_path(owner: str) -> Path:
    return QUICK_CRATES_DIR / f"{person_context(owner)['id']}.json"


def person_quick_crate_csv_path(owner: str) -> Path:
    return QUICK_CRATES_DIR / f"{person_context(owner)['id']}.csv"


def person_youtube_review_path(owner: str) -> Path:
    return person_workspace_path(owner, "youtube-music-review.json")


def person_playlists_path(owner: str) -> Path:
    return person_workspace_path(owner, "playlists.json")


def refresh_aggregate_quick_crate() -> int:
    """Rebuild the shared browser export from owner-specific quick crates."""
    aggregate_records = []
    for path in sorted(QUICK_CRATES_DIR.glob("*.json")):
        aggregate_records.extend(load_json(path, {"records": []}).get("records", []))
    write_json(AGGREGATE_QUICK_CRATE_PATH, {
        "schema_version": 2,
        "generated_at": utc_now(),
        "records": aggregate_records,
    })
    return len(aggregate_records)


def move_legacy_path(source: Path, destination: Path, moved: List[str]) -> None:
    """Move one old-layout item once, refusing to overwrite existing person state."""
    if not source.exists():
        return
    if destination.exists():
        raise SystemExit(f"Cannot migrate {source}: destination already exists at {destination}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    moved.append(f"{source.relative_to(DATA_DIR)} → {destination.relative_to(DATA_DIR)}")


def command_migrate_person_layout(args: argparse.Namespace) -> None:
    """Move the former one-person local state into an owner-specific layout."""
    owner = args.owner
    workspace = person_workspace_dir(owner)
    reports = person_reports_dir(owner)
    moved: List[str] = []
    for filename in ("photo-candidates.json", "review.json", "purchases.json", "youtube-music-review.json"):
        move_legacy_path(WORKSPACE_DIR / filename, workspace / filename, moved)
    legacy_overrides = WORKSPACE_DIR / "owned-overrides.json"
    target_overrides = workspace / "owned-overrides.json"
    if legacy_overrides.exists():
        legacy = load_json(legacy_overrides, {"owners": {}})
        records = legacy.get("owners", {}).get(owner, []) if isinstance(legacy.get("owners"), dict) else legacy.get("records", [])
        if target_overrides.exists():
            raise SystemExit(f"Cannot migrate {legacy_overrides}: destination already exists at {target_overrides}.")
        write_json(target_overrides, {"schema_version": 1, "owner": owner, "records": records})
        legacy_backup = workspace / "owned-overrides.legacy.json"
        if legacy_backup.exists():
            raise SystemExit(f"Cannot preserve {legacy_overrides}: legacy backup already exists at {legacy_backup}.")
        legacy_overrides.rename(legacy_backup)
        moved.append(f"workspace/owned-overrides.json → workspace/{person_context(owner)['id']}/owned-overrides.json (with legacy backup)")
    move_legacy_path(DISCOGS_CACHE_DIR / "wantlist.json", person_wantlist_path(owner), moved)
    move_legacy_path(REPORTS_DIR / "taste-profile.json", person_taste_profile_path(owner), moved)
    move_legacy_path(REPORTS_DIR / "taste-profile.md", person_taste_profile_markdown_path(owner), moved)
    legacy_seller_reports = REPORTS_DIR / "sellers"
    if legacy_seller_reports.exists() and any(legacy_seller_reports.iterdir()):
        target_seller_reports = person_seller_reports_dir(owner)
        if target_seller_reports.exists():
            raise SystemExit(f"Cannot migrate {legacy_seller_reports}: destination already exists at {target_seller_reports}.")
        target_seller_reports.parent.mkdir(parents=True, exist_ok=True)
        legacy_seller_reports.rename(target_seller_reports)
        moved.append(f"reports/sellers → reports/{person_context(owner)['id']}/sellers")
    move_legacy_path(LIBRARY_DIR / "quick-crate.csv", person_quick_crate_csv_path(owner), moved)
    legacy_quick_crate = AGGREGATE_QUICK_CRATE_PATH
    person_quick_crate = person_quick_crate_path(owner)
    # After an initial migration, quick-crate.json is the regenerated aggregate
    # and must not be mistaken for another legacy export on subsequent runs.
    if legacy_quick_crate.exists() and not person_quick_crate.exists():
        move_legacy_path(legacy_quick_crate, person_quick_crate, moved)
    catalog = load_catalog()
    owner_id = person_context(owner)["id"]
    catalog_changed = False
    for record in catalog.get("records", []):
        if record.get("owner", "").casefold() == owner.casefold() and record.get("owner_id") != owner_id:
            record["owner_id"] = owner_id
            catalog_changed = True
    if catalog_changed:
        save_catalog(catalog)
        moved.append("library/catalog.json owner_id metadata updated")
    total = refresh_aggregate_quick_crate()
    if moved:
        print("Migrated local state:")
        for item in moved:
            print(f"  {item}")
    else:
        print("No legacy one-person files were found; the person layout is already in use.")
    print(f"Shared quick-crate browser export now contains {total} records.")


def command_list_profiles(args: argparse.Namespace) -> None:
    profiles = load_profiles_config()
    if not profiles:
        print("No profiles configured. Use --owner with a local name directly, or copy config/profiles.example.json to config/profiles.local.json.")
        return
    for person_id, details in profiles.items():
        if not isinstance(details, dict):
            continue
        display_name = str(details.get("display_name") or person_id)
        username = profile_discogs_username(details) or "not set"
        print(f"{person_id}: {display_name} (Discogs: {username})")


def command_list_collectives(args: argparse.Namespace) -> None:
    collectives = available_collectives(args.profile or "")
    if not collectives:
        print("No collectives configured. Copy config/collectives.example.json to config/collectives.local.json when you are ready to share a crate.")
        return
    for collective in collectives:
        members = ", ".join(collective["members"]) or "no members"
        print(f"{collective['id']}: {collective['display_name']} ({members})")


def command_migrate_provider_token(args: argparse.Namespace) -> None:
    """Move one legacy machine-wide OAuth token into a profile-specific local store."""
    source = next((path for path in legacy_provider_token_paths(args.provider) if path.exists()), None)
    target = profile_provider_token_path(args.owner, args.provider)
    if source is None:
        candidates = ", ".join(str(path) for path in legacy_provider_token_paths(args.provider))
        raise SystemExit(f"No legacy {args.provider} OAuth token exists. Checked: {candidates}")
    if target.exists():
        raise SystemExit(f"A profile-specific {args.provider} OAuth token already exists at {target}; refusing to overwrite it.")
    try:
        payload = source.read_bytes()
        if not payload:
            raise ValueError("The legacy token file is empty.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        target.write_bytes(payload)
        target.chmod(0o600)
        source.unlink()
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise SystemExit(f"Could not migrate the {args.provider} token: {exc}") from exc
    print(f"Moved the legacy {args.provider} OAuth token into the local profile store for {profile_context(args.owner)['display_name']!r}.")


def command_set_record_location(args: argparse.Namespace) -> None:
    """Add or remove a shared physical-bin location without changing ownership."""
    location = args.location.strip()
    if not location:
        raise SystemExit("A non-empty --location is required.")
    catalog = load_catalog()
    record = next((item for item in catalog.get("records", []) if item.get("id") == args.record_id), None)
    if not record:
        raise SystemExit(f"No catalogue record has ID {args.record_id!r}.")
    if record.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"Record {args.record_id} belongs to {record.get('owner', 'another owner')}, not {args.owner}.")
    locations = [str(value) for value in record.get("crate_locations", []) if str(value).strip()]
    if args.remove:
        locations = [value for value in locations if value.casefold() != location.casefold()]
    elif not any(value.casefold() == location.casefold() for value in locations):
        locations.append(location)
    record["crate_locations"] = locations
    save_catalog(catalog)
    action = "Removed" if args.remove else "Added"
    print(f"{action} location {location!r} for {record['artist']} — {record['title']}; owner remains {record['owner']}.")


def command_set_record_collective(args: argparse.Namespace) -> None:
    """Share or unshare one owned physical copy with a configured collective."""
    collective = collective_context(args.collective)
    owner = profile_context(args.owner)
    if owner["id"] not in collective["members"]:
        raise SystemExit(f"Profile {owner['display_name']!r} is not a member of collective {collective['display_name']!r}.")
    catalog = load_catalog()
    record = next((item for item in catalog.get("records", []) if item.get("id") == args.record_id), None)
    if not record:
        raise SystemExit(f"No catalogue record has ID {args.record_id!r}.")
    if record.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"Record {args.record_id} belongs to {record.get('owner', 'another profile')}, not {args.owner}.")
    collective_ids = record_collective_ids(record)
    if args.remove:
        collective_ids = [value for value in collective_ids if value != collective["id"]]
    elif collective["id"] not in collective_ids:
        collective_ids.append(collective["id"])
    record["collective_ids"] = collective_ids
    save_catalog(catalog)
    action = "Removed" if args.remove else "Added"
    print(f"{action} {record['artist']} — {record['title']} {'from' if args.remove else 'to'} collective {collective['display_name']!r}; owner remains {record['owner']}.")


def command_export_person_bundle(args: argparse.Namespace) -> None:
    """Export one profile's shareable crate state without credentials or raw photos."""
    context = person_context(args.owner)
    private_record_fields = {"collection_notes", "quick_access_sources", "collective_ids"}
    records = [
        {key: value for key, value in record.items() if key not in private_record_fields}
        for record in load_catalog().get("records", [])
        if record.get("owner", "").casefold() == args.owner.casefold()
    ]
    quick_crate = load_json(person_quick_crate_path(args.owner), {"records": []})
    payload = {
        "schema_version": 2,
        "generated_at": utc_now(),
        "profile": {"id": context["id"], "display_name": args.owner, "discogs_username": context["discogs_username"]},
        "records": records,
        "quick_crate": {
            "generated_at": quick_crate.get("generated_at"),
            "records": quick_crate.get("records", []),
        },
        "notes": [
            "This bundle contains catalogue and reviewed quick-crate metadata only.",
            "It omits collection notes, raw-photo paths, tokens, OAuth credentials, review-server state, and purchase history.",
        ],
    }
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(records)} catalogue records and {len(payload['quick_crate']['records'])} quick-crate entries to {output}.")


def command_import_person_bundle(args: argparse.Namespace) -> None:
    """Merge a collaborator's credential-free bundle into this shared local catalogue."""
    source = Path(args.input).expanduser()
    bundle = load_json(source, {})
    profile = bundle.get("profile") if isinstance(bundle.get("profile"), dict) else bundle.get("person", {})
    bundle_owner = str(profile.get("display_name") or "").strip()
    if not bundle_owner:
        raise SystemExit("The bundle has no profile.display_name.")
    if bundle_owner.casefold() != args.owner.casefold():
        raise SystemExit(f"Bundle belongs to {bundle_owner}; run this command with --owner {bundle_owner!r}.")
    records = bundle.get("records", [])
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise SystemExit("The bundle records field must be an array of record objects.")
    for record in records:
        if str(record.get("owner", "")).casefold() != args.owner.casefold():
            raise SystemExit("Every imported record must belong to the bundle owner.")
        record["owner_id"] = person_context(args.owner)["id"]
    catalog = load_catalog()
    added, updated = merge_records(catalog, records)
    save_catalog(catalog)
    quick_records = bundle.get("quick_crate", {}).get("records", [])
    if not isinstance(quick_records, list) or not all(isinstance(record, dict) for record in quick_records):
        raise SystemExit("The bundle quick_crate.records field must be an array.")
    quick_path = person_quick_crate_path(args.owner)
    if quick_path.exists() and not args.replace_quick_crate:
        raise SystemExit(f"{quick_path} already exists. Re-run with --replace-quick-crate after checking it.")
    for record in quick_records:
        if str(record.get("owner", "")).casefold() != args.owner.casefold():
            raise SystemExit("Every quick-crate record must belong to the bundle owner.")
    write_json(quick_path, {
        "schema_version": 2,
        "generated_at": bundle.get("generated_at", utc_now()),
        "owner": args.owner,
        "records": quick_records,
    })
    total = refresh_aggregate_quick_crate()
    print(f"Imported {len(records)} {args.owner} records ({added} added, {updated} updated), {len(quick_records)} quick-crate entries; shared export now has {total} records.")


def read_token(token_file: Optional[str], owner: Optional[str] = None) -> Optional[str]:
    if token_file:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit(f"Could not read token file: {exc}")
        if not token:
            raise SystemExit("The token file is empty.")
        return token
    if token := os.getenv("DISCOGS_TOKEN"):
        return token
    token_paths: List[Path] = []
    if owner:
        person_id = person_context(owner)["id"]
        token_paths.extend([
            CONFIG_TOKEN_PATH.with_name(f"discogs-token-{person_id}"),
            LEGACY_CONFIG_TOKEN_PATH.with_name(f"discogs-token-{person_id}"),
        ])
    token_paths.extend([CONFIG_TOKEN_PATH, LEGACY_CONFIG_TOKEN_PATH])
    for local_path in token_paths:
        if local_path.exists():
            token = local_path.read_text(encoding="utf-8").strip()
            if token:
                return token
    if sys.platform == "darwin":
        services = [KEYCHAIN_SERVICE, LEGACY_KEYCHAIN_SERVICE]
        if owner:
            person_id = person_context(owner)["id"]
            services = [
                f"{KEYCHAIN_SERVICE}.{person_id}",
                f"{LEGACY_KEYCHAIN_SERVICE}.{person_id}",
                *services,
            ]
        for service in services:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-w"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    return None


def discogs_request(
    path: str,
    token: Optional[str] = None,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Discogs token={token}"
    data = None
    if payload is not None:
        data = urlencode(payload).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(f"{API_ROOT}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"Discogs API returned HTTP {exc.code}: {body}")
    except URLError as exc:
        raise SystemExit(f"Could not reach Discogs: {exc.reason}")


def read_getsongbpm_key(api_key_file: Optional[str] = None) -> Optional[str]:
    """Read the optional GetSongBPM credential without printing or committing it."""
    if api_key_file:
        try:
            key = Path(api_key_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit(f"Could not read GetSongBPM API-key file: {exc}")
        if not key:
            raise SystemExit("The GetSongBPM API-key file is empty.")
        return key
    if key := os.getenv("GETSONGBPM_API_KEY"):
        return key.strip()
    for config_path in (GETSONGBPM_CONFIG_PATH, LEGACY_GETSONGBPM_CONFIG_PATH):
        if config_path.exists():
            key = config_path.read_text(encoding="utf-8").strip()
            if key:
                return key
    if sys.platform == "darwin":
        for service in (GETSONGBPM_KEYCHAIN_SERVICE, LEGACY_GETSONGBPM_KEYCHAIN_SERVICE):
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-w"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    return None


def read_opencode_go_key(api_key_file: Optional[str] = None) -> Optional[str]:
    """Read an OpenCode Go credential without printing or committing it.

    OpenCode stores credentials from `/connect`/`opencode auth login` in
    ``~/.local/share/opencode/auth.json``.  The CLI also accepts an explicit
    file and a conventional environment variable so it can be used outside
    the OpenCode installation or in CI.
    """
    if api_key_file:
        try:
            key = Path(api_key_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit(f"Could not read OpenCode Go API-key file: {exc}")
        if not key:
            raise SystemExit("The OpenCode Go API-key file is empty.")
        return key
    if key := os.getenv("OPENCODE_GO_API_KEY"):
        return key.strip()
    for config_path in (OPENCODE_GO_CONFIG_PATH, LEGACY_OPENCODE_GO_CONFIG_PATH):
        if config_path.exists():
            key = config_path.read_text(encoding="utf-8").strip()
            if key:
                return key
    if OPENCODE_AUTH_PATH.exists():
        try:
            payload = json.loads(OPENCODE_AUTH_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        provider = payload.get("opencode-go", {}) if isinstance(payload, dict) else {}
        if isinstance(provider, dict) and provider.get("type") == "api":
            key = str(provider.get("key") or "").strip()
            if key:
                return key
    return None


def getsongbpm_request(path: str, api_key: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    query = dict(parameters)
    query["api_key"] = api_key
    request = Request(
        f"{GETSONGBPM_API_ROOT}{path}?{urlencode(query)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"GetSongBPM returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach GetSongBPM: {exc.reason}") from exc


def load_catalog() -> Dict[str, Any]:
    ensure_data_dir()
    if not CATALOG_PATH.exists():
        return {"schema_version": 1, "updated_at": None, "records": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def save_catalog(catalog: Dict[str, Any]) -> None:
    ensure_data_dir()
    catalog["updated_at"] = utc_now()
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_data_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalise_match_text(value: Optional[str]) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return "".join(char for char in value.casefold() if char.isalnum())


def similarity(left: Optional[str], right: Optional[str]) -> float:
    left_normalised = normalise_match_text(left)
    right_normalised = normalise_match_text(right)
    if not left_normalised or not right_normalised:
        return 0.0
    if left_normalised == right_normalised:
        return 1.0
    return difflib.SequenceMatcher(None, left_normalised, right_normalised).ratio()


def record_suggestions(candidate: Dict[str, Any], records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    suggestions = []
    for record in records:
        direct = 0.65 * similarity(candidate.get("title"), record.get("title")) + 0.35 * similarity(candidate.get("artist"), record.get("artist"))
        swapped = 0.65 * similarity(candidate.get("title"), record.get("artist")) + 0.35 * similarity(candidate.get("artist"), record.get("title"))
        score = max(direct, swapped)
        if score >= 0.28:
            suggestions.append({
                "record_id": record["id"],
                "score": round(score, 3),
                "artist": record.get("artist", ""),
                "title": record.get("title", ""),
                "label": record.get("label", ""),
                "year": record.get("year", ""),
                "discogs_release_id": record.get("discogs_release_id"),
                "discogs_url": record.get("discogs_url", ""),
            })
    return sorted(suggestions, key=lambda item: item["score"], reverse=True)[:3]


def build_review(owner: str) -> Dict[str, Any]:
    photo_candidates_path = person_workspace_path(owner, "photo-candidates.json")
    review_path = person_workspace_path(owner, "review.json")
    if not photo_candidates_path.exists():
        raise SystemExit("Run analyse-photos before building a review.")
    candidates = json.loads(photo_candidates_path.read_text(encoding="utf-8"))
    catalog = load_catalog()
    records = [record for record in catalog["records"] if record.get("owner", "").casefold() == owner.casefold()]
    previous = {}
    if review_path.exists():
        previous = {item["id"]: item for item in json.loads(review_path.read_text(encoding="utf-8")).get("items", [])}
    items = []
    for photo in candidates.get("photos", []):
        for candidate in photo.get("records", []):
            item_id = f"{photo.get('intake_id') or Path(photo['path']).name}#{candidate.get('position')}"
            old = previous.get(item_id, {})
            old_manual = old.get("manual_identification")
            # A high-confidence phone intake already has a useful working
            # identification. Prefill it for review, but keep it provisional
            # until the person explicitly saves or confirms it.
            if not old_manual and photo.get("intake_id") and str(candidate.get("confidence", "")).casefold() in {"high", "very high"}:
                old_manual = {
                    "artist": str(candidate.get("artist") or "").strip(),
                    "title": str(candidate.get("title") or "").strip(),
                }
            items.append({
                "id": item_id,
                "photo_path": photo["path"],
                "intake_id": photo.get("intake_id", ""),
                "intake_views": photo.get("views", {}),
                "position": candidate.get("position"),
                "observed": candidate,
                "suggestions": record_suggestions(candidate, records),
                "status": old.get("status", "unreviewed"),
                "matched_record_id": old.get("matched_record_id"),
                "manual_identification": old_manual,
                "discogs_selection": old.get("discogs_selection"),
                "note": old.get("note", ""),
            })
    review = {"schema_version": 1, "generated_at": utc_now(), "owner": owner, "items": items}
    ensure_data_dir()
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return review


def command_apply_review(args: argparse.Namespace) -> None:
    """Synchronise confirmed photo-review matches into local quick-access markers."""
    review = load_review(args.owner)
    if review.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"review.json belongs to {review.get('owner', 'an unknown owner')}; use that owner or rebuild the review.")

    catalog = load_catalog()
    records = [record for record in catalog["records"] if record.get("owner", "").casefold() == args.owner.casefold()]
    records_by_id = {record["id"]: record for record in records}
    sources_by_record: Dict[str, List[Dict[str, Any]]] = {}
    for item in review.get("items", []):
        if item.get("status") != "confirmed":
            continue
        record_id = item.get("matched_record_id")
        if record_id not in records_by_id:
            raise SystemExit(f"Confirmed review item {item.get('id')} has no matching {args.owner} catalogue copy.")
        sources_by_record.setdefault(record_id, []).append({
            "kind": "photo_review",
            "review_owner": args.owner,
            "candidate_id": item["id"],
            "photo_path": item["photo_path"],
            "grid_position": item.get("position"),
            "review_note": item.get("note", ""),
        })

    changed = 0
    for record in records:
        existing_sources = record.get("quick_access_sources", [])
        if not isinstance(existing_sources, list):
            existing_sources = []
        previous_review_sources = [
            source for source in existing_sources
            if source.get("kind") == "photo_review" and source.get("review_owner", "").casefold() == args.owner.casefold()
        ]
        retained_sources = [source for source in existing_sources if source not in previous_review_sources]
        new_sources = retained_sources + sources_by_record.get(record["id"], [])
        before = (record.get("quick_access"), existing_sources)
        if new_sources:
            record["quick_access"] = True
            record["quick_access_sources"] = new_sources
        elif previous_review_sources:
            record["quick_access"] = False
            record["quick_access_sources"] = []
        after = (record.get("quick_access"), record.get("quick_access_sources", []))
        if before != after:
            changed += 1

    if changed:
        save_catalog(catalog)
    confirmed_items = sum(len(sources) for sources in sources_by_record.values())
    print(f"Applied {confirmed_items} confirmed photo matches to {len(sources_by_record)} quick-access records ({changed} catalogue records changed).")


def command_prepare_additions(args: argparse.Namespace) -> None:
    """Create a local, editable queue of human-selected Discogs releases."""
    review = load_review(args.owner)
    if review.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"review.json belongs to {review.get('owner', 'an unknown owner')}; use that owner or rebuild the review.")
    additions = []
    for item in review.get("items", []):
        selection = item.get("discogs_selection")
        if item.get("status") != "identified_not_in_catalog" or not isinstance(selection, dict):
            continue
        release_id = selection.get("release_id")
        if not str(release_id).isdigit():
            continue
        additions.append({
            "owner": args.owner,
            "owner_id": person_context(args.owner)["id"],
            "release_id": int(release_id),
            "artist": selection.get("artist", ""),
            "title": selection.get("title", ""),
            "label": selection.get("label", ""),
            "catalog_number": selection.get("catalog_number", ""),
            "format": selection.get("format", ""),
            "review_candidate_id": item.get("id"),
        })
    output = Path(args.output).expanduser() if args.output else person_workspace_path(args.owner, "discogs-additions.local.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(additions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(additions)} selected releases at {output}. Inspect or edit it before using add-to-discogs.")


def quick_crate_entry(item: Dict[str, Any], owner: str, records_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Flatten a reviewed photo candidate into a portable DJ-list row."""
    record: Dict[str, Any] = {}
    identity_source = "observed_photo"
    selection = item.get("discogs_selection") or {}
    if item.get("status") == "confirmed":
        record = records_by_id.get(item.get("matched_record_id"), {})
        identity_source = "confirmed_catalog"
    elif item.get("manual_identification"):
        record = item["manual_identification"]
        identity_source = "manual_identification"
    elif selection:
        record = selection
        identity_source = "discogs_selected"
    else:
        record = item.get("observed", {})
    observed = item.get("observed", {})
    return {
        "review_candidate_id": item["id"],
        "owner": owner,
        "artist": record.get("artist", "") or "",
        "title": record.get("title", "") or "",
        "identity_source": identity_source,
        "review_status": item.get("status", ""),
        "crate_locations": record.get("crate_locations", []) or [],
        "label": record.get("label", "") or "",
        "catalog_number": record.get("catalog_number", "") or "",
        "year": record.get("year", "") or "",
        "format": record.get("format", "") or "",
        "discogs_release_id": record.get("discogs_release_id") or record.get("release_id") or "",
        "discogs_url": record.get("discogs_url", "") or "",
        "photo_file": Path(item["photo_path"]).name,
        "grid_position": item.get("position", ""),
        "visible_text": observed.get("visible_text", "") or "",
        "photo_confidence": observed.get("confidence", "") or "",
        "review_note": item.get("note", "") or "",
    }


def command_export_quick_crate(args: argparse.Namespace) -> None:
    """Export every reviewed photo position as a compact shareable DJ list."""
    review = load_review(args.owner)
    if review.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"review.json belongs to {review.get('owner', 'an unknown owner')}; use that owner or rebuild the review.")
    records_by_id = {
        record["id"]: record
        for record in load_catalog().get("records", [])
        if record.get("owner", "").casefold() == args.owner.casefold()
    }
    entries = [quick_crate_entry(item, args.owner, records_by_id) for item in review.get("items", [])]
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else QUICK_CRATES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{person_context(args.owner)['id']}.json"
    csv_path = output_dir / f"{person_context(args.owner)['id']}.csv"
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "generated_at": utc_now(),
        "owner": args.owner,
        "records": entries,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(entries[0].keys()) if entries else ["owner", "artist", "title"])
        writer.writeheader()
        writer.writerows(entries)
    # Keep a combined browser export for the shared crate view. Individual files
    # remain authoritative so one person's export cannot overwrite another's.
    refresh_aggregate_quick_crate()
    sources = {}
    for entry in entries:
        sources[entry["identity_source"]] = sources.get(entry["identity_source"], 0) + 1
    print(f"Exported {len(entries)} quick-crate records to {json_path} and {csv_path}: {sources}")


def command_build_review(args: argparse.Namespace) -> None:
    review = build_review(args.owner)
    suggested = sum(1 for item in review["items"] if item["suggestions"])
    print(f"Built {len(review['items'])} review items: {suggested} have existing-collection suggestions.")


def load_review(owner: str) -> Dict[str, Any]:
    review_path = person_workspace_path(owner, "review.json")
    if not review_path.exists():
        raise FileNotFoundError("Run build-review first.")
    return json.loads(review_path.read_text(encoding="utf-8"))


def write_json_response(handler: http.server.BaseHTTPRequestHandler, payload: Dict[str, Any], status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(data)


def require_loopback_bind(host: str, command: str) -> None:
    """Keep full-data review services on the serving computer only."""
    if str(host).casefold() == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise SystemExit(f"{command} only supports a loopback bind address. Use serve-mobile for the token-protected phone companion.")


def preview_photo(photo: Path) -> bytes:
    if photo.suffix.lower() not in {".heic", ".heif"}:
        return photo.read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            ["qlmanage", "-t", "-s", "1600", "-o", directory, str(photo)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        previews = list(Path(directory).glob("*.png"))
        if result.returncode or not previews:
            raise FileNotFoundError(photo)
        return previews[0].read_bytes()


def preview_media_type(photo: Path) -> str:
    """Return the media type matching the bytes served by preview_photo."""
    if photo.suffix.lower() in {".heic", ".heif"}:
        return "image/png"
    return mimetypes.guess_type(photo.name)[0] or "application/octet-stream"


def review_search_query(item: Dict[str, Any]) -> tuple[str, str]:
    identification = item.get("manual_identification") or {}
    return (
        str(identification.get("artist") or item.get("observed", {}).get("artist") or "").strip(),
        str(identification.get("title") or item.get("observed", {}).get("title") or "").strip(),
    )


def review_search_identifiers(item: Dict[str, Any]) -> tuple[str, str]:
    identification = item.get("manual_identification") or {}
    observed = item.get("observed", {})
    return (
        str(identification.get("catalog_number") or observed.get("catalog_number") or "").strip(),
        str(identification.get("barcode") or observed.get("barcode") or "").strip(),
    )


def normalise_discogs_search_result(result: Dict[str, Any]) -> Dict[str, Any]:
    release_id = result.get("id")
    formats = result.get("format", [])
    labels = result.get("label", [])
    raw_title = str(result.get("title") or "")
    artist, separator, title = raw_title.partition(" - ")
    return {
        "release_id": int(release_id) if str(release_id).isdigit() else None,
        "artist": artist.strip() if separator else "",
        "title": title.strip() if separator else raw_title,
        "label": ", ".join(labels) if isinstance(labels, list) else str(labels or ""),
        "catalog_number": result.get("catno", ""),
        "year": result.get("year", ""),
        "country": result.get("country", ""),
        "format": ", ".join(formats) if isinstance(formats, list) else str(formats or ""),
        "cover_image": result.get("cover_image", ""),
        "discogs_url": absolute_discogs_url(result.get("uri"), release_id),
    }


def enrich_discogs_search_result(result: Dict[str, Any], token: Optional[str]) -> Dict[str, Any]:
    """Add release-level fields that Discogs' database search omits.

    Search responses are useful for finding candidates, but they normally do not
    include identifiers such as barcodes. Fetching the release resource gives the
    picker the same authoritative country/label/catalogue/format data that a
    user sees on the release page. If one detail request fails, keep the search
    result so a transient rate limit does not make the whole picker unusable.
    """
    summary = normalise_discogs_search_result(result)
    release_id = summary.get("release_id")
    if not release_id:
        return summary
    try:
        detail = selected_discogs_release(int(release_id), token)
    except (SystemExit, ValueError, KeyError, TypeError, IndexError):
        return summary
    # Keep a stable shape and let authoritative release fields replace the
    # abbreviated search fields. The search title remains a fallback when a
    # release has no artist metadata.
    detail["artist"] = detail.get("artist") or summary.get("artist", "")
    detail["title"] = detail.get("title") or summary.get("title", "")
    detail["discogs_url"] = detail.get("discogs_url") or summary.get("discogs_url", "")
    return detail


def enrich_discogs_search_results(results: List[Dict[str, Any]], token: Optional[str]) -> List[Dict[str, Any]]:
    """Enrich the first candidates concurrently while preserving search order."""
    if not results:
        return []

    def enrich(index_and_result: tuple[int, Dict[str, Any]]) -> Dict[str, Any]:
        index, result = index_and_result
        return enrich_discogs_search_result(result, token) if index < 8 else normalise_discogs_search_result(result)

    with ThreadPoolExecutor(max_workers=min(4, len(results))) as executor:
        return list(executor.map(enrich, enumerate(results)))


def absolute_discogs_url(uri: Optional[str], release_id: Optional[int] = None) -> str:
    """Convert Discogs API-relative URIs into links that work in a browser."""
    value = str(uri or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value:
        return f"https://www.discogs.com/{value.lstrip('/')}"
    return f"https://www.discogs.com/release/{release_id}" if release_id else ""


def discogs_release_id_from_value(value: Any) -> int:
    """Extract a release ID from a Discogs release URL or a numeric ID."""
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    parsed = urlparse(text)
    host = parsed.netloc.casefold().split(":", 1)[0]
    if host not in {"discogs.com", "www.discogs.com", "api.discogs.com"} and not host.endswith(".discogs.com"):
        raise ValueError("Paste a Discogs release URL, such as https://www.discogs.com/release/123456")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    for index, part in enumerate(parts[:-1]):
        if part.casefold() in {"release", "releases"}:
            candidate = parts[index + 1].split("-", 1)[0]
            if candidate.isdigit():
                return int(candidate)
    raise ValueError("That Discogs URL does not contain a numeric release ID.")


def selected_discogs_release(release_id: int, token: Optional[str]) -> Dict[str, Any]:
    release = discogs_request(f"/releases/{release_id}", token)
    artists = ", ".join(artist.get("name", "") for artist in release.get("artists", [])).strip()
    labels = release.get("labels", [])
    label = labels[0] if labels else {}
    formats = release.get("formats", [])
    images = release.get("images") or [{}]
    format_parts = []
    for item in formats:
        format_parts.extend([item.get("name", ""), *item.get("descriptions", [])])
    barcode_values = [
        str(identifier.get("value") or "").strip()
        for identifier in release.get("identifiers", [])
        if str(identifier.get("type") or "").casefold() == "barcode" and identifier.get("value")
    ]
    return {
        "release_id": release_id,
        "artist": artists,
        "title": release.get("title", ""),
        "label": label.get("name", ""),
        "catalog_number": label.get("catno", ""),
        "barcode": barcode_values[0] if barcode_values else "",
        "year": release.get("year", ""),
        "country": release.get("country", ""),
        "format": ", ".join(part for part in format_parts if part),
        "cover_image": images[0].get("uri", ""),
        "discogs_url": absolute_discogs_url(release.get("uri"), release_id),
        "selected_at": utc_now(),
    }


def make_review_handler(owner: str, token: Optional[str] = None) -> type[http.server.SimpleHTTPRequestHandler]:
    review_path = person_workspace_path(owner, "review.json")

    class ReviewHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            print(f"[review] {format % args}")

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/review":
                try:
                    write_json_response(self, load_review(owner))
                except FileNotFoundError as exc:
                    write_json_response(self, {"error": str(exc)}, 404)
                return
            if path == "/api/catalog":
                try:
                    review = load_review(owner)
                    records = [
                        record for record in load_catalog().get("records", [])
                        if record.get("owner", "").casefold() == review["owner"].casefold()
                    ]
                    write_json_response(self, {"records": records})
                except FileNotFoundError as exc:
                    write_json_response(self, {"error": str(exc)}, 404)
                return
            if path == "/api/discogs-search":
                query_params = parse_qs(urlparse(self.path).query, keep_blank_values=True)
                item_id = query_params.get("id", [""])[0]

                def query_override(name: str, fallback: str) -> str:
                    if name in query_params:
                        return query_params[name][0].strip()
                    return fallback

                try:
                    item = next(item for item in load_review(owner)["items"] if item["id"] == item_id)
                    default_artist, default_title = review_search_query(item)
                    artist = query_override("artist", default_artist)
                    title = query_override("title", default_title)
                    default_catalog_number, default_barcode = review_search_identifiers(item)
                    catalog_number = query_override("catalog_number", default_catalog_number)
                    barcode = query_override("barcode", default_barcode)
                    if not any((artist, title, catalog_number, barcode)):
                        raise ValueError("Enter an artist, title, catalogue number, or barcode before searching Discogs")
                    base_parameters = {"type": "release", "per_page": 12}
                    if artist:
                        base_parameters["artist"] = artist
                    if title:
                        base_parameters["release_title"] = title
                    attempts = []
                    if barcode:
                        # Keep the name context alongside an uncertain barcode.
                        # Discogs may interpret a misread catalogue number as a
                        # numeric search term and return unrelated CDs or
                        # compilations when the identifier is sent alone.
                        attempts.append({**base_parameters, "barcode": barcode})
                    if catalog_number:
                        attempts.append({**base_parameters, "catno": catalog_number})
                    attempts.append(base_parameters)
                    if artist or title:
                        attempts.append({"type": "release", "per_page": 12, "q": " ".join(part for part in (artist, title) if part)})
                    # Only fall back to identifier-only searches after the
                    # artist/title routes. This preserves useful results when
                    # the photographed identifier is actually a catalogue
                    # number or is missing separators.
                    if barcode:
                        attempts.append({"type": "release", "per_page": 12, "barcode": barcode})
                    if catalog_number:
                        attempts.append({"type": "release", "per_page": 12, "catno": catalog_number})
                    response = {"results": []}
                    search_basis = "artist/title"
                    for parameters in attempts:
                        response = discogs_request(f"/database/search?{urlencode(parameters)}", token)
                        if response.get("results"):
                            search_basis = "barcode" if "barcode" in parameters else "catalogue number" if "catno" in parameters else "artist/title"
                            break
                    raw_results = [result for result in response.get("results", []) if result.get("id")]
                    # Eight detail requests keeps the picker responsive while
                    # supplying barcode/label data for the candidates users are
                    # most likely to compare. Remaining candidates still retain
                    # their search-level metadata.
                    results = enrich_discogs_search_results(raw_results, token)
                    results = [result for result in results if result["release_id"]]
                    write_json_response(self, {"query": {"artist": artist, "title": title, "catalog_number": catalog_number, "barcode": barcode, "basis": search_basis}, "results": results})
                except (FileNotFoundError, StopIteration, ValueError) as exc:
                    write_json_response(self, {"error": str(exc)}, 400)
                except SystemExit as exc:
                    write_json_response(self, {"error": str(exc)}, 502)
                return
            if path.startswith("/api/photo/"):
                item_id = unquote(path.removeprefix("/api/photo/"))
                try:
                    item = next(item for item in load_review(owner)["items"] if item["id"] == item_id)
                    image = preview_photo(Path(item["photo_path"]))
                except (FileNotFoundError, StopIteration):
                    self.send_error(404, "Photo not found")
                    return
                self.send_response(200)
                self.send_header("Content-Type", preview_media_type(Path(item["photo_path"])))
                self.send_header("Content-Length", str(len(image)))
                self.end_headers()
                self.wfile.write(image)
                return
            if path.startswith("/api/photo-view/"):
                parts = path.removeprefix("/api/photo-view/").split("/", 1)
                if len(parts) != 2:
                    self.send_error(404, "Photo view not found")
                    return
                item_id, role = unquote(parts[0]), unquote(parts[1])
                try:
                    item = next(item for item in load_review(owner)["items"] if item["id"] == item_id)
                    photo_path = item.get("intake_views", {}).get(role)
                    if not photo_path:
                        raise FileNotFoundError
                    image = preview_photo(Path(photo_path))
                except (FileNotFoundError, StopIteration):
                    self.send_error(404, "Photo view not found")
                    return
                self.send_response(200)
                self.send_header("Content-Type", preview_media_type(Path(photo_path)))
                self.send_header("Content-Length", str(len(image)))
                self.end_headers()
                self.wfile.write(image)
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in {"/api/decision", "/api/discogs-selection"}:
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                decision = json.loads(self.rfile.read(length).decode("utf-8"))
                if path == "/api/discogs-selection":
                    review = load_review(owner)
                    item = next(item for item in review["items"] if item["id"] == decision["id"])
                    if decision.get("clear"):
                        item["discogs_selection"] = None
                        message = "Discogs selection cleared locally."
                    else:
                        if item.get("status") not in {"unreviewed", "identified_not_in_catalog"}:
                            raise ValueError("Reopen this review item before choosing a Discogs pressing")
                        release_value = decision.get("release_url") or decision.get("release_id")
                        release_id = discogs_release_id_from_value(release_value)
                        if item.get("status") == "unreviewed":
                            # Choosing a pressing from an observed high-confidence
                            # name is itself an explicit identification decision.
                            observed = item.get("observed", {})
                            manual = item.get("manual_identification") or {
                                "artist": str(observed.get("artist") or "").strip(),
                                "title": str(observed.get("title") or "").strip(),
                            }
                            if not any(manual.values()):
                                raise ValueError("Save an artist or title before choosing a Discogs pressing")
                            item["manual_identification"] = manual
                            item["status"] = "identified_not_in_catalog"
                        item["discogs_selection"] = selected_discogs_release(release_id, token)
                        message = "Discogs release selected locally; it has not been added to Discogs."
                    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    write_json_response(self, {"ok": True, "item": item, "message": message})
                    return
                if decision.get("status") not in {"confirmed", "identified_not_in_catalog", "needs_better_photo", "unmatched", "unreviewed"}:
                    raise ValueError("Invalid review status")
                review = load_review(owner)
                item = next(item for item in review["items"] if item["id"] == decision["id"])
                matched_record_id = decision.get("matched_record_id")
                if decision["status"] == "confirmed":
                    record_ids = {
                        record["id"]
                        for record in load_catalog().get("records", [])
                        if record.get("owner") == review["owner"]
                    }
                    if matched_record_id not in record_ids:
                        raise ValueError("A confirmed candidate needs a record from this owner's catalogue")
                else:
                    matched_record_id = None
                manual_identification = None
                if decision["status"] == "identified_not_in_catalog":
                    supplied = decision.get("manual_identification", {})
                    if not isinstance(supplied, dict):
                        raise ValueError("Manual identification must be an object")
                    manual_identification = {
                        "artist": str(supplied.get("artist", "")).strip(),
                        "title": str(supplied.get("title", "")).strip(),
                        "catalog_number": str(supplied.get("catalog_number", "")).strip(),
                        "barcode": str(supplied.get("barcode", "")).strip(),
                    }
                    if not any(manual_identification.values()):
                        raise ValueError("Enter an artist or title before saving an identification")
                elif decision["status"] == "unreviewed":
                    # Reopening a decision should leave the typed correction visible for editing.
                    manual_identification = item.get("manual_identification")
                item["status"] = decision["status"]
                item["matched_record_id"] = matched_record_id
                item["manual_identification"] = manual_identification
                if decision["status"] != "unreviewed":
                    item["discogs_selection"] = None
                item["note"] = str(decision.get("note", ""))
                review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                write_json_response(self, {"ok": True, "item": item})
            except (ValueError, KeyError, StopIteration, json.JSONDecodeError) as exc:
                write_json_response(self, {"error": str(exc)}, 400)
            except SystemExit as exc:
                write_json_response(self, {"error": str(exc)}, 502)

    return ReviewHandler


def command_serve_review(args: argparse.Namespace) -> None:
    require_loopback_bind(args.host, "serve-review")
    if not person_workspace_path(args.owner, "review.json").exists():
        build_review(args.owner)
    os.chdir(ROOT)
    server = http.server.ThreadingHTTPServer((args.host, args.port), make_review_handler(args.owner, read_token(args.token_file, args.owner)))
    print(f"Review at http://{args.host}:{args.port}/review.html")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReview server stopped.")


MOBILE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
MOBILE_UPLOAD_ROLES = {"evidence", "front", "back", "label", "barcode", "other"}
MOBILE_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def mobile_advertised_address() -> str:
    """Find a reachable physical LAN address, avoiding VPN/tunnel interfaces."""
    try:
        interface_output = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
        interface = ""
        candidates: List[tuple[str, str]] = []
        for line in interface_output.splitlines():
            match = re.match(r"^([A-Za-z0-9]+):", line)
            if match:
                interface = match.group(1)
            address_match = re.search(r"\binet (\d+\.\d+\.\d+\.\d+)\b", line)
            if address_match and interface not in {"lo0", "lo", "bridge0", "awdl0", "llw0", "gif0", "stf0"} and not interface.startswith(("utun", "anpi")):
                address = address_match.group(1)
                if not address.startswith("127."):
                    candidates.append((interface, address))
        for preferred in ("en0", "en1", "en2", "en3", "en4"):
            for interface, address in candidates:
                if interface == preferred:
                    return address
        if candidates:
            return candidates[0][1]
    except (OSError, subprocess.SubprocessError):
        pass
    # Non-macOS fallback: ask the routing table, which is better than only
    # exposing localhost when the platform has no ifconfig parser above.
    for target in (("8.8.8.8", 80), ("1.1.1.1", 80)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(target)
                address = probe.getsockname()[0]
                if address and not address.startswith("127."):
                    return address
        except OSError:
            continue
    try:
        address = socket.gethostbyname(socket.gethostname())
        if address:
            return address
    except OSError:
        pass
    return "127.0.0.1"


def mobile_intake_records(owner: str) -> List[Dict[str, Any]]:
    inbox = person_inbox_dir(owner)
    if not inbox.exists():
        return []
    records = []
    for metadata_path in sorted(inbox.glob("*/intake.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        metadata = load_json(metadata_path, {})
        if metadata:
            records.append(metadata)
    return records


def mobile_qr_svg(value: str) -> bytes:
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError as exc:
        raise RuntimeError("QR support is not installed; run python3 -m pip install -r requirements.txt") from exc
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
    code.add_data(value)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    return output.getvalue()


def make_mobile_handler(owner: str, advertised_base: str, session_token: str) -> type[http.server.SimpleHTTPRequestHandler]:
    owner_id = person_context(owner)["id"]
    static_files = {
        "/mobile.html": (ROOT / "mobile.html", "text/html; charset=utf-8"),
        "/connect.html": (ROOT / "connect.html", "text/html; charset=utf-8"),
        "/app.css": (ROOT / "app.css", "text/css; charset=utf-8"),
        "/app.js": (ROOT / "app.js", "application/javascript; charset=utf-8"),
    }

    def mobile_url() -> str:
        # Fragments are not sent in HTTP requests, browser history referrers, or server logs.
        return f"{advertised_base}/mobile.html#token={quote(session_token)}"

    class MobileHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            print(f"[mobile] {format % args}")

        def is_loopback_client(self) -> bool:
            try:
                return ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:
                return False

        def authorised(self) -> bool:
            provided = self.headers.get("X-Cue-Crate-Session", "")
            if secrets.compare_digest(provided, session_token):
                return True
            write_json_response(self, {"error": "This local mobile link has expired or is invalid."}, 401)
            return False

        def serve_static(self, path: str) -> None:
            source = static_files.get(path)
            if source is None:
                self.send_error(404)
                return
            if path == "/connect.html" and not self.is_loopback_client():
                self.send_error(403, "The connect screen is available only on the serving computer.")
                return
            file_path, content_type = source
            try:
                body = file_path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/mobile/session":
                if not self.authorised():
                    return
                write_json_response(self, {
                    "owner": owner,
                    "owner_id": owner_id,
                    "mobile_url": mobile_url(),
                    "qr_url": "/api/mobile/qr.svg",
                    "catalog_count": len([record for record in load_catalog().get("records", []) if record.get("owner", "").casefold() == owner.casefold()]),
                })
                return
            if path == "/api/mobile/qr.svg":
                if not self.authorised():
                    return
                try:
                    image = mobile_qr_svg(mobile_url())
                except RuntimeError as exc:
                    write_json_response(self, {"error": str(exc)}, 503)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(image)))
                self.end_headers()
                self.wfile.write(image)
                return
            if path == "/api/mobile/catalog":
                if not self.authorised():
                    return
                records = [
                    record for record in load_catalog().get("records", [])
                    if record.get("owner", "").casefold() == owner.casefold()
                ]
                write_json_response(self, {"owner": owner, "records": records})
                return
            if path == "/api/mobile/intake":
                if not self.authorised():
                    return
                write_json_response(self, {"owner": owner, "uploads": mobile_intake_records(owner)})
                return
            self.serve_static(path)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path != "/api/mobile/upload":
                self.send_error(404)
                return
            if not self.authorised():
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MOBILE_UPLOAD_MAX_BYTES:
                    raise ValueError(f"Photo must be between 1 byte and {MOBILE_UPLOAD_MAX_BYTES // (1024 * 1024)} MB.")
                content_type = self.headers.get("Content-Type", "")
                if not content_type.lower().startswith("multipart/form-data"):
                    raise ValueError("Upload must use multipart/form-data.")
                body = self.rfile.read(content_length)
                message = BytesParser(policy=email_default_policy).parsebytes(
                    f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii") + body
                )
                fields: Dict[str, str] = {}
                upload_bytes = b""
                original_name = ""
                for part in message.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    filename = part.get_filename()
                    payload = part.get_payload(decode=True) or b""
                    if filename:
                        original_name = Path(filename).name
                        upload_bytes = payload
                    elif name:
                        fields[name] = payload.decode("utf-8", errors="replace").strip()
                upload_id = fields.get("upload_id", "")
                role = fields.get("role", "")
                if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", upload_id):
                    raise ValueError("Upload ID is invalid.")
                if role not in MOBILE_UPLOAD_ROLES:
                    raise ValueError("Photo role must be evidence, front, back, label, barcode, or other.")
                if not upload_bytes:
                    raise ValueError("No photo file was received.")
                suffix = Path(original_name).suffix.lower()
                if suffix not in MOBILE_UPLOAD_EXTENSIONS:
                    guessed = mimetypes.guess_extension(self.headers.get("Content-Type", "").split(";", 1)[0]) or ".jpg"
                    suffix = guessed if guessed in MOBILE_UPLOAD_EXTENSIONS else ".jpg"
                bundle_dir = person_inbox_dir(owner) / upload_id
                bundle_dir.mkdir(parents=True, exist_ok=True)
                for existing in bundle_dir.glob(f"{role}.*"):
                    existing.unlink()
                destination = bundle_dir / f"{role}{suffix}"
                destination.write_bytes(upload_bytes)
                metadata_path = bundle_dir / "intake.json"
                metadata = load_json(metadata_path, {
                    "schema_version": 1, "owner": owner, "owner_id": owner_id,
                    "upload_id": upload_id, "created_at": utc_now(), "files": {},
                })
                metadata["updated_at"] = utc_now()
                metadata.setdefault("files", {})[role] = {
                    "filename": destination.name,
                    "content_type": self.headers.get("Content-Type", "").split(";", 1)[0],
                    "bytes": len(upload_bytes),
                }
                write_json(metadata_path, metadata)
                write_json_response(self, {"ok": True, "upload": metadata})
            except (ValueError, OSError, UnicodeError) as exc:
                write_json_response(self, {"error": str(exc)}, 400)

    return MobileHandler


def command_serve_mobile(args: argparse.Namespace) -> None:
    ensure_data_dir()
    os.chdir(ROOT)
    address = args.advertise or mobile_advertised_address()
    base = f"http://{address}:{args.port}"
    token = secrets.token_urlsafe(24)
    server = http.server.ThreadingHTTPServer((args.host, args.port), make_mobile_handler(args.owner, base, token))
    print(f"Connect screen: http://127.0.0.1:{args.port}/connect.html#token={quote(token)}")
    print(f"Phone URL: {base}/mobile.html#token={quote(token)}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMobile server stopped.")


def youtube_record_key(record: Dict[str, Any]) -> str:
    return f"{normalise_match_text(str(record.get('artist', '')))}::{normalise_match_text(str(record.get('title', '')))}"


def youtube_query(record: Dict[str, Any]) -> str:
    parts = [str(record.get("artist", "")).strip(), str(record.get("title", "")).strip()]
    if record.get("year"):
        parts.append(str(record["year"]))
    return " ".join(part for part in parts if part)


def youtube_library_records(owner: str) -> List[Dict[str, Any]]:
    """Merge the photographed crate and Discogs catalogue into one listening list.

    A playlist is about music, not duplicate physical copies, so artist/title is the
    deliberate dedupe key. Pending purchases are omitted until they arrive.
    """
    merged: Dict[str, Dict[str, Any]] = {}

    def add(record: Dict[str, Any], source: str) -> None:
        artist, title = str(record.get("artist", "")).strip(), str(record.get("title", "")).strip()
        if not artist or not title:
            return
        key = youtube_record_key({"artist": artist, "title": title})
        source_record = {
            "kind": source,
            "record_id": record.get("id") or record.get("review_candidate_id", ""),
            "discogs_release_id": record.get("discogs_release_id") or "",
        }
        current = merged.get(key)
        if current is None:
            current = {
                "id": key, "artist": artist, "title": title, "year": record.get("year", ""),
                "label": record.get("label", ""), "catalog_number": record.get("catalog_number", ""),
                "format": record.get("format", ""), "discogs_release_id": record.get("discogs_release_id") or "",
                "discogs_url": record.get("discogs_url", ""), "tracklist": record.get("tracklist") or [], "sources": [],
            }
            merged[key] = current
        else:
            # Prefer a known Discogs release and fill any blanks without replacing
            # the user-reviewed photo identity with a different title spelling.
            for field in ("year", "label", "catalog_number", "format", "discogs_release_id", "discogs_url", "tracklist"):
                if not current.get(field) and record.get(field):
                    current[field] = record[field]
        if source_record not in current["sources"]:
            current["sources"].append(source_record)

    for record in load_json(person_quick_crate_path(owner), {"records": []}).get("records", []):
        add(record, "quick_crate")
    for record in load_catalog().get("records", []):
        if record.get("owner", "").casefold() == owner.casefold():
            add(record, "catalog")
    return sorted(merged.values(), key=lambda record: (normalise_match_text(record["artist"]), normalise_match_text(record["title"])))


def build_youtube_music_review(owner: str) -> Dict[str, Any]:
    review_path = person_youtube_review_path(owner)
    previous = load_json(review_path, {"owner": owner, "items": []})
    if previous.get("owner", "").casefold() not in {"", owner.casefold()}:
        raise SystemExit(f"youtube-music-review.json belongs to {previous.get('owner')}; use that owner or move it aside.")
    existing = {item.get("id"): item for item in previous.get("items", [])}
    items = []
    for record in youtube_library_records(owner):
        old = existing.get(record["id"], {})
        query = youtube_query(record)
        items.append({
            **record,
            "query": query,
            "youtube_search_url": "https://www.youtube.com/results?" + urlencode({"search_query": query}),
            "youtube_music_search_url": "https://music.youtube.com/search?" + urlencode({"q": query}),
            "selected_video_url": old.get("selected_video_url", ""),
            "selected_video_id": old.get("selected_video_id", ""),
            "match_status": old.get("match_status", "unmatched"),
            "youtube_music_verified": bool(old.get("youtube_music_verified", False)),
            "youtube_music_checked_at": old.get("youtube_music_checked_at", ""),
            "note": old.get("note", ""),
            "published_playlist_item_id": old.get("published_playlist_item_id", ""),
        })
    review = {
        "schema_version": 1, "generated_at": utc_now(), "owner": owner,
        "account_label": previous.get("account_label", ""),
        "playlist": previous.get("playlist", {}), "items": items,
        "notes": [
            "A YouTube Music check is a human approval: the public YouTube Data API does not expose a dependable in-YouTube-Music flag.",
            "Only items with an approved video ID and a checked YouTube Music verification box can be published.",
            "Pending Discogs purchases are intentionally excluded until they arrive.",
        ],
    }
    write_json(review_path, review)
    return review


def extract_youtube_video_id(value: str) -> str:
    value = value.strip()
    if len(value) == 11 and all(char.isalnum() or char in "-_" for char in value):
        return value
    parsed = urlparse(value)
    if parsed.netloc.endswith("youtu.be"):
        candidate = parsed.path.strip("/").split("/")[0]
    else:
        candidate = parse_qs(parsed.query).get("v", [""])[0]
        if not candidate and parsed.path.startswith(("/shorts/", "/embed/")):
            candidate = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else ""
    if len(candidate) == 11 and all(char.isalnum() or char in "-_" for char in candidate):
        return candidate
    raise ValueError("Paste a standard YouTube or YouTube Music video URL (or its 11-character video ID).")


def default_playlist(owner: str) -> Dict[str, Any]:
    """Return a non-secret draft playlist based on the existing YouTube review."""
    review = load_json(person_youtube_review_path(owner), {"items": [], "playlist": {}})
    youtube = review.get("playlist", {}) if isinstance(review, dict) else {}
    playlist_id = str(youtube.get("id") or "").strip()
    title = str(youtube.get("title") or f"{owner}'s Cue Crate").strip()
    destinations = ["youtube"] if playlist_id else []
    track_ids = [
        str(item.get("id")) for item in review.get("items", [])
        if item.get("id") and item.get("match_status") == "approved"
        and item.get("youtube_music_verified") and item.get("selected_video_id")
    ]
    return {
        "id": f"{person_context(owner)['id']}-cue-crate",
        "owner": owner,
        "name": title,
        "description": str(youtube.get("description") or f"Physical records from {owner}'s Cue Crate."),
        "visibility": str(youtube.get("privacy") or "unlisted"),
        "destinations": destinations,
        "source": "youtube-review",
        "track_ids": track_ids,
        "youtube": {
            "status": "published" if playlist_id else "ready",
            "playlist_id": playlist_id,
            "url": f"https://www.youtube.com/playlist?list={playlist_id}" if playlist_id else "",
        },
        "spotify": {"status": "not_connected", "playlist_id": "", "url": ""},
        "created_at": str(youtube.get("created_at") or ""),
        "updated_at": str(youtube.get("updated_at") or ""),
    }


def playlist_track_key(album_id: str, track: Dict[str, Any], index: int) -> str:
    """Build a stable local ID for one Discogs tracklist row."""
    position = normalise_match_text(str(track.get("position") or index + 1)) or str(index + 1)
    title = normalise_match_text(str(track.get("title") or "track")) or "track"
    return f"{album_id}::track::{position}::{title}"


def playlist_track_options(review: Dict[str, Any], owner: str) -> List[Dict[str, Any]]:
    """Return grouped album/track metadata for the manager's library picker."""
    library = {record.get("id"): record for record in youtube_library_records(owner)}
    options = []
    for item in review.get("items", []):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        album_id = str(item.get("id"))
        source = library.get(album_id, {})
        raw_tracklist = item.get("tracklist") or source.get("tracklist") or []
        tracks = []
        for index, raw_track in enumerate(raw_tracklist):
            if not isinstance(raw_track, dict):
                continue
            if raw_track.get("type") and raw_track.get("type") != "track":
                continue
            title = str(raw_track.get("title") or "").strip()
            if not title:
                continue
            tracks.append({
                "id": playlist_track_key(album_id, raw_track, index),
                "kind": "track", "album_id": album_id,
                "artist": raw_track.get("artist") or item.get("artist", ""),
                "title": title, "position": raw_track.get("position") or str(index + 1),
                "duration": raw_track.get("duration", ""),
            })
        options.append({
            "id": album_id, "kind": "album", "artist": item.get("artist", ""),
            "title": item.get("title", ""), "year": item.get("year", ""),
            "label": item.get("label", ""), "format": item.get("format", ""),
            "discogs_url": item.get("discogs_url", ""), "tracks": tracks,
            "match_status": item.get("match_status", "unmatched"),
            "selected_video_id": item.get("selected_video_id", ""),
            "youtube_music_verified": bool(item.get("youtube_music_verified")),
            "publish_ready": bool(item.get("selected_video_id"))
                and item.get("match_status") == "approved"
                and bool(item.get("youtube_music_verified")),
        })
    return options


def playlist_entries(playlist: Dict[str, Any], review: Dict[str, Any], owner: str) -> List[Dict[str, Any]]:
    """Return ordered album/track entries, migrating the first membership schema."""
    options = playlist_track_options(review, owner)
    albums = {option["id"]: option for option in options}
    tracks = {track["id"]: track for option in options for track in option["tracks"]}
    raw_entries = playlist.get("entries")
    if not isinstance(raw_entries, list):
        raw_ids = playlist.get("track_ids")
        if isinstance(raw_ids, list):
            raw_entries = [{"kind": "album", "id": value} for value in raw_ids]
        else:
            raw_entries = [
                {"kind": "album", "id": option["id"]} for option in options if option["publish_ready"]
            ]
    selected: List[Dict[str, Any]] = []
    seen = set()
    for raw in raw_entries:
        if isinstance(raw, str):
            raw = {"kind": "album", "id": raw}
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "album").strip().casefold()
        entry_id = str(raw.get("id") or "").strip()
        if kind == "album" and entry_id in albums:
            entry = {"kind": "album", "id": entry_id}
        elif kind == "track" and entry_id in tracks:
            entry = {"kind": "track", "id": entry_id, "album_id": tracks[entry_id]["album_id"]}
        else:
            continue
        dedupe_key = f"{entry['kind']}:{entry['id']}"
        if dedupe_key not in seen:
            selected.append(entry)
            seen.add(dedupe_key)
    playlist["entries"] = selected
    playlist["track_ids"] = [entry["id"] for entry in selected if entry["kind"] == "album"]
    return selected


def load_playlists(owner: str) -> Dict[str, Any]:
    """Load the owner-specific playlist manager state, migrating the old YouTube entry."""
    path = person_playlists_path(owner)
    if path.exists():
        payload = load_json(path, {})
        if isinstance(payload, dict) and isinstance(payload.get("playlists"), list):
            return payload
    return {"schema_version": 1, "owner": owner, "playlists": [default_playlist(owner)]}


def playlist_manager_payload(owner: str) -> Dict[str, Any]:
    playlists = load_playlists(owner)
    review = load_json(person_youtube_review_path(owner), {"items": [], "playlist": {}})
    items = review.get("items", []) if isinstance(review, dict) else []
    options = playlist_track_options(review, owner)
    approved = sum(1 for item in items if item.get("match_status") == "approved" and item.get("youtube_music_verified") and item.get("selected_video_id"))
    auto_selected = sum(1 for item in items if item.get("match_status") == "auto_selected" and item.get("selected_video_id"))
    for playlist in playlists.get("playlists", []):
        if not isinstance(playlist, dict):
            continue
        entries = playlist_entries(playlist, review, owner)
        selected = {entry["id"] for entry in entries if entry["kind"] == "album"}
        playlist["track_count"] = len(entries)
        playlist["album_count"] = len([entry for entry in entries if entry["kind"] == "album"])
        playlist["track_entry_count"] = len([entry for entry in entries if entry["kind"] == "track"])
        playlist["automatic_track_count"] = sum(
            1 for item in items if str(item.get("id")) in selected
            and item.get("match_status") == "auto_selected" and item.get("selected_video_id")
        )
    youtube_token_paths = profile_provider_token_paths(owner, "youtube")
    spotify_token_paths = profile_provider_token_paths(owner, "spotify")
    youtube_access = any(path.exists() for path in youtube_token_paths)
    spotify_access = bool(os.getenv("SPOTIFY_ACCESS_TOKEN", "").strip()) or any(path.exists() for path in spotify_token_paths)
    providers = {
        "youtube": {
            "label": "YouTube Music", "available": youtube_access,
            "detail": "OAuth is available for this profile." if youtube_access else "Connect a YouTube OAuth account for this profile before publishing.",
        },
        "spotify": {
            "label": "Spotify", "available": spotify_access,
            "detail": "An access token is available for this profile." if spotify_access else "Not connected yet. Store a Spotify access token for this profile to enable publishing.",
        },
    }
    return {
        "schema_version": 1, "owner": owner,
        "account_label": str(review.get("account_label") or "") if isinstance(review, dict) else "",
        "playlists": playlists.get("playlists", []), "track_options": options,
        "providers": providers,
        "track_review": {"total": len(items), "approved": approved, "automatic": auto_selected},
    }


def deploy_youtube_playlist(owner: str, playlist: Dict[str, Any]) -> Dict[str, Any]:
    """Create/update one manager playlist from the approved YouTube review items."""
    review_path = person_youtube_review_path(owner)
    review = load_json(review_path, {"items": [], "playlist": {}})
    entries = playlist_entries(playlist, review, owner)
    publishable, _duplicates = youtube_publishable_items(review, include_auto=False)
    publishable_by_id = {str(item.get("id")): item for item in publishable}
    desired = [
        publishable_by_id[entry["id"]] for entry in entries
        if entry["kind"] == "album" and entry["id"] in publishable_by_id
    ]
    if not desired:
        raise ValueError("This playlist has no selected albums with approved, YouTube Music-verified tracks ready to publish")
    # An existing OAuth refresh token is sufficient. If it is unavailable,
    # youtube_service will raise a clear setup error rather than opening an
    # unexpected browser flow from this local HTTP request.
    service = youtube_service("", owner)
    destination = playlist.setdefault("youtube", {})
    playlist_id = str(destination.get("playlist_id") or "").strip()
    title = str(playlist.get("name") or APP_NAME).strip()
    description = str(playlist.get("description") or "").strip()
    privacy = str(playlist.get("visibility") or "unlisted").strip()
    if playlist_id:
        youtube_execute_with_retries(service.playlists().update(part="snippet,status", body={
            "id": playlist_id,
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy},
        }), "updating manager playlist")
    else:
        created = youtube_execute_with_retries(service.playlists().insert(part="snippet,status", body={
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy},
        }), "creating manager playlist")
        playlist_id = created["id"]
    live = youtube_playlist_items(service, playlist_id)
    live_video_ids = set(live.values())
    desired_video_ids = {item.get("selected_video_id") for item in desired}
    removed = 0
    desired_by_id = {str(item.get("id")): item for item in desired}
    for item in review.get("items", []):
        published_id = item.get("published_playlist_item_id", "")
        if not published_id or published_id not in live:
            continue
        expected = desired_by_id.get(str(item.get("id")))
        expected_video_id = expected.get("selected_video_id") if expected else ""
        if expected_video_id == live[published_id]:
            continue
        youtube_execute_with_retries(service.playlistItems().delete(id=published_id), f"removing {item.get('artist', '')} — {item.get('title', '')}")
        item["published_playlist_item_id"] = ""
        item.pop("published_at", None)
        live_video_ids.discard(live[published_id])
        removed += 1
    if removed:
        write_json(review_path, review)
    added = 0
    for item in desired:
        if item.get("selected_video_id") in live_video_ids:
            continue
        created = youtube_execute_with_retries(service.playlistItems().insert(part="snippet", body={
            "snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": item["selected_video_id"]}},
        }), f"adding {item['artist']} — {item['title']}")
        item["published_playlist_item_id"] = created["id"]
        item["published_at"] = utc_now()
        live_video_ids.add(item["selected_video_id"])
        added += 1
    review.setdefault("playlist", {}).update({
        "id": playlist_id, "title": title, "description": description,
        "privacy": privacy, "account_label": review.get("account_label", ""), "updated_at": utc_now(),
    })
    write_json(review_path, review)
    destination.update({"status": "published", "playlist_id": playlist_id, "url": f"https://www.youtube.com/playlist?list={playlist_id}", "updated_at": utc_now()})
    track_entries = sum(1 for entry in entries if entry["kind"] == "track")
    return {"playlist_id": playlist_id, "url": destination["url"], "added": added, "removed": removed, "available": len(desired), "track_entries_pending": track_entries}


def make_youtube_review_handler(owner: str) -> type[http.server.SimpleHTTPRequestHandler]:
    review_path = person_youtube_review_path(owner)

    class YouTubeReviewHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            print(f"[youtube-review] {format % args}")

        def request_owner(self, supplied: Any = None) -> str:
            """Resolve an owner from the request, falling back to the CLI owner."""
            if supplied is None:
                supplied = parse_qs(urlparse(self.path).query, keep_blank_values=True).get("owner", [owner])[0]
            context = person_context(str(supplied or owner).strip())
            for person in available_people(owner):
                if person["id"] == context["id"]:
                    return person["display_name"]
            return context["display_name"]

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            request_owner = self.request_owner()
            if path == "/api/youtube-music-review":
                write_json_response(self, load_json(person_youtube_review_path(request_owner), {"error": "Run build-youtube-review first."}))
                return
            if path == "/api/playlists":
                write_json_response(self, playlist_manager_payload(request_owner))
                return
            if path == "/api/owners":
                write_json_response(self, {"owners": available_people(request_owner)})
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/playlists":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    update = json.loads(self.rfile.read(length).decode("utf-8"))
                    request_owner = self.request_owner(update.get("owner"))
                    manager = load_playlists(request_owner)
                    playlists = [item for item in manager.get("playlists", []) if isinstance(item, dict)]
                    action = str(update.get("action") or "save").strip().casefold()
                    playlist_id = str(update.get("id") or "").strip()
                    playlist = next((item for item in playlists if item.get("id") == playlist_id), None)
                    if action == "deploy":
                        if playlist is None:
                            raise ValueError("Playlist not found")
                        provider = str(update.get("provider") or "").strip().casefold()
                        if provider != "youtube":
                            raise ValueError("Spotify deployment is not connected yet; save the destination and add Spotify OAuth first")
                        result = deploy_youtube_playlist(request_owner, playlist)
                        manager.update({"schema_version": 1, "owner": request_owner, "playlists": playlists, "updated_at": utc_now()})
                        person_playlists_path(request_owner).parent.mkdir(parents=True, exist_ok=True)
                        write_json(person_playlists_path(request_owner), manager)
                        write_json_response(self, {"ok": True, "deployment": result, **playlist_manager_payload(request_owner)})
                        return
                    if action == "delete":
                        if playlist is None:
                            raise ValueError("Playlist not found")
                        playlists.remove(playlist)
                    else:
                        name = str(update.get("name") or "").strip()
                        description = str(update.get("description") or "").strip()
                        if not name:
                            raise ValueError("A playlist name is required")
                        if len(name) > 160 or len(description) > 1000:
                            raise ValueError("Playlist name or description is too long")
                        visibility = str(update.get("visibility") or "unlisted").strip().casefold()
                        if visibility not in {"private", "unlisted", "public"}:
                            raise ValueError("Visibility must be private, unlisted, or public")
                        destinations = update.get("destinations", [])
                        if not isinstance(destinations, list):
                            raise ValueError("Destinations must be a list")
                        destinations = [str(value).strip().casefold() for value in destinations if str(value).strip().casefold() in {"youtube", "spotify"}]
                        entries = None
                        track_ids = None
                        if "entries" in update:
                            if not isinstance(update.get("entries"), list):
                                raise ValueError("Playlist entries must be a list")
                            review = load_json(person_youtube_review_path(request_owner), {"items": []})
                            option_list = playlist_track_options(review, request_owner)
                            allowed_albums = {option["id"] for option in option_list}
                            allowed_tracks = {track["id"]: track for option in option_list for track in option["tracks"]}
                            entries, seen = [], set()
                            for raw_entry in update.get("entries", []):
                                if not isinstance(raw_entry, dict):
                                    continue
                                kind = str(raw_entry.get("kind") or "album").strip().casefold()
                                entry_id = str(raw_entry.get("id") or "").strip()
                                if kind == "album" and entry_id in allowed_albums:
                                    entry = {"kind": "album", "id": entry_id}
                                elif kind == "track" and entry_id in allowed_tracks:
                                    entry = {"kind": "track", "id": entry_id, "album_id": allowed_tracks[entry_id]["album_id"]}
                                else:
                                    continue
                                dedupe_key = f"{entry['kind']}:{entry['id']}"
                                if dedupe_key not in seen:
                                    entries.append(entry)
                                    seen.add(dedupe_key)
                            track_ids = [entry["id"] for entry in entries if entry["kind"] == "album"]
                        elif "track_ids" in update:
                            if not isinstance(update.get("track_ids"), list):
                                raise ValueError("Track IDs must be a list")
                            review = load_json(person_youtube_review_path(request_owner), {"items": []})
                            allowed = {str(item.get("id")) for item in review.get("items", []) if item.get("id")}
                            track_ids, seen = [], set()
                            for value in update.get("track_ids", []):
                                track_id = str(value).strip()
                                if track_id in allowed and track_id not in seen:
                                    track_ids.append(track_id)
                                    seen.add(track_id)
                        if playlist is None:
                            playlist_id = f"{person_context(request_owner)['id']}-{slugify_person(name)}-{uuid.uuid4().hex[:6]}"
                            playlist = {
                                "id": playlist_id, "owner": request_owner, "source": "youtube-review",
                                "youtube": {"status": "ready", "playlist_id": "", "url": ""},
                                "spotify": {"status": "not_connected", "playlist_id": "", "url": ""},
                                "created_at": utc_now(),
                            }
                            playlists.append(playlist)
                        playlist.update({"name": name, "description": description, "visibility": visibility, "destinations": destinations, "updated_at": utc_now()})
                        if entries is not None:
                            playlist["entries"] = entries
                            playlist["track_ids"] = track_ids
                        elif track_ids is not None:
                            playlist["track_ids"] = track_ids
                    manager.update({"schema_version": 1, "owner": request_owner, "playlists": playlists, "updated_at": utc_now()})
                    person_playlists_path(request_owner).parent.mkdir(parents=True, exist_ok=True)
                    write_json(person_playlists_path(request_owner), manager)
                    write_json_response(self, {"ok": True, "saved_id": playlist.get("id") if isinstance(playlist, dict) else "", **playlist_manager_payload(request_owner)})
                except (ValueError, KeyError, json.JSONDecodeError) as exc:
                    write_json_response(self, {"error": str(exc)}, 400)
                except SystemExit as exc:
                    write_json_response(self, {"error": str(exc)}, 409)
                except Exception as exc:
                    write_json_response(self, {"error": f"Could not update playlist: {exc}"}, 502)
                return
            if path != "/api/youtube-music-review":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                update = json.loads(self.rfile.read(length).decode("utf-8"))
                request_owner = self.request_owner(update.get("owner"))
                review_path = person_youtube_review_path(request_owner)
                review = load_json(review_path, {"items": []})
                item = next(item for item in review["items"] if item["id"] == update["id"])
                status = update.get("match_status", "unmatched")
                if status not in {"unmatched", "auto_selected", "approved", "rejected"}:
                    raise ValueError("Invalid match status")
                video_url = str(update.get("selected_video_url", "")).strip()
                video_id = extract_youtube_video_id(video_url) if video_url else ""
                verified = bool(update.get("youtube_music_verified", False))
                if status == "approved" and (not video_id or not verified):
                    raise ValueError("An approved item needs a video URL and a confirmed YouTube Music check.")
                item.update({
                    "selected_video_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                    "selected_video_id": video_id, "match_status": status,
                    "youtube_music_verified": verified,
                    "youtube_music_checked_at": utc_now() if verified else "",
                    "note": str(update.get("note", "")).strip(),
                })
                write_json(review_path, review)
                write_json_response(self, {"ok": True, "item": item})
            except (ValueError, KeyError, StopIteration, json.JSONDecodeError) as exc:
                write_json_response(self, {"error": str(exc)}, 400)

    return YouTubeReviewHandler


def command_build_youtube_music_review(args: argparse.Namespace) -> None:
    review = build_youtube_music_review(args.owner)
    print(f"Built YouTube Music review with {len(review['items'])} distinct crate titles at {person_youtube_review_path(args.owner)}.")


def command_serve_youtube_music_review(args: argparse.Namespace) -> None:
    require_loopback_bind(args.host, "serve-youtube-review")
    if not person_youtube_review_path(args.owner).exists():
        build_youtube_music_review(args.owner)
    os.chdir(ROOT)
    server = http.server.ThreadingHTTPServer((args.host, args.port), make_youtube_review_handler(args.owner))
    print(f"YouTube Music review at http://{args.host}:{args.port}/youtube-review.html")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nYouTube Music review server stopped.")


APP_STATIC_FILES = {
    "/viewer.html": "text/html; charset=utf-8",
    "/quick-crate.html": "text/html; charset=utf-8",
    "/review.html": "text/html; charset=utf-8",
    "/taste-profile.html": "text/html; charset=utf-8",
    "/youtube-review.html": "text/html; charset=utf-8",
    "/playlists.html": "text/html; charset=utf-8",
    "/mobile.html": "text/html; charset=utf-8",
    "/connect.html": "text/html; charset=utf-8",
    "/app.css": "text/css; charset=utf-8",
    "/app.js": "application/javascript; charset=utf-8",
}

REVIEW_GET_ROUTES = {"/api/review", "/api/catalog", "/api/discogs-search"}
REVIEW_POST_ROUTES = {"/api/decision", "/api/discogs-selection"}
YOUTUBE_GET_ROUTES = {"/api/youtube-music-review", "/api/playlists", "/api/owners"}
YOUTUBE_POST_ROUTES = {"/api/youtube-music-review", "/api/playlists"}


def make_cue_crate_handler(
    owner: str,
    advertised_base: str,
    session_token: str,
    discogs_token: Optional[str],
) -> type[http.server.SimpleHTTPRequestHandler]:
    """Serve the local product through one port while keeping phone access scoped."""
    MobileHandler = make_mobile_handler(owner, advertised_base, session_token)
    ReviewHandler = make_review_handler(owner, discogs_token)
    YouTubeHandler = make_youtube_review_handler(owner)

    class CueCrateHandler(MobileHandler, ReviewHandler, YouTubeHandler):
        def log_message(self, format: str, *args: Any) -> None:
            print(f"[cue-crate] {format % args}")

        def local_api_only(self) -> bool:
            if self.is_loopback_client():
                return True
            self.send_error(403, "This Cue Crate API is available only on the serving computer.")
            return False

        def serve_static(self, path: str) -> None:
            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/viewer.html")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            content_type = APP_STATIC_FILES.get(path)
            if content_type is None:
                self.send_error(404)
                return
            if path == "/connect.html" and not self.is_loopback_client():
                self.send_error(403, "The phone connect screen is available only on the serving computer.")
                return
            try:
                body = (ROOT / path.lstrip("/")).read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/api/mobile/"):
                MobileHandler.do_GET(self)
                return
            if path in REVIEW_GET_ROUTES or path.startswith("/api/photo/") or path.startswith("/api/photo-view/"):
                if self.local_api_only():
                    ReviewHandler.do_GET(self)
                return
            if path in YOUTUBE_GET_ROUTES:
                if self.local_api_only():
                    YouTubeHandler.do_GET(self)
                return
            if path == "/api/library/catalog":
                if self.local_api_only():
                    write_json_response(self, load_catalog())
                return
            if path == "/api/library/release-features":
                if self.local_api_only():
                    write_json_response(self, load_json(RELEASE_FEATURES_PATH, {"features": {}}))
                return
            if path == "/api/library/quick-crate":
                if self.local_api_only():
                    write_json_response(self, load_json(AGGREGATE_QUICK_CRATE_PATH, {"records": []}))
                return
            if path == "/api/scout/taste-profile":
                if not self.local_api_only():
                    return
                requested_owner = parse_qs(parsed.query, keep_blank_values=True).get("owner", [owner])[0]
                report_path = person_taste_profile_path(requested_owner)
                if not report_path.exists():
                    write_json_response(self, {"error": "Build a taste profile for this profile first."}, 404)
                    return
                write_json_response(self, load_json(report_path, {}))
                return
            self.serve_static(path)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/mobile/upload":
                MobileHandler.do_POST(self)
                return
            if path in REVIEW_POST_ROUTES:
                if self.local_api_only():
                    ReviewHandler.do_POST(self)
                return
            if path in YOUTUBE_POST_ROUTES:
                if self.local_api_only():
                    YouTubeHandler.do_POST(self)
                return
            self.send_error(404)

    return CueCrateHandler


def command_serve(args: argparse.Namespace) -> None:
    """Start every Cue Crate screen through one local server."""
    ensure_data_dir()
    review_path = person_workspace_path(args.owner, "review.json")
    if not review_path.exists():
        candidates_path = person_workspace_path(args.owner, "photo-candidates.json")
        if candidates_path.exists():
            build_review(args.owner)
        else:
            write_json(review_path, {
                "schema_version": 1,
                "generated_at": utc_now(),
                "owner": args.owner,
                "items": [],
            })
    if not person_youtube_review_path(args.owner).exists():
        build_youtube_music_review(args.owner)
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    address = args.advertise or (mobile_advertised_address() if args.lan else "127.0.0.1")
    base = f"http://{address}:{args.port}"
    token = secrets.token_urlsafe(24)
    os.chdir(ROOT)
    server = http.server.ThreadingHTTPServer(
        (host, args.port),
        make_cue_crate_handler(args.owner, base, token, read_token(args.token_file, args.owner)),
    )
    local_base = f"http://127.0.0.1:{args.port}"
    print(f"Cue Crate: {local_base}/viewer.html")
    print(f"Review: {local_base}/review.html")
    print(f"Playlists: {local_base}/playlists.html")
    print(f"Scout: {local_base}/taste-profile.html?owner={quote(person_context(args.owner)['id'])}")
    if args.lan:
        print(f"Phone connect screen: {local_base}/connect.html#token={quote(token)}")
    else:
        print("Phone companion is local-only. Re-run with --lan to create a trusted-network QR link.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCue Crate server stopped.")


def youtube_service(client_secrets: str, owner: str):
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.auth.exceptions import RefreshError
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit("Install YouTube publishing support: python3 -m pip install -r requirements.txt")
    scopes = ["https://www.googleapis.com/auth/youtube"]
    token_path, *legacy_token_paths = profile_provider_token_paths(owner, "youtube")
    credentials = None
    stored_token_path = next((path for path in [token_path, *legacy_token_paths] if path.exists()), None)
    if stored_token_path:
        credentials = Credentials.from_authorized_user_file(str(stored_token_path), scopes)
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleRequest())
        except RefreshError:
            # A revoked refresh token cannot recover in the background. Fall
            # through to a fresh local OAuth browser flow instead of failing.
            print("Saved YouTube authorization is no longer valid; sign in again in the browser.", flush=True)
            credentials = None
    if not credentials or not credentials.valid:
        if not client_secrets:
            raise SystemExit(
                f"No valid YouTube OAuth credential is stored for profile {profile_context(owner)['display_name']!r}. "
                "Run a deliberate publish or discovery command with --client-secrets to connect that profile."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(Path(client_secrets).expanduser()), scopes)
        credentials = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.parent.chmod(0o700)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    token_path.chmod(0o600)
    return build("youtube", "v3", credentials=credentials)


def youtube_match_score(item: Dict[str, Any], video: Dict[str, Any]) -> tuple[float, List[str]]:
    """Rank a likely original upload; view count only breaks musical near-ties."""
    snippet = video.get("snippet", {})
    title = str(snippet.get("title", ""))
    channel = str(snippet.get("channelTitle", ""))
    combined = normalise_match_text(title + " " + channel)
    artist = youtube_artist_match_text(item.get("artist", ""))
    track = normalise_match_text(item.get("title", ""))
    score, reasons = 0.0, []
    if artist and artist in combined:
        score += 45
        reasons.append("artist in upload title/channel")
    if track and track in combined:
        score += 50
        reasons.append("release title in upload title/channel")
    similarity_score = similarity(youtube_query(item), title)
    score += similarity_score * 35
    cue_text = (title + " " + channel).casefold()
    if any(cue in cue_text for cue in ("official audio", "official video", "provided to youtube", "topic", "full album", "album")):
        score += 14
        reasons.append("official/album cue")
    if any(cue in cue_text for cue in ("cover", "karaoke", "reaction", "tutorial", "tribute", "live at", "dj set")):
        score -= 35
        reasons.append("non-original cue")
    if str(snippet.get("categoryId", "")) == "10":
        score += 18
        reasons.append("YouTube Music category")
    views = int(video.get("statistics", {}).get("viewCount") or 0)
    score += min(math.log10(views + 1) * 3, 24)
    if views:
        reasons.append(f"{views:,} views")
    return round(score, 2), reasons


def youtube_artist_match_text(value: Any) -> str:
    """Remove Discogs' numeric disambiguator, e.g. Xavier (2) → Xavier."""
    value = str(value or "").strip()
    if value.endswith(")") and " (" in value:
        base, suffix = value.rsplit(" (", 1)
        if suffix[:-1].isdigit():
            value = base
    return normalise_match_text(value)


def youtube_candidate_matches_release(item: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    upload_title = str(candidate.get("title", ""))
    upload_text = normalise_match_text(upload_title)
    artist = youtube_artist_match_text(item.get("artist", ""))
    artist_text = normalise_match_text(upload_title + " " + str(candidate.get("channel", "")))
    release_title = normalise_match_text(item.get("title", ""))
    title_match = release_title in upload_text or similarity(item.get("title", ""), upload_title) >= 0.62
    return bool(artist and artist in artist_text and title_match)


def reassess_youtube_matches(review: Dict[str, Any], review_path: Path) -> tuple[int, int]:
    """Apply stricter artist-and-release-title guards to previously cached results."""
    automatic = 0
    exceptions = 0
    for item in review.get("items", []):
        if item.get("match_status") == "approved":
            continue
        candidates = item.get("auto_candidates", [])
        matching = next((candidate for candidate in candidates if youtube_candidate_matches_release(item, candidate)), None)
        if matching and float(matching.get("score", 0)) >= 65:
            item.update({
                "selected_video_url": matching["youtube_url"], "selected_video_id": matching["video_id"],
                "match_status": "auto_selected", "auto_confidence": matching["score"],
            })
            automatic += 1
        else:
            item.update({"selected_video_url": "", "selected_video_id": "", "match_status": "unmatched"})
            exceptions += 1
    write_json(review_path, review)
    return automatic, exceptions


def discover_youtube_matches(service: Any, review: Dict[str, Any], review_path: Path, limit: int, refresh: bool) -> tuple[int, int]:
    selected = 0
    skipped = 0
    for item in review.get("items", []):
        if limit and selected >= limit:
            break
        if not refresh and item.get("match_status") in {"approved", "rejected", "auto_selected"}:
            skipped += 1
            continue
        # Category filtering at search time unexpectedly returns sparse results
        # for older catalogue music. Search broadly, then strongly prefer actual
        # Music-category videos after fetching their metadata.
        search = service.search().list(part="snippet", q=item["query"], type="video", maxResults=5).execute()
        video_ids = [result.get("id", {}).get("videoId") for result in search.get("items", []) if result.get("id", {}).get("videoId")]
        if not video_ids:
            item.update({"match_status": "unmatched", "auto_confidence": 0, "auto_candidates": [], "auto_checked_at": utc_now()})
            write_json(review_path, review)
            selected += 1
            continue
        details = service.videos().list(part="snippet,statistics,status", id=",".join(video_ids)).execute().get("items", [])
        candidates = []
        for video in details:
            score, reasons = youtube_match_score(item, video)
            snippet = video.get("snippet", {})
            candidates.append({
                "video_id": video["id"], "title": snippet.get("title", ""), "channel": snippet.get("channelTitle", ""),
                "category_id": snippet.get("categoryId", ""), "views": int(video.get("statistics", {}).get("viewCount") or 0), "score": score, "reasons": reasons,
                "youtube_url": f"https://www.youtube.com/watch?v={video['id']}", "youtube_music_url": f"https://music.youtube.com/watch?v={video['id']}",
            })
        music_candidates = [candidate for candidate in candidates if str(candidate.get("category_id")) == "10"]
        if music_candidates:
            candidates = music_candidates
        candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
        best = candidates[0]
        # A score below this normally means that either artist or title did not
        # appear in the result; preserve it as an exception rather than guessing.
        if best["score"] >= 65 and youtube_candidate_matches_release(item, best):
            item.update({
                "selected_video_url": best["youtube_url"], "selected_video_id": best["video_id"],
                "match_status": "auto_selected", "youtube_music_verified": False,
                "youtube_music_checked_at": "", "auto_confidence": best["score"],
                "auto_candidates": candidates, "auto_checked_at": utc_now(),
            })
        else:
            item.update({"match_status": "unmatched", "auto_confidence": best["score"], "auto_candidates": candidates, "auto_checked_at": utc_now()})
        write_json(review_path, review)
        selected += 1
        print(f"Matched {selected}: {item['artist']} — {item['title']} → {best['title']} ({best['score']})", flush=True)
        time.sleep(0.15)
    return selected, skipped


def command_discover_youtube_matches(args: argparse.Namespace) -> None:
    review_path = person_youtube_review_path(args.owner)
    if not review_path.exists():
        build_youtube_music_review(args.owner)
    review = load_json(review_path, {"items": []})
    if review.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"youtube-music-review.json belongs to {review.get('owner')}; use that owner.")
    service = youtube_service(args.client_secrets, args.owner)
    try:
        searched, skipped = discover_youtube_matches(service, review, review_path, args.limit, args.refresh)
    except Exception as exc:
        # Keep the optional Google dependency local to this feature while
        # translating the most common first-run Console omission into action.
        status = getattr(getattr(exc, "resp", None), "status", None)
        detail = str(exc)
        if status == 403 and "accessNotConfigured" in detail:
            raise SystemExit("YouTube Data API v3 is disabled for this OAuth project. Enable it in Google Cloud Console, wait a few minutes, then rerun this command.")
        if status == 429 and "Search Queries" in detail:
            saved = sum(1 for item in review.get("items", []) if item.get("match_status") == "auto_selected")
            raise SystemExit(f"YouTube Search quota is exhausted for this Google project. {saved} saved automatic selections remain in the review queue. Wait for the quota reset, then rerun this command without --refresh to continue from the remaining titles.")
        raise
    automatic = sum(1 for item in review["items"] if item.get("match_status") == "auto_selected")
    unmatched = sum(1 for item in review["items"] if item.get("match_status") == "unmatched")
    print(f"YouTube discovery searched {searched} titles ({skipped} retained); {automatic} auto-selected, {unmatched} need attention.")


def command_reassess_youtube_matches(args: argparse.Namespace) -> None:
    review_path = person_youtube_review_path(args.owner)
    review = load_json(review_path, {"items": []})
    if review.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"youtube-music-review.json belongs to {review.get('owner')}; use that owner.")
    automatic, exceptions = reassess_youtube_matches(review, review_path)
    print(f"Reassessed cached YouTube candidates: {automatic} auto-selected, {exceptions} need attention.")


def command_reject_youtube_review_items(args: argparse.Namespace) -> None:
    """Exclude reviewed releases without removing them from the local crate."""
    review_path = person_youtube_review_path(args.owner)
    review = load_json(review_path, {"items": []})
    if review.get("owner", "").casefold() != args.owner.casefold():
        raise SystemExit(f"youtube-music-review.json belongs to {review.get('owner')}; use that owner.")

    requested = set(args.id)
    found = set()
    for item in review.get("items", []):
        if item.get("id") not in requested:
            continue
        found.add(item["id"])
        item.update({
            "match_status": "rejected",
            "selected_video_id": "",
            "selected_video_url": "",
            "youtube_music_verified": False,
            "youtube_music_checked_at": "",
            "note": args.note.strip(),
        })

    missing = requested - found
    if missing:
        raise SystemExit(f"No YouTube review items found for: {', '.join(sorted(missing))}")
    write_json(review_path, review)
    print(f"Excluded {len(found)} YouTube review items from {args.owner}'s playlist; the catalog records remain unchanged.")


def youtube_execute_with_retries(request: Any, action: str, attempts: int = 4) -> Dict[str, Any]:
    """Retry short-lived YouTube backend failures without duplicating saved work."""
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        return request.execute()
    for attempt in range(attempts):
        try:
            return request.execute()
        except HttpError as exc:
            status = getattr(exc.resp, "status", 0)
            if status not in {409, 429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise
            delay = 2 ** attempt
            print(f"YouTube temporarily rejected {action} (HTTP {status}); retrying in {delay}s…", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"Could not complete {action}")


def youtube_publishable_items(review: Dict[str, Any], include_auto: bool) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    candidates = [
        item for item in review.get("items", [])
        if item.get("selected_video_id") and (
            (item.get("match_status") == "approved" and item.get("youtube_music_verified"))
            or (include_auto and item.get("match_status") == "auto_selected")
        )
    ]
    unique, duplicates, seen_videos = [], [], set()
    for item in candidates:
        if item["selected_video_id"] in seen_videos:
            duplicates.append(item)
        else:
            seen_videos.add(item["selected_video_id"])
            unique.append(item)
    return unique, duplicates


def youtube_playlist_items(service: Any, playlist_id: str) -> Dict[str, str]:
    """Return the live playlist-item ID → video-ID mapping."""
    current: Dict[str, str] = {}
    page_token = None
    while True:
        response = youtube_execute_with_retries(service.playlistItems().list(
            part="id,snippet", playlistId=playlist_id, maxResults=50, pageToken=page_token,
        ), "reading playlist items")
        for entry in response.get("items", []):
            current[entry["id"]] = entry.get("snippet", {}).get("resourceId", {}).get("videoId", "")
        page_token = response.get("nextPageToken")
        if not page_token:
            return current


def command_sync_youtube_playlist(args: argparse.Namespace) -> None:
    review_path = person_youtube_review_path(args.owner)
    review = load_json(review_path, {"items": []})
    playlist = review.get("playlist", {})
    if not playlist.get("id"):
        raise SystemExit("No published playlist is recorded yet.")
    desired, duplicate_choices = youtube_publishable_items(review, args.include_auto)
    if not desired:
        raise SystemExit("No desired playlist items. Include automatic selections or review matches first.")
    service = youtube_service(args.client_secrets, args.owner)
    live = youtube_playlist_items(service, playlist["id"])
    desired_by_record = {item["id"]: item for item in desired}
    removals: List[Dict[str, Any]] = []
    additions: List[Dict[str, Any]] = []
    retained = 0
    duplicate_ids = {item["id"] for item in duplicate_choices}
    for item in review.get("items", []):
        published_id = item.get("published_playlist_item_id", "")
        if not published_id:
            continue
        desired_item = desired_by_record.get(item["id"])
        current_video = live.get(published_id, "")
        if item["id"] in duplicate_ids or desired_item is None or current_video != desired_item["selected_video_id"]:
            removals.append(item)
        else:
            retained += 1
    for item in desired:
        published_id = item.get("published_playlist_item_id", "")
        if not published_id or item in removals or live.get(published_id) != item["selected_video_id"]:
            additions.append(item)
    print(f"Playlist sync plan: retain {retained}, remove {len(removals)}, add {len(additions)}, suppress {len(duplicate_choices)} duplicate selection(s).")
    if not args.apply:
        for item in removals:
            print(f"  WOULD REMOVE {item['artist']} — {item['title']}")
        for item in additions:
            print(f"  WOULD ADD {item['artist']} — {item['title']}")
        for item in duplicate_choices:
            print(f"  WOULD SUPPRESS DUPLICATE {item['artist']} — {item['title']}")
        print("Dry run only. Re-run with --apply after checking the plan.")
        return
    for item in removals:
        published_id = item.get("published_playlist_item_id", "")
        if published_id and published_id in live:
            youtube_execute_with_retries(service.playlistItems().delete(id=published_id), f"removing {item['artist']} — {item['title']}")
        item["published_playlist_item_id"] = ""
        item.pop("published_at", None)
        write_json(review_path, review)
        print(f"Removed {item['artist']} — {item['title']}")
    for item in duplicate_choices:
        item["publication_excluded_reason"] = f"Duplicate video selection; retained {next(entry['artist'] + ' — ' + entry['title'] for entry in desired if entry['selected_video_id'] == item['selected_video_id'])}."
    for item in additions:
        created = youtube_execute_with_retries(service.playlistItems().insert(part="snippet", body={
            "snippet": {"playlistId": playlist["id"], "resourceId": {"kind": "youtube#video", "videoId": item["selected_video_id"]}},
        }), f"adding {item['artist']} — {item['title']}")
        item["published_playlist_item_id"] = created["id"]
        item["published_at"] = utc_now()
        item.pop("publication_excluded_reason", None)
        write_json(review_path, review)
        print(f"Added {item['artist']} — {item['title']}")
    write_json(review_path, review)
    print(f"Synced playlist: https://www.youtube.com/playlist?list={playlist['id']}")


def command_publish_youtube_music(args: argparse.Namespace) -> None:
    review_path = person_youtube_review_path(args.owner)
    review = load_json(review_path, {"items": []})
    playlist = review.setdefault("playlist", {})
    title = str(args.title or playlist.get("title") or f"{args.owner}'s Cue Crate").strip()
    description = str(args.description or playlist.get("description") or f"Physical records from {args.owner}'s Cue Crate.").strip()
    account_label = str(args.account or playlist.get("account_label") or review.get("account_label") or "").strip()
    if args.metadata_only:
        if not playlist.get("id"):
            raise SystemExit("No published playlist is recorded yet.")
        print(f"{'UPDATE' if args.apply else 'WOULD UPDATE'} playlist {playlist['id']} to {args.privacy}.")
        if not args.apply:
            return
        service = youtube_service(args.client_secrets, args.owner)
        youtube_execute_with_retries(service.playlists().update(part="snippet,status", body={
            "id": playlist["id"],
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": args.privacy},
        }), "updating playlist details")
        playlist.update({"title": title, "description": description, "privacy": args.privacy, "account_label": account_label, "updated_at": utc_now()})
        write_json(review_path, review)
        print(f"Updated playlist: https://www.youtube.com/playlist?list={playlist['id']}")
        return
    approved, _ = youtube_publishable_items(review, args.include_auto)
    if not approved:
        raise SystemExit("No publishable videos yet. Review matches first, or explicitly include high-confidence automatic matches.")
    automatic = sum(1 for item in approved if item.get("match_status") == "auto_selected")
    print(f"{len(approved)} videos ready for '{title}' ({automatic} high-confidence automatic selections).")
    if not args.apply:
        for item in approved:
            print(f"  WOULD ADD {item['artist']} — {item['title']} ({item['selected_video_id']})")
        print("Dry run only. Re-run with --apply after signing in to the intended Google account.")
        return
    service = youtube_service(args.client_secrets, args.owner)
    if not playlist.get("id"):
        created = youtube_execute_with_retries(service.playlists().insert(part="snippet,status", body={
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": args.privacy},
        }), "playlist creation")
        playlist.update({"id": created["id"], "title": title, "description": description, "privacy": args.privacy, "created_at": utc_now(), "account_label": account_label})
        write_json(review_path, review)
        print(f"Created {args.privacy} playlist {created['id']}.")
    for item in approved:
        if item.get("published_playlist_item_id"):
            continue
        created = youtube_execute_with_retries(service.playlistItems().insert(part="snippet", body={
            "snippet": {"playlistId": playlist["id"], "resourceId": {"kind": "youtube#video", "videoId": item["selected_video_id"]}},
        }), f"adding {item['artist']} — {item['title']}")
        item["published_playlist_item_id"] = created["id"]
        item["published_at"] = utc_now()
        write_json(review_path, review)
        print(f"Added {item['artist']} — {item['title']}")
    print(f"Published playlist: https://www.youtube.com/playlist?list={playlist['id']}")


def text(values: Iterable[Dict[str, Any]], key: str = "name") -> str:
    return ", ".join(str(item.get(key, "")) for item in values if item.get(key))


def normalise_api_item(item: Dict[str, Any], owner: str) -> Dict[str, Any]:
    info = item.get("basic_information", {})
    release_id = info.get("id")
    instance_id = item.get("instance_id")
    return {
        "id": f"{person_context(owner)['id']}-{release_id}-{instance_id}",
        "owner": owner,
        "owner_id": person_context(owner)["id"],
        "discogs_release_id": release_id,
        "discogs_instance_id": instance_id,
        "artist": text(info.get("artists", [])),
        "title": info.get("title", ""),
        "label": text(info.get("labels", [])),
        "catalog_number": text(info.get("labels", []), "catno"),
        "year": info.get("year") or "",
        "format": text(info.get("formats", [])),
        "cover_image": info.get("cover_image", ""),
        "discogs_url": info.get("resource_url", ""),
        "collection_folder_id": item.get("folder_id"),
        "collection_notes": item.get("notes", ""),
        "source": "discogs_api",
        "status": "confirmed",
        "tracklist": [],
        "dj_notes": {},
    }


def record_key(record: Dict[str, Any]) -> str:
    return f"{record.get('owner', '').lower()}::{record.get('discogs_release_id')}::{record.get('discogs_instance_id', '')}"


def merge_records(catalog: Dict[str, Any], incoming: List[Dict[str, Any]]) -> tuple[int, int]:
    existing = {record_key(record): index for index, record in enumerate(catalog["records"])}
    added = updated = 0
    for record in incoming:
        key = record_key(record)
        if key in existing:
            old = catalog["records"][existing[key]]
            for local_field in ("tracklist", "dj_notes", "quick_access", "quick_access_sources", "crate_locations", "collection_notes"):
                if local_field in old:
                    record[local_field] = old[local_field]
            catalog["records"][existing[key]] = record
            updated += 1
        else:
            catalog["records"].append(record)
            existing[key] = len(catalog["records"]) - 1
            added += 1
    return added, updated


def reviewed_record_ids(owner: str) -> set[str]:
    """Return catalogue IDs referenced by this person's saved photo review."""
    review = load_json(person_workspace_path(owner, "review.json"), {"items": []})
    return {
        str(item.get("matched_record_id"))
        for item in review.get("items", [])
        if item.get("matched_record_id")
    }


def replace_review_record_ids(owner: str, replacements: Dict[str, str]) -> int:
    """Keep completed photo reviews attached when a Discogs copy ID changes."""
    if not replacements:
        return 0
    review_path = person_workspace_path(owner, "review.json")
    if not review_path.exists():
        return 0
    review = load_json(review_path, {"items": []})
    changed = 0
    for item in review.get("items", []):
        old_id = item.get("matched_record_id")
        if old_id in replacements:
            item["matched_record_id"] = replacements[old_id]
            changed += 1
    if changed:
        write_json(review_path, review)
    return changed


def merge_unique_values(current: Any, incoming: Any) -> List[Any]:
    """Combine list-like local values while retaining their first-seen order."""
    values: List[Any] = []
    for value in [*(current or []), *(incoming or [])]:
        if value not in values:
            values.append(value)
    return values


def transfer_local_record_state(source: Dict[str, Any], destination: Dict[str, Any]) -> None:
    """Move local-only catalogue work to the current Discogs instance of a release."""
    if source.get("quick_access"):
        destination["quick_access"] = True
    for field in ("quick_access_sources", "crate_locations"):
        values = merge_unique_values(destination.get(field), source.get(field))
        if values:
            destination[field] = values
    if source.get("dj_notes") and not destination.get("dj_notes"):
        destination["dj_notes"] = source["dj_notes"]
    if source.get("tracklist") and not destination.get("tracklist"):
        destination["tracklist"] = source["tracklist"]


def reconcile_discogs_snapshot(catalog: Dict[str, Any], incoming: List[Dict[str, Any]], owner: str) -> Dict[str, int]:
    """Reconcile one owner's Discogs API rows with a newly fetched collection snapshot.

    Only `discogs_api` rows are candidates for removal. Locally reviewed or
    located records are retained if Discogs no longer returns them, while any
    such local state is moved to the current instance when the same release is
    still present in the snapshot.
    """
    incoming_keys = {record_key(record) for record in incoming}
    current_by_release: Dict[Any, Dict[str, Any]] = {
        record.get("discogs_release_id"): record
        for record in catalog.get("records", [])
        if record_key(record) in incoming_keys
        and record.get("owner", "").casefold() == owner.casefold()
    }
    review_ids = reviewed_record_ids(owner)
    replacements: Dict[str, str] = {}
    kept: List[Dict[str, Any]] = []
    removed = preserved = 0

    for record in catalog.get("records", []):
        is_owner_record = record.get("owner", "").casefold() == owner.casefold()
        is_stale_api_record = (
            is_owner_record
            and record.get("source") == "discogs_api"
            and record_key(record) not in incoming_keys
        )
        if not is_stale_api_record:
            kept.append(record)
            continue

        replacement = current_by_release.get(record.get("discogs_release_id"))
        has_local_evidence = bool(
            record.get("quick_access")
            or record.get("quick_access_sources")
            or record.get("crate_locations")
            or record.get("dj_notes")
            or record.get("id") in review_ids
        )
        if replacement:
            if has_local_evidence:
                transfer_local_record_state(record, replacement)
            replacements[str(record.get("id"))] = str(replacement.get("id"))
            removed += 1
            continue
        if has_local_evidence:
            # The record was intentionally reviewed or placed locally, so keep
            # it as a local physical record even if Discogs no longer lists it.
            record["source"] = "local_review"
            record["discogs_sync_status"] = "not_in_latest_snapshot"
            kept.append(record)
            preserved += 1
            continue
        removed += 1

    catalog["records"] = kept
    review_updates = replace_review_record_ids(owner, replacements)
    return {"removed": removed, "preserved": preserved, "review_updates": review_updates}


def command_import_csv(args: argparse.Namespace) -> None:
    path = Path(args.input).expanduser()
    if not path.exists():
        raise SystemExit(f"CSV file not found: {path}")
    incoming = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for number, row in enumerate(csv.DictReader(handle), start=2):
            release_id = (row.get("release_id") or row.get("Release ID") or "").strip()
            if not release_id.isdigit():
                print(f"Skipping CSV row {number}: it has no Discogs release_id.", file=sys.stderr)
                continue
            instance_id = (row.get("Instance ID") or row.get("instance_id") or row.get("Date Added") or str(number)).strip()
            incoming.append({
                "id": f"{person_context(args.owner)['id']}-{release_id}-{instance_id}",
                "owner": args.owner,
                "owner_id": person_context(args.owner)["id"],
                "discogs_release_id": int(release_id),
                "discogs_instance_id": instance_id,
                "artist": row.get("Artist", ""),
                "title": row.get("Title", ""),
                "label": row.get("Label", ""),
                "catalog_number": row.get("Catalog#", ""),
                "year": row.get("Released", ""),
                "format": row.get("Format", ""),
                "cover_image": "",
                "discogs_url": f"{API_ROOT}/releases/{release_id}",
                "collection_folder": row.get("CollectionFolder", ""),
                "collection_notes": row.get("Collection Notes", ""),
                "source": "discogs_csv",
                "status": "confirmed",
                "tracklist": [],
                "dj_notes": {},
            })
    catalog = load_catalog()
    added, updated = merge_records(catalog, incoming)
    save_catalog(catalog)
    print(f"Imported {len(incoming)} records for {args.owner}: {added} added, {updated} updated.")


def paged_releases(path: str, token: str) -> List[Dict[str, Any]]:
    page = 1
    releases: List[Dict[str, Any]] = []
    while True:
        separator = "&" if "?" in path else "?"
        response = discogs_request(f"{path}{separator}page={page}&per_page=100", token)
        releases.extend(response.get("releases", []))
        pages = response.get("pagination", {}).get("pages", 1)
        if page >= pages:
            return releases
        page += 1
        time.sleep(1.1)


def paged_items(path: str, token: str, key: str) -> List[Dict[str, Any]]:
    page = 1
    items: List[Dict[str, Any]] = []
    while True:
        separator = "&" if "?" in path else "?"
        response = discogs_request(f"{path}{separator}page={page}&per_page=100", token)
        items.extend(response.get(key, []))
        pages = response.get("pagination", {}).get("pages", 1)
        if page >= pages:
            return items
        page += 1
        time.sleep(1.1)


def release_feature(release: Dict[str, Any]) -> Dict[str, Any]:
    formats = []
    for format_info in release.get("formats", []):
        formats.extend([format_info.get("name", ""), *format_info.get("descriptions", [])])
    return {
        "release_id": release.get("id"),
        "artist": text(release.get("artists", [])),
        "title": release.get("title", ""),
        "genres": release.get("genres", []),
        "styles": release.get("styles", []),
        "labels": text(release.get("labels", [])),
        "year": release.get("year") or "",
        "country": release.get("country", ""),
        "formats": [format_name for format_name in formats if format_name],
        "community": release.get("community", {}),
        "uri": release.get("uri", ""),
        "fetched_at": utc_now(),
    }


def command_fetch_release_features(args: argparse.Namespace) -> None:
    token = read_token(args.token_file, args.owner)
    if not token:
        raise SystemExit("Supply --token-file or set DISCOGS_TOKEN.")
    catalog = load_catalog()
    records = [record for record in catalog["records"] if record.get("owner", "").casefold() == args.owner.casefold()]
    cache = load_json(RELEASE_FEATURES_PATH, {"schema_version": 1, "features": {}})
    features = cache.setdefault("features", {})
    pending = [record for record in records if str(record.get("discogs_release_id", "")).isdigit() and (str(record.get("discogs_release_id")) not in features or args.refresh)]
    if args.limit:
        pending = pending[:args.limit]
    fetched = 0
    for record in pending:
        release_id = str(record.get("discogs_release_id", ""))
        release = discogs_request(f"/releases/{release_id}", token)
        features[release_id] = release_feature(release)
        fetched += 1
        cache["updated_at"] = utc_now()
        write_json(RELEASE_FEATURES_PATH, cache)
        print(f"Fetched taste metadata: {record.get('artist', '')} — {record.get('title', '')}", flush=True)
        time.sleep(1.1)
    cache["updated_at"] = utc_now()
    write_json(RELEASE_FEATURES_PATH, cache)
    print(f"Taste metadata cache has {len(features)} releases ({fetched} fetched this run).")


def command_fetch_wantlist(args: argparse.Namespace) -> None:
    token = read_token(args.token_file, args.owner)
    if not token:
        raise SystemExit("Supply --token-file or set DISCOGS_TOKEN.")
    username = args.username or person_context(args.owner)["discogs_username"] or discogs_request("/oauth/identity", token).get("username")
    if not username:
        raise SystemExit("Discogs did not return an account username.")
    wants = paged_items(f"/users/{quote(username)}/wants", token, "wants")
    entries = []
    for want in wants:
        info = want.get("basic_information", {})
        entries.append({
            "release_id": info.get("id"),
            "artist": text(info.get("artists", [])),
            "title": info.get("title", ""),
            "year": info.get("year") or "",
            "genres": info.get("genres", []),
            "styles": info.get("styles", []),
            "labels": text(info.get("labels", [])),
            "formats": [format_info.get("name", "") for format_info in info.get("formats", [])],
            "notes": want.get("notes", ""),
        })
    write_json(person_wantlist_path(args.owner), {"schema_version": 1, "owner": args.owner, "username": username, "fetched_at": utc_now(), "releases": entries})
    print(f"Fetched {len(entries)} Wantlist releases for {args.owner}.")


DEFAULT_DISCOVERY_LANES = [
    {"id": "core_boogie", "name": "Core boogie / modern soul", "years": "1979–1986", "hints": ["Boogie", "Funk", "Soul", "Disco", "Post-Disco"]},
    {"id": "afro_boogie", "name": "Afro-boogie / highlife-funk", "years": "1979–1987", "hints": ["Boogie", "Highlife", "Afro-Disco", "Funk"]},
    {"id": "south_african", "name": "South African bubblegum / boogie", "years": "1980s", "hints": ["Bubblegum", "Boogie", "Disco", "Funk"]},
    {"id": "brazilian", "name": "Brazilian boogie / MPB-funk", "years": "late 1970s–mid 1980s", "hints": ["Boogie", "MPB", "Funk", "Disco"]},
    {"id": "open_exploration", "name": "Open complementary exploration", "years": "open", "hints": ["danceable", "soulful", "percussive", "synth-forward"]},
]


def ranked(counter: Counter, limit: int = 12) -> List[Dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def command_build_taste_profile(args: argparse.Namespace) -> None:
    catalog = load_catalog()
    owned = [record for record in catalog["records"] if record.get("owner", "").casefold() == args.owner.casefold()]
    feature_cache = load_json(RELEASE_FEATURES_PATH, {"features": {}}).get("features", {})
    quick = load_json(person_quick_crate_path(args.owner), {"records": []}).get("records", [])
    wantlist = load_json(person_wantlist_path(args.owner), {"releases": []}).get("releases", [])
    features = [feature_cache.get(str(record.get("discogs_release_id"))) for record in owned]
    features = [feature for feature in features if feature]
    styles = Counter(style for feature in features for style in feature.get("styles", []))
    genres = Counter(genre for feature in features for genre in feature.get("genres", []))
    labels = Counter(label.strip() for feature in features for label in feature.get("labels", "").split(",") if label.strip())
    catalog_artists = Counter(feature.get("artist", "") for feature in features if feature.get("artist"))
    quick_artists = Counter(entry.get("artist", "") for entry in quick if entry.get("artist"))
    years = Counter(str(feature.get("year")) for feature in features if feature.get("year"))
    want_styles = Counter(style for release in wantlist for style in release.get("styles", []))
    profile = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "owner": args.owner,
        "coverage": {"catalog_records": len(owned), "feature_records": len(features), "quick_crate_records": len(quick), "wantlist_records": len(wantlist)},
        "signals": {
            "styles": ranked(styles), "genres": ranked(genres), "labels": ranked(labels), "catalog_artists": ranked(catalog_artists),
            "quick_crate_artists": ranked(quick_artists), "years": ranked(years), "wantlist_styles": ranked(want_styles),
        },
        "discovery_lanes": DEFAULT_DISCOVERY_LANES,
        "notes": [
            "Catalogue-derived styles and genres use only exact Discogs release matches.",
            "Quick-crate titles are an artist/title signal, not assumed exact pressings.",
            "The exploration lanes are intentionally broad hypotheses to test, not genre restrictions.",
        ],
    }
    taste_profile_path = person_taste_profile_path(args.owner)
    taste_profile_markdown_path = person_taste_profile_markdown_path(args.owner)
    write_json(taste_profile_path, profile)
    lines = [f"# {args.owner}'s Crate Scout taste profile", "", f"Coverage: {len(features)} metadata-enriched releases / {len(owned)} catalogue records / {len(quick)} quick-crate titles.", ""]
    for label, values in [("Styles", profile["signals"]["styles"]), ("Genres", profile["signals"]["genres"]), ("Labels", profile["signals"]["labels"]), ("Quick-crate artists", profile["signals"]["quick_crate_artists"]), ("Wantlist styles", profile["signals"]["wantlist_styles"])]:
        lines.extend([f"## {label}", ""])
        lines.extend([f"- {entry['name']} ({entry['count']})" for entry in values] or ["- No data yet."])
        lines.append("")
    lines.extend(["## Discovery lanes", ""])
    lines.extend([f"- **{lane['name']}** — {lane['years']}; {', '.join(lane['hints'])}" for lane in DEFAULT_DISCOVERY_LANES])
    taste_profile_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    taste_profile_markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Built taste profile with {len(features)} metadata-enriched releases at {taste_profile_path} and {taste_profile_markdown_path}.")


def seller_cache_path(seller: str) -> Path:
    safe_name = "".join(char for char in seller.casefold() if char.isalnum() or char in {"-", "_"})
    return SELLER_CACHE_DIR / f"seller-{safe_name}.json"


def fetch_seller_inventory(seller: str, token: str, refresh: bool) -> Dict[str, Any]:
    path = seller_cache_path(seller)
    cache = load_json(path, {"schema_version": 1, "seller": seller, "listings": [], "fetched_pages": []})
    if cache.get("listings") and not refresh and cache.get("complete"):
        return cache
    by_id = {str(listing.get("id")): listing for listing in cache.get("listings", []) if listing.get("id") is not None}
    fetched_pages = set(cache.get("fetched_pages", [])) if not refresh else set()
    if refresh:
        by_id = {}
    first = discogs_request(f"/users/{quote(seller)}/inventory?status=For%20Sale&page=1&per_page=100", token)
    reported_pages = first.get("pagination", {}).get("pages", 1)
    # Discogs restricts third-party inventory pagination to the first 100 pages.
    # Retain that limitation in the cache/report instead of failing at page 101.
    pages = min(reported_pages, 100)
    responses = {1: first}
    cache.update({
        "schema_version": 1, "seller": seller, "fetched_at": utc_now(), "pages": pages,
        "reported_pages": reported_pages, "pagination_truncated": reported_pages > pages,
        "fetched_pages": sorted(fetched_pages), "listings": list(by_id.values()), "complete": len(fetched_pages) == pages,
    })
    write_json(path, cache)
    for page_number in range(1, pages + 1):
        if page_number in fetched_pages:
            continue
        response = responses.get(page_number) or discogs_request(
            f"/users/{quote(seller)}/inventory?status=For%20Sale&page={page_number}&per_page=100", token
        )
        for listing in response.get("listings", []):
            by_id[str(listing.get("id"))] = listing
        fetched_pages.add(page_number)
        cache.update({
            "schema_version": 1, "seller": seller, "fetched_at": utc_now(), "pages": pages,
            "reported_pages": reported_pages, "pagination_truncated": reported_pages > pages,
            "fetched_pages": sorted(fetched_pages), "listings": list(by_id.values()), "complete": len(fetched_pages) == pages,
        })
        write_json(path, cache)
        print(f"Fetched {seller} inventory page {page_number}/{pages}", flush=True)
        if page_number < pages:
            time.sleep(1.1)
    return cache


def listing_format_names(listing: Dict[str, Any]) -> List[str]:
    info = listing.get("basic_information") or listing.get("release", {})
    formats = info.get("formats")
    if isinstance(formats, list):
        names = []
        for format_info in formats:
            names.extend([format_info.get("name", ""), *format_info.get("descriptions", [])])
    else:
        names = str(info.get("format", "")).split(",")
    return [name for name in names if name]


def listing_price(listing: Dict[str, Any]) -> Optional[float]:
    try:
        return float(listing.get("price", {}).get("value"))
    except (TypeError, ValueError):
        return None


def listing_is_vinyl(formats: List[str]) -> bool:
    combined = " ".join(formats).casefold()
    return "vinyl" in combined or any(marker in combined for marker in ("lp", '12"', '10"', '7"'))


def artist_title_key(artist: str, title: str) -> str:
    return f"{normalise_match_text(artist)}::{normalise_match_text(title)}"


def command_add_owned_title(args: argparse.Namespace) -> None:
    """Record an owner-confirmed title when the exact pressing is not catalogued yet."""
    overrides_path = person_workspace_path(args.owner, "owned-overrides.json")
    overrides = load_json(overrides_path, {"schema_version": 1, "owner": args.owner, "records": []})
    records = overrides.setdefault("records", [])
    candidate = {"artist": args.artist.strip(), "title": args.title.strip(), "note": args.note.strip(), "added_at": utc_now()}
    key = artist_title_key(candidate["artist"], candidate["title"])
    if not all((candidate["artist"], candidate["title"])):
        raise SystemExit("Both --artist and --title are required.")
    for index, record in enumerate(records):
        if artist_title_key(record.get("artist", ""), record.get("title", "")) == key:
            records[index] = candidate
            break
    else:
        records.append(candidate)
    write_json(overrides_path, overrides)
    print(f"Saved owned-title override for {candidate['artist']} — {candidate['title']}.")


def normalise_purchase_listing(listing: Dict[str, Any], owner: str) -> Dict[str, Any]:
    release = listing.get("release", {})
    return {
        "listing_id": listing.get("id"), "owner": owner, "seller": listing.get("seller", {}).get("username", ""), "status": "ordered",
        "release_id": release.get("id"), "artist": release.get("artist", ""), "title": release.get("title", ""),
        "label": release.get("label", ""), "catalog_number": release.get("catalog_number", ""), "year": release.get("year", ""), "format": release.get("format", ""),
        "media_condition": listing.get("condition", ""), "sleeve_condition": listing.get("sleeve_condition", ""),
        "price": listing.get("price", {}).get("value"), "currency": listing.get("price", {}).get("currency", ""),
        "shipping_price": listing.get("shipping_price", {}).get("value"), "listing_url": listing.get("uri", f"https://www.discogs.com/sell/item/{listing.get('id')}"),
        "recorded_at": utc_now(),
    }


def cached_seller_listing(seller: str, listing_id: str) -> Optional[Dict[str, Any]]:
    """Find a previously captured marketplace listing after it has left the live inventory."""
    cache = load_json(seller_cache_path(seller), {"listings": []})
    return next((item for item in cache.get("listings", []) if str(item.get("id")) == str(listing_id)), None)


def save_purchase(path: Path, purchases: Dict[str, Any], existing: Dict[str, int], purchase: Dict[str, Any]) -> None:
    listing_id = str(purchase["listing_id"])
    if listing_id in existing:
        purchases["purchases"][existing[listing_id]] = purchase
    else:
        purchases["purchases"].append(purchase)
        existing[listing_id] = len(purchases["purchases"]) - 1
    write_json(path, purchases)


def command_record_order(args: argparse.Namespace) -> None:
    token = read_token(args.token_file, args.owner)
    if not token:
        raise SystemExit("Supply --token-file, set DISCOGS_TOKEN, or configure a local token.")
    purchases_path = person_workspace_path(args.owner, "purchases.json")
    purchases = load_json(purchases_path, {"schema_version": 1, "owner": args.owner, "purchases": []})
    existing = {str(purchase.get("listing_id")): index for index, purchase in enumerate(purchases["purchases"])}
    recorded = []
    for listing_id in args.listing_id:
        if not str(listing_id).isdigit():
            raise SystemExit(f"Invalid Discogs listing ID: {listing_id}")
        try:
            listing = discogs_request(f"/marketplace/listings/{listing_id}", token)
            source = "Discogs marketplace listing API"
        except SystemExit:
            listing = cached_seller_listing(args.seller, listing_id) if args.seller else None
            if not listing:
                raise
            source = "saved seller inventory snapshot"
            print(f"Live listing {listing_id} is no longer readable; using saved seller inventory data.", flush=True)
        purchase = normalise_purchase_listing(listing, args.owner)
        if args.seller and purchase["seller"].casefold() != args.seller.casefold():
            raise SystemExit(f"Listing {listing_id} belongs to {purchase['seller']}, not {args.seller}.")
        purchase["source"] = source
        save_purchase(purchases_path, purchases, existing, purchase)
        recorded.append(purchase)
        print(f"Recorded order: {purchase['artist']} — {purchase['title']}", flush=True)
        time.sleep(1.1)
    total = sum(float(purchase["price"] or 0) for purchase in recorded)
    currencies = {purchase["currency"] for purchase in recorded if purchase.get("currency")}
    print(f"Recorded {len(recorded)} ordered listings ({', '.join(currencies)} {total:.2f} item total).")


def command_record_manual_order(args: argparse.Namespace) -> None:
    """Keep a user-supplied ordered listing when it has vanished from Discogs inventory."""
    purchases_path = person_workspace_path(args.owner, "purchases.json")
    purchases = load_json(purchases_path, {"schema_version": 1, "owner": args.owner, "purchases": []})
    existing = {str(purchase.get("listing_id")): index for index, purchase in enumerate(purchases["purchases"])}
    purchase = {
        "listing_id": int(args.listing_id), "owner": args.owner, "seller": args.seller or "", "status": "ordered",
        "release_id": args.release_id, "artist": args.artist.strip(), "title": args.title.strip(),
        "label": args.label.strip(), "catalog_number": args.catalog_number.strip(), "year": args.year or "", "format": args.format.strip(),
        "media_condition": args.media_condition.strip(), "sleeve_condition": args.sleeve_condition.strip(),
        "price": args.price, "currency": args.currency.strip(), "shipping_price": None,
        "listing_url": f"https://www.discogs.com/sell/item/{args.listing_id}", "recorded_at": utc_now(), "source": "user-supplied order detail",
    }
    if not all((purchase["artist"], purchase["title"])):
        raise SystemExit("Both --artist and --title are required.")
    save_purchase(purchases_path, purchases, existing, purchase)
    print(f"Recorded user-supplied order: {purchase['artist']} — {purchase['title']}.")


def vg_plus_or_better(condition: str) -> bool:
    return condition.startswith(("Mint", "Near Mint", "Very Good Plus"))


def seller_candidate(listing: Dict[str, Any], profile: Dict[str, Any], want_ids: set[int], quick_artist_counts: Counter) -> Optional[Dict[str, Any]]:
    info = listing.get("basic_information") or listing.get("release", {})
    release_id = info.get("id")
    formats = listing_format_names(listing)
    condition = listing.get("condition", "")
    if not release_id or not listing_is_vinyl(formats) or not vg_plus_or_better(condition):
        return None
    styles = info.get("styles", [])
    genres = info.get("genres", [])
    profile_styles = {entry["name"]: entry["count"] for entry in profile.get("signals", {}).get("styles", [])}
    profile_genres = {entry["name"]: entry["count"] for entry in profile.get("signals", {}).get("genres", [])}
    core_hits = [style for style in styles if style in profile_styles]
    genre_hits = [genre for genre in genres if genre in profile_genres]
    exploration_words = {"Afrobeat", "Highlife", "African", "Bubblegum", "MPB", "Samba", "Latin Jazz", "Latin"}
    exploration_hits = [style for style in styles if style in exploration_words]
    artist = text(info.get("artists", [])) if info.get("artists") else str(info.get("artist", ""))
    score = sum(min(profile_styles[style], 8) * 1.4 for style in core_hits) + sum(min(profile_genres[genre], 8) * 0.7 for genre in genre_hits)
    if int(release_id) in want_ids:
        score += 45
    if artist in quick_artist_counts:
        score += min(quick_artist_counts[artist], 3) * 5
    score += len(exploration_hits) * 7
    demand = info.get("stats", {}).get("community", {}).get("in_wantlist", 0)
    score += min(math.log1p(int(demand or 0)) * 1.5, 10)
    price = listing_price(listing)
    return {
        "listing_id": listing.get("id"), "release_id": int(release_id), "artist": artist, "title": info.get("title", ""),
        "styles": styles, "genres": genres, "label": text(info.get("labels", [])) if info.get("labels") else str(info.get("label", "")), "catalog_number": text(info.get("labels", []), "catno") if info.get("labels") else str(info.get("catalog_number", "")),
        "year": info.get("year") or "", "formats": formats, "condition": condition, "sleeve_condition": listing.get("sleeve_condition", ""),
        "price": price, "currency": listing.get("price", {}).get("currency", ""), "listing_url": f"https://www.discogs.com/sell/item/{listing.get('id')}",
        "wantlist_match": int(release_id) in want_ids, "core_hits": core_hits, "exploration_hits": exploration_hits, "provisional_score": round(score, 2),
    }


def add_profile_matches(candidate: Dict[str, Any], feature: Dict[str, Any], profile: Dict[str, Any]) -> None:
    candidate["styles"] = feature.get("styles", [])
    candidate["genres"] = feature.get("genres", [])
    candidate["label"] = feature.get("labels", "") or candidate["label"]
    candidate["year"] = feature.get("year", "") or candidate["year"]
    profile_styles = {entry["name"]: entry["count"] for entry in profile.get("signals", {}).get("styles", [])}
    profile_genres = {entry["name"]: entry["count"] for entry in profile.get("signals", {}).get("genres", [])}
    candidate["core_hits"] = [style for style in candidate["styles"] if style in profile_styles]
    candidate["exploration_hits"] = [style for style in candidate["styles"] if style in {"Afrobeat", "Highlife", "African", "Bubblegum", "MPB", "Samba", "Latin Jazz", "Latin"}]
    candidate["provisional_score"] = round(
        candidate["provisional_score"]
        + sum(min(profile_styles[style], 8) * 1.4 for style in candidate["core_hits"])
        + sum(min(profile_genres[genre], 8) * 0.7 for genre in candidate["genres"] if genre in profile_genres)
        + len(candidate["exploration_hits"]) * 7,
        2,
    )


def community_score(feature: Dict[str, Any]) -> tuple[float, str, float, int]:
    rating = feature.get("community", {}).get("rating", {})
    average = float(rating.get("average") or 0)
    count = int(rating.get("count") or 0)
    if not count:
        return 0.0, "No community rating", 0.0, 0
    adjusted = ((average * count) + (3.5 * 25)) / (count + 25)
    confidence = min(math.log1p(count) / math.log(51), 1)
    return round(adjusted * 4 * confidence, 2), f"{average:.1f}/5 from {count} ratings", average, count


def command_scan_seller(args: argparse.Namespace) -> None:
    token = read_token(args.token_file, args.owner)
    if not token:
        raise SystemExit("Supply --token-file, set DISCOGS_TOKEN, or configure a local token.")
    profile = load_json(person_taste_profile_path(args.owner), {})
    if not profile:
        raise SystemExit("Run build-taste-profile before scanning a seller.")
    inventory = fetch_seller_inventory(args.seller, token, args.refresh_inventory)
    wantlist = load_json(person_wantlist_path(args.owner), {"releases": []})
    want_ids = {int(release["release_id"]) for release in wantlist.get("releases", []) if str(release.get("release_id", "")).isdigit()}
    quick = load_json(person_quick_crate_path(args.owner), {"records": []})
    quick_artist_counts = Counter(entry.get("artist", "") for entry in quick.get("records", []) if entry.get("artist"))
    quick_owned_keys = {
        artist_title_key(entry.get("artist", ""), entry.get("title", ""))
        for entry in quick.get("records", []) if entry.get("artist") and entry.get("title")
    }
    overrides = load_json(person_workspace_path(args.owner, "owned-overrides.json"), {"records": []}).get("records", [])
    override_owned_keys = {artist_title_key(record.get("artist", ""), record.get("title", "")) for record in overrides}
    purchases = [purchase for purchase in load_json(person_workspace_path(args.owner, "purchases.json"), {"purchases": []}).get("purchases", []) if purchase.get("status") == "ordered"]
    ordered_title_keys = {artist_title_key(purchase.get("artist", ""), purchase.get("title", "")) for purchase in purchases}
    known_owned_keys = quick_owned_keys | override_owned_keys | ordered_title_keys
    owned_ids = {record.get("discogs_release_id") for record in load_catalog().get("records", []) if record.get("owner", "").casefold() == args.owner.casefold()}
    owned_ids.update(purchase.get("release_id") for purchase in purchases)
    candidates = [seller_candidate(listing, profile, want_ids, quick_artist_counts) for listing in inventory.get("listings", [])]
    candidates = [candidate for candidate in candidates if candidate and candidate["release_id"] not in owned_ids and (args.max_price is None or candidate["price"] is None or candidate["price"] <= args.max_price)]
    if args.max_year is not None:
        candidates = [candidate for candidate in candidates if not str(candidate.get("year", "")).isdigit() or int(candidate["year"]) <= args.max_year]
    before_quick_exclusion = len(candidates)
    candidates = [candidate for candidate in candidates if artist_title_key(candidate["artist"], candidate["title"]) not in known_owned_keys]
    excluded_quick_titles = before_quick_exclusion - len(candidates)
    candidates.sort(key=lambda candidate: candidate["provisional_score"], reverse=True)
    feature_cache = load_json(RELEASE_FEATURES_PATH, {"schema_version": 1, "features": {}})
    features = feature_cache.setdefault("features", {})
    for candidate in candidates[:args.metadata_limit]:
        release_id = str(candidate["release_id"])
        if release_id not in features:
            features[release_id] = release_feature(discogs_request(f"/releases/{release_id}", token))
            feature_cache["updated_at"] = utc_now()
            write_json(RELEASE_FEATURES_PATH, feature_cache)
            time.sleep(1.1)
        add_profile_matches(candidate, features[release_id], profile)
        candidate["community_score"], candidate["community_summary"], candidate["community_rating_average"], candidate["community_rating_count"] = community_score(features[release_id])
    if args.min_rating is not None:
        candidates = [candidate for candidate in candidates if candidate.get("community_rating_average", 0) >= args.min_rating]
    prices = sorted(candidate["price"] for candidate in candidates if candidate["price"] is not None)
    for candidate in candidates:
        if candidate["price"] is not None and prices:
            candidate["price_score"] = round(10 * (1 - prices.index(candidate["price"]) / max(len(prices) - 1, 1)), 2)
        else:
            candidate["price_score"] = 0
        candidate["score"] = round(candidate["provisional_score"] + candidate.get("community_score", 0) + candidate["price_score"], 2)
        reasons = []
        if candidate["wantlist_match"]: reasons.append("already on Wantlist")
        if candidate["core_hits"]: reasons.append("core: " + ", ".join(candidate["core_hits"]))
        if candidate["exploration_hits"]: reasons.append("exploration: " + ", ".join(candidate["exploration_hits"]))
        if candidate.get("community_summary"): reasons.append(candidate["community_summary"])
        reasons.append(candidate["condition"])
        candidate["why"] = reasons
    best_by_release: Dict[int, Dict[str, Any]] = {}
    for candidate in candidates:
        current = best_by_release.get(candidate["release_id"])
        if current is None or candidate["score"] > current["score"] or (
            candidate["score"] == current["score"] and candidate["price"] is not None and (current["price"] is None or candidate["price"] < current["price"])
        ):
            best_by_release[candidate["release_id"]] = candidate
    best_by_artist_title: Dict[str, Dict[str, Any]] = {}
    for candidate in best_by_release.values():
        title_key = artist_title_key(candidate["artist"], candidate["title"])
        current = best_by_artist_title.get(title_key)
        if current is None or candidate["score"] > current["score"] or (
            candidate["score"] == current["score"] and candidate["price"] is not None and (current["price"] is None or candidate["price"] < current["price"])
        ):
            best_by_artist_title[title_key] = candidate
    recommendations = sorted(best_by_artist_title.values(), key=lambda candidate: candidate["score"], reverse=True)[:args.limit]
    first_listing = inventory.get("listings", [{}])[0]
    seller_info = first_listing.get("seller", {})
    shipping_text = str(seller_info.get("shipping", ""))
    output = {
        "schema_version": 1, "generated_at": utc_now(), "seller": args.seller, "inventory_listings": len(inventory.get("listings", [])),
        "inventory_pagination_truncated": inventory.get("pagination_truncated", False), "inventory_reported_pages": inventory.get("reported_pages", inventory.get("pages", 1)),
        "qualified_vinyl_vg_plus_or_better": len(candidates), "qualified_distinct_releases": len(best_by_release), "qualified_distinct_artist_titles": len(best_by_artist_title), "metadata_enriched_candidates": min(len(candidates), args.metadata_limit),
        "filters": {"max_price": args.max_price, "currency": next((candidate["currency"] for candidate in candidates if candidate.get("currency")), ""), "minimum_release_rating": args.min_rating, "maximum_year": args.max_year},
        "seller_summary": {
            "ships_from": first_listing.get("ships_from", ""), "rating_percent": seller_info.get("stats", {}).get("rating", ""),
            "rating_count": seller_info.get("stats", {}).get("total", ""), "combines_orders": "combine order" in shipping_text.casefold(),
            "free_shipping_mentioned": "free shipping" in shipping_text.casefold(),
        },
        "excluded_known_owned_title_matches": excluded_quick_titles, "pending_ordered_releases": len(purchases),
        "recommendations": recommendations,
        "shipping_note": "All recommendations are from one seller, so they can be combined in one order. Exact shipping bands, destination eligibility, and any seller order limit must be verified in the Discogs cart.",
    }
    output_path = person_seller_reports_dir(args.owner) / f"seller-scout-{args.seller.casefold()}.json"
    write_json(output_path, output)
    markdown_path = person_seller_reports_dir(args.owner) / f"seller-scout-{args.seller.casefold()}.md"
    seller_summary = output["seller_summary"]
    filter_text = []
    if args.max_price is not None: filter_text.append(f"price at or below {output['filters']['currency']} {args.max_price:.2f}")
    if args.min_rating is not None: filter_text.append(f"release community rating at least {args.min_rating:.1f}/5")
    if args.max_year is not None: filter_text.append(f"released no later than {args.max_year}")
    lines = [f"# Seller Scout: {args.seller}", "", f"{len(candidates)} Vinyl listings at VG+ or better qualified from {len(inventory.get('listings', []))} active listings; {excluded_quick_titles} known-owned title matches were excluded.", "", f"Filters: {', '.join(filter_text) if filter_text else 'none beyond format, condition, and ownership'}.", "", f"Seller: {seller_summary['rating_percent']}% positive from {seller_summary['rating_count']} ratings · ships from {seller_summary['ships_from']} · combines orders: {'yes' if seller_summary['combines_orders'] else 'not stated'} · free shipping mentioned: {'yes' if seller_summary['free_shipping_mentioned'] else 'no'}.", "", output["shipping_note"], "", "## Recommendations", ""]
    if output["inventory_pagination_truncated"]:
        lines[3:3] = [f"Note: Discogs only permits this tool to inspect the first 100 of {output['inventory_reported_pages']} seller inventory pages. The report is ranked from the accessible listings.", ""]
    for number, candidate in enumerate(recommendations, start=1):
        price = f"{candidate['currency']} {candidate['price']:.2f}" if candidate["price"] is not None else "price unavailable"
        lines.extend([f"{number}. **{candidate['artist']} — {candidate['title']}** — {price}; {candidate['condition']}", f"   - {', '.join(candidate['why'])}", f"   - {candidate['listing_url']}"])
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Seller Scout wrote {len(recommendations)} recommendations to {output_path} and {markdown_path}.")


def command_fetch_collection(args: argparse.Namespace) -> None:
    token = read_token(args.token_file, args.owner)
    if not token:
        raise SystemExit("Supply --token-file or set DISCOGS_TOKEN.")
    username = args.username or person_context(args.owner)["discogs_username"]
    if not username:
        username = discogs_request("/oauth/identity", token).get("username")
    if not username:
        raise SystemExit("Discogs did not return an account username.")
    folders = discogs_request(f"/users/{quote(username)}/collection/folders", token).get("folders", [])
    # Discogs exposes folder 0 as the virtual "All" collection. Fetching it as
    # well as every physical folder duplicates copies that are categorised.
    all_folder = next((folder for folder in folders if folder.get("id") == 0), None)
    if all_folder:
        folders = [all_folder]
    incoming = []
    for folder in folders:
        folder_id = folder["id"]
        releases = paged_releases(f"/users/{quote(username)}/collection/folders/{folder_id}/releases", token)
        for release in releases:
            release["folder_id"] = folder_id
            incoming.append(normalise_api_item(release, args.owner))
    catalog = load_catalog()
    added, updated = merge_records(catalog, incoming)
    reconciliation = {"removed": 0, "preserved": 0, "review_updates": 0}
    if args.reconcile:
        reconciliation = reconcile_discogs_snapshot(catalog, incoming, args.owner)
    save_catalog(catalog)
    message = f"Fetched {len(incoming)} records for {args.owner}: {added} added, {updated} updated."
    if args.reconcile:
        message += (
            f" Reconciled {reconciliation['removed']} stale Discogs rows; "
            f"preserved {reconciliation['preserved']} local-only rows; "
            f"updated {reconciliation['review_updates']} saved review references."
        )
    print(message)


def command_enrich(args: argparse.Namespace) -> None:
    token = read_token(args.token_file, args.owner)
    catalog = load_catalog()
    selected = [record for record in catalog["records"] if not args.owner or record["owner"].lower() == args.owner.lower()]
    changed = 0
    for record in selected:
        if record.get("tracklist") and not args.refresh:
            continue
        release = discogs_request(f"/releases/{record['discogs_release_id']}", token)
        record["cover_image"] = release.get("images", [{}])[0].get("uri", record.get("cover_image", ""))
        record["discogs_url"] = release.get("uri", record.get("discogs_url", ""))
        tracklist = []
        for track in release.get("tracklist", []):
            if track.get("type_", "track") != "track":
                continue
            track_artists = text(track.get("artists", []))
            tracklist.append({
                "position": track.get("position", ""),
                "artist": track_artists or record.get("artist", ""),
                "title": track.get("title", ""),
                "duration": track.get("duration", ""),
                "type": track.get("type_", "track"),
                "dj_notes": {},
            })
        record["tracklist"] = tracklist
        changed += 1
        time.sleep(1.1)
    save_catalog(catalog)
    print(f"Enriched {changed} releases with Discogs tracklists.")


def getsongbpm_artist_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    if isinstance(value, list):
        return ", ".join(getsongbpm_artist_name(item) for item in value if getsongbpm_artist_name(item))
    return str(value or "").strip()


def rank_getsongbpm_candidates(artist: str, title: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked_candidates = []
    for candidate in candidates:
        candidate_artist = getsongbpm_artist_name(candidate.get("artist"))
        candidate_title = str(candidate.get("title") or "").strip()
        title_score = similarity(title, candidate_title)
        artist_score = similarity(artist, candidate_artist)
        score = 0.65 * title_score + 0.35 * artist_score
        if title_score == 1.0 and artist_score == 1.0:
            confidence = "high"
        elif score >= 0.78 and title_score >= 0.82:
            confidence = "high"
        elif score >= 0.60 and title_score >= 0.65:
            confidence = "medium"
        else:
            confidence = "low"
        ranked_candidates.append({
            "candidate": candidate,
            "artist": candidate_artist,
            "title": candidate_title,
            "score": round(score, 3),
            "confidence": confidence,
        })
    return sorted(ranked_candidates, key=lambda item: item["score"], reverse=True)


def apply_getsongbpm_metadata(track: Dict[str, Any], match: Optional[Dict[str, Any]], checked_at: str) -> None:
    """Write provider data while leaving an explicit user override untouched."""
    if track.get("bpm_user_override"):
        return
    if not match:
        track.update({
            "bpm": None,
            "key": "",
            "open_key": "",
            "bpm_source": "getsongbpm",
            "bpm_match_confidence": "none",
            "bpm_match": None,
            "bpm_checked_at": checked_at,
        })
        return
    candidate = match["candidate"]
    tempo = candidate.get("tempo")
    try:
        bpm = float(tempo) if tempo not in (None, "") else None
        if bpm is not None and bpm.is_integer():
            bpm = int(bpm)
    except (TypeError, ValueError):
        bpm = None
    track.update({
        "bpm": bpm,
        "key": str(candidate.get("key_of") or "").strip(),
        "open_key": str(candidate.get("open_key") or "").strip(),
        "danceability": candidate.get("danceability"),
        "bpm_source": "getsongbpm",
        "bpm_match_confidence": match["confidence"],
        "bpm_match": {
            "id": candidate.get("id"),
            "artist": match["artist"],
            "title": match["title"],
            "uri": candidate.get("uri", ""),
            "score": match["score"],
        },
        "bpm_checked_at": checked_at,
    })


def command_enrich_bpm(args: argparse.Namespace) -> None:
    api_key = read_getsongbpm_key(args.api_key_file)
    if not api_key:
        raise SystemExit(
            "No GetSongBPM API key found. Supply --api-key-file, set GETSONGBPM_API_KEY, "
            "or store it as cue-crate.getsongbpm-api-key in macOS Keychain."
        )
    catalog = load_catalog()
    selected = [
        record for record in catalog.get("records", [])
        if not args.owner or record.get("owner", "").casefold() == args.owner.casefold()
    ]
    search_cache = load_json(GETSONGBPM_CACHE_PATH, {"schema_version": 1, "queries": {}})
    cached_queries = search_cache.setdefault("queries", {})
    tracks_seen = tracks_checked = matched = unmatched = skipped = 0
    cached = 0
    for record in selected:
        tracklist = record.get("tracklist") or []
        for track in tracklist:
            if args.limit and tracks_checked >= args.limit:
                break
            tracks_seen += 1
            if track.get("bpm_user_override") and not args.refresh:
                skipped += 1
                continue
            if track.get("bpm_source") == "getsongbpm" and not args.refresh:
                skipped += 1
                continue
            artist = str(track.get("artist") or record.get("artist") or "").strip()
            title = str(track.get("title") or "").strip()
            if not title:
                continue
            query_key = f"{normalise_match_text(artist)}::{normalise_match_text(title)}"
            if query_key in cached_queries and not args.refresh:
                candidates = cached_queries[query_key]
                cached += 1
            else:
                try:
                    response = getsongbpm_request("/search/", api_key, {
                        "type": "both",
                        "lookup": f"song:{title} artist:{artist}" if artist else f"song:{title}",
                        "limit": 10,
                    })
                except RuntimeError as exc:
                    raise SystemExit(str(exc)) from exc
                candidates = response.get("search", []) if isinstance(response, dict) else []
                cached_queries[query_key] = candidates
                search_cache["updated_at"] = utc_now()
                write_json(GETSONGBPM_CACHE_PATH, search_cache)
            ranked_candidates = rank_getsongbpm_candidates(artist, title, candidates)
            acceptable = [item for item in ranked_candidates if item["confidence"] in {"high", "medium"}]
            match = acceptable[0] if acceptable else None
            checked_at = utc_now()
            apply_getsongbpm_metadata(track, match, checked_at)
            tracks_checked += 1
            if match:
                matched += 1
                print(f"BPM {record.get('artist', '')} — {title}: {match['candidate'].get('tempo', '?')} ({match['confidence']}, {match['score']})", flush=True)
            else:
                unmatched += 1
                print(f"BPM no confident match: {record.get('artist', '')} — {title}", flush=True)
            time.sleep(0.15)
        if args.limit and tracks_checked >= args.limit:
            break
    search_cache["updated_at"] = utc_now()
    write_json(GETSONGBPM_CACHE_PATH, search_cache)
    save_catalog(catalog)
    print(f"GetSongBPM checked {tracks_checked}/{tracks_seen} tracks: {matched} matched, {unmatched} need review, {skipped} already enriched/overridden, {cached} served from cache.")


PHOTO_PROMPT = """You are cataloguing a photograph that shows several separate vinyl records.
Identify EACH physical record visible, ordered left-to-right then top-to-bottom. Return ONLY a JSON object:
{"records":[{"position":1,"artist":"string or null","title":"string or null","label":"string or null","catalog_number":"string or null","visible_text":"string","confidence":"high|medium|low"}]}
Only transcribe text that is visible. Do not guess titles, artists, editions, BPM, genre, or Discogs IDs. A cover/label is not enough to distinguish every pressing; confidence should reflect that."""


INTAKE_PROMPT = """You are identifying one physical vinyl record from several photographs of the same item.
Reconcile all views before answering. The primary evidence view is usually the back cover; optional label, barcode close-up, and front views provide context.
Return ONLY a JSON object with this shape:
{"artist":"string or null","title":"string or null","label":"string or null","catalog_number":"string or null","barcode":"string or null","country":"string or null","year":"string or null","format":"string or null","visible_text":"string","confidence":"high|medium|low","confidence_reason":"string"}
Only report text and identifiers visible in the supplied photographs. Do not guess a pressing or Discogs release ID. Treat these as different fields: catalog_number is the label/sleeve catalogue or matrix code (for example TSR 330701), while barcode is the complete numeric string printed directly under the barcode bars (preserve readable spaces, for example 4 006759 984444). Never copy a nearby number above the bars into barcode. Prefer a dedicated BARCODE view when present; if it is not legible, return null rather than inventing digits."""


def image_data_url(path: Path, max_dimension: int = 2048) -> str:
    supported = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
    if path.suffix.lower() not in supported:
        raise SystemExit(f"Unsupported photo type: {path.name}")
    # The phone originals are 5712 × 4284 HEICs. Quick Look decodes their HDR
    # variant correctly; sips rendered them as black JPEGs on this macOS setup.
    if path.suffix.lower() in {".heic", ".heif"}:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = subprocess.run(
                ["qlmanage", "-t", "-s", str(max_dimension), "-o", temporary_dir, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            previews = list(Path(temporary_dir).glob("*.png"))
            if result.returncode or not previews:
                raise SystemExit(f"Could not prepare HEIC photo: {path.name}")
            encoded = base64.b64encode(previews[0].read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    # Other source formats use a 2048px JPEG upload for the same reason.
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
        temporary = Path(handle.name)
    temporary.unlink()
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", "-Z", str(max_dimension), str(path), "--out", str(temporary)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        temporary.unlink(missing_ok=True)
        raise SystemExit(f"Could not prepare photo: {path.name}")
    try:
        encoded = base64.b64encode(temporary.read_bytes()).decode("ascii")
    finally:
        temporary.unlink(missing_ok=True)
    return f"data:image/jpeg;base64,{encoded}"


def minimax_photo_completion(api_key: str, photo: Path, max_tokens: int) -> str:
    """Send one image to the Anthropic-compatible MiniMax M3 Go endpoint."""
    # MiniMax's Anthropic-compatible gateway closes very large base64 image
    # bodies; 1024px is about 3.2 MB for the current six-record grids.
    data_url = image_data_url(photo, max_dimension=1024)
    header, encoded = data_url.split(",", 1)
    media_type = header.removeprefix("data:").removesuffix(";base64")
    payload = {
        "model": "minimax-m3",
        "max_tokens": max_tokens,
        "system": PHOTO_PROMPT,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": encoded}},
                {"type": "text", "text": "Identify the six physical records in this photograph. JSON only."},
            ],
        }],
    }
    request = Request(
        "https://opencode.ai/zen/go/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"MiniMax returned HTTP {exc.code}: {detail}")
    except URLError as exc:
        raise SystemExit(f"MiniMax could not be reached: {exc.reason}")
    except OSError as exc:
        if exc.errno == 32:
            raise SystemExit("MiniMax's OpenCode Go gateway closed the image request. Text requests work, but image input is not currently usable through this route.")
        raise
    return "\n".join(block.get("text", "") for block in body.get("content", []) if block.get("type") == "text")


def command_analyse_photos(args: argparse.Namespace) -> None:
    try:
        from openai import APIError, APITimeoutError, OpenAI
    except ImportError:
        raise SystemExit("Install optional photo support first: python3 -m pip install -r requirements.txt")
    api_key = read_opencode_go_key(args.api_key_file)
    if not api_key:
        raise SystemExit(
            "No OpenCode Go credential found. Run `opencode auth login` and choose OpenCode Go, "
            "set OPENCODE_GO_API_KEY, or pass --api-key-file PATH."
        )
    photo_dir = Path(args.photo_dir).expanduser()
    photos = sorted(path for path in photo_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})
    existing_paths = set()
    photo_candidates_path = person_workspace_path(args.owner, "photo-candidates.json")
    if args.resume and photo_candidates_path.exists():
        result = json.loads(photo_candidates_path.read_text(encoding="utf-8"))
        existing_paths = {entry.get("path") for entry in result.get("photos", [])}
        photos = [photo for photo in photos if str(photo) not in existing_paths]
    else:
        result = {"generated_at": utc_now(), "owner": args.owner, "photos": []}
    if args.limit:
        photos = photos[:args.limit]
    if not photos:
        raise SystemExit(f"No supported photos found in {photo_dir}")
    client = None
    if args.provider in {"kimi", "mimo"}:
        client = OpenAI(api_key=api_key, base_url="https://opencode.ai/zen/go/v1", timeout=90.0, max_retries=0)
    model = args.model or ("mimo-v2.5" if args.provider == "mimo" else "kimi-k2.6")
    for photo in photos:
        if args.provider == "minimax":
            content = minimax_photo_completion(api_key, photo, args.max_tokens)
            if not content:
                raise SystemExit(f"MiniMax returned no final JSON for {photo.name}.")
        else:
            try:
                image_size = 1024 if args.provider == "mimo" else 2048
                completion_args = dict(
                    model=model,
                    messages=[
                        {"role": "system", "content": PHOTO_PROMPT},
                        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_data_url(photo, max_dimension=image_size), "detail": "high"}}]},
                    ],
                    temperature=0,
                    # Kimi may use part of this allowance for reasoning before emitting
                    # the JSON. Six covers need more room than a single SellBucket item.
                    max_tokens=args.max_tokens,
                )
                if args.provider == "mimo":
                    completion_args["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**completion_args)
            except APITimeoutError:
                raise SystemExit(f"{args.provider.title()} timed out while analysing {photo.name}. No result was saved for that photo; retry later or choose another provider.")
            except APIError as exc:
                raise SystemExit(f"{args.provider.title()} could not analyse {photo.name}: {exc}")
            message = response.choices[0].message
            if not message.content:
                finish_reason = response.choices[0].finish_reason
                raise SystemExit(f"{args.provider.title()} returned no final JSON for {photo.name} (finish reason: {finish_reason}).")
            content = message.content
        content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            identified = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Could not parse analysis for {photo.name}: {exc}")
        result["photos"].append({"path": str(photo), "records": identified.get("records", [])})
        ensure_data_dir()
        photo_candidates_path.parent.mkdir(parents=True, exist_ok=True)
        photo_candidates_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Analysed {photo.name}: {len(identified.get('records', []))} records found", flush=True)
    print(f"Review candidates at {photo_candidates_path}")


def intake_bundle_for(owner: str, upload_id: Optional[str] = None) -> tuple[Path, Dict[str, Any]]:
    inbox = person_inbox_dir(owner)
    if upload_id:
        bundle_dir = inbox / upload_id
        metadata_path = bundle_dir / "intake.json"
        if not metadata_path.exists():
            raise SystemExit(f"No intake bundle found for upload ID {upload_id!r}.")
        return bundle_dir, load_json(metadata_path, {})
    bundles = sorted(inbox.glob("*/intake.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not bundles:
        raise SystemExit(f"No uploaded intake bundles found for {owner}.")
    metadata_path = bundles[0]
    return metadata_path.parent, load_json(metadata_path, {})


def parse_model_json(content: str, label: str) -> Dict[str, Any]:
    cleaned = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse analysis for {label}: {exc}") from exc
    if isinstance(payload.get("record"), dict):
        payload = payload["record"]
    if isinstance(payload.get("records"), list):
        payload = payload["records"][0] if payload["records"] else {}
    if not isinstance(payload, dict):
        raise SystemExit(f"The analysis for {label} did not contain a record object.")
    return payload


def command_analyse_intake(args: argparse.Namespace) -> None:
    try:
        from openai import APIError, APITimeoutError, OpenAI
    except ImportError:
        raise SystemExit("Install optional photo support first: python3 -m pip install -r requirements.txt")
    api_key = read_opencode_go_key(args.api_key_file)
    if not api_key:
        raise SystemExit(
            "No OpenCode Go credential found. Run `opencode auth login` and choose OpenCode Go, "
            "set OPENCODE_GO_API_KEY, or pass --api-key-file PATH."
        )
    bundle_dir, metadata = intake_bundle_for(args.owner, args.upload_id)
    upload_id = str(metadata.get("upload_id") or bundle_dir.name)
    review_path = person_workspace_path(args.owner, "intake-review.json")
    intake_review = load_json(review_path, {"schema_version": 1, "owner": args.owner, "items": []})
    existing = {item.get("id"): item for item in intake_review.get("items", [])}
    item_id = f"intake::{upload_id}"
    if item_id in existing and not args.refresh:
        raise SystemExit(f"{upload_id} already has an intake analysis. Re-run with --refresh to replace it.")
    files = metadata.get("files", {})
    ordered_roles = ["evidence", "back", "label", "barcode", "front", "other"]
    views = {}
    for role in ordered_roles:
        filename = (files.get(role) or {}).get("filename")
        path = bundle_dir / str(filename or "")
        if filename and path.exists() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
            views[role] = str(path)
    if not views:
        raise SystemExit(f"No supported photos found in intake bundle {upload_id}.")
    primary_path = Path(views.get("evidence") or next(iter(views.values())))
    client = OpenAI(api_key=api_key, base_url="https://opencode.ai/zen/go/v1", timeout=120.0, max_retries=0)
    model = args.model or ("mimo-v2.5" if args.provider == "mimo" else "kimi-k2.6")
    content = [{"type": "text", "text": "These are multiple views of one physical record. Reconcile them into one identification."}]
    for role, path_string in views.items():
        content.append({"type": "text", "text": f"VIEW: {role}"})
        content.append({"type": "image_url", "image_url": {"url": image_data_url(Path(path_string), max_dimension=1024 if args.provider == "mimo" else 2048), "detail": "high"}})
    completion_args = {
        "model": model,
        "messages": [{"role": "system", "content": INTAKE_PROMPT}, {"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": args.max_tokens,
    }
    if args.provider == "mimo":
        completion_args["response_format"] = {"type": "json_object"}
    try:
        response = client.chat.completions.create(**completion_args)
    except APITimeoutError as exc:
        raise SystemExit(f"{args.provider.title()} timed out while analysing intake {upload_id}.") from exc
    except APIError as exc:
        raise SystemExit(f"{args.provider.title()} could not analyse intake {upload_id}: {exc}") from exc
    message = response.choices[0].message
    if not message.content:
        raise SystemExit(f"{args.provider.title()} returned no final JSON for intake {upload_id}.")
    observed = parse_model_json(message.content, upload_id)
    observed = {field: observed.get(field, "") for field in ("artist", "title", "label", "catalog_number", "barcode", "country", "year", "format", "visible_text", "confidence", "confidence_reason")}
    records = [record for record in load_catalog().get("records", []) if record.get("owner", "").casefold() == args.owner.casefold()]
    candidate = {"position": 1, **observed}
    old = existing.get(item_id, {})
    item = {
        "id": item_id, "upload_id": upload_id, "owner": args.owner, "bundle_path": str(bundle_dir),
        "views": views, "observed": candidate, "analysis_provider": args.provider, "analysis_model": model,
        "analyzed_at": utc_now(), "status": old.get("status", "unreviewed"),
        "matched_record_id": old.get("matched_record_id"), "manual_identification": old.get("manual_identification"),
        "discogs_selection": old.get("discogs_selection"), "note": old.get("note", ""),
        "suggestions": record_suggestions(candidate, records),
    }
    intake_review["owner"] = args.owner
    intake_review["generated_at"] = utc_now()
    intake_review["items"] = [item if existing_item.get("id") == item_id else existing_item for existing_item in intake_review.get("items", [])]
    if not any(existing_item.get("id") == item_id for existing_item in intake_review["items"]):
        intake_review["items"].append(item)
    write_json(review_path, intake_review)

    candidates_path = person_workspace_path(args.owner, "photo-candidates.json")
    candidates = load_json(candidates_path, {"generated_at": utc_now(), "owner": args.owner, "photos": []})
    candidates["photos"] = [photo for photo in candidates.get("photos", []) if photo.get("intake_id") != upload_id]
    candidates["photos"].append({"path": str(primary_path), "intake_id": upload_id, "views": views, "records": [candidate]})
    candidates["generated_at"] = utc_now()
    write_json(candidates_path, candidates)
    review = build_review(args.owner)
    print(f"Analysed intake {upload_id}: {observed.get('artist') or 'unknown artist'} — {observed.get('title') or 'unknown title'} ({observed.get('confidence') or 'unknown'} confidence).")
    print(f"Saved intake review to {review_path}; review queue now contains {len(review.get('items', []))} items.")


def command_add_to_discogs(args: argparse.Namespace) -> None:
    token = read_token(args.token_file, args.owner)
    if not token:
        raise SystemExit("Supply --token-file or set DISCOGS_TOKEN.")
    additions = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(additions, list) or not all(str(item.get("release_id", "")).isdigit() for item in additions):
        raise SystemExit("Input must be a JSON array of objects with a numeric release_id.")
    mismatched = {str(item.get("owner", "")).casefold() for item in additions if item.get("owner") and str(item.get("owner")).casefold() != args.owner.casefold()}
    if mismatched:
        raise SystemExit("The additions queue belongs to another owner; run this command as that person.")
    username = args.username or person_context(args.owner)["discogs_username"]
    if not username:
        raise SystemExit("Supply --username or set providers.discogs.username for this profile in config/profiles.local.json.")
    target = f"/users/{quote(username)}/collection/folders/{args.folder_id}/releases"
    if args.apply:
        token_username = str(discogs_request("/oauth/identity", token).get("username") or "")
        if token_username.casefold() != username.casefold():
            raise SystemExit(f"The supplied token belongs to {token_username or 'an unknown account'}, not {username}. Refusing to write.")
    existing_ids = set()
    if args.skip_existing:
        existing_ids = {
            int(release.get("id"))
            for release in paged_releases(f"/users/{quote(username)}/collection/folders/0/releases", token)
            if str(release.get("id", "")).isdigit()
        }
        print(f"{len(additions)} approved releases targeted at Discogs folder {args.folder_id}; {len(existing_ids)} existing collection releases checked.")
    else:
        print(f"{len(additions)} approved releases targeted at Discogs folder {args.folder_id}.")
    for item in additions:
        release_id = item["release_id"]
        if release_id in existing_ids:
            print(f"  SKIP existing release {release_id}")
            continue
        print(f"  {'ADD' if args.apply else 'WOULD ADD'} release {release_id}")
        if args.apply:
            discogs_request(f"{target}/{release_id}", token, method="POST")
            time.sleep(1.1)
    print("Completed." if args.apply else "Dry run only. Re-run with --apply after checking the release IDs.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    profiles = commands.add_parser("profiles", help="List configured local profiles; tokens are never shown or stored here")
    profiles.set_defaults(func=command_list_profiles)

    people = commands.add_parser("people", help="Legacy alias for profiles")
    people.set_defaults(func=command_list_profiles)

    collectives = commands.add_parser("collectives", help="List configured local collaborations and their members")
    collectives.add_argument("--profile", help="Only show collectives that include this profile")
    collectives.set_defaults(func=command_list_collectives)

    migrate_token = commands.add_parser("migrate-provider-token", help="Move a legacy machine-wide OAuth token into one profile's local credential store")
    migrate_token.add_argument("--owner", required=True, help="Configured profile ID or display name that should receive the credential")
    migrate_token.add_argument("--provider", required=True, choices=["youtube", "spotify"])
    migrate_token.set_defaults(func=command_migrate_provider_token)

    migrate_profile = commands.add_parser("migrate-profile-layout", help="Move legacy single-profile local state into a profile-specific layout")
    migrate_profile.add_argument("--owner", required=True, help="Configured profile ID or display name that owns the existing local state")
    migrate_profile.set_defaults(func=command_migrate_person_layout)

    migrate_people = commands.add_parser("migrate-person-layout", help="Legacy alias for migrate-profile-layout")
    migrate_people.add_argument("--owner", required=True, help="Configured profile ID or display name that owns the existing local state")
    migrate_people.set_defaults(func=command_migrate_person_layout)

    location = commands.add_parser("set-record-location", help="Place one owned physical copy in or out of a shared crate/bin")
    location.add_argument("--owner", required=True, help="Configured person ID or display name that owns the physical copy")
    location.add_argument("--record-id", required=True, help="Exact local catalogue record ID")
    location.add_argument("--location", required=True, help="Location label, for example regular-bar-bin")
    location.add_argument("--remove", action="store_true", help="Remove this location instead of adding it")
    location.set_defaults(func=command_set_record_location)

    share_record = commands.add_parser("set-record-collective", help="Share one owned physical copy with a configured collective")
    share_record.add_argument("--owner", required=True, help="Configured profile ID or display name that owns the physical copy")
    share_record.add_argument("--record-id", required=True, help="Exact local catalogue record ID")
    share_record.add_argument("--collective", required=True, help="Configured collective ID or display name")
    share_record.add_argument("--remove", action="store_true", help="Remove this collective scope instead of adding it")
    share_record.set_defaults(func=command_set_record_collective)

    export_bundle = commands.add_parser("export-profile-bundle", help="Create a credential-free catalogue/quick-crate handoff for one profile")
    export_bundle.add_argument("--owner", required=True, help="Configured profile ID or display name to export")
    export_bundle.add_argument("--output", required=True, help="Portable JSON bundle path to send to a collaborator")
    export_bundle.set_defaults(func=command_export_person_bundle)

    export_person_bundle = commands.add_parser("export-person-bundle", help="Legacy alias for export-profile-bundle")
    export_person_bundle.add_argument("--owner", required=True, help="Configured profile ID or display name to export")
    export_person_bundle.add_argument("--output", required=True, help="Portable JSON bundle path to send to a collaborator")
    export_person_bundle.set_defaults(func=command_export_person_bundle)

    import_bundle = commands.add_parser("import-profile-bundle", help="Merge a collaborator's credential-free bundle into this shared local crate")
    import_bundle.add_argument("--owner", required=True, help="Configured profile ID or display name expected in the bundle")
    import_bundle.add_argument("--input", required=True, help="Portable JSON bundle received from the collaborator")
    import_bundle.add_argument("--replace-quick-crate", action="store_true", help="Replace this profile's existing quick-crate export after checking it")
    import_bundle.set_defaults(func=command_import_person_bundle)

    import_person_bundle = commands.add_parser("import-person-bundle", help="Legacy alias for import-profile-bundle")
    import_person_bundle.add_argument("--owner", required=True, help="Configured profile ID or display name expected in the bundle")
    import_person_bundle.add_argument("--input", required=True, help="Portable JSON bundle received from the collaborator")
    import_person_bundle.add_argument("--replace-quick-crate", action="store_true", help="Replace this profile's existing quick-crate export after checking it")
    import_person_bundle.set_defaults(func=command_import_person_bundle)

    csv_parser = commands.add_parser("import-csv", help="Import a Discogs collection CSV into the shared catalogue")
    csv_parser.add_argument("--owner", required=True)
    csv_parser.add_argument("--input", required=True)
    csv_parser.set_defaults(func=command_import_csv)

    fetch = commands.add_parser("fetch-collection", help="Read one owner's Discogs collection into the catalogue")
    fetch.add_argument("--owner", required=True, help="Display name used in the shared catalogue")
    fetch.add_argument("--username", help="Discogs username; omitted uses the token owner's account")
    fetch.add_argument("--token-file", help="Path to a local personal access token")
    fetch.add_argument("--reconcile", action="store_true", help="Remove stale Discogs API rows for this owner while preserving locally reviewed records")
    fetch.set_defaults(func=command_fetch_collection)

    wantlist = commands.add_parser("fetch-wantlist", help="Read one owner's Discogs Wantlist as a local taste signal")
    wantlist.add_argument("--owner", required=True)
    wantlist.add_argument("--username", help="Discogs username; omitted uses the token owner's account")
    wantlist.add_argument("--token-file", help="Optional token file; omitted reads DISCOGS_TOKEN or macOS Keychain")
    wantlist.set_defaults(func=command_fetch_wantlist)

    features = commands.add_parser("fetch-release-features", help="Cache Discogs genre/style metadata for an owner's catalogue")
    features.add_argument("--owner", required=True)
    features.add_argument("--token-file", help="Optional token file; omitted reads DISCOGS_TOKEN or macOS Keychain")
    features.add_argument("--refresh", action="store_true", help="Refetch feature metadata already in the local cache")
    features.add_argument("--limit", type=int, help="Fetch at most N missing releases; safe to repeat")
    features.set_defaults(func=command_fetch_release_features)

    profile = commands.add_parser("build-taste-profile", help="Build an explainable profile from local crate, Wantlist, and release metadata")
    profile.add_argument("--owner", required=True)
    profile.set_defaults(func=command_build_taste_profile)

    seller_scout = commands.add_parser("scan-seller", help="Rank one seller's Vinyl inventory against your crate and Wantlist")
    seller_scout.add_argument("--owner", required=True)
    seller_scout.add_argument("--seller", required=True)
    seller_scout.add_argument("--token-file", help="Optional token file; omitted uses configured token lookup")
    seller_scout.add_argument("--limit", default=10, type=int, help="Number of recommendations to return")
    seller_scout.add_argument("--metadata-limit", default=30, type=int, help="Top provisional candidates to enrich with community ratings")
    seller_scout.add_argument("--max-price", type=float, help="Optional per-item ceiling in the seller's listing currency")
    seller_scout.add_argument("--min-rating", type=float, help="Require this minimum Discogs release community-rating average")
    seller_scout.add_argument("--max-year", type=int, help="Optional latest release year to include")
    seller_scout.add_argument("--refresh-inventory", action="store_true", help="Refetch cached seller inventory")
    seller_scout.set_defaults(func=command_scan_seller)

    owned_title = commands.add_parser("add-owned-title", help="Exclude a manually known owned title from seller recommendations")
    owned_title.add_argument("--owner", required=True)
    owned_title.add_argument("--artist", required=True)
    owned_title.add_argument("--title", required=True)
    owned_title.add_argument("--note", default="")
    owned_title.set_defaults(func=command_add_owned_title)

    order = commands.add_parser("record-order", help="Record ordered Discogs listings locally and exclude them from future seller scans")
    order.add_argument("--owner", required=True)
    order.add_argument("--seller", help="Optional seller username safety check")
    order.add_argument("--listing-id", action="append", required=True, help="Repeat once for each Discogs marketplace listing ID")
    order.add_argument("--token-file", help="Optional token file; omitted uses configured token lookup")
    order.set_defaults(func=command_record_order)

    manual_order = commands.add_parser("record-manual-order", help="Record an ordered listing from receipt details when it is no longer in inventory")
    manual_order.add_argument("--owner", required=True)
    manual_order.add_argument("--listing-id", required=True)
    manual_order.add_argument("--artist", required=True)
    manual_order.add_argument("--title", required=True)
    manual_order.add_argument("--seller")
    manual_order.add_argument("--release-id", type=int)
    manual_order.add_argument("--label", default="")
    manual_order.add_argument("--catalog-number", default="")
    manual_order.add_argument("--year", type=int)
    manual_order.add_argument("--format", default="")
    manual_order.add_argument("--media-condition", default="")
    manual_order.add_argument("--sleeve-condition", default="")
    manual_order.add_argument("--price", type=float)
    manual_order.add_argument("--currency", default="USD")
    manual_order.set_defaults(func=command_record_manual_order)

    enrich = commands.add_parser("enrich", help="Add Discogs tracklists to imported releases")
    enrich.add_argument("--owner", help="Only enrich records for this owner")
    enrich.add_argument("--token-file", help="Optional token for better API allowance")
    enrich.add_argument("--refresh", action="store_true", help="Replace existing tracklists")
    enrich.set_defaults(func=command_enrich)

    enrich_bpm = commands.add_parser("enrich-bpm", help="Look up track-level BPM/key metadata from GetSongBPM")
    enrich_bpm.add_argument("--owner", help="Limit enrichment to one configured owner; omitted processes the combined catalogue")
    enrich_bpm.add_argument("--api-key-file", help="Local GetSongBPM API-key file; omitted uses env/config/Keychain lookup")
    enrich_bpm.add_argument("--limit", type=int, help="Check at most N tracks (useful for a first test)")
    enrich_bpm.add_argument("--refresh", action="store_true", help="Recheck tracks even when they already have provider metadata")
    enrich_bpm.set_defaults(func=command_enrich_bpm)

    photos = commands.add_parser("analyse-photos", help="Create review-only drafts from multi-record photos")
    photos.add_argument("--owner", required=True)
    photos.add_argument("--photo-dir", required=True, help="Folder containing the six-record photos")
    photos.add_argument("--provider", choices=["kimi", "mimo", "minimax"], default="kimi")
    photos.add_argument("--model", help="Override the provider's default model ID")
    photos.add_argument("--api-key-file", help="Read the OpenCode Go API key from this local file; omitted uses env/config/OpenCode auth")
    photos.add_argument("--max-tokens", type=int, default=4096)
    photos.add_argument("--limit", type=int, help="Analyse only the first N photos (useful for a trial run)")
    photos.add_argument("--resume", action="store_true", help="Skip photo grids already saved in this person's workspace")
    photos.set_defaults(func=command_analyse_photos)

    intake = commands.add_parser("analyse-intake", help="Analyse one phone-uploaded record bundle as a single physical record")
    intake.add_argument("--owner", required=True)
    intake.add_argument("--upload-id", help="Specific mobile upload ID; omitted uses the most recent bundle")
    intake.add_argument("--provider", choices=["kimi", "mimo"], default="kimi")
    intake.add_argument("--model", help="Override the provider's default model ID")
    intake.add_argument("--api-key-file", help="Read the OpenCode Go API key from this local file; omitted uses env/config/OpenCode auth")
    intake.add_argument("--max-tokens", type=int, default=2048)
    intake.add_argument("--refresh", action="store_true", help="Reanalyse a bundle that already has an intake result")
    intake.set_defaults(func=command_analyse_intake)

    review = commands.add_parser("build-review", help="Match photo candidates against the local Discogs catalogue")
    review.add_argument("--owner", required=True)
    review.set_defaults(func=command_build_review)

    apply_review = commands.add_parser("apply-review", help="Mark confirmed photo-review copies as quick access in the local catalogue")
    apply_review.add_argument("--owner", required=True)
    apply_review.set_defaults(func=command_apply_review)

    prepare_additions = commands.add_parser("prepare-additions", help="Create a local editable queue from selected Discogs releases")
    prepare_additions.add_argument("--owner", required=True)
    prepare_additions.add_argument("--output", help="Optional portable queue path; defaults to this person's workspace")
    prepare_additions.set_defaults(func=command_prepare_additions)

    export_quick_crate = commands.add_parser("export-quick-crate", help="Export all reviewed photo positions as shareable JSON and CSV")
    export_quick_crate.add_argument("--owner", required=True)
    export_quick_crate.add_argument("--output-dir", help="Optional export directory; defaults to data/library/quick-crates")
    export_quick_crate.set_defaults(func=command_export_quick_crate)

    serve = commands.add_parser("serve", help="Start the complete local Cue Crate app through one port")
    serve.add_argument("--owner", required=True, help="Configured profile ID or display name for review, playlists, and phone intake")
    serve.add_argument("--port", default=8765, type=int, help="Single local app port (default: 8765)")
    serve.add_argument("--lan", action="store_true", help="Enable the token-protected phone companion on the trusted local network")
    serve.add_argument("--advertise", help="LAN address to place in the QR URL when auto-detection is unsuitable")
    serve.add_argument("--token-file", help="Optional local Discogs token for the in-app review search and release picker")
    serve.set_defaults(func=command_serve)

    serve_review = commands.add_parser("serve-review", help="Open the local review interface")
    serve_review.add_argument("--owner", required=True)
    serve_review.add_argument("--host", default="127.0.0.1")
    serve_review.add_argument("--port", default=8765, type=int)
    serve_review.add_argument("--token-file", help="Optional local Discogs token for the in-app search and release lookup")
    serve_review.set_defaults(func=command_serve_review)

    serve_mobile = commands.add_parser("serve-mobile", help="Serve the local phone companion and photo intake page")
    serve_mobile.add_argument("--owner", required=True, help="Configured profile ID or display name whose catalogue and intake are shown")
    serve_mobile.add_argument("--host", default="0.0.0.0", help="Bind address; 0.0.0.0 allows a phone on the same LAN")
    serve_mobile.add_argument("--port", default=8780, type=int)
    serve_mobile.add_argument("--advertise", help="LAN address to place in the QR URL when auto-detection is unsuitable")
    serve_mobile.set_defaults(func=command_serve_mobile)

    youtube_review = commands.add_parser("build-youtube-review", help="Build a local, review-first YouTube Music matching queue from owned crate titles")
    youtube_review.add_argument("--owner", required=True)
    youtube_review.set_defaults(func=command_build_youtube_music_review)

    serve_youtube_review = commands.add_parser("serve-youtube-review", help="Open the local YouTube Music matching checklist")
    serve_youtube_review.add_argument("--owner", required=True)
    serve_youtube_review.add_argument("--host", default="127.0.0.1")
    serve_youtube_review.add_argument("--port", default=8766, type=int)
    serve_youtube_review.set_defaults(func=command_serve_youtube_music_review)

    discover_youtube = commands.add_parser("discover-youtube-matches", help="Automatically search/rank music-category YouTube videos for the crate review")
    discover_youtube.add_argument("--owner", required=True)
    discover_youtube.add_argument("--client-secrets", required=True, help="Local Google OAuth desktop-client JSON; never place it in this repository")
    discover_youtube.add_argument("--limit", type=int, default=100, help="Maximum new titles to search; 100 matches the default daily Search API allowance")
    discover_youtube.add_argument("--refresh", action="store_true", help="Re-search titles already auto-selected")
    discover_youtube.set_defaults(func=command_discover_youtube_matches)

    reassess_youtube = commands.add_parser("reassess-youtube-matches", help="Apply strict artist/title checks to cached YouTube match candidates without a new API search")
    reassess_youtube.add_argument("--owner", required=True)
    reassess_youtube.set_defaults(func=command_reassess_youtube_matches)

    reject_youtube = commands.add_parser("reject-youtube-review-items", help="Exclude specific releases from a person's YouTube playlist review")
    reject_youtube.add_argument("--owner", required=True)
    reject_youtube.add_argument("--id", action="append", required=True, help="Review item ID to exclude; may be supplied more than once")
    reject_youtube.add_argument("--note", default="", help="Reason recorded with each exclusion")
    reject_youtube.set_defaults(func=command_reject_youtube_review_items)

    publish_youtube = commands.add_parser("publish-youtube-playlist", help="Create/update an approved YouTube Music-friendly playlist")
    publish_youtube.add_argument("--owner", required=True, help="Configured profile ID or display name whose review/playlist is being published")
    publish_youtube.add_argument("--client-secrets", required=True, help="Local Google OAuth desktop-client JSON; never place it in this repository")
    publish_youtube.add_argument("--account", help="Optional label for the intended Google account; confirm it in the browser OAuth prompt")
    publish_youtube.add_argument("--title", help="Optional playlist title; defaults to the configured profile's crate")
    publish_youtube.add_argument("--description", help="Optional playlist description")
    publish_youtube.add_argument("--privacy", choices=["private", "unlisted", "public"], default="unlisted")
    publish_youtube.add_argument("--include-auto", action="store_true", help="Include high-confidence automatic Music-category selections alongside explicitly verified approvals")
    publish_youtube.add_argument("--metadata-only", action="store_true", help="Only update the existing playlist title, description, or privacy; do not add tracks")
    publish_youtube.add_argument("--apply", action="store_true", help="Actually create/update the YouTube playlist; omitted means dry run")
    publish_youtube.set_defaults(func=command_publish_youtube_music)

    sync_youtube = commands.add_parser("sync-youtube-playlist", help="Reconcile the published YouTube playlist with changed review choices and rejected tracks")
    sync_youtube.add_argument("--owner", required=True, help="Configured profile ID or display name whose playlist is being synced")
    sync_youtube.add_argument("--client-secrets", required=True, help="Local Google OAuth desktop-client JSON; never place it in this repository")
    sync_youtube.add_argument("--include-auto", action="store_true", help="Keep high-confidence automatic selections in the desired playlist")
    sync_youtube.add_argument("--apply", action="store_true", help="Actually remove/add playlist items; omitted means a read-only plan")
    sync_youtube.set_defaults(func=command_sync_youtube_playlist)

    add = commands.add_parser("add-to-discogs", help="Add manually approved release IDs to a Discogs folder")
    add.add_argument("--owner", required=True, help="Configured person ID or display name that owns this additions queue")
    add.add_argument("--username", help="Discogs username; defaults to the configured person's discogs_username")
    add.add_argument("--folder-id", required=True, type=int)
    add.add_argument("--input", required=True, help="JSON list of manually approved release_id values")
    add.add_argument("--token-file", help="Optional token file; omitted uses DISCOGS_TOKEN, local config, or macOS Keychain")
    add.add_argument("--skip-existing", action="store_true", help="Check the Discogs collection and skip release IDs already present")
    add.add_argument("--apply", action="store_true", help="Actually write to Discogs; omitted means dry run")
    add.set_defaults(func=command_add_to_discogs)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    if hasattr(args, "owner") and args.owner:
        args.owner = owner_label(args.owner)
    args.func(args)
