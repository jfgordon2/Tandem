# Shared US routing data

The `valhalla` implementation assembles an exact selection of states from one
compatible national driving graph. State extracts are never built separately and
then concatenated. The existing geographic picker and Update action remain the
driver interface. The two `valhalla3-regions-*` mocks were approved on November 4.

## Updating a selection

1. Check the states to retain, then choose **Update maps**. The selection is the
   complete desired routing set, rather than a list to append to an old bundle.
2. Refresh the maintained catalog. A cached catalog remains usable if its host is
   unavailable. A newer published dataset requires its matching data; graph IDs
   from different builds cannot be mixed.
3. Fully checksum the existing compressed graph and inventory before reusing
   them. Download only missing packs from that same dataset. Completed cached
   packs are also checksummed before reuse; damaged completed files are fetched
   again. Transfers retain the existing byte-range resume behavior.
4. Stream the retained and newly downloaded tiles into one compressed replacement
   image. Keep the working image intact until the replacement is verified and
   atomically activated. No expanded graph is stored on disk or in tmpfs.
5. Remove superseded images and consumed download packs. Tiles shared by checked
   states remain exactly once. An active reader can defer physical cleanup, but
   the committed selection immediately determines routing eligibility.

Deselecting one state uses the remaining tiles locally, with **zero routing-data
downloads** when the dataset is unchanged and checksums pass. Deselecting every
state and choosing Update clears routing images, partial routing downloads and
recognized legacy road tiles;
it does not run the compressor or install a runtime. The empty selection stays
in the picker instead of displaying download progress.
For a nonempty local rebuild, the existing approved Install screen shows download
complete at 100%, with the region still current. Ready follows verification and
activation; the percentage does not claim to measure compression progress.

The same Update now removes unneeded legacy road tiles after verified routing
activation, before the job becomes Ready. It keeps the union of mapd archive
groups requested by the selected regions, including border/padding groups.
Recognized leftover legacy archives in `osm/tmp/offline` follow the same rule.
No retained road tiles are downloaded again for a local selection reduction.
Old Ready receipts for deselected regions are retired and physical storage is
recounted. A pre-activation routing failure leaves previous road data intact;
an interrupted cleanup can leave extra tiles, which the next Update removes.
The existing global **Remove maps** / Storage **Delete** action still removes
both datasets. Saved places are retained. No migration of the
owner's old Iowa / Iowa–Illinois test bundles is required; remove those test
graphs when switching to the new catalog.

Weekly and Monthly updates enqueue the same exact-selection job through the
existing guarded scheduler hook. An unchanged dataset verifies and reuses its
installed data; a newer immutable dataset downloads the required new packs.
Publishing data is a maintainer operation. The device never builds OSM.
An ordinary Update with the same states still uses upstream's road-data update
controller. A changed routing selection can retain already-downloaded road data.

### Legacy tile ownership

Owned `starpilot/tandem/routing/road.py` reads `mapd_download_menu.json` when
present, otherwise the JSON embedded in the installed `starpilot/navigation/mapd`
binary. It maps the same rounded 2-degree download archive groups to their
quarter-degree tile directories. Sparse `download_rows` are honored only when
the installed binary declares that field; older binaries use bounding boxes.
The binary is memory-mapped and only a bounded menu slice is decoded. No tile
contents, second geographic catalog or network request is needed for cleanup.

Cleanup rechecks parked state, cancellation and downloader activity between
files. Only recognized map tile names under valid grid directories are removed;
unknown files and symlinks stay untouched. Unreadable or unknown region metadata
prevents cleanup before files or readiness receipts change. The current embedded
menu lacks `us_state.GU`; selecting it (including the whole-US expansion) requires
a corrected mapd menu before cleanup can run. Routing coverage for Guam is
separate from this legacy metadata limitation.

Legacy-only country updates apply their selection after the road download
completes even when the routing catalog reports that country's routes unavailable.
TANDEM_ROUTING=0 retains the original upstream behavior. The helper adds no
upstream hook and uses the existing Install/Ready flow with no visual changes.
Tests redirect road data to `TANDEM_ROAD_MAPS_DIR` and never touch live maps.

