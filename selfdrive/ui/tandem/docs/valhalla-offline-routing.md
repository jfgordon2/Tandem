# Offline routing on the valhalla branch

The approved revision adds routing policy to Navigation and manages routing graphs through the existing Offline Maps flow. It uses StarPilot's destination store, route model, progress loop, navigation publishers and control decisions. There is no driver-facing package URL or routing-software setup page.

## Driver flow

Open **Settings › Driving › Speed & Steering › Navigation**:

- **Offline maps only** prevents all online route attempts and fallback. Missing data or an unsuccessful local route produces a clear unavailable state. Turning it off does not disable offline capability.
- **Preferred maps (when available)** chooses Online then Offline, or Offline then Online. The first usable route wins. Missing credentials/data/coverage, failed requests, invalid results and no route trigger the other provider once. A Wi-Fi connection alone does not mean online routing is available.
- Strict offline mode disables the preference row while remembering its selection. Default: strict off, Online preferred. An earlier explicit offline trial marker migrates to strict offline mode.

Preview, initial guidance and recalculation use the same `PolicyRouteEngine`. Online transport has the existing five-second timeout; local transport has a fifteen-second deadline, giving a finite twenty-second transport budget with at most one attempt per provider. A changed policy rejects an old result. Local routing never requires a Mapbox key. Place/address search remains online and needs its public key.

In **Offline Maps**, select states, U.S. region groups or countries. One download includes missing road data and available offline routing data. Already-installed road data can be retained when adding routing. First-time native setup happens automatically in Prepare. Routing coverage is shown separately from road-data readiness; current published routing coverage is **Iowa and Illinois**.

**Weekly and Monthly** reuse `PreferredSchedule` and upstream's existing Sunday / first-of-month eligibility gates. Every eligible road-data update queues the companion routing-data update. The shared job checks the maintained catalog for a newer immutable bundle; it does not rebuild OSM on the car. A new graph must be published by the maintainer before a device can download that update. Both routing policy choices allow scheduled downloads.

**Remove maps** and Storage & Data's **Delete** remove both installed road data and routing graphs, plus partial routing downloads. They retain saved places, selected geographic regions, the schedule and the isolated routing runtime. These are the existing global map-deletion actions. Per-region deletion is not exposed because mapd does not provide tile ownership/removal by region. Deletion is blocked while a download or active trip is running; graph leases protect active readers.

## Download behavior

The familiar percentage/bar, Prepare / Download / Install / Ready steps, region tiles, settings footer and top-right action are preserved. A small label identifies the current map set. Road data reports files; routing reports bytes. Percentages are phase-specific and can restart when the label changes. No byte/file averaging or invented overall progress is used. Download at 100% is not Ready until validation and installation finish. A green region means both required map sets are installed.

Routing jobs persist outside the UI, pause while driving/an active trip or without fresh Wi-Fi state, and retain partial files for byte-range resume. The companion hook queues its journal atomically without waiting for the graph install lock. Its upstream import/call and owned body both contain ordinary exceptions so routing cannot interrupt the road-map signal. Cancellation is scoped to the current job. An old cancellation cannot cancel a later request. Completed road data and existing good graphs survive a failed routing download. Retry downloads missing routing data in the same screen. Native setup uses its own environment and does not modify openpilot's interpreter.

