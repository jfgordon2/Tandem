# Approved routing revision: verification

November 3, 2026, branch `valhalla`. The owner approved the revised preferences, automatic inclusion of both map sets, current-style progress, shared schedule/deletion and existing status chip. This report covers that implementation; the earlier comma trial remains separate evidence. Current device checks ran only from an isolated source copy under `/data/tandem/navigation/revision2-source`; the live checkout reported `edaf013f` afterward. These checks did not switch its branch or install this implementation there.

## Review hardening and release integration

`valhalla` was fast-forwarded to fetched `origin/release` at `fc62697690` before reapplying the uncommitted implementation. All release changes are ancestors of the branch; no rebase was used. Both comparison-entry sets are retained. The release RAM/search/process-name changes and root README installation instructions remain intact.

- The upstream companion hook guards its import and call with `except Exception`. The owned hook contains its enabled check and enqueue inside the same exception boundary. Import, callback and unexpected configuration failures cannot suppress the original mapd download signal.
- Requests are published through the existing atomic JSON journal without taking the graph install lock. A real held-flock regression verifies that the hook returns and persists its request while that install lock remains held. Weekly/Monthly/manual schedule tests also inject import and callback failures and verify that the original road-data message still sends.
- Routing precedes Low on RAM in chip priority. RamWatch, its 85% clear threshold, the snapshot call with `self._ram`, and the per-drive `self._ram_log.note(...)` call remain intact. Both routing process names have the existing Routing description in RAM details.
- Release catalogs and fonts were chosen as the regeneration baseline, then `translations.py update` and `fallback_font.py subset` / `build` ran against the combined code. There are 1,789 catalog entries and 2,976 fallback glyphs, with no missing glyphs. Existing release translations were preserved; 88 new navigation entries per language are explicitly identified English placeholders, not completed native translations.
- The host UI suite passed **694 tests, two existing skips**, excluding the four AGENTS.md cereal/hardware files. The host routing suite passed **73 tests**. The complete device backend/upstream regression suite passed **144 tests**, with the existing ReactiveX deprecation warning.
- The complete device UI rerun passed **819 tests with no skips**. Its initial run exposed a constructor-bypassing speed-limit fixture missing the new RAM fields. The fixture now initializes real RamWatch/RamLog state; its original assertions are unchanged. An added regression verifies RAM recording while the HUD is hidden.

The full native `scene_compare.py` capture completed on the isolated device copy. The focused comparison retains all 26 routing mocks and both release RAM mocks; its additional combined-chip render shows the requested priority with the time/street bar intact. Playwright/Chromium verified 28 comparisons and 56 images without missing images, overflow or JavaScript errors (`tools/out/compare-release-merge/index.html`). The routing pseudo-language scene drew 196 strings; its 45 unbracketed values are sample geography/names, fixture notes, units and instructions, not new unmarked production labels.

The first supervised routed-drive RAM check remains open. The current guide records the parked baseline, routed/modeld/UI measurements and the 90% warning / 85% clear thresholds to check. No live-checkout install or drive is claimed. Iowa and Illinois data are both published, as recorded below.

## Earlier implementation results

