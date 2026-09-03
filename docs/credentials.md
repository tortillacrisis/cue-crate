# Credentials and provider setup

Credentials belong on the computer that runs Cue Crate. Do not commit them, paste them
into issues, or put them in a shared profile configuration file.

## Discogs

The CLI checks, in order: an explicit `--token-file`, `DISCOGS_TOKEN`, a local Cue Crate
config file, and macOS Keychain. A per-profile Keychain item uses this pattern:

```text
cue-crate.discogs-token.<profile-id>
```

For a generic local token, create the Keychain item without putting the secret in shell
history:

```bash
read -r token < /tmp/discogs-token
security add-generic-password -U -s cue-crate.discogs-token -a "$USER" -w "$token"
unset token
```

Public Discogs collection imports need only the username. Adding records to another
person's private collection requires that person to run the final write with their own
token.

## OpenCode Go

Photo analysis looks for `OPENCODE_GO_API_KEY`, then
`~/.config/cue-crate/opencode-go-api-key`, then the normal OpenCode authentication file.
Use `opencode auth login` to set up the provider in its own application; Cue Crate does
not copy that credential into the repository.

## YouTube and Spotify

YouTube OAuth tokens are stored per profile under:

```text
~/.config/cue-crate/profiles/<profile-id>/youtube-oauth.json
```

The CLI opens a browser only when a deliberate YouTube publish/discovery command needs
authorization. Spotify is documented as a future showcase destination and is not yet a
publishing integration.

## GetSongBPM

Keep a GetSongBPM key in `GETSONGBPM_API_KEY`, a local key file, or the Keychain item
`cue-crate.getsongbpm-api-key`. Provider matches remain separate from manual track
metadata and can be refreshed without overwriting an explicit user override.

Cue Crate reads older local credential locations during its product rename, but writes
new credentials only to the Cue Crate namespace.
