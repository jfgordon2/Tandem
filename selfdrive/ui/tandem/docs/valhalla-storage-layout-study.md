# Installed routing storage: further reductions

2026-11-04. This is a follow-up experiment, not a production package change. The published driving-only packages remain the current zstd-download/plain-tar format. This study changes no navigation UI, live checkout, active bundle or routing cost options.

## The current sizes are not minimums

The 212.64 MiB Iowa / 682.76 MiB connected graph figures describe **expanded installed tars**. The previous zstd change compressed their downloads, not the installed data. A lossless compressed filesystem can preserve the exact tar bytes while reducing physical storage. This is independent of removing graph content.

Measured alternatives:

| Storage representation | Iowa MiB | Iowa + Illinois MiB | Status |
| --- | ---: | ---: | --- |
| Current plain graph tar | 212.64 | 682.76 | Published test format |
| No shortcut edges or bounding-circle index; plain tar | 202.55 | 654.35 | Native off-device sample comparisons |
| Individually gzip-compressed native tiles, 4 KiB allocation estimate | 78.06 | 246.90 | Graph bytes preserved, but poor long-route performance with the tested cache |
| SquashFS image containing the exact current tar | 76.74 | 245.98 | Mounted, routed and hash-verified on the device |

The rows are separate experiments, not cumulative savings. SquashFS image sizes are 80,465,920 and 257,925,120 bytes. They exclude the separate native runtime, StarPilot road maps and any retained previous graph. The Iowa image used gzip level 9 and the connected image level 6, each with 1 MiB blocks. Their compressed sizes are not proven optimal.

## Where the plain graph space goes

Read-only inventory of every tile uses the pinned 3.9.1 header layout and validates each tile size and section boundaries. Key sections:

| Section | Iowa MiB | Iowa + Illinois MiB |
| --- | ---: | ---: |
| Directed road-link records | 114.57 | 374.63 |
| Junction/node records | 35.22 | 110.58 |
| Geometry and edge information | 42.88 | 134.70 |
| Spatial search bins | 10.09 | 32.46 |
| Bounding-circle acceleration index | 5.05 | 16.23 |
| Hierarchy transitions | 2.78 | 7.26 |
| All names, sign text and tagged text | 1.27 | 4.36 |

Approximately 70% is nodes and road-link records, with another 20% in geometry and edge information. Unused bicycle/truck fields inside fixed-width records are not separable files: discarding their values does not shrink those structures. A smaller structure would require a matching custom reader/tile format. All names/sign text together account for about 0.6%, so deleting optional text cannot yield a large saving. The inventory confirms no elevation payload, predicted traffic-speed profiles or transit stop/route records in either graph.

## Optional acceleration data

