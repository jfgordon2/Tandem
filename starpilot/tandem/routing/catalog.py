"""Maintainer-owned region catalog. Drivers choose geography, never package URLs."""
from __future__ import annotations

import json
from pathlib import Path
import re
import urllib.request

from openpilot.starpilot.common.maps_selection import normalize_maps_selected
from openpilot.starpilot.tandem.routing import bundles, config as C, verified
from openpilot.starpilot.tandem.routing.tools.manage import HTTPSRedirect

URL = "https://github.com/jfgordon2/Tandem/releases/download/routing-data-v1/catalog-squashfs-v1.json"


def tokens(selection: str) -> set[str]:
  result = set(filter(None, normalize_maps_selected(selection).split(",")))
  if "nation.US" in result:
    from openpilot.starpilot.common.maps_catalog import VALID_MAP_TOKENS
    result.remove("nation.US")
    result.update(t for t in VALID_MAP_TOKENS if t.startswith("us_state."))
  return result


def validate(data: dict) -> dict:
  try:
    if data["schema"] != 1 or data["runtime_version"] != C.VERSION or not isinstance(data["packages"], list):
      raise ValueError
    identities = set()
    for p in data["packages"]:
      if (not bundles.ID.fullmatch(p["id"]) or p["id"] in identities or not p["manifest"].startswith("https://")
          or not re.fullmatch("[a-f0-9]{64}", p["sha256"]) or type(p["bytes"]) is not int or p["bytes"] <= 0
          or not p["regions"] or set(p["regions"]) != tokens(",".join(p["regions"]))):
        raise ValueError
      identities.add(p["id"])
    return data
  except (KeyError, ValueError, TypeError, AttributeError):
    raise C.RoutingError("catalog_unavailable") from None


def load(refresh=False, gate=lambda: None) -> dict:
  cache = C.root() / "catalog.json"
  if refresh:
    gate()
    opener = urllib.request.build_opener(HTTPSRedirect())
    try:
      with opener.open(URL, timeout=15) as response:
        raw = response.read(1024 * 1024 + 1)
      if len(raw) > 1024 * 1024:
        raise C.RoutingError("catalog_unavailable")
      result = validate(json.loads(raw))
      C.atomic_json(cache, result)
      return result
    except (OSError, ValueError):
      # A cached catalog can finish an interrupted download while the catalog
      # host is unavailable. Integrity is still checked against each manifest.
      pass
  for path in (cache, Path(__file__).with_suffix(".json")):
    try:
      return validate(json.loads(path.read_text()))
    except (OSError, ValueError, C.RoutingError):
      continue
  raise C.RoutingError("catalog_unavailable")


def plan(selection: str, data: dict | None = None) -> tuple[list[dict], set[str]]:
  remaining, result = tokens(selection), []
  # Prefer connected graphs covering several selected regions. Additional
  # independent graphs can serve separate trips, never a stitched cross-border route.
  packages = (data or load())["packages"]
  while remaining:
    candidates = [p for p in packages if remaining.intersection(p["regions"])]
    if not candidates:
      break
    p = min(candidates, key=lambda p: (-len(remaining.intersection(p["regions"])), p["bytes"]))
    result.append(p)
    remaining.difference_update(p["regions"])
  return result, remaining


def ready_regions() -> set[str]:
  result = set()
  known = {p["id"]: p["regions"] for p in load()["packages"]}
  for b in bundles.installed():
    if not verified.read(b):
      continue
    # Recognize the measured legacy Iowa graph only by its exact checksum.
    trial = ["us_state.IA"] if b.manifest["files"].get("tiles.tar", {}).get("sha256") == \
      "ba3f1eadcb4ddcb27f32f3b709d98eb62510617519bdf359dc28fe2d235b3019" else []
    result.update(b.manifest.get("regions", known.get(b.id, trial)))
  return result
