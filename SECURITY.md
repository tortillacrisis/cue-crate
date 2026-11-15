# Security

Cue Crate is a local/trusted-LAN prototype, not an Internet-ready multi-user service.
Only the latest reviewed version is maintained; no long-term support promise is made.

## Report privately

Private vulnerability reporting is enabled on the public GitHub repository (confirmed
15 November 2026). Use **Security → Advisories → Report a vulnerability** to report
privately. If that option is unavailable, open a minimal issue asking the maintainer
for a private contact channel, without vulnerability details, credentials, personal
catalogue data, or an exploit. Do not disclose vulnerability details in a public issue.

Include affected version, reproduction with fictional data, impact, and any proposed
mitigation. Do not test against other users, third-party accounts, or live providers.

## Local boundaries

- Default binding is loopback. Desktop APIs and the phone connect screen are local-only.
- Host/origin checks and a random in-memory session capability protect desktop writes.
  Static serving uses an explicit allowlist, including on legacy entry points.
- Phone capabilities are separate, reusable during the server session, and invalidated
  on restart. HTTP on trusted Wi-Fi is not encrypted; do not use untrusted networks.
- Profiles/collective roles describe ownership and collaboration metadata; they are not
  authentication or access control between people sharing a computer.
- Keep long-lived credentials in Keychain or owner-restricted configuration outside Git.
  Spotify Web Playback intentionally receives a short-lived access token in the local
  browser; long-lived refresh credentials remain server-side.
- Do not expose the server through port forwarding, a public reverse proxy, or a tunnel.
  Hosting requires a separate authentication/authorization and managed-secrets design.

See [architecture](docs/architecture.md) and [credential setup](docs/credentials.md).
The lightweight text-secret guard is an accident check, not proof that a release is safe.
