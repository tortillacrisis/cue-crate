# Credentials and provider setup

Credentials belong on the computer that runs Cue Crate. Do not commit them, paste them
into issues, or put them in a shared profile configuration file.

## Discogs

The CLI checks, in order: an explicit `--token-file`, `DISCOGS_TOKEN`, a local Cue Crate
config file, and macOS Keychain. A per-profile Keychain item uses this pattern:

```text
cue-crate.discogs-token.<profile-id>
```

For a generic local token, leave `-w` as the last option so macOS prompts privately:

```bash
security add-generic-password -U -s cue-crate.discogs-token -a "$USER" -w
```

Paste the token at that prompt, never into the command. This keeps it out of both
shell history and process arguments. Do not add `-A`. Prefer this persistent item to
keeping a long-lived token in `/tmp`.

Another person's public collection can use your locally stored token and their username;
their private token is unnecessary. Adding records to another
person's private collection requires that person to run the final write with their own
token.

## OpenCode Go

### Use a dedicated Cue Crate key

For an app-specific key, **do not use OpenCode's `/connect`**: that command changes the
credential used by your normal OpenCode client. Cue Crate can read a separate key from
macOS Keychain without editing or replacing OpenCode's login.

A separate key allows independent replacement/revocation; it does not create a
separate subscription allowance when the keys belong to the same workspace.

Run this in your own Terminal, leaving `-w` as the **last option**:

```bash
security add-generic-password -U -a "$USER" -s cue-crate.opencode-go-api-key -w
```

The system tool prompts for the key privately; paste it at that prompt, not into the
shell command or this chat. The secret is not included in shell history or process
arguments. Do not add `-A` (which would allow unrestricted application access).

Alternatively, create a Password item in **Keychain Access**, with item/service name
`cue-crate.opencode-go-api-key`, account set to your Mac username, and the API key as
its password. This is the generic-password Keychain store, not a website login in the
Passwords app.

The lookup order is:

1. Explicit `--api-key-file PATH`.
2. `CUE_CRATE_OPENCODE_GO_API_KEY` (Cue Crate-specific environment variable).
3. `~/.config/cue-crate/opencode-go-api-key` (restrict to your user, mode `600`).
4. The Keychain item `cue-crate.opencode-go-api-key` on macOS.
5. Legacy `OPENCODE_GO_API_KEY`, old Vinyl Crate config, and the OpenCode auth file.

Dedicated settings therefore take precedence over shared OpenCode credentials. Cue
Crate reads the old auth file only as a compatibility fallback; it never writes to it.
If an older dedicated key file exists, replace/remove that yourself before expecting
the Keychain item to take precedence. Installing or replacing a key does not run any
photo analysis, and no server restart is needed for the next CLI analysis command.

An active subscription and a valid API key are separate things. If the API reports
`api_key_expired`, create a replacement key in [OpenCode Console](https://opencode.ai)
and replace the dedicated Cue Crate item or key file. Signing in again does not renew
the expired key. Never paste a key into a chat, issue, or commit.

Keep **Extra Usage off** on the Go plan if you do not want the service to consume
pay-as-you-go credits after an allowance is exhausted. Cue Crate never enables it or
automatically switches to a pay-as-you-go endpoint.

Non-secret photo settings live separately in `config/photo-analysis.local.json`;
see [phone intake and image models](phone-intake.md). Current Go requests identify
Cue Crate with its own user agent and a per-analysis session ID. Go's documentation
describes the plan as intended for coding-agent traffic; verify with OpenCode that
your photo-cataloging use is permitted before relying on it for large batches.

## YouTube

YouTube OAuth tokens are stored per profile under:

```text
~/.config/cue-crate/profiles/<profile-id>/youtube-oauth.json
```

The CLI opens a browser only when a deliberate YouTube publish/discovery command needs
authorization.

## Spotify

Create a Development Mode application in the Spotify Developer Dashboard, enable the
Web API, and register this redirect URI exactly:

```text
http://127.0.0.1:8765/api/spotify/callback
```

Store its Client ID (not the Client Secret) in `SPOTIFY_CLIENT_ID` or this local file:

```text
~/.config/cue-crate/spotify-client-id
```

Cue Crate uses Authorization Code with PKCE, so it never needs to distribute a Spotify
Client Secret. Start the unified service, open the Playlist manager, and choose
**Connect Spotify account** for the selected profile. Renewable OAuth credentials are
written with owner-only permissions to:

```text
~/.config/cue-crate/profiles/<profile-id>/spotify-oauth.json
```

The requested scopes cover reading the selected profile's playlists, creating/updating
public or private playlists, and controlling Cue Crate's browser playback device. Full
Web Playback requires a Spotify Premium account. If Spotify was connected before player
support was added, use **Reconnect with another account** once so Spotify can grant the
new `streaming`, playback-state, and playback-control scopes. Do not copy OAuth JSON into
the project.

## GetSongBPM

Keep a GetSongBPM key in `GETSONGBPM_API_KEY`, a local key file, or the Keychain item
`cue-crate.getsongbpm-api-key`. Provider matches remain separate from manual track
metadata and can be refreshed without overwriting an explicit user override.

```bash
security add-generic-password -U -s cue-crate.getsongbpm-api-key -a "$USER" -w
```

The API key travels in the `X-API-KEY` request header, not the query URL. Provider error
bodies are not displayed. Registration requires a public project/backlink page; the
integration is still awaiting its reviewed pilot. See the [provider's requirements](https://getsongbpm.com/api).

Cue Crate reads older local credential locations during its product rename, but writes
new credentials only to the Cue Crate namespace.