Host validation: 27 dedicated ownership/deletion tests, 289 routing tests total,
and 750 UI tests passed (two skips; four hardware-dependent UI files omitted).
The SSH device check timed out, so this cleanup has not been exercised on live
device data.

## Format and memory

`tools/us_build.py` builds the dated main US, American Oceania, Puerto Rico and
US Virgin Islands extracts in **one native build**. Osmium first merges and
deduplicates the dated extracts into one input PBF, avoiding the pinned builder's
[multiple-input caveat](https://github.com/valhalla/valhalla/issues/3925).
The main US extract omits the
Caribbean territories. The combined inputs support the selector's 50 states,
District of Columbia and five territories.

The build includes administrative metadata and time zones. Complete US parent
boundaries supplement the regional extracts, which omit complete parent ways.
The pinned timezone-boundary-builder 2026d archive has a checked SHA-256. Auxiliary
input receipts and resulting database checksums enter the graph-build receipt.
Valhalla 3.9.1 inherits the parent's driving side onto child administrations; the
build preserves its own left-driving rule for the Virgin Islands after that
inheritance. These are off-device inputs, not extra device downloads.

`tools/states.py` assigns every GPH tile at every hierarchy level to the state
polygons it intersects. Border tiles form shared membership groups. Groups split
at 128 MiB of logical tile data. Fringe tiles outside all polygons go to the
nearest state, so the partition drops no graph tiles. Before compression, every
declared region must have data. This retains hierarchy, shortcuts, restrictions,
street names, mapped signs, lanes and speed limits from the driving build.

Catalog schema 2 maps regions to immutable disjoint packs. Each schema 4 pack
contains a SquashFS image with an indexed `tiles.tar`, plus a checked `tiles.json`
inventory. Dataset ID and checksum identify one compatible build. The assembled
state-set manifest records the exact selected regions and referenced packs.

On the device, `datasets.py` reuses verified ranges from the previous image and
mounts at most one incoming pack at a time. `tiles.py` streams the canonical tar
in `(part ID, tile path)` order, checking each tile's length and SHA-256 as it
goes. Selecting states together or incrementally produces the same logical tar.
The native reader continues to map **one indexed tar**, with no runtime patch,
directory cache, custom filesystem or multi-graph route stitching.

The replacement goes directly through `mksquashfs -tar`, gzip level 6, 128 KiB
blocks, **two compression threads and a 64 MiB compressor memory setting**. Checksum and
file-copy buffers are bounded. The installer reserves compressed replacement
space plus headroom, rather than the logical tar's full size. It keeps temporary
input packs only until activation, preventing permanent double storage. A
preflight reserves the missing downloads and compressed replacement together
before transferring state data; unchecked cached data is reclaimed first. A
separate nonblocking updater lock prevents concurrent assemblers; the road-map
enqueue hook never takes that lock. Restart reclaims abandoned assembly outputs
while retaining resumable incoming packs.

Recompression costs CPU time while parked. It is cancelled on a drive, active
destination, policy cancellation or shutdown; completed packs remain resumable.
The compressor is terminated even if its pipe is full. Unused parent heap pages
are returned after the job. Existing receipt-based route startup, idle native
worker exit and mount reclamation are unchanged. Full graph hashes stay out of
route startup. Nonadjacent selected states do not supply missing connecting
states; a route through absent coverage can fail.
Very large selections can take much longer than the two-state measurements.
Use sufficient parked power/time, as for an upstream country download. Existing
shutdown and low-voltage policy remains in StarPilot; an interrupted assembly
restarts from its retained verified packs.

Missing packs use two transfer workers, with 256 KiB transfer buffers and bounded
checksum buffers. The owning job thread alone checks the policy gate, publishes
aggregate byte progress and performs logical image acceptance. Workers pause on
that gate and stop together on a failure or cancellation; an in-flight network
read retains the existing 15-second socket timeout. Every worker is joined before
assembly begins. Completed and partial private files remain resumable on failure.

Hash evidence can be reused within an operation only while path, device/inode,
size, modification time and change time all still match. Downloads use their
final staging paths and images become read-only before their first checksum.
Renames or permission changes do not receive exceptions from this check. The
completed image still gets independent full logical readback. Existing-data
Update checks and parked audits use fresh physical checksums; route startup
continues to use its cheap metadata receipt. See the [speed verification](valhalla-update-speed.md).

The UI caches parsed catalog metadata by file identity and caches download plans
for its existing half-second snapshot. Drawing state cards uses catalog coverage
directly, without reading installed graphs or building download plans each frame.

## Maintainer build and publication

Off-device dependencies are the pinned Valhalla runtime, Shapely, Osmium,
`mksquashfs`/`unsquashfs`, and the SpatiaLite tools. Source downloads are dated,
resumable and checked against Geofabrik's published MD5 before recording SHA-256.
Country boundary and timezone source receipts remain with the build output.

```sh
PYTHONPATH=. TANDEM_ROUTING_DIR=/path/to/build-runtime \
  python -m starpilot.tandem.routing.tools.us_build /path/to/output \
  --snapshot 261102 --id us-driving-20261104-v1 \
  --base-url https://github.com/jfgordon2/Tandem/releases/download/routing-us-20261104-v1 \
  --concurrency 4
```

Retain generous build scratch space. A country build takes substantially longer
than the two-state pilot. Never mark a partially built graph complete. The
`--resume-from` native stage option is for a maintainer who has checked that all
inputs/configuration match and the preceding intermediates are complete.

Compare every region's sampled local route, plus interstate/border cases,
against the complete graph before publication. The check also routes the same
corpus through the complete indexed tar, exercising offsets beyond 8 GiB:

```sh
PYTHONPATH=. TANDEM_ROUTING_DIR=/path/to/build-runtime \
  python -m starpilot.tandem.routing.tools.check_states \
  /path/to/output/graph/tiles /path/to/output/packages \
  --out /path/to/output/route-equivalence.json
```

This off-device check writes one temporary plain tar per sampled state selection
and deletes it after routing. It compares normalized geometry, maneuvers,
distance, time, lane banners and speed slots by their full route checksum.
`--regions us_state.IA,us_state.IL` limits a pilot run. It does not enforce Linux
seccomp on macOS; the native device trial checks that isolation separately.

Export checks every image before preparing immutable assets. National exports
can spread packs over release buckets to avoid GitHub's per-release asset limit:

```sh
python -m starpilot.tandem.routing.tools.export /path/to/output/packages \
  /path/to/assets --catalog-name catalog-us-v1.json \
  --base-url 'https://github.com/jfgordon2/Tandem/releases/download/routing-us-20261104-v1-{bucket}'
```

Upload every pack's image, inventory and manifest first, then verify the remote
asset SHA-256 values. Publish source/provenance and attribution with the data.
Publish the **exported** catalog last, since export updates manifest URLs and
their checksums. Only then change `catalog.URL` and the bundled fallback catalog.
Never overwrite a published immutable pack or silently mix an older graph into
a newer dataset. Keep all code on `valhalla`; `release` remains separate.

## National build, November 4

Dataset `us-driving-20261104-v1` uses the November 2 extracts and contains
17,035 GPH tiles. Its dataset checksum is
`12eccd3c52fc25d3059511746114670e2345fa44d857deca93a0830880f02661`.
There are 343 disjoint packs covering all 56 selector entries. The full logical
indexed tar is 16,210,022,400 bytes; initial pack downloads total about 5.78 GiB.

| Initial selection | Routing download |
| --- | ---: |
| Iowa | 125.01 MiB |
| Illinois | 245.48 MiB |
| Iowa + Illinois | 344.95 MiB |

These are the new national build's transfer sizes, including shared border and
hierarchy packs. They differ from the original two-state pilot below. Incoming
packs are removed after successful assembly, leaving one compressed image plus
its inventory and receipt. Exact installed sizes and update costs depend on the
selection; the table excludes upstream road data and the one-time runtime.
Small manifest requests add metadata overhead to these payload sizes.

All 61 sampled routes matched the complete loose graph using their selected
state packs. The same 61 also matched through the full 15 GiB indexed tar.
Comparisons include geometry, maneuvers, distance, duration, lane banners and
speed slots. The corpus includes a local route in every selectable region and
five interstate/border routes; it is a smoke corpus, not exhaustive US route
coverage or driving-load RAM acceptance. `ROUTE-VERIFICATION.json` accompanies
the published catalog.

The [catalog](https://github.com/jfgordon2/Tandem/releases/tag/routing-us-v1),
both graph buckets and the source release were published as prereleases after
all 1,054 assets were checked against their remote SHA-256 values. A fresh
unauthenticated public HTTPS check downloaded the catalog and three DC packs,
verified them, assembled a temporary maintainer QA tar and matched the native
DC route to the full graph. That check ran on macOS, took 6.8 seconds, and
deleted its expanded scratch files. It does not exercise the device's kernel
mount or represent an on-device install.

The final host routing suite passed 151 tests. The UI suite passed 698 tests
with two skips; the four cereal/hardware UI files listed in AGENTS.md were
excluded. Ruff and translation-template checks passed. The isolated device
routing suite passed 151 tests before the final bundled-catalog test was added.
The national-package update/route matrix is prepared, but its device run is
pending: SSH at 192.168.4.40 became unavailable, and the owner asked to retry
later. The live checkout and destinations were not changed. The hardware pilot
below uses the earlier connected graph and must not be reported as a national
package test. A supervised routed drive with the new data remains outstanding.

### Owner test on the new catalog

1. Update the `valhalla` branch and restart. Keep the device powered, parked and
   on Wi-Fi. Choose Iowa in Offline Maps and Update; wait for Ready. The first
   update downloads the new dataset rather than reusing incompatible old IDs.
2. Keep Iowa checked, add Illinois and Update. This downloads missing shared
   packs, rather than another complete combined bundle. Check a saved route in
   each state and a route across their border.
3. Uncheck Iowa and Update with Illinois still checked. With the same catalog
   and valid checksums, routing downloads are zero. Install rebuilds from the
   retained data. Road tiles are retained by upstream mapd.
4. Add Iowa again and Update, or uncheck every state and Update to clear routing
   data. Returning to the same state selection must produce the same logical
   graph. Saved places remain.
5. On a supervised routed drive, watch the existing Low on RAM status and record
   memory through initial routing and a reroute. The parked/desktop results
   above do not establish driving-load headroom.

## Device pilot, November 4

The isolated trial used the existing connected Iowa–Illinois graph, repartitioned
into seven shared packs. It did not install this source or change destinations
in the live checkout. Nineteen seccomp-isolated native routes matched the previous
normalized route hashes, including the river crossing and both interstate
directions. This validates partition/assembly behavior, independently of a new
national graph's routing results.

| Update | New routing bytes | Elapsed | Installed image |
| --- | ---: | ---: | ---: |
| Iowa | 91,055,414 | 79.0 s | 90,972,160 |
| Add Illinois | 167,869,654 | 196.7 s | 258,781,184 |
| Same Iowa + Illinois | 0 | 3.2 s | 258,781,184 |
| Keep Illinois only | 0 | 100.0 s | 186,077,184 |
| Add Iowa again | 72,781,903 | 168.0 s | 258,781,184 |
| Keep Iowa only | 0 | 50.3 s | 90,972,160 |

Re-adding Iowa reproduced the exact combined tar checksum; returning to Iowa
alone reproduced the initial Iowa checksum. Shared packs were not fetched
twice. Empty selection subsequently removed all test graphs and mounts. Native
worker peak RSS in this corpus was about 111 MiB. A separate sampled compressor
reading was about 21 MiB RSS; the pilot monitor did not capture a compressor
peak. These are parked measurements, not evidence of driving-load RAM headroom.

The approved picker states have native 2160×1080 captures and a comparison page
under `tools/out/us-state-native-compare/index.html`. The built screens retain the
existing shared footer and inline page header. The sample readiness of states
beyond the pilot is illustrative. The national build's checks are recorded
separately above; the original pilot measurements do not describe its packages.

An additional device format check streamed 8,589,935,104 synthetic zero bytes,
verified the complete logical checksum, mounted the resulting image read-only
with the device kernel, and mapped the logical file while touching its final
512 bytes. Parent peak RSS was 39,728 KiB. This verifies GNU large-file tar and
kernel/mmap support beyond 8 GiB; zero data is sparse and does not represent real
map compression size, speed or native route memory.

A real kernel cancellation check also interrupted the compressor while its
producer was suspended on a mounted input file. The producer closed before lease
cleanup and the mount was released before the interruption reached its caller.
Stream cleanup is explicit, so an exception traceback cannot retain that input
descriptor across an unmount.
