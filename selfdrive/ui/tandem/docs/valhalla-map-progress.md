# Shared-state map progress review

The owner reported that the top bar finished at download and only Iowa showed a
percentage for an Iowa/Illinois selection. The current screen forces Install to
100%, and paints a percentage on only the first active tile. Both states' routing
packs were downloaded: the device journal recorded 361,706,227 of 361,706,227
payload bytes, followed by `data_incompatible` before activation.

## UI proposal, pending owner review

The three `valhalla4-shared-*` mocks retain the existing progress layout. They are
proposals, not approved implementation references. No screen code has changed.
The owner will review them, and requested the fixed-length sentence
**All selected regions are installed together.** in both install/check mocks.
No sentence lists state names or grows with the selection.

- `valhalla4-shared-download`: show every selected state, including 0% while
  waiting, and its own progress through its required shared packs. Shared bytes
  count once in the overall transfer total.
- `valhalla4-shared-install`: show measured installation progress rather than a
  forced 100%. All states share the same installation counter because they form
  one atomic routing image.
- `valhalla4-shared-check`: continue through full verification, then show Ready
  only after activation. The proposed percentage measures logical bytes fed to
  the builder plus logical bytes checked, rather than estimating elapsed time.

The percentage would be phase-specific, preserving the existing Prepare,
Download, Install and Ready steps. Screen wiring and translation changes remain
pending the owner's approval. Existing approved mocks remain unchanged.

## Install failure reproduced separately

A standalone device install using copies of the same 33 cached packs succeeded
in 112.647 seconds. Adding concurrent `images.release_unused()` calls reproduced
`data_incompatible` at mount creation. The kernel reported **mount point does not
exist**. A deterministic regression test reproduced the same empty-directory
removal before the fix.

The broker's idle `Native.close()` calls cleanup even while the map manager is
assembling. Before a mount exists, cleanup cannot find its backing-file lease and
could remove the empty directory that the installer just created. The failed live
journal did not retain its original kernel stderr; the controlled reproduction
establishes this concrete race rather than claiming to recover that lost trace.

A namespace flock now covers mount-directory creation, mounting and unmounting.
Idle cleanup takes that lock nonblocking and skips a cycle during a transition.
Existing reader leases still govern whether a mounted graph can be reclaimed.
This coordinates threads and processes without changing the graph format or the
native reader.

With the fix, the real device completed the same install while cleanup ran every
5 ms, deliberately faster than the broker's normal idle cadence. It took 117.282
seconds and produced a 992,634,880-byte logical graph with SHA-256
`5398f20aeb484a038f77b292746f4facb4ded14eb6a4e0e94f9eed0be88e6fe8`, matching
the standalone result. No trial mounts remained. Seven native, seccomp-isolated
routes matched the full-country reference hashes, including both interstate
directions and Davenport/Moline. This is a parked private-data check, not a drive.

## Filesystem timestamp precision

Device regression tests also caught a checksum-cache assumption: rapid writes or
permission changes can share a ctime tick despite the nanosecond stat API. New
hash evidence now waits for a metadata-clock probe on the same filesystem to
advance beyond the file's ctime before hashing. Changes during hashing then have
a distinguishable ctime, even on the coarse device clock. The wait is bounded,
cancellable and uses a temporary inode, without changing the checked file.

No timestamp exceptions are allowed at a handoff. Later Update checks and audits
still use fresh checksums; full logical acceptance remains independent. Existing
mutation tests were retained, and a simulated coarse-clock regression was added.

Validation passed: 165 host routing tests and 166 device routing tests, including
the device's compiled-message case. The UI suite passed 698 tests with two skips;
the four cereal/hardware UI files listed in AGENTS.md were excluded on the host.
Ruff and `git diff --check` passed. The new proposal screenshots were captured
with Chromium and inspected for layout and overflow; no built progress screen
has been changed while approval is pending.

## Retrying on the device

The diagnostic used separate copied data and did not install code, alter the live
selection or overwrite the live graphs. After updating the branch and restarting,
use **Retry download** in Offline Maps. Valid cached packs can be reused, so the
routing payload does not need to download again when catalog and checksums match.
Small catalog/manifest requests still occur. Do not delete the cached packs merely
to retry this failure.

The progress-screen behavior remains as before until its proposed mocks are
approved and implemented. The backend mount fix can be tested independently.
