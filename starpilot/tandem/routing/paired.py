"""Per-state download barriers over the existing two-worker routing transfer pool."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from openpilot.starpilot.tandem.routing import config as C, downloads
from openpilot.starpilot.tandem.routing.handoff import road_receipt

if TYPE_CHECKING:
  from openpilot.starpilot.tandem.routing.bundles import Bundle
  from openpilot.starpilot.tandem.routing.maps import Manager


class Transfers:
  """Downloads a dataset's parts alongside StarPilot's road downloader, one region at a time."""

  def __init__(self, manager: Manager) -> None:
    self.manager = manager

  def fetch(self, package: dict, gate: C.Gate, progress: C.Progress) -> list[Bundle]:
    """Downloads the package's missing parts, region by region, while the road data for each region downloads."""
    manager, dataset = self.manager, package["dataset"]
    regions = sorted(package["regions"])
    missing = {part["id"]: part for part in package["missing"]}
    counts: dict[str, int] = {}
    incoming: dict[str, Bundle] = {}
    visited, finished = set(), set()
    current = None

    def report() -> dict:
      receipt = road_receipt(manager.state["id"])
      if receipt.get("error"):
        raise C.RoutingError(receipt["error"])
      try:
        road = json.loads(manager.memory.get("MapsDownloadProgress", encoding="utf-8") or "{}")
      except (ValueError, TypeError):
        road = {}
      values = {}
      for region in regions:
        needed = set(dataset["regions"][region]["parts"]) & missing.keys()
        total = sum(missing[part]["bytes"] for part in needed)
        route = min(1, sum(counts.get(part, 0) for part in needed) / total) if total else 1
        road_fraction = float(region in receipt["completed"])
        if (not road_fraction and region == current and road.get("selectedKey") == region
            and road.get("updatedAt", 0) >= manager.state["created"] and road.get("totalFiles", 0) > 0):
          # Receipt, not a 100% counter, is the road-side completion barrier.
          road_fraction = min(.99, road.get("downloadedFiles", 0) / road["totalFiles"])
        fraction = min(road_fraction, route) if region in visited else 0
        values[region] = {"done": int(1000 * fraction), "total": 1000, "downloaded": region in finished}
      manager.publish(phase="download", stage="", done=sum(r["done"] for r in values.values()), total=1000 * len(regions),
                      region_progress=values, current_regions=[current] if current else [], road_region=current,
                      road_ready=set(regions) <= set(receipt["completed"]))
      return receipt

    def check() -> None:
      gate()
      report()

    for current in regions:
      gate()
      visited.add(current)
      # Persist the command even when the transfer is entirely cached. The
      # existing road worker waits on it and never rewrites MapsSelected.
      report()
      manager.publish(force=True)
      parts = [part for part in package["missing"]
               if part["id"] in dataset["regions"][current]["parts"] and part["id"] not in incoming]
      def part_progress(snapshot: dict[str, int]) -> None:
        counts.update(snapshot)
        report()
      prepared = downloads.prepare_many(parts, check, parts_progress=part_progress)
      incoming.update((part["id"], value) for part, value in zip(parts, prepared, strict=True))
      while current not in report()["completed"]:
        check()
        manager.stop.wait(.1)
      finished.add(current)
      report()
    manager.publish(force=True, road_region=None, current_regions=[], road_ready=True)
    return [incoming[part["id"]] for part in package["missing"]]
