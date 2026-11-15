# Architecture and local-network security

Cue Crate is intentionally local-first. It is a Python application with static browser
screens and a small local HTTP API; it does not require a hosted backend or user account
system to catalogue records.

## One server

`cue_crate.py serve --owner <profile>` starts one server on `127.0.0.1:8765` by default.
It serves an explicit allowlist of app pages and assets, rather than the project directory.
This prevents `data/`, local configuration, raw intake photos, and other repository files
from being exposed as static URLs.

The local API supplies catalogue, quick-crate, taste-profile, review, playlist, and
provider-review data. Desktop routes are loopback-only. Every server entry point
validates its Host header and rejects foreign browser origins/Fetch Metadata for APIs.
Desktop JSON writes additionally require a random server-session capability in
`X-Cue-Crate-CSRF`, `application/json`, and a body no larger than 2 MiB.

The browser obtains that capability from the loopback-only, uncached `/api/session`
endpoint and keeps it in memory, not local storage. A server restart invalidates it;
reload the page if a save reports an expired session. Mutations are never automatically
retried because a provider write may already have occurred. Spotify's cross-site OAuth
callback is a deliberate exception to the Origin/Fetch Metadata gate, not to Host or
loopback checks; its expiring, single-use OAuth state and PKCE remain authoritative.

Legacy standalone servers use the same guards and static-file allowlist. They cannot
serve repository files through the inherited directory or HEAD handlers.

## Optional phone companion

`--lan` binds the same server to the trusted local network and enables the QR flow. The
connect page remains loopback-only. Its generated phone URL carries a server-session token in
the URL fragment, which is not sent to the server in a request URL or referrer. The phone
sends that token in a request header for every mobile API call.

Only the mobile catalogue and intake endpoints accept a valid phone token. The desktop
review, playlist, and library APIs reject non-loopback requests. Never expose this local
server directly to the Internet. The phone capability can be reused until the server
restarts; it has no fixed time-to-live. Trusted-LAN HTTP does not encrypt the token or
photos in transit. The phone token is separate from the desktop write capability.

## Data boundaries

```text
Tracked in Git                 Local-only data
---------------------------    --------------------------------
Application source and docs    data/ catalogue, photos, caches, reports
Example configuration          config/*.local.json
                               ~/.config/cue-crate/ credentials
                               macOS Keychain provider secrets
```

A physical record copy has one profile owner. It may be assigned to several collectives
for shared bins and future setlists, but that does not duplicate the underlying copy.

### Credentials remain a server concern

Provider code resolves credentials on the serving computer; the browser receives no
long-lived Go API key. macOS Keychain is the local implementation, not a requirement
of the collection or photo-intake data model. A dedicated Cue Crate key does not
modify the normal OpenCode login.

For a future hosted deployment, keep the same server-side boundary and resolve an
operator key from the host's managed secret store. If users eventually bring their
own keys, add authenticated ownership, authorization, rotation/deletion, and managed
encryption before storing them. Do not build a custom cryptographic vault now, copy
Mac credentials to a host automatically, or put long-lived provider keys in browser
storage. Hosted credential handling is deferred; the current application stays local-first.

## Identity and evidence

The catalogue record ID identifies a physical copy. A photo-review ID identifies evidence
about that copy; it is not a second record. Several photos may therefore point to the same
catalogue ID. Listening-service choices attach to a canonical listening identity backed by
the catalogue's Discogs release and record IDs, while retaining aliases for older
artist/title keys. Playlist entries use those listening IDs. This separation lets corrected
Discogs metadata supersede an early photo transcription without losing photos, selected
videos, or published-playlist receipts.

Discogs imports refresh these derived local identity views. They never update a remote
YouTube or Spotify playlist unless the user explicitly invokes a publish or sync action.
