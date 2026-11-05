# Paired state downloads

The owner approved the four single-bar `valhalla5-paired-*` mocks on November 4,
after confirming that multithreaded downloads remain enabled. These supersede
the proposed two-bar layout. The approved HTML and Chromium screenshots are
unchanged by implementation.

## Download order

For a supported US selection, both map sets download for Iowa, then both for
Illinois, and so on in token order. StarPilot's native road downloader runs on
its existing update thread. Valhalla's existing pool still has two routing
transfer workers, running alongside that road downloader. A barrier waits for
both sides before requesting the next state. A pack needed by several states
downloads once; verified installed data and resumable download caches retain
their existing checks and reuse rules.

After all selected states finish downloading, one shared routing image is built,
checked and activated. The existing Install and Checking screens use measured
bytes, capped at 99% until activation. Green checks appear on all regions and
all four steps only when that activation succeeds.

The single download bar averages the selected states' completion fractions.
Each state's fraction is the smaller of its road-file fraction and routing-byte
fraction. For example, Iowa at 26% with Illinois waiting gives 13% overall;
Iowa downloaded and Illinois at 18% gives 59%. Queued states remain at zero,
even if some of their routing data arrives in shared packs for an earlier state.
These normalized fractions are not a byte throughput measurement, so this phase
does not show an estimated time remaining. Install/Checking retain their own
separate, measured percentage. The UI exposes neither internal map-set names
nor a second download bar.

## Integration and recovery

`routing/handoff.py` is a lightweight adapter called after StarPilot's existing
schedule/date gates. It wakes/probes the demand-driven broker, then queues a
durable paired job without an install lock. The existing road updater is called
for each state with scoped parameter views: the real `MapsSelected` stays intact,
per-state storage receipts still use StarPilot's helpers, and `DownloadMaps`
stays set until the whole operation finishes. This retains ThreadManager's
existing update lock instead of launching another update on each tick. The
recursive road call suppresses the old companion hook and does not import the
broker/installer into StarPilot's main process.

`routing/paired.py` supplies a transfer callback to the existing dataset installer.
It publishes the current state, invokes the unchanged two-worker transfer pool
for that state's missing packs, and waits for the matching road completion
receipt. The same callback also runs when the routing selection is already
current, so a manual or scheduled road update still happens before the graph's
measured verification pass. This adds no graph copy, decoding pass or full-file
buffer. The small journal and counter dictionaries scale with states/packs;
journal writes retain the five-per-second limit apart from transitions.

`map-road.json` binds completed road states to the request ID. A restarted broker
or updater can resume the same job without treating another job's receipts as
current. Before sending a road command, the adapter waits for fresh native idle
progress: mapd ignores commands while active, and a cancellation can outlast the
upstream updater's five-second wait. Cancel remains scoped to the request. A
paused job does not start the next state until permitted again. Native road
downloads already in flight retain StarPilot's behavior across a drive.

Routing/runtime/space failures still let StarPilot finish all remaining road
states, then report the routing failure for retry. A failed/cancelled native road
download cannot mark a region Ready. LastMapsUpdate is written once all road
states complete, preserving StarPilot's scheduling semantics. Routing-only
selection changes still reuse the existing route-only path, avoiding unnecessary
road downloads.

`TANDEM_ROUTING=0`, screen rollback switches, unsupported selections and a broker
that cannot start use the original updater. Both small upstream guards swallow
ordinary exceptions. A broker that does not acknowledge a queued job within
30 seconds also returns control to the original path. New map-progress wording
has marked English fallbacks pending translation; it adds no fallback-font
characters.

## Verification

Host routing tests passed **218 tests**. The device routing suite passed **219**,
including compiled messages. The host UI suite passed **743 tests, two skips**,
with the four cereal/hardware files listed in AGENTS.md omitted. The full device
UI suite passed **868 tests, two skips**, including those four files.

Tests exercise two real transfer threads overlapping with a road worker,
shared-pack deduplication, per-state barriers, current-set road updates followed
by measured verification, scoped cancellation, same-job road receipts after
restart, and route/runtime failures that still complete all road states. The
actual upstream updater is exercised with transport stand-ins for successful
manual, Weekly and Monthly paired updates; its import/call failure fallbacks
and schedule gates are tested too. A fresh import of `handoff` loads none of the
broker, downloader, dataset, image or bundle modules.

All four 2160×1080 native captures were inspected against the approved Chromium
screenshots. The comparison page is
`selfdrive/ui/tandem/tools/out/paired-v5-compare/index.html`. Expanded-language
captures fit, and `missed.txt` contains sample names/units and pre-existing fake
source text, with none of the new wording unmarked. Five new strings have
annotated English fallbacks. Ruff, whitespace checks and the upstream integration
audit pass against merged StarPilot `4a553da9ac`.

An additional parked protocol check used the device's actual mapd binary and
compiled cereal transport in a private mount namespace. Its map directory,
params, message queues and source view were isolated. A custom test menu selected
one real road archive per state; a private sample catalog selected three real
published routing packs (6,989,242 bytes total). Both routing transfer threads
ran, the states completed in Iowa/Illinois order, and the resulting shared image
passed build/check/activation in **25.594 seconds**. The sample graph contained
18,790,400 logical bytes. Peak Python RSS was **57,612 KiB** in this small parked
check; this is not a measurement under driving load or a full-state routing
coverage test. The raw result is in `tools/out/paired-v5-device-result.json`.

The first isolated attempts exposed test setup issues, not a product failure:
the private queues needed a directory, and mapd's library normally discovers
the `msgq_` prefix from the live logMessage queue. The isolated run set
`USE_MSGQ_PREFIX=true` and left OPENPILOT_PREFIX unset, matching native params
at `/data/params/d`. Once those private paths matched, the check succeeded.

These checks use private sources and data. The live checkout, selected states
and installed graphs remain unchanged.

## Owner test

Update the `valhalla` branch, restart, and open Offline Maps while parked on Wi-Fi.
With Iowa and Illinois selected, choose Update maps. Expect Iowa's tile and the
single overall bar to advance first, then Illinois's tile. A routing set already
current needs no routing payload; its state percentages still wait for each road
update. After both finish, expect measured Install/Checking and then four green
steps plus green region checks. Cancelling and retrying must not start the next
road command until mapd has finished the previous operation. A drive is not
needed to test this download change.
