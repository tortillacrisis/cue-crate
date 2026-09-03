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
provider-review data. It is accessible only from the serving computer.

## Optional phone companion

`--lan` binds the same server to the trusted local network and enables the QR flow. The
connect page remains loopback-only. Its generated phone URL carries a short-lived token in
the URL fragment, which is not sent to the server in a request URL or referrer. The phone
sends that token in a request header for every mobile API call.

Only the mobile catalogue and intake endpoints accept a valid phone token. The desktop
review, playlist, and library APIs reject non-loopback requests. Never expose this local
server directly to the Internet.

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
