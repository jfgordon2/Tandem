# Shared-state map progress review

The owner reported that the top bar finished at download and only Iowa showed a
percentage for an Iowa/Illinois selection. The current screen forces Install to
100%, and paints a percentage on only the first active tile. Both states' routing
packs were downloaded: the device journal recorded 361,706,227 of 361,706,227
payload bytes, followed by `data_incompatible` before activation.

## Approved progress states, implemented

The owner approved all five `valhalla4-shared-*` mocks on November 4 after a second
report of Iowa reaching 100%, Illinois receiving no visible progress, and Ready
lacking its green check. They retain the existing progress layout and the fixed-length sentence
**All selected regions are installed together.** in both install/check mocks.
No sentence lists state names or grows with the selection.

- `valhalla4-shared-queued`: show both states at 0% before progress arrives.
- `valhalla4-shared-download`: show every selected state and its own progress
  through its required shared packs. Shared bytes
  count once in the overall transfer total.
- `valhalla4-shared-install`: show measured installation progress rather than a
  forced 100%. All states share the same installation counter because they form
  one atomic routing image.
- `valhalla4-shared-check`: continue through full verification. A rebuilt graph's
  install counter measures logical bytes fed to the builder plus logical bytes
  checked, rather than estimating elapsed time.
- `valhalla4-shared-ready`: show green checks on all four steps, including Ready,
  and on every selected region, only after verified activation.

Percentages are phase-specific, preserving Prepare, Download, Install and Ready.
The install display is capped at 99% until the job commits Ready. A no-op update
checks the existing compressed files with measured physical-byte progress and
does not rebuild or decode a graph whose verification receipt is valid. A region
reused from the previous set has no new download bytes and can show 100%
downloaded while still awaiting the shared installation. Missing mapd region
reports are filled with selected states at 0%, so a waiting state never disappears.

The transfer pool publishes per-pack counts on its owner thread. The dataset
maps those counts to each region's required packs, counting a shared pack once
overall. Build/check callbacks reuse existing streaming operations and checksum
passes: they add no graph copies, decoding passes or full-file buffers. Journal
writes remain bounded to five per second, apart from phase/stage transitions and
the initial job snapshot. The download ETA resets across phases and retries and
does not pretend installation byte progress is time remaining.

All new text is marked for translation; eight new strings have noted English
fallbacks in the catalogs. Earlier approved mocks were left unchanged; their
comparison entries explain where the new approved states supersede them.

## Progress verification

Host routing tests passed **191 tests**; the device routing suite passed **192**,
including its compiled-message case. The host UI suite passed **738 tests, two
skips**, with the four cereal/hardware UI files listed in `AGENTS.md` omitted.
The native device captured all five built screens at 2160×1080; those captures
were inspected beside the approved Chromium screenshots.
The complete device UI suite also passed **862 tests, two skips**, including all
four files omitted on the host. Its existing low-memory fixture now supplies
the real alert's visible size, as required by the earlier empty-alert chip fix.
The isolated overlay needed consistent repository/asset paths before its path
assertions could pass; no tests were skipped or weakened to fix those paths.
The final queued-start regression and related progress/UI cases also passed on
the device. A new request is shown as pending while the demand-driven broker
starts, rather than briefly displaying the previous job's Ready result.

Expanded-language captures were inspected too. The progress wording is marked
and fits; `missed.txt` contains sample destinations, codes, units and pre-existing
fake-source captions, with none of the new progress wording. The local comparison
page is `tools/out/progress-v4-compare/index.html`. Ruff, whitespace checks and
the upstream integration audit passed against merged StarPilot `4a553da9ac`.

A parked test used copies of the owner's installed state set in a private store:

| Operation | Time | Observed progress |
| --- | --- | --- |
| Verify existing Iowa/Illinois selection | 2.791 s | 352 checksum updates over 361,609,471 stored bytes; Ready after activation |
| Deselect Illinois and rebuild Iowa locally | 28.541 s | 2,206 build and 2,264 check updates; 354,703,360 logical bytes fed, then checked; no new map payload |
| Verify existing Iowa selection | 1.598 s | 132 checksum updates over 131,040,186 stored bytes; no rebuild |

The retained two-state graph's logical SHA-256 remained
`5398f20aeb484a038f77b292746f4facb4ded14eb6a4e0e94f9eed0be88e6fe8`.
The rebuilt Iowa graph's logical SHA-256 was
`fa54f9cd3bf7ad49635001debaffb557dcba8cd2cc9dabdc06287ebf819d4e57`.
The checks used private graph copies and did not change the live selection,
installed maps or checkout. The first private attempt was correctly rejected
because its custom mount parent was writable; securing that test directory
allowed the existing mount guard to pass, without changing product checks.

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

Update the `valhalla` branch and restart before testing the new progress screen.
If the selected set is already current, expect measured Checking maps rather
than another payload download or rebuild. During a download, each state's
percentage represents its own required shared packs; during installation, all
selected states use the same measured shared counter and become ready together.