The native builder supports `mjolnir.shortcuts: false` and `mjolnir.data_processing.build_bounding_circles: false`. The latter index is used during ordinary [Loki candidate search](https://github.com/valhalla/valhalla/blob/3.9.1/src/loki/search.cc); it is not an unused product feature. The search includes a fallback when the index is absent. Shortcut edges likewise accelerate routing. These can be tested as performance/storage tradeoffs without deleting physical driving roads.

Native builds with both disabled, while retaining hierarchy, driving access, driveways, lanes/signs and all other current flags, produced the 202.55 / 654.35 MiB tars above. Iowa's local sample and all six connected samples had identical geometry, per-segment speed-limit data and lane components to the current driving graph. Instructions matched except for one additional `Keep left to stay on I 80` in the Chicago-to-Des Moines sample; the geometry still matched exactly. The longest measured warm host route was 0.067 seconds. This is a small sample, not on-device performance or broad routing acceptance.

## Individually compressed native tiles

The [pinned native reader](https://github.com/valhalla/valhalla/blob/3.9.1/src/baldr/graphtile.cc) supports `.gph.gz` files and inflates them into tile-cache memory. Every tile's gzip roundtrip was checked by SHA-256. Total payloads were 81,158,100 and 257,571,663 bytes; the table includes estimated 4 KiB allocation for their individual files, excluding directory metadata.

All six connected routes retained distance, lane counts and mapped speed-limit counts in a host trial with a 64 MiB hard LRU tile cache. However, the interstate samples took 13-15 seconds, with process peak RSS around 301 MiB. Cache pressure and repeated full-tile decompression make that tested configuration unsuitable for the current route deadline. Those measurements do not establish behavior for other cache sizes or devices.

## Lossless compressed filesystem on the actual device

The device runs kernel 4.9.103 and already provides SquashFS, gzip support, `mksquashfs` and mount tools. Its kernel configuration does **not** declare SquashFS zstd support, so the test images use gzip. [Kernel documentation](https://docs.kernel.org/filesystems/squashfs.html) describes SquashFS as a compressed read-only filesystem with decompressed file data managed through the normal page cache.

Each image contains the existing `tiles.tar` unchanged. The test mounted it read-only with `nodev,nosuid,noexec`, pointed the existing Valhalla 3.9.1 memory-mapped reader at the mounted tar, and ran public-coordinate route samples with socket/connect calls denied. Full mounted-tar SHA-256 matched the current graph manifest. Both temporary mounts were unmounted afterward.

- Iowa local route: 0.48 seconds; full native process including interpreter/Actor startup: 4.87 seconds; peak native RSS: 62,016 KiB.
- Connected graph: all six samples succeeded in 0.12-0.81 seconds each; full process including startup and all samples: 9.51 seconds; peak native RSS: 128,652 KiB.
- Geometry lengths, mapped speed-limit counts and lane counts matched the current driving graph's samples. The mounted file hash establishes that the underlying graph contents were identical.

These are parked feasibility checks. Caches were not flushed; full-file SHA verification ran after the route samples. RSS is the native process, not total system memory or all kernel compressed/decompressed page-cache use. This does not establish first-route latency under driving load, mount/reboot behavior or RAM headroom alongside modeld.

## Controlled performance comparison

A subsequent parked-device comparison measured plain and SquashFS graphs in alternating order, using a fresh native process for each trial. Iowa has two trials per format; the connected graph has three. Each process verified the full logical tar SHA-256 **before** constructing the Actor, matching the existing worker's startup verification, then ran each route three times. Only the test tar/image received `POSIX_FADV_DONTNEED`; the image was remounted for each trial. These are targeted best-effort cache-eviction hints, not a global cache flush or a guarantee that every hardware cache was cold. The supervisor stopped if the device went onroad or acquired a destination. Every temporary mount was released.

Median results:

| Measurement | Plain tar | SquashFS |
| --- | ---: | ---: |
| Iowa, new worker to first local-route result | 1.80 s | 4.28 s |
| Iowa-Illinois, new worker to first local-route result | 3.77 s | 12.72 s |
| Iowa-Illinois, full graph hash verification alone | 3.24 s | 12.14 s |
| Iowa-Illinois, Actor/config construction after verification | 0.038 s | 0.052 s |
| Iowa-Illinois, repeated Des Moines to Chicago route | 0.241 s | 0.242 s |
| Iowa-Illinois, native process peak RSS | 125.95 MiB | 125.89 MiB |

The first-result timing starts in the native benchmark script and includes native import, full graph verification, Actor/config construction and the first route. It excludes broker/UI transport and the separately measured mount operation. Thus it approximates the current worker path rather than claiming a full application response-time measurement.

All normalized route results, including geometry, step instructions, banners, lane components, distance, duration and speed limits, hashed identically across formats, repetitions and trials. Warm-route median differences for the six connected samples were under one millisecond. Full verification deliberately warms logical graph pages, so those steady-state results do not predict rerouting after cache eviction under driving load.

The major measured penalty is full logical-tar verification at each new worker or bundle load. SquashFS must decompress the entire graph before hashing it. With the current 15-second local deadline, a 12.72-second first result leaves little margin for additional load or queueing. The worker remains resident during an active trip; the broker releases it after more than 60 seconds idle when there is no destination. This startup penalty therefore does not repeat on every route request, but can repeat after worker restart or bundle selection changes.

Kernel decompression adds work and uses the page cache beyond native-process RSS. The test does not establish total CPU/RAM impact alongside modeld. A compressed-image hash/acceptance design and native tar index are candidates for reducing startup work; their performance has not been measured here, and integrity checks must be preserved. The current cold-start behavior is a reason to finish that design before making SquashFS the default.

Raw measurements and the derived medians are in `squashfs-performance.json` and `squashfs-performance-summary.json` under the ignored report directory. These measurements extend, rather than replace, the earlier feasibility checks.

## Implementation direction (historical study)

The subsequent [compressed-image implementation](valhalla-verified-startup.md) implements this direction with smaller blocks, a native index and receipt-based startup checks. The measurements above describe the earlier full-hash startup experiment, not the current route path. The new immutable test catalog is `catalog-squashfs-v1.json`; older assets remain available.

The large opportunity is **compressed installed storage**, not deleting useful road information. SquashFS retains acceleration data and exact graph bytes while reducing physical graph storage by roughly 64%. It requires owned integration for image validation, read-only mount lifecycle, reboot recovery, reader leases, deletion/unmount, disk accounting and legacy plain-tar compatibility. The existing worker's startup verification also needs measuring because scanning/hash-verifying a mounted logical tar can force decompression of the whole graph. Prefer verifying the immutable image's declared hash at runtime, with logical graph verification at package acceptance, rather than silently removing integrity checks.

Mount paths should be outside storage-accounting walks of the physical bundle directory to avoid counting both the image and the exposed logical tar. Installation and activation must survive cancellation/restart and preserve the previous bundle. No new driver URL or screen is needed. The existing supervised-drive RAM acceptance remains required.

Do not describe the earlier plain-tar sizes as the smallest safe result. Optional acceleration removal yields a modest additional reduction; the tested compressed-filesystem representation offers substantial installed-size savings. At the time of this study no new representation had been published; the linked follow-up records the implemented default.

Local raw reports are under ignored `tools/out/routing-reports/`: `tile-inventory.json`, `gzip-tiles-study.json`, `gzip-native-*.json`, `lean-*.json`, `lean-semantic-comparison.json` and `squashfs-device-*.json`. Experimental scripts and native builds remain in task-specific temporary directories. The linked follow-up changes the builder to compressed images while retaining the driving graph.
