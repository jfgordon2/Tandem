# Smaller offline routing packages

Research date: 2026-11-04. This study uses Valhalla / pyvalhalla 3.9.1 and the same Iowa and Illinois OSM PBF inputs used for the published connected bundle. It does not change the published release, production builder, downloader, runtime options or live device checkout.

The subsequent test implementation is documented in [compressed-package verification](valhalla-compressed-routing-verification.md). It adopts the standard driving filter and zstd transport, retains ordinary maneuver penalties, and records the name-consistency issue below as open. The historical experiment measurements below remain unchanged.

A [further installed-storage study](valhalla-storage-layout-study.md) measures each tile section, optional acceleration removal and lossless compressed storage. The current installed tar sizes are not minimums: SquashFS images of the exact graph tars measured 76.74 MiB for Iowa and 245.98 MiB for both states and routed successfully in isolated device checks. That representation is not yet integrated into the normal installer/worker lifecycle.

## Findings

There are two separate opportunities: compress the download without changing graph contents, and build a smaller graph containing only the driving network. The first is lossless transport. The second changes the routing graph and needs routing acceptance work.

| Local experiment | Download bytes | Download MiB | Installed graph MiB |
| --- | ---: | ---: | ---: |
| Current uncompressed graph tar | 1,108,899,840 | 1,057.53 | 1,057.53 |
| Same graph, zstd level 6 | 369,769,947 | 352.64 | 1,057.53 |
| Driving graph, zstd level 6 | 249,796,527 | 238.22 | 682.76 |

The driving graph is 715,929,600 bytes before compression: 35.4% less installed graph storage. Its compressed download is 77.5% smaller than the current release asset. The original and driving graph compression roundtrips both restored the exact original bytes, verified by SHA-256. These measurements exclude the separate routing runtime and StarPilot road-map data. They do not imply a measured reduction in RAM.

## What upstream supports

