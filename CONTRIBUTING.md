# Contributing

Cue Crate is an early local-first project. Discuss substantial changes before building
them, especially data migrations, provider writes, authentication, and licensing.
Submit contributions under the [MIT License](LICENSE). Preserve upstream
attribution and do not include third-party code or media without the necessary rights.

## Development

Use Python 3.12+; Node.js is needed only for JavaScript syntax checks. Start with the
[README](README.md), then run:

```bash
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/check_project.py
.venv/bin/python scripts/check_secrets.py --history
git diff --check
```

The HTTP tests bind ephemeral loopback ports and use fictional data, temporary files,
and mocked provider boundaries. They require permission to bind localhost but no API
keys, paid requests, live account logins, or published-playlist changes. CI targets
Python 3.12 and 3.14 on Linux/macOS; hosted runs begin after the workflow is published.

Use `.venv/bin/python scripts/serve_demo.py` for privacy-safe browser checks and screenshots.
It isolates temporary data/configuration and disables credentials/provider calls.

## Data and behavior

- Never commit personal catalogues, photos, purchase histories, OAuth exports, or API keys.
  Use fictional fixtures. Review the actual staged diff; `.gitignore` is not a security boundary.
- Treat a physical copy, photo evidence, a recording/mix, and a provider match as distinct.
  Preserve owner/share assignments and deliberate manual overrides on refresh.
- Keep discovery/review separate from provider writes. A test must not need a real publish
  or Discogs collection mutation to prove local behavior.
- Route browser mutations through `cueCrateFetch`; keep desktop CSRF and phone capabilities
  separate. Test rejection paths alongside successful saves.
- Follow [DESIGN.md](DESIGN.md); test narrow layouts and avoid screenshots with real profiles
  or token-bearing QR/connect links.

Report ordinary bugs with a minimal reproduction, OS/Python/browser versions, and redacted
logs. For possible vulnerabilities, use [SECURITY.md](SECURITY.md) instead of posting details publicly.
