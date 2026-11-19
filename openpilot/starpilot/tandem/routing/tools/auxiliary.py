"""Off-device administrative and time-zone inputs for the national graph."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from openpilot.starpilot.tandem.routing import bundles, config as C

COUNTRY_URL = "https://api.openstreetmap.org/api/0.6/relation/148838/full"
TZ_URL = "https://github.com/evansiroky/timezone-boundary-builder/releases/download/2026d/timezones-with-oceans-1970.shapefile.zip"
TZ_SHA = "f9b2f0304772f2a944486da5d13d1740ff9754e76b983f80450b0e4d74131931"


def checked_source(url, path, checksum=None):
  path.parent.mkdir(parents=True, exist_ok=True)
  receipt = path.with_name(path.name + ".source.json")
  if not path.exists():
    partial = path.with_name(path.name + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as target:
      count = 0
      while block := response.read(1024**2):
        count += len(block)
        if count > 128 * 1024**2:
          raise C.RoutingError("data_incompatible")
        target.write(block)
    partial.replace(path)
  sha = bundles.digest(path)
  if (checksum and sha != checksum) or (receipt.exists() and json.loads(receipt.read_text())["sha256"] != sha):
    raise C.RoutingError("data_incompatible")
  if receipt.exists():
    return json.loads(receipt.read_text())
  result = {"url": url, "bytes": path.stat().st_size, "sha256": sha,
            "retrieved_at": datetime.datetime.now(datetime.UTC).isoformat()}
  C.atomic_json(receipt, result)
  return result


def prepare(output: Path, sources, required_states):
  """Regional extracts omit complete parent boundaries; supplement the US parent."""
  country = output / "sources/us-country.osm"
  country_source = checked_source(COUNTRY_URL, country)
  found = False
  for _, element in ET.iterparse(country):
    if element.tag == "relation" and element.get("id") == "148838":
      tags = {tag.get("k"): tag.get("v") for tag in element.findall("tag")}
      found = tags.get("ISO3166-1") == "US" and tags.get("admin_level") == "2"
  if not found:
    raise C.RoutingError("data_incompatible")
  archive = output / "sources/timezones-with-oceans-1970-2026d.zip"
  timezone_source = checked_source(TZ_URL, archive, TZ_SHA)
  inputs = {"osm": [bundles.digest(path) for path, _ in sources],
            "country": country_source["sha256"], "timezones": timezone_source["sha256"], "runtime_version": C.VERSION}
  folder = output / "auxiliary"
  folder.mkdir(exist_ok=True)
  receipt = folder / "receipt.json"
  admin, timezone = folder / "admins.sqlite", folder / "timezones.sqlite"
  if receipt.exists():
    previous = json.loads(receipt.read_text())
    if (previous["inputs"] == inputs and admin.exists() and timezone.exists()
        and all(bundles.digest(folder / name) == sha for name, sha in previous["files"].items())):
      return admin, timezone, previous
    raise C.RoutingError("bundle_exists")
  config = folder / "admin-config.json"
  pending = folder / "admins.pending.sqlite"
  pending.unlink(missing_ok=True)
  config.write_text(json.dumps({"mjolnir": {"admin": str(pending.resolve())}, "logging": {"type": "std_out", "color": False}}))
  builder = subprocess.check_output([str(C.runtime_python()), "-c",
    "from valhalla import PYVALHALLA_DIR; print(PYVALHALLA_DIR / 'bin' / 'valhalla_build_admins')"], text=True).strip()
  subprocess.run([builder, "-c", str(config), *(str(path) for path, _ in sources), str(country)], check=True)
  with sqlite3.connect(pending) as database:
    # 3.9.1 copies the parent's driving side onto every child admin. Preserve
    # its own admin.lua rule for the US territory that drives on the left.
    database.execute("UPDATE admins SET drive_on_right=0 WHERE iso_code='VI' AND admin_level=4")
    rows = database.execute("SELECT iso_code,drive_on_right FROM admins WHERE admin_level IN (2,4)").fetchall()
    codes = {code for code, _ in rows}
    if not {"US", *required_states} <= codes or ("VI", 0) not in rows:
      raise C.RoutingError("coverage_unavailable")
    parents = database.execute("SELECT s.iso_code,p.iso_code FROM admins s LEFT JOIN admins p ON s.parent_admin=p.rowid " +
                               "WHERE s.admin_level=4").fetchall()
    if any(code in required_states and parent != "US" for code, parent in parents):
      raise C.RoutingError("coverage_unavailable")
  pending.replace(admin)
  tool, sql = shutil.which("spatialite_tool"), shutil.which("spatialite")
  if not tool or not sql:
    raise C.RoutingError("data_missing")
  shapes = folder / "timezones"
  shapes.mkdir(exist_ok=True)
  stem = "combined-shapefile-with-oceans-1970"
  with zipfile.ZipFile(archive) as compressed:
    for suffix in (".shp", ".shx", ".dbf", ".prj"):
      compressed.extract(stem + suffix, shapes)
  pending = folder / "timezones.pending.sqlite"
  pending.unlink(missing_ok=True)
  subprocess.run([tool, "-i", "-shp", str(shapes / stem), "-d", str(pending), "-t", "tz_world", "-s", "4326", "-g", "geom", "-c", "UTF-8"],
                 check=True)
  subprocess.run([sql, "-batch", str(pending), "SELECT CreateSpatialIndex('tz_world','geom'); VACUUM; ANALYZE;"], check=True)
  with sqlite3.connect(pending) as database:
    if database.execute("SELECT count(*) FROM tz_world").fetchone()[0] < 200:
      raise C.RoutingError("data_incompatible")
  pending.replace(timezone)
  result = {"inputs": inputs, "files": {path.name: bundles.digest(path) for path in (admin, timezone)},
            "sources": [country_source, timezone_source]}
  C.atomic_json(receipt, result)
  return admin, timezone, result