The [pinned build configuration](https://github.com/valhalla/valhalla/blob/3.9.1/scripts/valhalla_build_config) exposes `include_driving`, `include_bicycle` and `include_pedestrian`. The candidate changes only these two access filters from the original build, plus its output paths:

```json
{
  "mjolnir": {
    "include_driving": true,
    "include_bicycle": false,
    "include_pedestrian": false,
    "include_driveways": true,
    "hierarchy": true,
    "shortcuts": true
  }
}
```

The [graph filter](https://github.com/valhalla/valhalla/blob/3.9.1/src/mjolnir/graphfilter.cc#L248-L268) retains an edge if either direction has vehicular access when driving is enabled. Roads shared with pedestrians or bicycles remain. This flag retains vehicular modes more broadly than passenger cars; the runtime still requests `costing: auto` to apply car access rules.

Filtering runs after parsing and also aggregates some remaining segments. Thus, turning off walking and cycling is not equivalent to deleting unrelated files from a fixed graph. Junctions, local edge indexes and name-consistency metadata can change. The filter explicitly copies mapped signs, turn lanes, access restrictions and lane connectivity, and refuses to aggregate edges with certain restrictions or traffic signals. Those code paths establish intent; they do not prove preservation for every road in this dataset.

Upstream has fixed relevant bugs before:

- [#5464: Graph filter fixes](https://github.com/valhalla/valhalla/pull/5464): local indexes, headings, transitions, restrictions and name consistency after filtering.
- [#5877: false intersection stop impact](https://github.com/valhalla/valhalla/pull/5877): extra penalties where a road merely has a segment boundary.
- [#6050: accidental loop edges](https://github.com/valhalla/valhalla/pull/6050): aggregation after removing pedestrian connections.

All three appear in the [3.9.1 changelog](https://github.com/valhalla/valhalla/blob/3.9.1/CHANGELOG.md). These are historical fixes already included in our runtime, not an established explanation of the current discrepancy. On the research date, the fetched `master` graphfilter.cc was byte-identical to the pinned 3.9.1 file. A targeted issue search did not identify a confirmed existing fix for our reproduction.

## Local routing checks

Six smoke-test routes succeeded on both graphs: Des Moines local, Chicago local, Springfield to Chicago, Davenport to Moline, Des Moines to Chicago and the reverse trip. Five had identical instruction lists and equal counts of lane components and mapped speed-limit segments. Their distance differences were at most 3.3 metres. Counts alone are not a semantic check of every lane or speed limit.

Chicago to Des Moines differed in its final downtown approach. The original took 3rd Street, Grand Avenue and 7th Street; the candidate took Day Street and 5th Avenue. The candidate was about 144 metres shorter and its reported ETA about two seconds lower.

Further checks isolated an important scoring difference:

1. `/locate` snaps both destination requests to precisely `41.586808, -93.624959` on OSM way `702228231`, 6th Avenue. The different percentage along the edge reflects aggregation; it is not a different destination.
2. Using [`trace_attributes` with `shape_match: edge_walk`](https://valhalla.github.io/valhalla/api/map-matching/) successfully walks both downtown approaches in both graphs. Their sequences of distinct OSM way IDs match across graphs for each supplied approach. This verifies the connections are present and the exact shapes match, not universal restriction correctness.
3. The fixed-shape scores below switch which approach is preferred. Lower cost is better; cost is a routing score, not the reported ETA.

| Graph | 3rd / Grand / 7th approach | Day / 5th approach |
| --- | ---: | ---: |
| Original, normal penalties | 391.102 | 436.760 |
| Driving graph, normal penalties | 451.151 | 446.915 |
| Original, `maneuver_penalty: 0` | 366.102 | 421.760 |
| Driving graph, `maneuver_penalty: 0` | 366.151 | 421.915 |

The original approach acquires 60 extra cost units from maneuver penalties after filtering; the other approach acquires 10. Upstream documents [`maneuver_penalty`](https://valhalla.github.io/valhalla/api/route/api-reference/#automobile-and-bus-costing-options) as a default five-second-equivalent penalty for roads without consistent names. The [costing implementation](https://github.com/valhalla/valhalla/blob/3.9.1/valhalla/sif/dynamiccost.h#L1578-L1585) directly tests the graph's name-consistency flag.

The extra penalties occur at several successive edges still called 3rd Street, and also along Grand Avenue and 7th Street. With only that penalty disabled in an experimental request, both complete Chicago-to-Des Moines routes use the original downtown approach and have identical instruction lists. That is strong evidence of a name-consistency / indexing problem affecting route scoring. The precise faulty builder operation has not yet been proved with a minimal graph reproduction or a corrected build.

The experiment does **not** justify globally disabling maneuver penalties in production. That would change route preferences everywhere and could conceal malformed metadata. The production routing request is unchanged.

## Reproducing the diagnosis

Use the isolated 3.9.1 native Python environment with `valhalla.Actor`. For each `tiles.tar`, construct `get_config(tile_dir="", tile_extract=...)` and clear `mjolnir.tile_dir` and `mjolnir.tile_url`, as the actual worker does. Start with the actual worker's `route_options` for origin `41.8781, -87.6298` and destination `41.5868, -93.6250`, without a heading.

For diagnostic summaries, change `format` to `json`; repeat with:

```json
{"costing_options": {"auto": {"maneuver_penalty": 0}}}
```

Decode each default native leg's polyline at precision 6 and use the points from shape index 3399 onward. Both routes reach that point just before exit 8A. Supply each of those two shapes to each graph using:

```json
{"shape": [{"lat": 0, "lon": 0}], "shape_match": "edge_walk", "costing": "auto"}
```

Replace the example point with the decoded shape points. Read `edges[-1].end_node.elapsed_cost` and repeat with the zero maneuver penalty. `/trace_attributes` uses a different cost reconstruction path from `/route`; its absolute score is not a full-route cost or ETA. The complete-route counterfactual above independently demonstrates the preference change.

Local raw results are kept in the ignored `tools/out/routing-reports/` directory:

- `map-size-study.json`: bytes, six-route comparison and SHA-256 roundtrips.
- `map-size-diagnosis.json`: default / shortest requests and verbose endpoint locations.
- `map-size-path-comparison.json`: two approaches walked on both graphs.
- `map-size-path-no-maneuver-penalty.json`: the same four walks with the diagnostic penalty disabled.
- `map-size-no-maneuver-penalty-routes.json`: complete-route counterfactual.

These are local research artifacts, not release assets or CI fixtures. No on-device RAM or routed-drive acceptance was performed for this candidate.

## Implementation direction

Lossless [zstd](https://github.com/meta/zstd) download compression is independently useful and does not depend on accepting the driving graph. The installer would need a declared transport encoding, compressed and installed byte lengths/checksums, resumable download handling, streamed decompression to a bounded temporary file, cancellation and free-space checks, validation, then atomic activation. Retain compatibility with existing plain-tar packages. Keep the installed tar uncompressed for the existing reader; a maintainer [explains the mmap advantage](https://github.com/valhalla/valhalla/issues/5720) over loading individual tile files.

For broader driving acceptance, reproduce and correct the name-consistency issue in the off-device builder, while keeping the normal runtime costing. A subsequent experiment reran enhancement after filtering; it lost lane guidance and was rejected. The test implementation uses the standard native build pipeline. Compare a broader route corpus: same-street junctions, one-way roads, simple and complex turn restrictions, driveways and parking access, rural roads, highway exits, mapped lanes/speed limits and the Iowa-Illinois border in both directions. A repeated all-mode control build should also rule out independent build variation. Validate startup, long routes, reroutes and RAM on the actual device alongside modeld, followed by the already-required supervised drive.

Keep hierarchy, shortcuts, driving access and driveways during that work. Do not claim savings from removing data that is already absent. Compatible tile-based package sharing may later avoid downloading duplicate states, but is a separate packaging/ownership change from this filter and compression study.
