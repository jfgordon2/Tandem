# Valhalla implementation and device trial

Historical evidence from the initial opt-in trial. Its UI, default-off policy and package-management limitations were superseded by the owner-approved revision. See [the current guide](valhalla-offline-routing.md) and [revision 2 verification](valhalla-revision-2-verification.md) for current behavior and checks. The measurements below describe only the earlier source and run.

November 3, 2026. Branch: `valhalla`, based on `78c75a0a94e7e746f1798cd77c81da936bceaff0`. This is an opt-in test implementation, not a driving-workload acceptance result. The live device checkout remains on that base revision. All native trials and device tests ran from separate trees under `/data/tandem/navigation`; no real destination, ignition state or control authority was changed. Offline routing remains persistently disabled.

## Installed and measured

Hardware: comma 3X (`tizi`), ARM64, Ubuntu 24.04.5, Linux 4.9.103, glibc 2.39. The native environment uses Python 3.12.3; the managed openpilot environment was left untouched. Before the last run the device had 3,692,804 KiB total RAM, 2,226,856 KiB available, no swap and roughly 9.8 GiB free on `/data`.

| Item | Result |
| --- | --- |
| Native package | pyvalhalla 3.9.1, CPython abi3, manylinux_2_28_aarch64 |
| Dedicated runtime disk use | 136,088 KiB, about 133 MiB, including pip and graph tools |
| Iowa graph | 293,140,480 bytes, about 280 MiB; installed directory 286,284 KiB |
| Iowa coverage precheck | west -96.65, south 40.37, east -90.10, north 43.51 |
| Latest timed set | 50/50 successful requests, five public routes repeated ten times |
| First native process plus route | 1.68 seconds in the last run; earlier fresh-process runs 3.34 and 3.74 seconds |
| Warm median / p95 | 0.236 / 0.536 seconds in the last run, excluding the first request for each pair |
| Peak worker RSS | 97,884 KiB, about 95.6 MiB |
| Conservative broker + worker peak-RSS sum | 116,048 KiB, about 113.3 MiB; individual peaks need not coincide |
| Largest sampled simultaneous RSS / PSS sum | about 111.1 / 103.8 MiB after requests; not continuous peak PSS |
| Native CPU over timed requests | about 13.2 seconds cumulative user + system time |
| Coverage / invalid coordinate probes | `outside_coverage` / `invalid_request`, each about 0.02 seconds |
| Recovery after those failures | valid local route in 0.18 seconds |
| Network isolation | all successful native responses report `seccomp_socket_connect_denied` |

The five routes cover urban Des Moines (2.9 km), Des Moines to Ankeny (21.5 km), Ankeny to Ames (42.6 km), Des Moines to Cedar Rapids (205.8 km), and a changed origin near Ankeny to Ames (42.6 km). Public endpoints are in `routing/tools/benchmark.py`. There were multiple successful trial runs during development; the table describes the last complete 50-request set at `2026-11-03T23:03:56Z`, including memory instrumentation and the current source hashes.

First process startup is not a cold filesystem-cache measurement: the cache was never flushed. The worker memory includes mapped graph pages, and summing RSS counts shared pages more than once; sampled PSS is also recorded. Readiness and speed measurements pass the spec's parked trial targets. They do not predict latency alongside modeld, UI, cameras or other driving processes.

The report records every readable thermal-zone temperature rather than interpreting every zone as CPU temperature. Zone 0 changed from 37.5 to 37.9°C across the last run. Some zones have fixed/sentinel values (including -40 and 75°C). This short parked sample is not a controlled thermal baseline or a sustained onroad comparison. Available RAM changed to 2,170,128 KiB afterward, which includes other running processes and page-cache effects.

Linux seccomp denies both socket creation and connect before importing Valhalla, and the worker verifies that attempting an IPv4 socket returns EPERM. SSH networking remains available to the rest of the device. No network interfaces were disabled. Graph download URLs are also empty. On a Mac the tool explicitly reports that kernel isolation is not enforced.

## Provenance and artifacts

- Wheel: `pyvalhalla-3.9.1-cp312-abi3-manylinux_2_28_aarch64.whl`, SHA-256 `6ebe5f9dd6ce3b16413f939a271d68e64a4addd44df8a802a8eda0b9ca0bf16f`.
- pip bootstrap: 25.3 wheel, SHA-256 `9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd`.
- Iowa PBF: Geofabrik `north-america/us/iowa-latest.osm.pbf`, SHA-256 `d2bb8eabafc3c27033141073d3349129ed6b1b7ce77e431937cdc0a3b56cb927`.
- Graph: SHA-256 `ba3f1eadcb4ddcb27f32f3b709d98eb62510617519bdf359dc28fe2d235b3019`; manifest generation `a346cfabcd677ae15daa77493226a692e8343697ea7f44054abd9e92ce5c92e1`.
- Device raw result: `/data/tandem/navigation/benchmarks/iowa-device-final.json`; per-request log alongside it. Local copy: `selfdrive/ui/tandem/tools/out/routing-reports/iowa-device-final.json` (ignored). The JSON contains hashes for the exact routing source used during the run.
- Runtime receipt: `/data/tandem/navigation/runtimes/3.9.1/receipt.json`; local ignored copy under `tools/out/routing-reports/runtime-receipt.json`.
- A real public route response with lanes and unknown legal-speed slots is committed in `starpilot/tandem/tests/fixtures/valhalla-iowa-3.9.1.json`, with separate provenance/attribution notes.

