"""Partition ONE graph build into disjoint packs referenced by state footprints.

Shapely is an off-device build dependency only. The car uses the resulting index.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from openpilot.starpilot.tandem.routing import bundles, config as C, images, tiles as T


def polygon(path):
  from shapely.geometry import Polygon
  from shapely.ops import unary_union
  lines = iter(path.read_text().splitlines()[1:])
  positive, negative = [], []
  for name in lines:
    name = name.strip()
    if not name or name == "END":
      continue
    ring = []
    for line in lines:
      if line.strip() == "END":
        break
      lon, lat = map(float, line.split())
      ring.append((lon, lat))
    shape = Polygon(ring)
    if not shape.is_valid:
      shape = shape.buffer(0)
    (negative if name.startswith("!") else positive).append(shape)
  shape = unary_union(positive).difference(unary_union(negative))
  if shape.is_empty or not shape.is_valid:
    raise C.RoutingError("invalid_request")
  return shape


def tile_bounds(name):
  identity = T.graph_id(name)
  level, number = identity % 8, identity // 8
  step = (4, 1, .25)[level]
  columns = int(360 / step)
  west, south = -180 + number % columns * step, -90 + number // columns * step
  return west, south, west + step, south + step


def partition(graph: Path, output: Path, identity: str, regions: dict, provenance: dict, base_url: str,
              *, max_part_bytes=128 * 1024**2):
  """regions maps canonical state tokens to checked .poly paths and titles."""
  from shapely.geometry import box
  from openpilot.starpilot.tandem.routing.catalog import tokens
  if (not bundles.ID.fullmatch(identity) or len(identity) > 48 or not base_url.startswith("https://")
      or not regions or set(regions) != tokens(",".join(regions)) or not 1024 <= max_part_bytes <= 1024**3):
    raise C.RoutingError("invalid_request")
  if (output / "catalog.json").exists():
    raise C.RoutingError("bundle_exists")
  shapes = {region: polygon(spec["polygon"]) for region, spec in regions.items()}
  groups, records = defaultdict(list), []
  for path in sorted(graph.rglob("*.gph")):
    name = path.relative_to(graph).as_posix()
    size = path.stat().st_size
    if not 0 < size <= T.MAX_TILE:
      raise C.RoutingError("data_incompatible")
    footprint = box(*tile_bounds(name))
    members = tuple(sorted(region for region, shape in shapes.items() if shape.intersects(footprint)))
    if not members:
      # Complete ways can extend beyond extract/state polygons. Keep every
      # graph tile by assigning these fringe tiles to the nearest state.
      members = (min(shapes, key=lambda region: (shapes[region].distance(footprint), region)),)
    record = {"path": name, "bytes": size, "sha256": bundles.digest(path)}
    groups[members].append(record)
    records.append(record)
  if not records:
    raise C.RoutingError("data_missing")
  if set(regions) != {region for members in groups for region in members}:
    raise C.RoutingError("coverage_unavailable")
  boundary = {region: bundles.digest(spec["polygon"]) for region, spec in regions.items()}
  fingerprint = hashlib.sha256(json.dumps({"tiles": records, "boundaries": boundary, "provenance": provenance,
    "runtime_version": C.VERSION, "profile": "driving", "partition_version": 1}, sort_keys=True).encode()).hexdigest()
  dataset = {"id": identity, "sha256": fingerprint, "runtime_version": C.VERSION, "profile": "driving",
    **provenance, "regions": {region: {"title": spec["title"], "bounds": list(shapes[region].bounds), "parts": []}
                             for region, spec in sorted(regions.items())}, "parts": []}
  for members, rows in sorted(groups.items()):
    chunks, chunk, size = [], [], 0
    for row in rows:
      if chunk and size + row["bytes"] > max_part_bytes:
        chunks.append(chunk)
        chunk, size = [], 0
      chunk.append(row)
      size += row["bytes"]
    chunks.append(chunk)
    for chunk in chunks:
      suffix = hashlib.sha256(json.dumps([members, chunk], sort_keys=True).encode()).hexdigest()[:16]
      part = identity + "-" + suffix
      print(json.dumps({"pack": part, "regions": members, "logical_tile_bytes": sum(row["bytes"] for row in chunk)}), flush=True)
      folder = output / "parts" / part
      folder.mkdir(parents=True, exist_ok=True)
      # Completed immutable packs can be reused after a packaging interruption.
      if (folder / "manifest.json").exists():
        manifest = bundles.load(folder, verify=True).manifest
        if manifest["dataset"]["sha256"] != fingerprint:
          raise C.RoutingError("bundle_exists")
      else:
        (folder / "tiles.squashfs").unlink(missing_ok=True)
        indexed, length = T.layout([{**row, "part": part} for row in chunk])
        logical = images.pack_stream(T.stream(indexed, lambda row: T.file_chunks(graph / row["path"], 0, row["bytes"])),
                                     length, folder / "tiles.squashfs")
        C.atomic_json(folder / "tiles.json", {"schema": 1, "dataset": fingerprint, "tiles": indexed})
        bounds = [tile_bounds(row["path"]) for row in chunk]
        manifest = {"schema": 4, "id": part, "title": "Shared routing tiles", "kind": "tile-part", "runtime_version": C.VERSION,
          **provenance, "bounds": [min(b[0] for b in bounds), min(b[1] for b in bounds), max(b[2] for b in bounds), max(b[3] for b in bounds)],
          "dataset": {"id": identity, "sha256": fingerprint, "index": "tiles.json"}, "parts": [part], "regions": [],
          "graph": {"format": "squashfs", "file": "tiles.squashfs", "path": "tiles.tar", **logical},
          "files": {name: {"bytes": (folder / name).stat().st_size, "sha256": bundles.digest(folder / name),
                           "url": base_url.rstrip("/") + "/" + part + (".squashfs" if name.endswith("squashfs") else ".tiles.json")}
                    for name in ("tiles.squashfs", "tiles.json")}}
        C.atomic_json(folder / "manifest.json", manifest)
        bundles.load(folder, verify=True)
      entry = {"id": part, "bytes": sum(r["bytes"] for r in manifest["files"].values()),
               "manifest": base_url.rstrip("/") + "/" + part + ".json", "sha256": bundles.digest(folder / "manifest.json")}
      dataset["parts"].append(entry)
      for region in members:
        dataset["regions"][region]["parts"].append(part)
  for region in dataset["regions"].values():
    if not region["parts"]:
      raise C.RoutingError("coverage_unavailable")
    region["parts"].sort()
  dataset["parts"].sort(key=lambda part: part["id"])
  result = {"schema": 2, "runtime_version": C.VERSION, "dataset": dataset, "packages": []}
  from openpilot.starpilot.tandem.routing.catalog import validate
  validate(result)
  C.atomic_json(output / "catalog.json", result)
  return result


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("graph", type=Path)
  parser.add_argument("output", type=Path)
  parser.add_argument("--id", required=True)
  parser.add_argument("--regions", type=Path, required=True, help="JSON mapping state tokens to title and polygon path")
  parser.add_argument("--provenance", type=Path, required=True, help="source, attribution and built_at metadata from the ONE graph build")
  parser.add_argument("--base-url", required=True)
  args = parser.parse_args()
  regions = json.loads(args.regions.read_text())
  for spec in regions.values():
    spec["polygon"] = Path(spec["polygon"])
  partition(args.graph, args.output, args.id, regions, json.loads(args.provenance.read_text()), args.base_url)


if __name__ == "__main__":
  main()
