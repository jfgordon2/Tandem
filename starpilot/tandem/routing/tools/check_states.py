"""Off-device route equivalence: selected shared tiles versus the complete graph.

Temporary plain tars exist only in this maintainer QA tool, never on the device.
It uses the pinned Actor, normalizer, route options and memory configuration.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C, tiles as T

# Public city-center coordinates, with short local routes. These are a smoke
# corpus, not a substitute for testing trips the owner actually drives.
CENTERS = {
  "AL": (32.3668, -86.3000), "AK": (61.2181, -149.9003), "AZ": (33.4484, -112.0740),
  "AR": (34.7465, -92.2896), "CA": (38.5816, -121.4944), "CO": (39.7392, -104.9903),
  "CT": (41.7658, -72.6734), "DE": (39.1582, -75.5244), "DC": (38.9072, -77.0369),
  "FL": (30.4383, -84.2807), "GA": (33.7490, -84.3880), "HI": (21.3099, -157.8581),
  "ID": (43.6150, -116.2023), "IL": (39.7817, -89.6501), "IN": (39.7684, -86.1581),
  "IA": (41.5868, -93.6250), "KS": (39.0473, -95.6752), "KY": (38.2009, -84.8733),
  "LA": (30.4515, -91.1871), "ME": (44.3106, -69.7795), "MD": (38.9784, -76.4922),
  "MA": (42.3601, -71.0589), "MI": (42.7325, -84.5555), "MN": (44.9537, -93.0900),
  "MS": (32.2988, -90.1848), "MO": (38.5767, -92.1735), "MT": (46.5884, -112.0245),
  "NE": (40.8136, -96.7026), "NV": (39.1638, -119.7674), "NH": (43.2081, -71.5376),
  "NJ": (40.2171, -74.7429), "NM": (35.6870, -105.9378), "NY": (42.6526, -73.7562),
  "NC": (35.7796, -78.6382), "ND": (46.8083, -100.7837), "OH": (39.9612, -82.9988),
  "OK": (35.4676, -97.5164), "OR": (44.9429, -123.0351), "PA": (40.2732, -76.8867),
  "RI": (41.8240, -71.4128), "SC": (34.0007, -81.0348), "SD": (44.3683, -100.3510),
  "TN": (36.1627, -86.7816), "TX": (30.2672, -97.7431), "UT": (40.7608, -111.8910),
  "VT": (44.2601, -72.5754), "VA": (37.5407, -77.4360), "WA": (47.0379, -122.9007),
  "WV": (38.3498, -81.6326), "WI": (43.0731, -89.4012), "WY": (41.1400, -104.8202),
  "PR": (18.4655, -66.1057), "VI": (18.3419, -64.9307), "AS": (-14.2756, -170.7020),
  "GU": (13.4763, 144.7508), "MP": (15.1778, 145.7509),
}


def samples():
  result = [{"name": code + " local", "regions": ["us_state." + code], "start": [lat, lon, None],
             "destination": {"latitude": lat, "longitude": round(lon + .02, 7)}} for code, (lat, lon) in sorted(CENTERS.items())]
  for name, regions, start, end in (
      ("Des Moines to Chicago", ["IA", "IL"], (41.5868, -93.6250), (41.8781, -87.6298)),
      ("Chicago to Des Moines", ["IA", "IL"], (41.8781, -87.6298), (41.5868, -93.6250)),
      ("Davenport to Moline", ["IA", "IL"], (41.5236, -90.5776), (41.5067, -90.5151)),
      ("New York to Newark", ["NY", "NJ"], (40.7128, -74.0060), (40.7357, -74.1724)),
      ("Washington to Arlington", ["DC", "VA"], (38.9072, -77.0369), (38.8816, -77.0910))):
    result.append({"name": name, "regions": ["us_state." + r for r in regions], "start": [*start, None],
                   "destination": {"latitude": end[0], "longitude": end[1]}})
  return result


def native(graph):
  from openpilot.starpilot.tandem.routing.metrics import memory
  from openpilot.starpilot.tandem.routing.native_worker import actor_config, compact_response, isolate_network, release_heap, route_options
  from openpilot.starpilot.tandem.routing.normalize import normalize
  isolation = isolate_network()
  from valhalla import Actor
  config = actor_config(graph)
  if graph.is_dir():
    config["mjolnir"].update(tile_dir=str(graph), tile_extract="")
  actor = Actor(config)
  for sample in json.load(sys.stdin):
    started = time.monotonic()
    try:
      route = normalize(compact_response(actor.route(route_options(sample))))
      result = {"name": sample["name"], "status": "ok", "sha256": hashlib.sha256(json.dumps(route, sort_keys=True).encode()).hexdigest(),
                "meters": route["totalDistance"], "duration": route["totalDuration"], "steps": len(route["steps"]),
                "speed_slots": len(route["maxspeed"])}
      route = None
    except Exception as error:
      result = {"name": sample["name"], "status": "failed", "error": str(error)}
    print(json.dumps({**result, "seconds": time.monotonic() - started, "network_isolation": isolation, **memory()}), flush=True)
    release_heap()


def routes(graph, cases):
  raw = subprocess.check_output([str(C.runtime_python()), "-m", "openpilot.starpilot.tandem.routing.tools.check_states", str(graph), "--native"],
                                 input=json.dumps(cases), text=True, timeout=max(45, len(cases) * C.DEADLINE + 10))
  result = [json.loads(line) for line in raw.splitlines()]
  if len(result) != len(cases):
    raise C.RoutingError("invalid_response")
  return result


def check(graph, packages, out, regions=None):
  data = catalog.validate(json.loads((packages / "catalog.json").read_text()))["dataset"]
  selected = set(data["regions"]) if regions is None else set(regions)
  if not selected <= set(data["regions"]) or not selected:
    raise C.RoutingError("invalid_request")
  cases = [sample for sample in samples() if set(sample["regions"]) <= selected]
  if {sample["regions"][0] for sample in cases if len(sample["regions"]) == 1} != selected:
    raise C.RoutingError("coverage_unavailable")
  inventories = {}
  for part in data["parts"]:
    folder = packages / "parts" / part["id"]
    bundle = bundles.load(folder)
    if bundle.generation != part["sha256"]:
      raise C.RoutingError("data_incompatible")
    inventories[part["id"]] = T.read_index(folder / "tiles.json", data["sha256"])
  baseline = routes(graph.resolve(), cases)
  expected = {item["name"]: item for item in baseline}
  report = {"dataset": data["id"], "sha256": data["sha256"], "baseline": baseline, "selected": [], "national": [], "complete": False}
  groups = defaultdict(list)
  for sample in cases:
    groups[tuple(sorted(sample["regions"]))].append(sample)
  out.parent.mkdir(parents=True, exist_ok=True)
  C.atomic_json(out, report)
  def run(selection, group):
    parts = sorted({part for region in selection for part in data["regions"][region]["parts"]})
    rows, length = T.layout([row for part in parts for row in inventories[part]])
    with tempfile.TemporaryDirectory(dir=out.parent) as directory:
      archive = Path(directory) / "tiles.tar"
      with archive.open("wb") as target:
        for block in T.stream(rows, lambda row: T.file_chunks(graph / row["path"], 0, row["bytes"])):
          target.write(block)
      assert archive.stat().st_size == length
      results = routes(archive, group)
      for item in results:
        item.update(regions=selection, logical_bytes=length, parts=len(parts))
        control = expected[item["name"]]
        item["matches"] = item["status"] == control["status"] == "ok" and item["sha256"] == control["sha256"]
        print(json.dumps(item), flush=True)
      return results
  for selection, group in sorted(groups.items()):
    report["selected"].extend(run(selection, group))
    C.atomic_json(out, report)
  # Exercise the full indexed extract too: its 64-bit offsets cross the 8 GiB
  # boundary, which small state selections cannot validate with native routes.
  if selected == set(data["regions"]) and len(selected) > 1:
    report["national"] = run(tuple(sorted(selected)), cases)
  report["complete"] = all(item["matches"] for item in report["selected"] + report["national"])
  C.atomic_json(out, report)
  if not report["complete"]:
    raise C.RoutingError("data_incompatible")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("graph", type=Path)
  parser.add_argument("packages", type=Path, nargs="?")
  parser.add_argument("--out", type=Path)
  parser.add_argument("--regions", help="comma-separated canonical state tokens; default every catalog region")
  parser.add_argument("--native", action="store_true", help=argparse.SUPPRESS)
  args = parser.parse_args()
  if args.native:
    native(args.graph)
  elif args.packages and args.out:
    check(args.graph, args.packages, args.out, args.regions.split(",") if args.regions else None)
  else:
    parser.error("packages and --out are required")


if __name__ == "__main__":
  main()