- **678 UI tests passed**, with two existing skips. The four hardware/cereal UI files named in AGENTS.md were excluded on this host: `test_headroom_warning.py`, `test_home_layout.py`, `test_limit_offers.py`, `test_onroad.py`. Tests use the repository's `stub_plugin`; macOS additionally needs `SP_HEADLESS_TEST=1 SCALE=1` to avoid a display probe during imports.
- **802 UI tests passed on the device**, without exclusions or skips, using its real compiled dependencies and isolated params/state. This includes all four files excluded from the host run and the prebuilt parameter-registry checks. Missing source references and Flask test dependencies were supplied only in the isolated test tree/test-dependency folder; the live environment was left unchanged.
- **129 routing and upstream regression tests passed on the device**, including all owned backend tests, real cereal serialization, destination-store, route-engine, navigationd and navigation-desire checks. One existing ReactiveX datetime deprecation warning remains. The test helper import was qualified by package so it also works under the device’s package layout.
- **58 routing tests passed on the host** across `test_routing.py`, `test_routing_navigation.py`, `test_routing_policy_maps.py` and `test_routing_build.py`. These include real upstream navigation/model code with transport stand-ins, both provider orders, strict-mode races/corrupt preferences, rollback separation, preview generations, freshness, download range/checksum handling, interrupted connections, scoped cancellation, restart journaling, deletion leases, and the actual upstream Weekly/Monthly gates.
- **Ruff and `git diff --check` passed.** Translations and search index were updated. New navigation wording has explicitly documented English fallbacks in the PO catalogs, as permitted by AGENTS.md; this is not a claim of completed translation of the new wording.
- **Published Iowa assets downloaded without authentication.** The maintained catalog, manifest and graph are in the owner's approved [routing-data-v1 data release](https://github.com/jfgordon2/Tandem/releases/tag/routing-data-v1). The graph and source extract were checksummed before publication.
- **A real HTTPS resume/install/activation test passed.** An isolated `/tmp/tandem-catalog-smoke` download was seeded with 292,091,904 of 293,140,480 graph bytes. The downloader requested the remaining 1 MiB from GitHub, verified the whole graph's SHA-256, installed immutable bundle `iowa-20261103-v1` and activated it. No live device data was changed.
- **A real native route through the new client/broker path passed.** The published graph produced 105 geometry points and eight normalized steps in 0.992 seconds, including native startup on the host. This is a single functional smoke test, not a device performance benchmark. Desktop execution does not enforce the Linux seccomp network restriction; the earlier device trial reports that separately. The isolated server and native worker were closed afterward.
- **Native routing with the current code passed on the comma device.** Ten public Iowa sample requests, outside-coverage/invalid-coordinate/recovery probes, and three provider-policy cases passed. Strict offline and prefer-offline made no online attempt; an injected online failure made one online attempt before successful local fallback. All native responses confirmed `seccomp_socket_connect_denied`. The isolated broker and worker were closed afterward. Raw results and source hashes are in `tools/out/routing-reports/revision2-native.json` (ignored). This was a short offroad functional run alongside synthetic UI tests, not a driving-performance comparison.
- **26 native device component states captured and visually reviewed.** The capture executes the real Python components/layouts with sample data and shipped fonts/icons through the device’s raylib backend. `TANDEM_CAPTURE_TEXTURE=1` reads the landscape render target before physical panel rotation/color transforms. Playwright/Chromium verified all 26 comparisons, 52 images and local links, with no missing images, page overflow or JavaScript errors. The unused B alternative is retained in design history and has no implementation.

## Visual findings and differences

The routing pseudo-language scene rendered 188 strings. Its 42 unbracketed values were sample addresses/names, codes, units and route instructions; no new production label was unmarked. The region summary keeps its action pinned and scrolls the middle for long wording.

Capture caught and corrected a clipped Choose regions action, long region-status text, a missing strict-preview import, and a stale fake Start state. Current-style progress keeps its percentage, bar, region grid, four steps, cancel position and settings footer. Routing status stays in the existing chip and the time/street bar remains visible. Estimates retained during short interruptions are display-only and expire after twenty seconds.

The Navigation maps row keeps a general description; actual geographic readiness is shown in the maps page/panes rather than inferred for a trip from a global capability flag. Mapbox keeps its configured-key status, with optional wording in strict mode. Shared settings headers/footer, the complete device-storage bar and the existing global Delete/Remove maps semantics are retained. The one-region mock's Remove region caption becomes **Remove maps**, with a confirmation that covers all downloaded data. mapd has no per-region tile ownership/deletion interface, so per-region deletion is not advertised. Both datasets are deleted by the global action; saved places, selected regions, schedule and runtime remain.

Iowa and Illinois routing is published. Other countries/states in the design and sample captures illustrate layout, not actual download availability. Production labels use the catalog and report unavailable coverage accurately.

## Remaining acceptance

The macOS session has no active display, so its initial captures used the software component renderer. SSH became available afterward, allowing full device tests and native render-target captures. The device’s Xvfb server failed to initialize; its raylib build uses the native comma display backend, so the final capture ran directly with the texture option. These are synthetic scenes, without a live camera stream or driving workload.

This revision has **not** been deployed to the live driving checkout or validated while driving. Saved-place Start, missed turns, GPS loss/recovery, reboot, and sustained concurrent model/UI/control deadlines still need a supervised device session. The short native run records timings and memory for provenance; it establishes no onroad performance or thermal acceptance claim.

## Reproduce host checks

Use the project's normal Python environment with pytest, raylib and Pillow installed. On Linux, follow AGENTS.md's xvfb invocation. This host used a dedicated Python 3.11 environment:

```sh
PYTHONPATH=selfdrive/ui/tandem/tools/render:. BIG=1 SP_HEADLESS_TEST=1 SCALE=1 python3 -m pytest -q -c /dev/null \
  --confcutdir=selfdrive/ui/tandem -p stub_plugin selfdrive/ui/tandem/tests \
  --ignore=selfdrive/ui/tandem/tests/test_headroom_warning.py --ignore=selfdrive/ui/tandem/tests/test_home_layout.py \
  --ignore=selfdrive/ui/tandem/tests/test_limit_offers.py --ignore=selfdrive/ui/tandem/tests/test_onroad.py
python3 -m pytest -q -c /dev/null --confcutdir=starpilot/tandem/tests \
  starpilot/tandem/tests/test_routing.py starpilot/tandem/tests/test_routing_navigation.py \
  starpilot/tandem/tests/test_routing_policy_maps.py starpilot/tandem/tests/test_routing_build.py
ruff check selfdrive/ui/tandem starpilot/tandem/routing
PYTHONPATH=. BIG=1 SP_HEADLESS_TEST=1 SCALE=1 python3 selfdrive/ui/tandem/tools/render/software.py \
  selfdrive/ui/tandem/tools/render/scene_routing.py selfdrive/ui/tandem/tools/out/renders
python3 selfdrive/ui/tandem/tools/compare.py selfdrive/ui/tandem/tools/out/renders \
  selfdrive/ui/tandem/tools/out/compare-valhalla valhalla2-
```