The [public data release](https://github.com/jfgordon2/Tandem/releases/tag/routing-data-v1) contains `catalog.json`, the Iowa and connected Iowa–Illinois manifests/graphs, both original OSM extracts and attribution. The catalog selects packages by geography. A catalog checksum authenticates each manifest's content over HTTPS; manifests declare file lengths and SHA-256. Downloads validate those before atomic installation/activation. Immutable IDs prevent overwriting a graph in use.

The current test catalog, `catalog-squashfs-v1.json`, selects driving-only graphs in read-only compressed images. Iowa downloads and installs 81,522,688 bytes (77.75 MiB) of graph data. Connected Iowa–Illinois downloads and installs 258,793,472 bytes (246.80 MiB). A manifest and small local verification receipt add under 3 KiB. Old catalogs and plain/zstd packages remain available to older software. The isolated Valhalla 3.9.1 runtime was about 133 MiB in the earlier device trial. Existing mapd road data remains under `/data/media/0/osm/offline`; routing lives under `/data/tandem/navigation`. Maps storage accounting includes physical routing images and partial downloads. Mounts sit outside that directory so the exposed logical tar is not counted a second time.

Manifest schema 3 declares the stored image and the logical graph separately. Installation checks both SHA-256 values, streaming the logical tar through a bounded `unsquashfs` pipe without retaining an expanded copy. The image is made read-only, synced and atomically installed with a verification receipt bound to its manifest generation and file identity (device/inode, size, modification and change times). Route startup checks that receipt and metadata, then mounts with `ro,nodev,nosuid,noexec,loop`; it never hashes the full image or logical graph. Native startup reads the tar's small `index.bin` rather than scanning every tile header. The pinned reader still memory-maps the native tar, and normal route costing is unchanged.

Parked maintenance checks due bundles every 24 hours when the existing Wi-Fi/parked gate permits. Routine checks hash the stored image only; a missing or changed receipt requires full acceptance checks again. Maintenance yields to downloads, driving and an active destination. Normal file replacement or modification invalidates readiness immediately. Silent corruption that preserves metadata can remain undetected until the next full audit; the receipt deliberately avoids an expensive full scan before every route. Legacy schema 1 plain and schema 2 zstd-transport packages remain supported, with a parked verification pass to create their first receipt. There is also an explicit maintainer `verify` command. Decoder queues, checksum buffers and subprocess lifetime are bounded; no full graph is expanded into tmpfs or Python memory.

Driving graphs exclude roads usable only by pedestrians or cyclists. They retain vehicular access, driveways/parking access, hierarchy, shortcuts and mapped lane/sign/speed-limit data. Platforms, bike-share stations, construction roads, retained OSM node IDs and pedestrian-area traversals are disabled; these were already absent in the earlier build defaults. Source PBFs, build intermediates and elevation/transit datasets are not part of the device download. The known name-consistency penalty difference remains under investigation: the Chicago-to-Des Moines sample chooses a different final approach. An extra enhancement pass lost lane guidance and was rejected. See [size research](valhalla-map-size-research.md) and [compressed-package verification](valhalla-compressed-routing-verification.md).

States can be selected one at a time. Iowa alone uses the smaller Iowa package. Illinois alone currently uses the 246.80 MiB connected Iowa–Illinois package too; no dedicated Illinois-only package is published. Adding Illinois downloads the connected package and keeps the existing Iowa graph; it does not concatenate independently built graphs. Selecting both afterward reuses the installed connected package. The Illinois addition currently downloads the entire combined graph, including Iowa routing data again; this is not an incremental tile downloader. Existing road data is retained, and the original source PBFs are not downloaded to the device. Separate state downloads can give exactly the combined result if they contain compatible tile subsets from the same shared build, with shared-border deduplication, dataset-version validation and an atomic combined graph view. The current single-extract reader would need that integration; connected packages are a test limitation rather than a Valhalla requirement.

Separate graphs can serve separate trips. Each route must fit one connected graph; independently built neighboring extracts are never concatenated. Bounding boxes only precheck coverage; interior roads can still be absent or disconnected.

## Onroad behavior

The existing bottom-left status chip shows Finding route, Recalculating route, Waiting for GPS or route failure. Successful fallback briefly shows Using offline maps / Using online maps. Strict offline mode never shows an online fallback confirmation. Driving/safety reasons have priority, and alerts hide the existing chip stack normally.

The arrival/time-left/street bar stays in place. The last useful estimates may remain for a maximum twenty-second display-only grace during recalculation or GPS loss; then they become dashes. New destinations and End route clear them immediately. These retained values never enter `navInstruction` or `NavInstructionState`. Stale turn cards and control-facing guidance are invalidated immediately.

## Process and compatibility boundaries

`tandem_routingd` runs at nice 19 for Tandem, independent of the strict/preferred settings. Its map manager handles persistent download jobs; the broker owns a mode-0600 Unix socket, bounded queue and one serialized native Actor subprocess. Navigation has priority over queued previews. Crashes/timeouts discard the native worker and back off. After 15 seconds without a request, the worker exits and unused image mounts are released, even during guidance: navigation owns the completed route. Native search arrays are released between requests, the simple tile cache avoids a fixed global flat index, unused response trees are discarded, and Linux heap trimming returns unused allocations. These choices trade some repeated-route speed for lower retained RAM; they do not impose a hard search-size limit. See the [device measurements](valhalla-verified-startup.md).

On Linux the native worker denies socket/connect syscalls before importing Valhalla, confirms the denial, and clears remote tile URLs. Desktop native execution reports that kernel isolation is not enforced there. The broker talks to the worker over pipes. Graphs are leased while read. Both route providers convert to the existing route model and existing message schemas.

The owned navigation subclass checks GPS freshness, destination/policy/data generations and terminal-step arrival cleanup. The owned cruise observer and turn card reject stale guidance. The upstream integration inventory in [README](../README.md#keeping-rebases-easy) lists every external hook, including the exception-isolated companion-download hook after upstream's schedule gates.

## Rollback and maintainer tools

`TANDEM_ROUTING=0` restores the original online provider and disables the broker/map companion. Any of `TANDEM_SETTINGS=0`, `TANDEM_HOME=0`, `TANDEM_ONROAD=0`, `TANDEM_SIDEBAR=0` also disables the integration, preserving upstream UI behavior. The driver's Offline maps only switch is a routing policy, not this integration rollback.

The CLI remains available for maintainer diagnostics, not the driver flow:

```sh
python3 -m starpilot.tandem.routing.tools.manage status
python3 -m starpilot.tandem.routing.tools.manage runtime
python3 -m starpilot.tandem.routing.tools.manage install /path/to/complete-bundle
python3 -m starpilot.tandem.routing.tools.manage activate BUNDLE_ID
python3 -m starpilot.tandem.routing.tools.manage verify BUNDLE_ID
```

CLI `enable`/`disable` control a separate maintainer integration marker, preserving the rollback command's meaning. They do not change the driver's strict/preferred policy. `TANDEM_ROUTING=0` forces complete rollback, while `TANDEM_ROUTING=1` explicitly overrides the maintainer marker; upstream screen switches still win. Policy JSON lives beside the existing `.tandem_*` preferences and participates in their backup/restore convention.

Build a new connected graph off-device with `starpilot.tandem.routing.tools.build`. Driving-only and SquashFS storage are the defaults; `--storage zstd`, `--storage plain`, `--all-modes` and `--uncompressed` are maintainer control-build options. `mksquashfs` packages gzip level 6 in 128 KiB blocks with two threads and a 64 MiB packaging-memory setting. Gzip supports the device's existing 4.9 kernel; its SquashFS driver lacks zstd. The repeatable `--additional-source PATH URL` option feeds all PBFs into one native build; repeat `--region` for the covered state/country tokens. Each input's checksum and URL remain in the manifest's `sources` list. This follows [Valhalla's multi-extract build flow](https://valhalla.github.io/valhalla/start/building/). Use a new immutable ID, add accurate `regions`, retain source/provenance and ODbL attribution, and publish manifest/files with matching checksums before updating the maintained catalog. Schema 3 catalog bytes count the installed physical image, not the logical tar. The matching PBFs are distributed with the current data release. No source graph build runs on the car.

## Verification and remaining device checks

Host checks cover provider ordering, strict-mode races, preview invalidation, GPS/control freshness, actual upstream Weekly/Monthly gates, pause/cancel/retry, checksum/range download, readiness, deletion leases, settings search and UI components. A real unauthenticated HTTPS catalog/manifest/range download installed and activated the published Iowa graph in an isolated host directory. The earlier [device trial](valhalla-device-trial.md) measures native routing separately.

The host component captures and pseudo-language checks were followed by native raylib captures from an isolated source copy on the comma device. Chromium checks the mock/comparison pages. The optional `TANDEM_CAPTURE_TEXTURE=1` screenshot mode reads the landscape render target before physical panel rotation/color transforms. Four cereal/hardware UI test files remain omitted on the host as documented in AGENTS.md; they also ran with the device’s compiled dependencies. See [revision 2 verification](valhalla-revision-2-verification.md) for results and limits. This revision has not been deployed to the live driving checkout or verified while driving. New navigation wording uses explicitly noted English PO fallbacks pending translation.

## First supervised routed-drive RAM check

This remains acceptance work, not a completed drive test. The review reported about 3.5 GiB of device RAM and 47% used while parked; the earlier Iowa worker peaked around 100 MiB RSS. Those parked figures do not establish headroom alongside modeld, the camera/UI and a routed drive, especially with the larger Iowa–Illinois graph.

Before departure, record the software revision, graph ID, model and parked memory baseline. During a supervised drive, watch `deviceState.memoryUsagePercent` and record native_worker, routingd, modeld and UI RSS/PSS through initial routing and a reroute. Compare with a similar drive without a route and check missed frames/planner deadlines. StarPilot raises Low Memory above 90%; RamWatch holds its Low on RAM chip until usage falls to 85%. Routing remains ahead of that lowest-priority chip. Do not deliberately exhaust RAM to trigger it.

The existing per-drive RAM recorder and conditional Device › RAM section are preserved. They retain snapshots at the drive's low-RAM peak when that event occurs; normal drives need the observed memory readings too. Both `routingd` and `native_worker` are identified as Routing in the existing RAM view. Do not mark driving/RAM acceptance complete from the parked or synthetic-scene results.
