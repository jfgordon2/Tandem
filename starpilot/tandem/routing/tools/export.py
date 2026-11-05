"""Export checked packs as immutable release assets, with bounded release batches."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C


def export(source: Path, output: Path, *, catalog_name="catalog.json", base_url=None, batch=300):
  data = catalog.validate(json.loads((source / "catalog.json").read_text()))
  if data["schema"] != 2 or not bundles.ID.fullmatch(catalog_name) or not 1 <= batch <= 300:
    raise C.RoutingError("invalid_request")
  result = json.loads(json.dumps(data))
  for index, entry in enumerate(result["dataset"]["parts"]):
    folder = source / "parts" / entry["id"]
    bundle = bundles.load(folder, verify=True)
    if bundle.generation != entry["sha256"]:
      raise C.RoutingError("data_incompatible")
    bucket = index // batch
    destination = output / str(bucket)
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(json.dumps(bundle.manifest))
    url = base_url.format(bucket=bucket).rstrip("/") if base_url else entry["manifest"].rsplit("/", 1)[0]
    if not url.startswith("https://"):
      raise C.RoutingError("invalid_request")
    for name, record in manifest["files"].items():
      filename = entry["id"] + (".squashfs" if name == "tiles.squashfs" else ".tiles.json")
      record["url"] = url + "/" + filename
      target = destination / filename
      if target.exists():
        if bundles.digest(target) != record["sha256"]:
          raise C.RoutingError("bundle_exists")
      else:
        os.link(folder / name, target)
    raw = (json.dumps(manifest, indent=2) + "\n").encode()
    target = destination / (entry["id"] + ".json")
    if target.exists() and target.read_bytes() != raw:
      raise C.RoutingError("bundle_exists")
    target.write_bytes(raw)
    entry["manifest"], entry["sha256"] = url + "/" + target.name, hashlib.sha256(raw).hexdigest()
  catalog.validate(result)
  C.atomic_json(output / catalog_name, result)
  return result


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("source", type=Path)
  parser.add_argument("output", type=Path)
  parser.add_argument("--catalog-name", default="catalog.json")
  parser.add_argument("--base-url", help="release URL template, optionally containing {bucket}")
  args = parser.parse_args()
  export(args.source, args.output, catalog_name=args.catalog_name, base_url=args.base_url)


if __name__ == "__main__":
  main()
