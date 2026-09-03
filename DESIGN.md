# Cue Crate design system

## Direction: After-Hours Index

Cue Crate is a contemporary record library for physical DJ collections. It should feel
calm, premium, and practical: record covers carry the personality, while the interface
provides a quiet, trustworthy index for ownership, curation, and DJ preparation.

It deliberately avoids fake-retro decoration. The early-80s soul, funk, disco, and
boogie character belongs in the records themselves, not in ornamental interface chrome.

## Product map

```text
Library       Browse all owned physical copies and inspect a release.
Quick Crate   See the selected shared DJ bin.
Review        Confirm photographed copies and exact Discogs releases.
Playlists     Choose and verify representative YouTube Music tracks.
Scout         Read the local taste profile and discovery lanes.
```

The shared shell in `app.js` owns this navigation. Every screen identifies the active
destination with `data-page` on the HTML element.

## Tokens

The source of truth is `app.css`.

- **Ink and surfaces**: warm charcoal rather than neutral black, so covers feel at home.
- **Paper and muted text**: bone text with readable warm-gray secondary copy.
- **Amber**: a reserved signal colour for primary actions, active state, and verified
  attention. It must not be the only way information is conveyed.
- **Semantic status colours**: green for confirmed, amber for review, coral for excluded,
  blue for contextual information. Each status also has a written label.
- **Type**: serif display titles, system sans-serif interface text, and monospaced factual
  metadata. This makes titles expressive and pressing/BPM/key data fast to scan.
- **Shape**: 8px, 14px, and 22px radii only. Borders carry grouping; elevation is subtle.

## Component rules

- `surface`: framed workspace, toolbar, report card, or playlist item.
- `record-card`: cover-led library browsing. Do not add more than two metadata lines.
- `record-row`: dense quick-crate or list-mode entry.
- `chip`: ownership, scope, or compact neutral metadata.
- `badge`: status or source. Use a semantic modifier such as `badge--confirmed`.
- `button--primary`: the one next action. Use quiet buttons for back, close, and utility
  actions; use danger treatment for exclusions.
- `empty-state`: explain what is absent and the next local action to take.

## Responsive behaviour

Desktop uses a centred page shell with a horizontal navigation bar. Below 820px, the same
navigation becomes a fixed bottom bar, cover grids become two columns, and review work
flows stack into a deliberate single-column sequence. Controls should not rely on hover,
drag, or dense tables to remain usable.

## Accessibility baseline

- All interactive controls retain visible keyboard focus.
- Buttons and main controls meet a 40px minimum desktop target; mobile layouts retain
  comfortably tappable controls.
- Status is written as text as well as colour.
- User feedback is rendered in text, with page regions using `aria-live` where appropriate.
- Motion is reduced for `prefers-reduced-motion`.

## Adding a screen

1. Link `app.css` and `app.js`.
2. Set `data-page` to one of the shell destinations, or add a new destination deliberately.
3. Compose from the existing page header, toolbar, surface, card, row, badge, and empty
   state primitives before writing page-specific styles.
4. Verify desktop, a narrow mobile viewport, keyboard focus, loading, empty, and error
   states before treating the screen as complete.
