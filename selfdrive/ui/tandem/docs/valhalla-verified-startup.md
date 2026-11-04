# Compressed installed maps, verified startup and RAM

November 4, 2026, `valhalla` branch. This changes owned routing code and maintainer tools only. No screen, wording, approved mock or additional upstream hook changes are part of this storage revision. The live device checkout has not been updated and no drive has been performed.

## Installed representation

The new [test catalog](https://github.com/jfgordon2/Tandem/releases/download/routing-data-v1/catalog-squashfs-v1.json) references immutable schema-3 packages in the existing data release. Older catalogs and assets remain unchanged.

| Package | Download and installed graph | Logical indexed tar |
| --- | ---: | ---: |
| `iowa-squashfs-20261104-v1` | 81,522,688 bytes / 77.75 MiB | 222,627,840 bytes / 212.31 MiB |
| `iowa-illinois-squashfs-20261104-v1` | 258,793,472 bytes / 246.80 MiB | 715,274,240 bytes / 682.14 MiB |

Each image contains one native `tiles.tar`, with an `index.bin` first member. Its graph tiles are unchanged from the accepted driving-only build. Gzip level 6, 128 KiB blocks, two packaging threads and `mksquashfs -mem 64M` keep off-device packaging modest. Smaller blocks limit decompression granularity at a small size cost compared with the earlier 1 MiB-block experiment. The device's built-in SquashFS supports gzip, but not zstd. No kernel, system-package or live-checkout change is needed.

The native reader maps the mounted tar; no expanded tar is installed or placed in tmpfs. Read-only mounts use `nodev,nosuid,noexec`, verify the loop backing file and logical size, and live outside bundle disk accounting. Their namespace includes a digest of the data root, so an isolated test cannot reclaim live routing mounts. Shared reader leases protect mounts and images from deletion/replacement. Idle workers and orphan mounts are reclaimed without forced unmounts. Deletion unmounts before removing the physical image.

The runtime and existing mapd road maps add their own storage. Illinois alone currently selects the connected 246.80 MiB package. Separate shared-build state subsets, border-tile deduplication and a combined reader view remain future work; independently built state graphs are not joined.

## Integrity outside the route path

Installation hashes the physical image and checks the declared expanded tar length/SHA-256 through a streaming `unsquashfs -cat` pipe. On the device's 4.6 decoder, one thread uses 4 MiB data and 1 MiB fragment queues. Newer decoders use an 8 MiB memory setting. Python uses a bounded 256 KiB read buffer, checks cancellation between reads, and terminates the decoder on failure. The expanded graph is never retained.

Before acceptance, image files become read-only and files/manifest are synced. An atomic `.verified.json` receipt binds the manifest digest and physical files' device, inode, size, mtime and ctime. The receipt and installed parent directories are synced. Atomic rename preserves file identity. Copy installs verify the copied files before publication. A damaged same-generation package can be replaced only under an exclusive lease; another manifest under the same immutable ID is rejected.

Readiness, activation of an accepted bundle, route selection and native startup read the manifest/receipt and stat the files. They do not hash the graph. A missing/changed receipt prevents routing until a parked check completes. Normal same-size modification, restored mtime and inode replacement are covered; ctime still changes. This is deliberately not a guarantee against silent bit rot with unchanged metadata. A due parked audit detects that later.

The manager checks for due audits at most once per minute, with a 24-hour verification interval. The existing parked/Wi-Fi gate and absence of an active destination apply. New map jobs, shutdown and driving interrupt the scan. An unchanged accepted image needs only its physical hash checked again, without a second logical decompression pass. File-cache eviction hints target only the verified physical file. Legacy schema-1 and schema-2 bundles get a parked acceptance receipt before routing; maintainers can invoke `tools.manage verify ID`. No full scan runs as fallback inside a route call.

## RAM policy

The native tar index avoids touching every graph-tile header at startup. A simple metadata cache replaces Valhalla's fixed global flat index. Search reserves start at 100,000 labels, can grow as needed, and are cleared between requests; this is not a route-size cap. Unused intersections/waypoint trees are dropped before JSON transport, while the normalized guidance contract is preserved. Temporary responses are released and Linux heap trimming returns unused allocations.

The broker closes the native worker after 15 idle seconds even during guidance, then releases unused mounts. Navigation retains the completed route; the Actor is needed for initial routing or rerouting. Releasing it also allows the compressed filesystem's decompressed pages to be reclaimed. The persistent broker remains. These choices can increase repeated-route allocation work. Native RSS does not account for every kernel cache page, and these settings do not impose a hard system-RAM ceiling.

## Parked device measurements

The comma 3X ran new code only under `/data/tandem/verified-routing-trial-20261104`, with a private data root and the existing isolated 3.9.1 runtime. Real `IsOnroad` and `NavDestination` were checked throughout; no destination, control state or live publisher was changed. The worker confirmed Linux socket/connect denial. Each first route used a fresh worker, an unmounted image and targeted `POSIX_FADV_DONTNEED` on that test image. These are best-effort cache hints, not a global cache flush or proof of cold hardware caches.

Two trials per package, two repetitions of two Iowa samples and seven connected samples, produced 36 results. Every normalized result hashed identically to the preceding driving-only graph's results, including geometry, steps, instructions, banners, lane components, distance, duration and speed limits.

| Measurement | Iowa | Iowa and Illinois |
| --- | ---: | ---: |
| First local route, full broker-to-worker exchange | 1.45 / 1.48 s | 1.49 / 1.48 s |
| Largest observed native peak RSS | 66.99 MiB | 110.85 MiB |
| Largest post-trim native RSS | 58.11 MiB | 92.88 MiB |
| Largest post-trim native PSS | 54.75 MiB | 89.52 MiB |
| Largest post-trim anonymous memory | 27.42 MiB | 29.28 MiB |
| Idle worker exit and image unmount | 15.53 s | 15.53 s |
| Routine physical-image audit | 0.61 s | 1.75 s |

Warm full IPC roundtrips had medians of 0.14 seconds for the Iowa local route and 0.73 seconds for Des Moines to Chicago on the connected package. The previous study's 0.24-second interstate figure timed the native routing call directly; the new figures include the worker envelope, memory measurements, JSON and pipe transport, so those timings are not an isolated measure of the cache-policy tradeoff. The earlier compressed full-hash startup took 12.72 seconds for the connected graph; that scan is now absent. The new startup measurement also includes mount/IPC work that the old native-only measurement excluded.

The initial Iowa image install took 2.51 seconds in the first trial; the connected install took 8.54 seconds. Both installed only the image, manifest and receipt. Runtime/reboot caches and concurrent driving load were not simulated.

## Verification

- Host routing regressions: 122 passed. The host cannot import the ELF cereal/msgq extension; its separate real-schema test runs on the device.
- Device routing regressions: 123 passed, including the real cereal serialization test. These use `/usr/local/venv/bin/python`, existing isolated test dependencies, a private `OPENPILOT_PREFIX` and `/data` temporary directory. The source copy includes this branch's navigation/download hooks; the live checkout is used only for read-only dependency links. Other unrelated backend suites were outside this routing run.
- Host UI suite: 694 passed, two existing skips. As prescribed in AGENTS.md, `test_headroom_warning.py`, `test_home_layout.py`, `test_limit_offers.py` and `test_onroad.py` were omitted on this Mac.
- Native route checks: 36 matching results, zero hot-path graph hashes, actual read-only mounts, worker exit and mount cleanup.
- Every `.gph` member in both new indexed tars was compared by name and SHA-256 with its preceding driving-only tar; all tile contents matched. Only archive indexing/metadata and physical compression changed.
- A real HTTPS Iowa download was cancelled after 1 MiB, resumed from that offset, verified, installed without an expanded tar and activated in an isolated host root. GitHub asset digests matched both images and manifests before the new catalog was published.
- Final device acceptance fetched both published manifests, checked their catalog digests, installed and routed each package with zero hot-path graph hashes, rejected changed image metadata, detected deliberately altered physical bytes in a full check, restored/reverified the private image, blocked deletion during a native reader lease, and unmounted it before deletion. Temporary installed bundles were removed afterward.
- The native reader also returned the matching Iowa route from a legacy unindexed tar with the new cache configuration.
- Ruff and whitespace checks cover the owned routing/UI code. No UI render changes require new mocks.

Raw reports under ignored `tools/out/routing-reports/`: `verified-startup-device.json`, `squashfs-device-acceptance.json`, `squashfs-https-install.json`, `squashfs-tile-equivalence.json` and the earlier `squashfs-performance*.json`. Benchmark scripts remain in the isolated device directory. Tests exercise stale/missing receipts, same-size mutation, inode changes, parked migration/audit, full-hash failure, bounded decoder protocol, schema compatibility, install repair, mount identity/flags, leases, deletion, idle release and normalized response equivalence.

The known driving-only name-consistency penalty variation near the Des Moines destination remains unchanged. No useful graph fields, hierarchy, shortcuts or lane guidance were removed for these storage savings. Translation acceptance and the first supervised routed drive alongside modeld remain open. Watch the existing Low on RAM threshold and per-drive recorder; these parked process measurements do not establish total-system RAM headroom while driving.