Where OpenGL is available, the same `scene_routing.py` runs through the normal `snap.py` renderer. It is also included in `scene_compare.py`.

## Reproduce device checks

Use an isolated source copy with the compiled dependencies available from the live build, a separate `OPENPILOT_PREFIX` (and its `/dev/shm/msgq_<prefix>` directory), isolated `TANDEM_STATE_DIR`, `TANDEM_PREFS_DIR` and `TANDEM_ROUTING_DIR`, and a pytest temporary root on `/data`. Keep the device offroad and stop checks if it starts driving. Do not run test publishers against live params/IPC.

```sh
# With those environment paths set, from the isolated source root:
BIG=1 SP_HEADLESS_TEST=1 SCALE=1 python3 -m pytest -q -c /dev/null \
  --basetemp=/data/tandem/navigation/revision2-ui-pytest-temp \
  --confcutdir=selfdrive/ui/tandem selfdrive/ui/tandem/tests
TANDEM_ROUTING=0 python3 -m pytest -q -c /dev/null --confcutdir=. \
  --basetemp=/data/tandem/navigation/revision2-pytest-temp \
  starpilot/tandem/tests starpilot/navigation/test_destination_store.py \
  starpilot/navigation/test_route_engine.py starpilot/navigation/test_navigationd.py \
  selfdrive/controls/tests/test_navigation_desires.py
BIG=1 SP_HEADLESS_TEST=1 SCALE=1 TANDEM_CAPTURE_TEXTURE=1 python3 \
  selfdrive/ui/tandem/tools/render/snap.py selfdrive/ui/tandem/tools/render/scene_routing.py \
  /data/tandem/navigation/revision2-renders
```

## Illinois test extension

The original Iowa bundle remains unchanged. The added `iowa-illinois-20261103-v1` graph was built in one Valhalla 3.9.1 invocation from both source PBFs, with shared border connections. It is 1,108,899,840 bytes (about 1,058 MiB / 1.03 GiB). Both source checksums and URLs are recorded in its manifest. The public data release includes the Illinois PBF in addition to the existing Iowa source.

- Graph SHA-256: `790c880c4f9f69492bdfd9f2aa0f0d0f2635dcf9f938df00fd0691cc1fcb0ae8`.
- Published manifest SHA-256: `09a0fdd49c7111f122d40ff1b1566eadabd5a3c5c0752b875d10cf2616f31f47`.
- Illinois source SHA-256: `2af4a64d5774061ae8219ef87c3935449838334fc8b7588e5d62fb215a75f075`.

Six real native routes passed on both host and comma device: Des Moines local, Chicago local, Springfield–Chicago, Davenport–Moline, and Des Moines–Chicago in both directions. Cross-border geometry was checked on the three interstate cases. All device responses confirmed `seccomp_socket_connect_denied`. The test began with only Iowa installed, verified that Chicago was outside its coverage, then installed Illinois’s connected package and verified that cross-state routing selected it while retaining the Iowa graph. The device used an isolated `/data/tandem/navigation/ia-il-test` data/state tree and offroad guard, leaving the live checkout/params unchanged. The broker and worker were closed afterward. Raw reports are `tools/out/routing-reports/iowa-illinois-host.json` and `iowa-illinois-device.json` (ignored).

Automated tests also cover choosing Iowa, then Illinois separately, then both: the combined graph is installed once and reused afterward. This is whole-package reuse, not incremental compatible-tile downloading. Adding Illinois still downloads Iowa routing data again as part of the larger connected graph; unrelated independently built state graphs are never stitched. A future efficient state-by-state implementation needs compatible tile subsets from the same shared dataset build and atomic dataset-version handling.

A real unauthenticated HTTPS test fetched the updated public catalog and manifest, resumed the final 1 MiB of the 1,108,899,840-byte graph, verified its complete SHA-256, and installed/activated it through the actual map-job manager. The journal reached Ready for Iowa and Illinois and retained the original Iowa graph. Its report is `tools/out/routing-reports/iowa-illinois-download.json` (ignored). No source PBF was downloaded by that job.
