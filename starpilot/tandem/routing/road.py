"""Retain mapd's archive groups for exactly the committed region selection.

Read the installed downloader's own menu, including its optional override.
Missing entries use the existing local routing catalog as a retention guard.
Mapd's 2-degree archives contain quarter-degree tiles, shared by every region
requesting that archive. Cleanup never needs a network lookup.
"""
from __future__ import annotations

import json
import math
import mmap
import os
from pathlib import Path
import re
from typing import Any, TYPE_CHECKING

from openpilot.starpilot.common.maps_download_progress import load_maps_storage_cache, storage_bytes
from openpilot.starpilot.common.maps_selection import US_STATE_CODES, normalize_maps_selected
from openpilot.starpilot.tandem.routing import config as C

if TYPE_CHECKING:
  from openpilot.common.params import Params

REPO = Path(__file__).resolve().parents[3]
MENU_START = re.compile(rb'\{\s*"(?:nation|us_state)"\s*:\s*\{')
TILE = re.compile(r"(-?\d+\.\d{6})_(-?\d+\.\d{6})_(-?\d+\.\d{6})_(-?\d+\.\d{6})(?:\.part|\.corrupt\.\d+)?")
ARCHIVE = re.compile(r"(-?\d+)\.tar\.gz(?:\.part)?")
CACHE = "MapsDownloadSizeCache"


def root() -> Path:
  # Same on-device location as mapd_wrapper.OFFLINE_ROOT. Private trials/tests
  # can redirect cleanup without touching any live road or routing data.
  return Path(os.getenv("TANDEM_ROAD_MAPS_DIR", "/data/media/0/osm/offline"))


def menu(binary: Path | None = None, override: Path | None = None) -> dict:
  """mapd's download menu: its override file, else the menu embedded in the binary."""
  binary = binary or REPO / "starpilot/navigation/mapd"
  override = override or REPO / "mapd_download_menu.json"
  if override.exists():
    with override.open("rb") as stream:
      raw = stream.read(1024**2 + 1)
    if len(raw) > 1024**2:
      raise C.RoutingError("data_incompatible")
    value = json.loads(raw)
  else:
    # Go embeds download_menu.json verbatim. mmap avoids loading the 20 MiB
    # executable into Python's heap; decode only a bounded menu-sized slice.
    with binary.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
      values = []
      for match in MENU_START.finditer(data):
        try:
          candidate, _ = json.JSONDecoder().raw_decode(data[match.start():match.start() + 1024**2].decode("utf-8", errors="replace"))
          if isinstance(candidate, dict) and "nation" in candidate and "us_state" in candidate:
            values.append(candidate)
        except ValueError:
          continue
      if len(values) != 1:
        raise C.RoutingError("data_incompatible")
      value = values[0]
  if not isinstance(value, dict) or not all(isinstance(value.get(key), dict) for key in ("nation", "us_state")):
    raise C.RoutingError("data_incompatible")
  with binary.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
    # Older binaries ignore this optional JSON field, even in a custom menu.
    # Never prune their bounding-box coverage down to rows they did not use.
    value["_download_rows_supported"] = data.find(b'json:"download_rows,omitempty"') >= 0
  return value


def regions(selection: str) -> set[str]:
  """The region tokens of a selection, a whole country expanded to its states."""
  normalized = normalize_maps_selected(selection)
  if selection and not normalized:
    raise C.RoutingError("invalid_request")
  result = set(filter(None, normalized.split(",")))
  if "nation.US" in result:
    result.remove("nation.US")
    result.update("us_state." + code for code in US_STATE_CODES)
  return result


def groups(location: dict, *, sparse: bool = True) -> set[tuple[int, int]]:
  """Match settings/download.go: adjustedBounds and downloadRows (step 2)."""
  try:
    bounds = location["bounding_box"]
    a, b, c, d = (bounds[key] for key in ("min_lat", "min_lon", "max_lat", "max_lon"))
    if (any(type(n) not in (int, float) or not math.isfinite(n) for n in (a, b, c, d))
        or not -90 <= a < c <= 90 or not -180 <= b < d <= 180):
      raise ValueError("bounds")
    a, b, c, d = math.floor(a / 2) * 2, math.floor(b / 2) * 2, math.ceil(c / 2) * 2, math.ceil(d / 2) * 2
  except (KeyError, TypeError, ValueError):
    raise C.RoutingError("data_incompatible") from None
  rows: Any = location.get("download_rows")   # from the JSON menu: checked below before use
  valid = sparse and isinstance(rows, list) and bool(rows)
  previous = None
  for row in rows if valid else ():
    if (not isinstance(row, list) or len(row) != 3 or any(type(n) is not int or n % 2 for n in row)
        or not (a <= row[0] < c and b <= row[1] < row[2] <= d)
        or previous is not None and (row[0] < previous[0] or row[0] == previous[0] and row[1] < previous[2])):
      valid = False
      break
    previous = row
  if not valid:
    rows = [(lat, b, d) for lat in range(a, c, 2)]
  return {(lat, lon) for lat, first, end in rows for lon in range(first, end, 2)}


