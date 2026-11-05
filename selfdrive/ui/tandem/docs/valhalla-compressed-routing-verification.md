# Compressed driving-only routing packages

2026-11-04, branch `valhalla`. This changes the off-device builder, owned bundle/download tooling and maintained catalog. It adds no UI changes or upstream hooks. The live device checkout and active navigation data are unchanged.

## Published test data

The [existing routing-data release](https://github.com/jfgordon2/Tandem/releases/tag/routing-data-v1) now also contains `catalog-driving-v1.json`, two new immutable driving-package manifests/archives, and `README-driving-v1.md`. The old catalog, manifests, graphs and OSM source assets remain available. Updated branch code reads the new catalog; older code retains its old catalog URL.

| Bundle | Download bytes | Download MiB | Installed bytes | Installed MiB |
| --- | ---: | ---: | ---: | ---: |
| `iowa-driving-20261104-v1` | 78,783,911 | 75.13 | 222,965,760 | 212.64 |
| `iowa-illinois-driving-20261104-v1` | 249,796,427 | 238.22 | 715,929,600 | 682.76 |

The current native builder creates one connected graph from the same checksummed Iowa/Illinois PBF sources. It retains vehicular access, driveways, hierarchy and shortcuts. It explicitly disables walking-only/cycling-only roads, platforms, bike-share stations, construction roads, stored OSM node IDs and pedestrian-area traversals. The last group was already disabled by earlier defaults, so it is not an additional measured saving. No source PBF, build intermediate, elevation dataset or transit feed is included in a device graph download.

Manifest schema 2 declares installed file hashes/sizes and a separate zstd transport record. Schema 1 plain-tar downloads/installations remain supported. Catalog bytes and progress count the compressed transfer. The runtime still reads a plain uncompressed tar. Compression level 6 uses two off-device threads; decompression is streamed with a 64 MiB maximum window, small output buffers and an exact expanded-size limit. Frame boundaries/checksum presence, transport SHA-256 and expanded SHA-256 are checked before activation. No graph members are extracted.

The installed staging directory is renamed into place, avoiding a second expanded graph copy. Space checks include compressed input, expanded output and the existing reserve. Interrupted expansion is reclaimed on retry; partial compressed downloads remain resumable. Checksums, decompression and installation validation invoke the same pause/cancel gate. A failed or cancelled package cannot replace the previous active selection. Installed compressed inputs are removed. The native AGNOS zstd command is used when Python's optional module is absent; it is not necessary to install system packages or change openpilot's interpreter. Maintainer CLI download continues to require a separate activation command.

## Checks

- **101 backend routing tests passed**, including compressed and legacy installation, range resume, transport/expanded corruption, truncated footer, concatenated/trailing data, checksum errors, decoder window limits, cancellation, free space, activation and the device command-decoder fallback. Coverage includes the existing policy, scheduler, deletion and navigation tests.
- **694 UI tests passed, two existing skips**, using the host stand-ins and `SP_HEADLESS_TEST=1 SCALE=1`. The four hardware/cereal files named in AGENTS.md were omitted on this host: `test_headroom_warning.py`, `test_home_layout.py`, `test_limit_offers.py`, `test_onroad.py`. The UI did not change in this revision.
- Ruff and `git diff --check` pass.
- Both real archives were expanded off-device and restored the exact declared installed SHA-256. GitHub's uploaded asset sizes/hashes match the prepared artifacts.
- A real unauthenticated HTTPS check retrieved the published new catalog, cancelled Iowa after 1 MiB, resumed its partial download, expanded, verified, installed and activated it in a temporary host directory. Its compressed download directory was removed afterward.
- Native off-device routing through the actual worker request/normalizer succeeds for Iowa plus the six Iowa-Illinois smoke tests. Instructions and lane-component counts match the studied driving candidate. The known final Des Moines approach differs from the earlier all-mode graph.

The device checks use `/data/tandem/compressed-maps-trial-20261104`, outside the live data. Its system Python lacks the zstandard module, so these exercise the actual installed `zstd` 1.5.5 command. Iowa expanded and verified in **2.15 seconds**, Iowa-Illinois in **7.16 seconds**. Decoder peak RSS was **16,404 KiB**, with parent peak RSS **16,932 KiB**. These are parked decompression measurements, not total device RAM or a driving-workload estimate.

Raw local reports are under the ignored `tools/out/routing-reports/` directory: `driving-release-routes.json`, `compressed-https-install.json`, and copied device reports. They are research artifacts, not CI fixtures. The published README records the known route preference difference.

## Limits and next work

The [research note](valhalla-map-size-research.md) isolates extra name-change penalties after filtering. Disabling that penalty makes both complete sample routes choose the same approach, but production costing is unchanged. A trial extra enhancement pass dropped lane guidance and was rejected. The standard native build retains the observed mapped lanes/speed limits; the underlying name-consistency issue and a broader turn/access-restriction corpus remain open.

No live-checkout deployment or supervised routed drive has occurred. The existing first-drive RAM protocol remains required alongside modeld. New navigation translations still have the previously documented English fallbacks. Per-state shared-tile downloads, incremental updates and removal of rollback graphs are separate changes; this revision retains the existing recovery policy.
