"""Build a dated national driving graph ONCE, then publish state-selectable packs.

Run off-device with Shapely and the pinned native runtime. No OSM build runs on
the car; it only recompresses verified tile packs into its selected graph.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import urllib.request

from openpilot.starpilot.common.maps_catalog import STATE_REGION_GROUPS
from openpilot.starpilot.tandem.routing import bundles, config as C
from openpilot.starpilot.tandem.routing.tools import auxiliary, build, sources, states

REGIONS = {code: title for group in STATE_REGION_GROUPS for code, title in group["regions"].items()}
PACIFIC = {"AS": (-172, -16, -167, -10), "GU": (143, 12, 146, 14), "MP": (143, 14, 147, 22)}


def territory_polygons(output):
  """Split the American Oceania extract footprint into its named island groups."""
  from shapely.geometry import box
  path = output / "sources/american-oceania.poly"
  if not path.exists():
    with urllib.request.urlopen("https://download.geofabrik.de/australia-oceania/american-oceania.poly", timeout=60) as response:
      path.write_bytes(response.read(1024 * 1024))
  shape = states.polygon(path)
  result = {}
  for code, bounds in PACIFIC.items():
    clipped = shape.intersection(box(*bounds))
    if clipped.is_empty or not clipped.is_valid:
      raise C.RoutingError("coverage_unavailable")
    polygons = [clipped] if clipped.geom_type == "Polygon" else list(clipped.geoms)
    lines = [code]
    for index, polygon in enumerate(polygons):
      if polygon.geom_type != "Polygon":
        continue
      for hole, ring in enumerate([polygon.exterior, *polygon.interiors]):
        lines.append(("!" if hole else "") + f"{index}-{hole}")
        lines.extend(f" {lon:.9f} {lat:.9f}" for lon, lat in ring.coords)
        lines.append("END")
    lines.append("END")
    target = output / "sources" / (code + ".poly")
    target.write_text("\n".join(lines) + "\n")
    states.polygon(target)
    result["us_state." + code] = {"title": REGIONS[code], "polygon": target}
  return result


def build_us(output: Path, snapshot: str, identity: str, base_url: str, *, concurrency=4, start=None):
  if not re.fullmatch("[0-9]{6}", snapshot) or not bundles.ID.fullmatch(identity) or len(identity) > 48:
    raise C.RoutingError("invalid_request")
  if (output / "packages/catalog.json").exists():
    raise C.RoutingError("bundle_exists")
  source = output / "sources" / f"us-{snapshot}.osm.pbf"
  origin = sources.fetch(f"https://download.geofabrik.de/north-america/us-{snapshot}.osm.pbf", source)
  pacific_path = output / "sources" / f"american-oceania-{snapshot}.osm.pbf"
  pacific = sources.fetch(f"https://download.geofabrik.de/australia-oceania/american-oceania-{snapshot}.osm.pbf", pacific_path)
  inputs = [(source, origin), (pacific_path, pacific)]
  # The mainland US extract excludes these Caribbean territories.
  for slug in ("puerto-rico", "us-virgin-islands"):
    path = output / "sources" / f"{slug}-{snapshot}.osm.pbf"
    receipt = sources.fetch(f"https://download.geofabrik.de/north-america/us/{slug}-{snapshot}.osm.pbf", path)
    inputs.append((path, receipt))
  regions = territory_polygons(output)
  for code, title in sorted(REGIONS.items()):
    if code in PACIFIC:
      continue
    slug = {"VI": "us-virgin-islands"}.get(code, title.lower().replace(" ", "-"))
    path = output / "sources" / f"{slug}.poly"
    if not path.exists():
      with urllib.request.urlopen(f"https://download.geofabrik.de/north-america/us/{slug}.poly", timeout=60) as response:
        raw = response.read(1024 * 1024 + 1)
      if len(raw) > 1024 * 1024:
        raise C.RoutingError("data_incompatible")
      path.write_bytes(raw)
    states.polygon(path)  # validate before starting the national build
    regions["us_state." + code] = {"title": title, "polygon": path}
  marker = output / "graph-build.json"
  boundaries = {region: bundles.digest(spec["polygon"]) for region, spec in regions.items()}
  combined = output / "sources" / f"us-combined-{snapshot}.osm.pbf"
  merged = sources.merge(inputs, combined)
  native_sources = [(combined, "Merged verified same-snapshot extracts")]
  admin, timezone, auxiliary_receipt = auxiliary.prepare(output, native_sources, REGIONS)
  signature = {"sources": [item for _, item in inputs], "merged_sha256": merged["sha256"],
               "boundaries": boundaries, "auxiliary": auxiliary_receipt,
               "runtime_version": C.VERSION, "profile": "driving"}
  if marker.exists():
    receipt = json.loads(marker.read_text())
    if receipt["inputs"] != signature:
      raise C.RoutingError("bundle_exists")
  else:
    stamp = datetime.datetime.now(datetime.UTC).isoformat()
    receipt = {"inputs": signature, "built_at": stamp, "complete": False}
    C.atomic_json(marker, receipt)
  graph = output / "graph/tiles"
  if not receipt["complete"]:
    if shutil.disk_usage(output).free < origin["bytes"] * 8 + 16 * 1024**3:
      raise C.RoutingError("no_space")
    print(json.dumps({"stage": "national_graph", "snapshot": snapshot, "concurrency": concurrency}), flush=True)
    graph = build.build_graph(native_sources, output / "graph", concurrency=concurrency, start=start, admin=admin, timezone=timezone)
    C.atomic_json(marker, {**receipt, "complete": True})
  provenance = {"source": {**origin, "retrieved_at": receipt["built_at"]}, "built_at": receipt["built_at"],
                "sources": [{**item, "retrieved_at": receipt["built_at"]} for _, item in inputs] + auxiliary_receipt["sources"],
                "attribution": "© OpenStreetMap contributors, https://www.openstreetmap.org/copyright (ODbL)"}
  print(json.dumps({"stage": "state_packages", "states": len(regions)}), flush=True)
  return states.partition(graph, output / "packages", identity, regions, provenance, base_url)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("output", type=Path)
  parser.add_argument("--snapshot", required=True, help="dated Geofabrik extract, YYMMDD")
  parser.add_argument("--id", required=True)
  parser.add_argument("--base-url", required=True)
  parser.add_argument("--concurrency", type=int, default=4)
  parser.add_argument("--resume-from", help="native stage after an interrupted build, e.g. parsenodes")
  args = parser.parse_args()
  build_us(args.output, args.snapshot, args.id, args.base_url, concurrency=args.concurrency, start=args.resume_from)


if __name__ == "__main__":
  main()
