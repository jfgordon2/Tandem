# Valhalla UI approval drafts

**Superseded:** the owner's feedback replaces this initial review. See the [current revision 2 gallery](revision-2/index.html) and [routing/download decisions](revision-2/README.md). User-entered package URLs are rejected; a separate routing-manager page and replacing the arrival/street bar are no longer proposed.

Owner approval is pending for every change in this review. The feature was implemented before its UI received approval; the seven earlier mock variants did not provide a complete state-by-state review. This set is retrospective. Creating these files does not approve the existing implementation.

Open [the interactive gallery](index.html). It contains 64 individually captured HTML mocks, with the conditions and visible change next to each one. The category filters and full-size preview work offline. Sample roads, destinations, times and package URLs are illustrative. These are mocks, not live-device captures. The normal fresh-guidance image is an existing-design reference.

## Scope of the application diff

| Application file | Visible changes covered |
| --- | --- |
| `onroad/view.py`, `onroad/layers.py` | Independent turn-card freshness expiry; active-route waiting/rerouting/error text replaces arrival/time-left/street while instruction messages are invalid or stale. End route remains available. Every status wording has its own mock. |
| `settings/speed_steering.py` | New Offline routes / Manage entry, optional Mapbox-key wording when local routing is enabled, corrected Offline Maps description. Both scrolled and top views are shown. |
| `settings/search.py` | New Offline routes result and matching terms; changed Mapbox/Offline Maps indexing text. The visible result still shows its setting name and location, not the internal indexing description. |
| `destinations.py` | Installed-data readiness badge, Offline routes footer action, local/old-alternative preview notes, Start gating, and legacy name-only recent fallback/error wording. |
| `routemap.py` | Local preview geometry/estimates, pending/error states with no route and disabled Start. Existing grid/map styling is retained. |
| `settings/routing.py` | New management page: initial setup, empty/installed/active data, switch off/on, busy/cancellable setup/download, successful/cancelled/failed operation, storage/verification/conflicting-ID errors, reader lease busy, parked guard, link entry and its keyboard validation. |
| `routing_status.py` | Added driver wording appears within preview, driving bar or management footer as shown in each state's condition. Shared status strings are not separate alerts. |
| `mapbox_help.py` | Optional-online-features subtitle when local routing is enabled. Existing steps are retained. |
| `controls.py` | Compact Use/Remove button sizing only where the new management rows opt in; other callers keep their prior sizing. |
| Translation catalogs and fallback font | New strings in 12 languages and 11 extra fallback characters; no intentional redesign of existing translated screens. Approval mocks show English. |

The precise switch conditions, per-state triggers and findings are also available as structured data in [manifest.json](manifest.json). `approval` remains `pending` for every state.

## Visibility rules

- **Navigation entry/search:** visible in Tandem settings before offline routing is enabled, so the owner can set it up.
- **Local saved-place badge/footer, preview notes and optional Mapbox subtitle:** effective offline routing must be on. The badge additionally requires a matching runtime receipt and selected usable graph; it does not certify coverage for an individual trip.
- **Driver status text:** effective offline routing is on, a destination is set, and the instruction message is invalid or older than 2.5 seconds. A fresh status snapshot supplies the text; an absent/stale snapshot uses the worker-unavailable wording. The turn card checks its own instruction-state timestamp separately. It can disappear before the bottom-bar estimate expires, as its dedicated mock illustrates.
- **Data-page mutations:** require offroad state and no destination, even if the car is stationary. Busy operations also disable mutating rows and expose Cancel. Opening the page does not itself require that guard.
- **Start:** requires a current successful preview while local routing is selected. Pending, missing data, missing GPS and route failures leave it disabled.

An environment override can force routing off: `TANDEM_ROUTING=0`, or any of `TANDEM_SETTINGS`, `TANDEM_HOME`, `TANDEM_ONROAD`, `TANDEM_SIDEBAR` set to `0`. With no override, the persistent preference controls it; `TANDEM_ROUTING=1` forces it on for testing. Offline routing starts disabled by default.

## Implementation gaps surfaced by the review

These are recorded for approval discussion; this design-only pass does not change application behavior:

1. The legacy name-only recent fallback sets the query and then clears it when opening search. The existing missing-public-key notice can hide the newly added missing-coordinate explanation.
2. A rejected package URL reuses the route's “no usable coordinates” error; a software-setup timeout reuses “The route took too long.”
3. A busy package removal says “Trying again” although the management action does not retry automatically.
4. The separate existing Display › Map screen still uses the older “routing without a connection” subtitle. The feature changed Navigation and the search index, not that screen.

## Rebuild and capture

From the repository root:

```sh
node selfdrive/ui/tandem/design/valhalla-review/build.js
node -e 'process.argv=["node","shoot",...require("./selfdrive/ui/tandem/design/valhalla-review/names.json")]; require("./selfdrive/ui/tandem/tools/shoot_mocks.js");'
node selfdrive/ui/tandem/design/valhalla-review/shoot_review.js
```

The capture commands need the same Playwright/Chromium dependency as the existing mock tooling. This session used `NODE_PATH=/tmp/tandem-playwright/node_modules` and `PLAYWRIGHT_BROWSERS_PATH=/tmp/tandem-playwright-browsers`.

Screenshots for individual states live in `design/screenshots/valhalla-*.png`. Compact review boards live beside this README. Existing approved mocks and the seven earlier feature drafts are left intact. `qa.json` checks all draft dimensions, fonts, gallery links, category filtering and full-size preview behavior. Screenshot overflow reports must also be inspected.