def _fallback_location(region: str) -> dict:
  """Local geographic coverage may protect tiles, never certify a download."""
  from openpilot.starpilot.tandem.routing import catalog
  data = catalog.load()  # cached/bundled metadata only; no refresh or network
  spec = data.get("dataset", {}).get("regions", {}).get(region)
  if spec is None:
    # A valid older cached catalog may cover fewer regions than the bundled one.
    data = catalog.validate(json.loads(Path(catalog.__file__).with_suffix(".json").read_text()))
    spec = data.get("dataset", {}).get("regions", {}).get(region)
  if spec is None:
    raise C.RoutingError("data_incompatible")
  west, south, east, north = spec["bounds"]
  return {"bounding_box": {"min_lat": south, "min_lon": west, "max_lat": north, "max_lon": east}}


def footprint(selection: str, data: dict) -> dict:
  """The 2-degree archive groups each region of a selection needs."""
  result = {}
  for region in regions(selection):
    try:
      kind, code = region.split(".")
      location = data.get(kind, {}).get(code)
      result[region] = groups(location if location is not None else _fallback_location(region),
                              sparse=data.get("_download_rows_supported", False))
    except (KeyError, TypeError, ValueError):
      raise C.RoutingError("data_incompatible") from None
  return result


def _group(path: Path, low: int, high: int) -> int | None:
  try:
    number = int(path.name)
    if path.name == str(number) and low <= number < high and number % 2 == 0 and path.is_dir() and not path.is_symlink():
      return number
  except ValueError:
    pass
  return None


def _tile(path: Path, lat: int, lon: int) -> bool:
  match = TILE.fullmatch(path.name)
  if match is None or path.is_symlink() or not path.is_file():
    return False
  a, b, c, d = map(float, match.groups())
  return (c - a == d - b == .25 and a * 4 == int(a * 4) and b * 4 == int(b * 4)
          and lat <= a < c <= lat + 2 and lon <= b < d <= lon + 2)


def _prune(folder: Path, keep: set[tuple[int, int]], gate: C.Gate) -> None:
  for latitude in folder.iterdir():
    lat = _group(latitude, -90, 90)
    if lat is None:
      continue
    for longitude in latitude.iterdir():
      gate()
      lon = _group(longitude, -180, 180)
      if lon is None or (lat, lon) in keep:
        continue
      for path in longitude.iterdir():
        gate()
        if _tile(path, lat, lon):
          path.unlink()
      if not any(longitude.iterdir()):
        longitude.rmdir()
    if not any(latitude.iterdir()):
      latitude.rmdir()


def _prune_archives(folder: Path, keep: set[tuple[int, int]], gate: C.Gate) -> None:
  if not folder.exists() or folder.is_symlink() or folder.parent.is_symlink():
    return
  for latitude in folder.iterdir():
    lat = _group(latitude, -90, 90)
    if lat is None:
      continue
    for path in latitude.iterdir():
      gate()
      match = ARCHIVE.fullmatch(path.name)
      if match is None or path.is_symlink() or not path.is_file():
        continue
      lon = int(match[1])
      if match[1] == str(lon) and -180 <= lon < 180 and lon % 2 == 0 and (lat, lon) not in keep:
        path.unlink()
    if not any(latitude.iterdir()):
      latitude.rmdir()


def apply(selection: str, gate: C.Gate, memory: Params, *, params: Params | None = None, paired: bool = False) -> None:
  """After verified activation, remove only unneeded recognized road tiles.

  An interruption may leave extra deselected tiles for retry; selected tiles
  are never touched. Unknown files and symlinks are deliberately left alone.
  """
  folder = root()
  archives = folder.parent / "tmp/offline"
  if not folder.exists() and not archives.exists():
    return
  if folder.is_symlink():
    raise C.RoutingError("data_incompatible")
  def check() -> None:
    gate()
    C.require_parked()
    if not C.enabled():
      raise C.RoutingError("cancelled")
    if memory.get_bool("DownloadMaps") and not paired:
      raise C.RoutingError("busy")
    progress = json.loads(memory.get("MapsDownloadProgress", encoding="utf-8") or "{}")
    if progress.get("active"):
      raise C.RoutingError("busy")
  check()
  data = menu()
  wanted = footprint(selection, data)  # resolve every selected region before deleting anything
  fallback = {region for region in wanted if data.get(region.split(".")[0], {}).get(region.split(".")[1]) is None}
  keep = set().union(*wanted.values())
  if params is None:
    from openpilot.common.params import Params
    params = Params()
  cache = load_maps_storage_cache(params.get(CACHE, encoding="utf-8") or "")
  retained: dict = {}
  covered: dict = {}
  for key, entry in cache._selections.items():
    try:
      previous = regions(key)
    except C.RoutingError:
      continue
    if previous and previous <= wanted.keys() and not previous & fallback:
      retained[key] = entry
    if cache.selection_total_files(key) and cache.selection_updated_at(key):
      covered.update((region, cache.selection_updated_at(key)) for region in previous)
  for region in (wanted.keys() & covered.keys()) - fallback:
    retained.setdefault(region, {"totalFiles": len(wanted[region]), "updatedAt": covered[region], "estimatedAdditionalStorageBytes": 0})
  cache._selections = retained
  cache.mark_unknown()
  check()
  params.put(CACHE, cache.to_json())  # retire removed regions' Ready receipts before physical cleanup
  if folder.exists():
    _prune(folder, keep, check)
  _prune_archives(archives, keep, check)
  check()
  cache.reconcile(storage_bytes(folder))
  params.put(CACHE, cache.to_json())
