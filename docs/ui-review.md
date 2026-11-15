# UI alignment review

Reviewed 4 October 2026. Direction: keep **After-Hours Index**; improve the component
mechanics rather than replace the visual identity.

## Evidence and scope

A delegated design specialist reviewed the shared stylesheet and page structure.
Live browser inspection covered Library, Crate Review, Playlist Manager, and
YouTube Track Review at desktop, tablet, and narrow phone sizes. This pass does not
change record identities, provider matching, saved selections, or publishing logic.

## Main findings and first-pass corrections

| Finding | Correction |
| --- | --- |
| Global text-field styling also affected checkboxes and sliders. | Type-specific input styles; compact native check controls and consistent 44px main controls. |
| Review filters and navigation competed with the title. | Dedicated full-width toolbar; aligned filter fields and grouped navigation. |
| Nested workspaces stayed two-column even when too narrow. | Separate workbench breakpoint and container-aware inner columns. |
| Fields and action buttons shared equal-width grids. | Visible field labels; flexible-input/intrinsic-button rows. |
| Playlist sidebar consumed too much horizontal space. | Stable 260px sidebar, more room for the editor. |
| Library and listening-order lists started at different heights. | Shared heading height and aligned list edges. |
| Reorder controls crowded playlist titles and were hard to tap. | Separate action row; 40px dense controls. |
| Save, publishing, and Delete were visually peers. | Three distinct action groups. |
| Every nested surface had the same shadow. | Border-led internal panels; elevation reserved for primary workspaces. |
| Quick Crate computed but omitted its identity-source badge. | Source badge rendered beside ownership. |
| Some link-actions had button colours but no button geometry. | Compound button classes on quiet anchor actions. |

Shared spacing now uses a small 4px-based token scale. Mobile navigation also accounts
for safe-area insets. Pressing tables retain readable columns with local horizontal
scrolling rather than wrapping words into single-character columns.

## Follow-up work, intentionally separate

- Replace the artist desktop multi-select with a mobile-friendly searchable picker.
- Give the record detail dialog a clearer listening-source hierarchy and a mobile
  close/header treatment.
- Make profile/scope switching consistent across Library, Scout, and Playlists.
- Add persistent unsaved-change feedback and consider a sticky mobile Save action.
- Review keyboard and screen-reader behavior as a dedicated accessibility pass.
- Add visual regression fixtures for empty queues, long metadata, disconnected
  providers, and unusually long playlist names.

## Validation

The four core screens were checked at 1280, 900, 390, and 320px widths. Narrow layouts
were inspected for horizontal page overflow and controls protruding beyond the
viewport. Playlist list edges and toolbar control heights were also measured in the
browser. Expanded facets, saved-item review, and the narrow playlist builder were
checked separately. No saved selections or remote playlists were changed.

A second specialist inspection found no blocking regression in this scoped pass.
Its final recommendations—consistent anchor hit areas and outlined secondary
publishing actions—were applied. Inline JavaScript syntax checks and `git diff
--check` pass.
