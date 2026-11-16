# Routing UI, revision 2

[Open the revised approval gallery](index.html). This is the current proposal following the owner's comments. The earlier 64-state gallery is retained as a superseded implementation audit, not a design to implement.

The owner approved the selected design and revised progress layout on November 3, then requested implementation. The branch now uses these references. Original upstream-era mocks remain untouched; new screens use the `valhalla2-` prefix. See the [current behavior and verification guide](../../../docs/valhalla-offline-routing.md).

Owner review update, November 3: the owner likes the overall redesign and selected A, downloading both map sets automatically. B is retained as a historical alternative and must not be implemented. The owner rejected the changed progress layout and asked to keep it closer to the current implementation. Only the progress mocks are visually revised in this update; the preference, region-picker and status-chip mocks are unchanged. The owner subsequently approved the revised progress screens and requested implementation.

## Owner requirements reflected here

| Requirement | Proposed UI and behavior |
| --- | --- |
| Offline maps only | Boolean switch on the existing Navigation page. When on, calculate routes only with downloaded data and never request or fall back to Mapbox routing. |
| Preferred maps (when available) | Online / Offline segmented control on the same page. When offline-only is off, try the preferred provider and then the other provider if the first cannot produce a usable route. |
| Strict setting overrides preference | Disable the preference row while offline-only is on, retaining the saved preference for when the override is turned off. |
| Map downloads in existing region panes | Preserve U.S. regions, U.S. states and Other countries. Extend selection summaries and progress to account for road data plus routing data. |
| Bottom-left status chip | Use the existing `StatusChip` dark surface, 44 px height, icon, spacing and stack. Recalculating route is shown there; the arrival/time-left/street bar stays in place. |
| No user-entered URL | Remove package-link entry and the separate routing-software setup page from the proposed flow. A maintained catalog supplies downloads; first-time preparation is automatic. |

The strict switch applies to routing. Address/place search remains a separately online feature. The policy must apply equally to preview, first-route calculation and missed-turn recalculation. A preferred provider has to produce a valid route to count as available; connectivity alone is not sufficient. Missing keys, coverage, data, route failures, timeouts and invalid results are fallback cases. Try each provider once per attempt, with a bounded overall deadline rather than alternating indefinitely.

This is a routing policy, not a renamed enable switch: turning Offline maps only off must not disable offline capability or offline fallback. Installed-data readiness is independent of both preferences. The previous experimental Use offline routes setting is superseded by this model.

Proposed defaults for review: offline-only off, Online preferred. These preserve the initial provider preference while adding offline fallback. This default is a proposal; it was not specified by the owner.

## Selected download-management direction

**A, selected by the owner: one region selection downloads all missing map data.** A driver selects Iowa and presses Download. If road data is already on the device, only the missing routing data downloads. One shared maps page shows both readiness states and handles update/removal. One update schedule applies to both. The user makes a geographic choice without managing package types.

**B, not selected:** the earlier Include offline routes checkbox is retained in the review history only. Do not implement it.

Both designs include preparation, component progress, verification, partial failure/retry and ready states in the existing maps flow. Existing good data remains usable until a complete replacement passes verification. Region removal gets a confirmation and preserves saved places. A routing-data failure must not remove successfully installed road data.

## Progress stays close to the current implementation

The reference is `settings/maps.py`'s `DownloadView` and its existing `design/mapdownloading.html` mock. The earlier draft's large component count and two component rows have been replaced with the current screen structure:

- Large 44 px percentage and one progress bar in the existing 136 px card.
- The current Prepare / Download / Install / Ready steps, including the original Install wording.
- Seven-column region grid with green completed regions, a blue current region and muted waiting regions.
- The existing title, background-download message, top-right Cancel download action, settings footer/back action and pause/power note.
- One small active-map-set label beside the percentage, and a short readiness line in the existing region card. No component dashboard is added.

The top percentage describes the explicitly labelled phase: road data keeps its existing file count, while offline routes report bytes. When the phase changes, its label and percentage change together; a percentage reset is permitted, and must not be mistaken for lost progress. Do not average file counts and bytes or invent a byte total for mapd. Time remaining is for that phase and appears only after a useful rate is known. Mock numbers and time estimates are sample data.

A green region means all required map sets for it are installed, including data that was ready before the job. During the second phase, the region stays blue until its routing data is installed. Download at 100% advances to Install, not Ready. Group downloads retain the existing sorted tiles and current-tile window behavior; the new group example demonstrates both map sets completing per region. The implementation will need to normalize readiness from both data sources for these tiles.

Preparation includes any first-time routing setup automatically. Partial failure retains the same screen with an amber affected region and Retry download in the header; retry skips successful data. Existing installed maps survive cancellation or failure. The existing pause/resume and power behavior must apply to the routing download as well as road data before the shared footer makes that claim.

`board-progress.png` shows routing, road-data, multiple-region and Install examples. `board-downloads.png` covers Prepare, downloading, failure and Ready.

Map catalogs and hosting still need implementation. A selected set of regions must map to a compatible connected routing graph; independently generated overlapping extracts cannot simply be concatenated. Unsupported routing coverage is shown explicitly rather than inferred from the availability of road/speed-limit data. Dataset accounting stays separate internally, even though selection, scheduling and status are unified.

The measured Iowa routing package is about 280 MiB. Other catalog availability, addresses, timestamps and storage values in these design examples are illustrative; they do not claim that a production download catalog has been published.

## Status-chip behavior

- Recalculating route: keep the normal bar with the last useful estimates and current street while a replacement is attempted. Stale turn guidance remains hidden and cannot supply a control target.
- Finding route: before a first estimate exists, show dashes in its normal fields; keep the street when available.
- Using offline maps / Using online maps: proposed brief confirmations after successful fallback, using the existing fade/stack behavior. An online confirmation is impossible in strict offline-only mode.
- Offline maps unavailable: strict offline-only cannot produce a route. No online fallback occurs. The mock without an earlier route uses dashes for estimates.
- Waiting for GPS: use the chip and preserve the bar layout. The example represents a short interruption; implementation must deliberately expire or mark old estimates during a long outage rather than making stale guidance actionable.
- Existing steering/safety chips keep their priority and styling. Routing adds informational status to the existing stack and yields to safety alerts.

## Review files and checks

`manifest.json` records each state, its conditions, and its approval status. The selected 26 references are approved; B remains not selected and is retained for history. The implementation comparison is generated in `tools/out/compare-valhalla/index.html`. Shared settings chrome and global map deletion are retained; the main README records those differences. Native GPU capture was unavailable, so this run uses component captures with the shipped bitmap fonts/icons and Chromium review.

Build and capture from the repository root:

```sh
node selfdrive/ui/tandem/design/valhalla-review/revision-2/build.js
node -e 'process.argv=["node","shoot",...require("./selfdrive/ui/tandem/design/valhalla-review/revision-2/names.json")]; require("./selfdrive/ui/tandem/tools/shoot_mocks.js");'
node selfdrive/ui/tandem/design/valhalla-review/revision-2/shoot.js
```

Capture needs Playwright and Chromium, as in the existing repository workflow. This session uses `NODE_PATH=/tmp/tandem-playwright/node_modules` and `PLAYWRIGHT_BROWSERS_PATH=/tmp/tandem-playwright-browsers`. Individual PNGs are in `design/screenshots/valhalla2-*.png`; review boards are beside this README. `qa.json` records dimensions, font loading, gallery filters, full-size preview, and link/image checks.
