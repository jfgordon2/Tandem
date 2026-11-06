# Faster offline map updates

The `valhalla` branch uses two transfer workers, two local compression threads,
and operation-local reuse of verified physical file checksums. Gzip remains at
level 6 with 128 KiB blocks and a 64 MiB compressor memory setting. Published
packs and the catalog are unchanged. This work adds no upstream hooks, screens,
settings or new dependencies.

## Transfers and cancellation

`downloads.prepare_many` keeps at most two transfers in flight. Workers fetch
manifests and physical files, check their hashes, and update bounded progress
counters. Each file uses 256 KiB transfer and 1 MiB checksum buffers. Logical
verification remains serial on the owner thread; its decoder retains the existing
small queue budget. Assembly starts only after the workers have shut down.

The owner alone calls the existing map-job gate and publishes aggregate progress.
While that gate pauses, workers wait on a shared event. Failure or cancellation
stops peers and joins them before returning. Active socket reads retain the
existing 15-second timeout. Completed and partial downloads survive, and the
working graph remains active. Resume accepts the prior cache layout too.

## Checksums and acceptance

`verified.Hashes` lives only within an operation. It binds an actual SHA-256 result
to the path and the full file identity: device, inode, size, mtime and ctime. It
also checks identity before and after reading. A replacement, content change,
rename or permission change invalidates reuse. There is no exemption for ctime
changes and no reuse across a later job or parked audit.

Downloads go straight to their final private staging paths, rather than being
hashed and then moved to another filename. Images become read-only before the
first checksum. The acceptance and install handoffs can therefore compare the
unchanged file identity instead of scanning the same physical bytes again.

Local assembly uses the same technique when writing its manifest and passing the
completed image to installation. It still checks every input tile while streaming
and independently decodes the complete output to verify its logical checksum
before activation. Existing installed data is freshly checksummed on Update.
Parked audits remain full physical checks, and route startup remains metadata-only.

## Host measurements

These are single macOS host trials, not comma performance or driving-load RAM
acceptance. They use real published graph data and full logical checksum checks.

The compression/acceptance trial used the 134,205,440-byte logical Iowa pack
`us-driving-20261104-v1-5c3d7e3774dc3517`. Before uses the `5b6b98f5e7` implementation;
after uses the faster path. Both produced a 49,025,024-byte image and the same
logical SHA-256, `a1cd0fa2e01974e4c1393fee6277072d71cd127cfe44b2b37a027960a07e4373`.

| Measure | Before | After |
| --- | ---: | ---: |
| Compression | 5.548 s | 2.812 s |
| Compression, manifest and acceptance | 5.794 s | 3.051 s |
| Full physical image checksum passes | 2 | 1 |
| Largest child-process peak RSS | 40.6 MiB | 42.8 MiB |

The child RSS is the largest individual compressor/decoder process, not total
system memory. The full logical decoder still ran in both cases.

A fresh unauthenticated HTTPS trial used the three published DC packs, totaling
38,331,647 payload bytes. Both runs used the new checksum path; only transfer
concurrency differed. Sequential preparation took 4.855 seconds, and two-worker
preparation took 2.434 seconds. The observed concurrent fetch counts were one and
two respectively. All three packs passed logical acceptance in each run. Server
cache and network variability limit what this single comparison can establish.

Raw reports are under ignored `tools/out/routing-speed-study/`:
`pipeline.json` and `downloads.json`. Expanded benchmark scratch and temporary
images were removed.

## Verification and remaining device checks

The host routing suite passed 163 tests. New coverage checks real overlapping
transfers, the two-worker ceiling, owner-only progress/gating/acceptance, failure
propagation, paused shutdown, partial range resume, checksum-pass counts,
post-check mutation, and unchanged independent logical acceptance. Existing
corruption, canonical assembly, empty selection and drive-transition tests pass.
The UI suite passed 698 tests with two skips; its four cereal/hardware files were
excluded as documented in AGENTS.md. Ruff and `git diff --check` passed.

The comma did not answer SSH at 192.168.4.40 during this work. No live checkout,
destination or map data was changed. Device benchmarks remain pending. When it
is available, use an isolated parked trial to compare download and assembly time,
parent/compressor/decoder RSS and device temperature. Exercise pause, resume and
cancellation during both transfers and compression, then compare normalized
route hashes. A supervised routed drive remains the final driving-load check.

Subsequent device follow-up reproduced and fixed an install/idle-cleanup race and
caught coarse filesystem timestamp behavior in the hash-evidence cache. The
[progress review](valhalla-map-progress.md) records those checks, a successful
private Iowa/Illinois install, and seven matching native routes. The new cache
waits past the checked file's metadata-clock tick before hashing; it does not
assume that the nanosecond stat API means nanosecond filesystem resolution.
