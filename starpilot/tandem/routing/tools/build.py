"""Build one connected routing bundle off-device using the pinned native builder."""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import subprocess
import urllib.request

from openpilot.starpilot.tandem.routing import archive as transport, config as C, images
from openpilot.starpilot.tandem.routing.bundles import ID, digest, load
from openpilot.starpilot.tandem.routing.tools import graph_tar


def build(source: Path, output: Path, bundle_id: str, title: str, bounds: list[float], source_url: str, *,
          additional_sources: tuple[tuple[Path, str], ...] = (), regions: tuple[str, ...] = (),
          all_modes=False, compressed=True, storage=None) -> None:
  if not ID.fullmatch(bundle_id) or (output / "manifest.json").exists():
    raise C.RoutingError("bundle_exists")
  sources = ((source, source_url), *additional_sources)
  storage = storage or ("squashfs" if compressed else "plain")
  if storage not in ("squashfs", "zstd", "plain"):
    raise C.RoutingError("invalid_request")
  if not all(path.is_file() for path, _ in sources):
    raise C.RoutingError("data_missing")
  if regions:
    from openpilot.starpilot.tandem.routing.catalog import tokens
    if set(regions) != tokens(",".join(regions)):
      raise C.RoutingError("invalid_request")
  output.mkdir(parents=True, exist_ok=True)
  tiles = output / "tiles"
  tiles.mkdir(exist_ok=True)
  # Run configuration and graph tools in the isolated environment, not the UI interpreter.
  code = ("import json,sys; from valhalla import get_config; " +
          "c=get_config(tile_dir=sys.argv[1], tile_extract=''); " +
          "c['mjolnir']['concurrency']=2; print(json.dumps(c))")
  config = json.loads(subprocess.check_output([str(C.runtime_python()), "-c", code, str(tiles.resolve())], text=True))
  config["mjolnir"].update(include_driving=True, include_bicycle=all_modes, include_pedestrian=all_modes,
                          include_driveways=True, hierarchy=True, shortcuts=True,
                          keep_osm_node_ids=False, keep_all_osm_node_ids=False, include_platforms=False,
                          import_bike_share_stations=False, include_construction=False, pedestrian_areas=False)
  config_path = output / "build-config.json"
  config_path.write_text(json.dumps(config, indent=2) + "\n")
  builder = subprocess.check_output([str(C.runtime_python()), "-c",
    "from valhalla import PYVALHALLA_DIR; print(PYVALHALLA_DIR / 'bin' / 'valhalla_build_tiles')"], text=True).strip()
  # Feed every extract into one native build so shared roads connect across borders.
  subprocess.run([builder, "-c", str(config_path), *(str(path) for path, _ in sources)], check=True)
  graph_tar.write(tiles, output / "tiles.tar")
  graph = output / "tiles.tar"
  stamp = datetime.datetime.now(datetime.UTC).isoformat()
  provenance = [{"url": url, "sha256": digest(path), "retrieved_at": stamp} for path, url in sources]
  manifest = {"schema": 1, "id": bundle_id, "title": title, "runtime_version": C.VERSION,
    "builder_version": C.VERSION, "built_at": stamp, "bounds": bounds,
    "source": provenance[0],
    "coverage_note": "Connected extract; bounds are a precheck, not proof of interior road coverage.",
    "attribution": "© OpenStreetMap contributors, https://www.openstreetmap.org/copyright (ODbL)",
    "features": ["auto", "banners", "lanes_where_mapped", "maxspeed_where_mapped"],
    "profile": "all_modes" if all_modes else "driving",
    "files": {"tiles.tar": {"bytes": graph.stat().st_size, "sha256": digest(graph)}}}
  if storage == "squashfs":
    image = output / "tiles.squashfs"
    images.pack(graph, image)
    manifest["schema"] = 3
    manifest["graph"] = {"format": "squashfs", "file": image.name, "path": "tiles.tar",
                         "bytes": graph.stat().st_size, "sha256": digest(graph)}
    manifest["files"] = {image.name: {"bytes": image.stat().st_size, "sha256": digest(image)}}
  elif storage == "zstd":
    manifest["schema"] = 2
    manifest["files"]["tiles.tar"]["download"] = transport.compress(graph, output / "tiles.tar.zst")
  if additional_sources:
    manifest["sources"] = provenance
  if regions:
    manifest["regions"] = sorted(set(regions))
  C.atomic_json(output / "manifest.json", manifest)
  load(output, verify=True)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("source", type=Path)
  parser.add_argument("output", type=Path)
  parser.add_argument("--id", required=True)
  parser.add_argument("--title", required=True)
  parser.add_argument("--bounds", nargs=4, type=float, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
  parser.add_argument("--source-url", required=True)
  parser.add_argument("--additional-source", nargs=2, action="append", default=[], metavar=("PATH", "URL"),
                      help="additional extract to build into the same connected graph; must already exist")
  parser.add_argument("--region", action="append", default=[], help="covered map-selection token, e.g. us_state.IA")
  parser.add_argument("--all-modes", action="store_true", help="maintainer control build including walking and cycling")
  parser.add_argument("--uncompressed", action="store_true", help="maintainer control build with plain-tar transport")
  parser.add_argument("--storage", choices=("squashfs", "zstd", "plain"), default="squashfs")
  args = parser.parse_args()
  if not args.source.exists():
    with urllib.request.urlopen(args.source_url, timeout=60) as response, args.source.open("wb") as stream:
      import shutil
      shutil.copyfileobj(response, stream)
  build(args.source, args.output, args.id, args.title, args.bounds, args.source_url,
        additional_sources=tuple((Path(path), url) for path, url in args.additional_source), regions=tuple(args.region),
        all_modes=args.all_modes, storage="plain" if args.uncompressed else args.storage)
  print(json.dumps(load(args.output).manifest, indent=2))


if __name__ == "__main__":
  main()
