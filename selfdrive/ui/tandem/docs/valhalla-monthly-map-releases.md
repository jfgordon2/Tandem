# Monthly routing-data releases

The owned `Monthly routing maps` workflow uses standard GitHub-hosted
`ubuntu-24.04` runners. It calls no upstream build/setup/cache composites, runs
no device build and pushes no branch commits. The separate
[workflow review](github-workflows.md) records the three inherited publishers
disabled in Tandem.

## Schedule and manual use

The schedule is **04:17 UTC on the 26th of each month**, allowing time before the
device's existing first-of-month download. All four OSM extracts use the same
dated snapshot, defaulting to two days before the build. IDs include the source
date, Actions run ID and attempt, so retries never overwrite another dataset.

GitHub schedules require the workflow on the default `release` branch. Its
checkout remains `valhalla`; the offline-navigation implementation stays on its
separate branch. The build records the actual builder commit in source metadata
and its publication plan. Data-release tags use GitHub's default branch; they
identify data, while the manifest identifies the exact builder. Creating a draft
omits `target_commitish`, and publishing preserves its target. This avoids
GitHub's workflow-write permission guard when `valhalla` or an older trigger
commit has different workflow files. The built-in token needs no workflow-write
PAT. An empty source draft tests release permissions before the large download.

Manual inputs:

- **snapshot:** optional `YYMMDD` extract date.
- **publish:** off by default. A manual build stages checked drafts for review;
  scheduled runs also publish after all checks.
- **staged_tag:** optional existing `routing-us-...-catalog` draft. With Publish
  selected, it verifies and promotes that checked build without rebuilding.

Ordinary `valhalla` pushes touching the workflow/tools run the read-only review
job. A commit deliberately beginning `[routing-build-check] ` also requests a
full hosted build that stages drafts; it cannot publish the maintained catalog.

## Jobs and publication order

1. **Review** checks fingerprints for all reviewed workflows/composites, validates
   maintainer script syntax and records hosted resources. Its token is read-only.
2. **Build** reclaims unused SDK space only on its disposable hosted VM, installs
   the pinned tools, and tests the release gates. It builds one connected US
   driving graph, partitions it and checks all 61 local/interstate samples
   against both selected state packs and the complete indexed tar. Every image
   receives physical and logical verification during export. Sources and graph
   assets are uploaded to dated drafts, with each remote SHA-256 checked. A small
   publication plan and reports pass to the next job; multi-gigabyte map files
   do not use Actions artifact storage.
3. **Publish** independently rechecks every remote asset, the dataset identity
   and all route-check results. It makes source/graph/catalog releases public as
   prereleases with `make_latest=false`, downloads the new catalog without
   authentication, then downloads/assembles DC and matches its native route to
   the complete graph. Only then does it update `routing-us-v1/catalog.json`.

The build and publish jobs request contents write access solely for routing data
releases. Their targets are checked against this repository and the build's
`routing-us-*` names; app releases and branches are not publication targets.
Official actions use exact commit pins. No cloud credentials, custom runner,
GHCR publisher or personal GitHub token is required.

Sources are preserved before scratch reclamation: large PBFs use individually
checksummed 1 GiB release assets, with a manifest for reassembly. Only the
verified combined PBF remains on the runner for the native build. Country/admin
and timezone inputs, polygons, attribution and provenance accompany the data.
The normal maintainer builder retains its source files by default; the hosted
job explicitly opts into reclamation.

Graph releases use at most 300 packs per bucket (900 assets), below GitHub's
1,000-asset release limit. Files stay below 2 GiB. Uploads are streamed and
reconciled after ambiguous failures; an existing immutable asset with a different
digest is rejected. API rate limits pause and retry instead of issuing repeated
requests. Each hosted job is bounded by GitHub's six-hour limit.

## Catalog recovery

Dated data assets are never overwritten. The maintained catalog is the sole
mutable pointer. Promotion uploads/checks a uniquely named candidate first,
renames the old catalog to a retained backup, then renames the candidate to
`catalog.json`. Failed renames reconcile remote state and restore the old name
when necessary. GitHub offers no transactional asset replacement; during the
brief rename gap, devices use their existing cached/bundled catalog.

Failed builds/checks leave the working catalog untouched. A failed public smoke
test leaves the previous catalog selected even though the independently checked
dated assets may already be public. Newer catalogs cannot be replaced by an
older build. A runtime-version change requires an explicitly migrated maintained
catalog URL. Existing saved places and device map-download schedules are unchanged.

## Hosted resource check and validation

The initial resource probe succeeded on four CPUs and 16 GB RAM, with 107.6 GiB
available after SDK cleanup. The previous full-US build also succeeded on a
16 GB maintainer host. The hosted build uses two native builder threads,
requires 90 GiB before downloads and 64 GiB after archiving/reclaiming original
sources, and records available RAM/disk every minute. These are conservative
preflight checks, not a guarantee that every future US snapshot fits unchanged.

Release tests cover full route evidence, repository/tag/manifest/size binding,
streamed upload recovery, immutable assets, API throttling, source reclamation
only after archival, public-download/route failure gates, and catalog rollback.
The first hosted trial downloaded/prepared the national input, then stopped at
draft creation with HTTP 403 because its trigger commit had different workflows
from the default branch. It changed no public maps. The release-target fix and
early permission check are covered by regression tests; a full retry is pending.

GitHub may disable schedules in an inactive public repository after 60 days;
check the Actions page if an expected monthly release is absent. Retained
immutable sources and graphs support rollback and interrupted device updates.