The original OSM speed-limit maps remain untouched. Trial transfer staging, test dependencies and isolated source directories add temporary disk use beyond the installed sizes above. There is no production region catalog, hosted Iowa download URL or automatic update cadence in this change.

## Automated and visual verification

- **676 UI tests passed, 2 existing skips** with the AGENTS stand-ins on macOS. The four prescribed files were excluded because this host cannot run the full cereal/device UI imports: `test_headroom_warning.py`, `test_home_layout.py`, `test_limit_offers.py`, `test_onroad.py`.
- **101 device tests passed**, including the complete owned backend suite plus upstream destination-store, route-engine, navigationd and navigation-desire regressions. They used the managed interpreter's compiled dependencies, separately installed pytest under the owned test directory, an isolated `OPENPILOT_PREFIX`, and recorder objects rather than live publishers. One existing ReactiveX datetime deprecation warning remains.
- The new real-schema test serializes instructions at every point of the native fixture, including actual lane enums, through the existing navigation publisher method with an in-memory recorder. The owned cruise tests preserve upstream targets for equivalent valid input, and reject stale/future local state. Existing DesireHelper tests cover split/shared lanes, forks, signals and stale state.
- New tests cover default-off/mixed-screen fallback, missing runtime and incompatible receipts, keyless saved selection, pending/error Start, unknown-speed alignment, corrupt manifests/graphs, atomic rollback, reader leases, independent mapd files, insufficient space, staged download cancellation, setup cancellation/parking transitions, native child crash/hang/restart, request supersession, A-to-B-to-A previews, destination replacement, GPS freshness, terminal arrival and invalid off-route guidance.
- **Ruff, `git diff --check`, and the upstream integration audit pass.** Only two unowned files changed for this feature: `starpilot/navigation/navigationd.py` (+6/-2 lines) and `system/manager/process_config.py` (+2). Both hooks are listed in the Tandem README; no message schema or upstream UI was modified.
- New HTML mock variants and PNGs precede the UI implementation. Built screens were rendered, inspected, and compared at 2160×1080. The full pseudo-language scene ran; its `missed.txt` contains sample names/addresses, units, developer identifiers and existing scene data. The new routing labels/statuses are marked. All 12 existing catalogs are current, and the fallback font was rebuilt for 11 new characters. Some long preview notes and the data-ready badge use an ellipsis in the pseudo-language.
- The pinned native library also routed successfully for all 12 UI-language selections on the desktop trial graph. Arabic, Thai and Chinese navigation instructions currently fall back to English; UI labels remain translated.

Reproducible host command (use the project test interpreter; this session used `/tmp/starpilot-ui-venv/bin/python`):

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python3 -m pytest -q -c /dev/null \
  --confcutdir=starpilot/tandem/tests starpilot/tandem/tests/test_routing.py \
  starpilot/tandem/tests/test_routing_navigation.py starpilot/navigation/test_destination_store.py
```

The device command, from the isolated source root, was:

```sh
OPENPILOT_PREFIX=tandem-valhalla-trial-tests TANDEM_ROUTING=0 \
TANDEM_STATE_DIR=/data/tandem/navigation/regression-state PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTHONPATH=/data/tandem/navigation/regression-source:/data/tandem/navigation/test-deps:/data/openpilot \
/usr/local/venv/bin/python -m pytest -q -c /dev/null \
  --basetemp=/data/tandem/navigation/pytest-temp \
  --confcutdir=/data/tandem/navigation/regression-source/openpilot \
  starpilot/tandem/tests starpilot/navigation/test_destination_store.py \
  starpilot/navigation/test_route_engine.py starpilot/navigation/test_navigationd.py \
  selfdrive/controls/tests/test_navigation_desires.py
```

Create the separate `/dev/shm/msgq_tandem-valhalla-trial-tests` directory first. `/tmp` on the device has too little free space for the intentional 256 MiB installation reserve, so the test temporary root must be on `/data`. Initial runs exposed those environment requirements; neither the reserve nor tests were weakened. This Mac cannot collect the complete backend suite against its ELF messaging extension, so the full suite was run on the device instead.

## Remaining acceptance work

Deploy the branch through the normal workflow, then test actual saved-place preview/Start, guidance, missed turns, GPS loss, End route, ignition/offroad, reboot and data rollback in a normal user-supervised session. Measure concurrent model/UI deadlines, missed frames, memory and sustained temperatures against a comparable baseline. No real onroad session was simulated or conducted for this implementation.

Native no-path cases inside an extract and difficult boundary journeys still need a broader route corpus; bounds do not prove road connectivity. Real low-storage interruption/power loss during installation and full hardware UI tests remain unrun. Automated failures use synthetic corrupt packages and controlled child processes. Treat these as explicit test limits rather than claiming every acceptance case in the original spec is complete.

Use the [setup/rollback guide](valhalla-offline-routing.md) for the switch, package commands and removal. The change is left uncommitted on `valhalla` for review and has not been pushed or deployed into the live driving tree.
