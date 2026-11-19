"""The Offline Maps page's source (settings/maps.py) on StarPilot 7: Tandem's map jobs, which get road data from StarPilot's
map owner and install Tandem's offline routes (starpilot/tandem/routing/maps.py and road.py).

Release combined StarPilot 6's maps screen controller with Tandem's routing jobs. On StarPilot 7 one map job does both,
so this source reads its progress, what's installed, and the regions: Tandem's US states and region groups, and the other
countries StarPilot's map owner offers (road data only: Tandem's offline routes cover the US).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_
from openpilot.selfdrive.ui.tandem.settings.maps import Progress, Region, RegionProgress
from openpilot.starpilot.tandem.routing import bundles, catalog, maps as jobs, road
from openpilot.starpilot.tandem.routing.regions import NATION_US, STATE_GROUPS, STATE_PREFIX, STATE_TOKENS, STATES, name as state_name

GROUP_PREFIX = "group."
GROUPS = {GROUP_PREFIX + title.lower(): (title, frozenset(STATE_PREFIX + code for code in states)) for title, states in STATE_GROUPS}
GROUP_NAMES = {"Midwest": N_("Midwest"), "Northeast": N_("Northeast"), "South": N_("South"), "West": N_("West"),
               "Territories": N_("Territories")}
REFRESH_S = 2.0


class TandemMaps:
  """MapsSource over Tandem's map jobs and StarPilot 7's map owner.

  Args:
    parked: Whether the car is parked (StarPilot's offroad state).
    wifi: Whether the device is on Wi-Fi; downloads run only then.
    remove_maps: Deletes every downloaded map through StarPilot's map owner (Storage & Data's Delete).
    owner: StarPilot's map owner requests (road._request); a stand-in in tests.
    clock: Monotonic seconds.
  """

  def __init__(self, parked: Callable[[], bool], wifi: Callable[[], bool], remove_maps: Callable[[], None],
               owner: Callable[[dict], dict] = road._request, clock: Callable[[], float] = time.monotonic):
    self._parked, self._wifi, self._remove, self._owner, self._clock = parked, wifi, remove_maps, owner, clock
    self._read_at = -1e9
    self.job: dict = {}
    self.road_ready: set[str] = set()
    self.route_ready: set[str] = set()
    self.countries: dict[str, str] = {}
    self.catalog: dict = {}
    self._routes_bytes = 0
    self._plans: dict[str, tuple[list[dict], set[str]]] = {}
    self._chosen: set[str] | None = None

  # ── Reading ──

  def tick(self) -> None:
    """Reads the job, what's installed and StarPilot's road data, at most every REFRESH_S."""
    if self._clock() - self._read_at < REFRESH_S:
      return
    self._read_at = self._clock()
    self.job = jobs.read()
    pending = jobs.read("map-request.json")
    if pending.get("id") and pending["id"] != self.job.get("id"):
      # The broker may still be starting: never show an old result for a newly queued job.
      self.job = {**pending, "phase": "road", "done": 0, "total": 0, "regions_ready": [], "current_regions": []}
    try:
      self.catalog = catalog.load()
    except Exception:
      self.catalog = {"schema": 2, "packages": [], "dataset": {"regions": {}}}
    self._plans.clear()
    self.route_ready = catalog.ready_regions()
    self._routes_bytes = sum(record["bytes"] for bundle in bundles.installed() for record in bundle.manifest["files"].values())
    try:
      self.road_ready = road.present(self._owner)
      if not self.countries:
        self.countries = {row["token"]: str(row["name"]) for row in self._owner({"op": "catalog"}).get("regions", [])
                          if row["token"].startswith("nation.") and row["token"] != NATION_US and row.get("available")}
    except Exception:
      self.road_ready = set()   # StarPilot's map owner runs only while parked
    if self._chosen is None:
      self._chosen = catalog.tokens(jobs.selection()) or set(self.route_ready | self.road_ready)

  def refresh(self) -> None:
    self._read_at = -1e9
    self.tick()

  def chosen(self) -> set[str]:
    self.tick()
    return set(self._chosen or set())

  def _plan(self, selection: str) -> tuple[list[dict], set[str]]:
    if selection not in self._plans:
      try:
        self._plans[selection] = catalog.plan(selection, self.catalog)
      except Exception:
        self._plans[selection] = ([], catalog.tokens(selection))
    return self._plans[selection]

  def _selection(self) -> str:
    return ",".join(sorted(self.chosen()))

  # ── Regions and the selection ──

  def expand(self, token: str) -> set[str]:
    if token == NATION_US:
      return set(STATE_TOKENS)
    if token in GROUPS:
      return set(GROUPS[token][1])
    return {token}

  def regions(self, tab: int) -> list[Region]:
    self.tick()
    if tab == 0:
      return [Region(NATION_US, N_("Whole U.S."), N_("Every state and territory")),
              *(Region(token, GROUP_NAMES[title], t_("{} states", len(states))) for token, (title, states) in GROUPS.items())]
    if tab == 1:
      return [Region(STATE_PREFIX + code, label) for code, label in sorted(STATES.items(), key=lambda item: item[1])]
    return [Region(token, label) for token, label in sorted(self.countries.items(), key=lambda item: item[1])]

  def name(self, token: str) -> str:
    self.tick()
    if token in GROUPS:
      return GROUP_NAMES[GROUPS[token][0]]
    return self.countries.get(token) or state_name(token)

  def selected(self, token: str) -> bool:
    expanded = self.expand(token)
    return bool(expanded) and expanded <= self.chosen()

  def set_selected(self, token: str, on: bool) -> None:
    chosen = self.chosen()
    self._chosen = chosen | self.expand(token) if on else chosen - self.expand(token)

  def selection_summary(self) -> str:
    chosen = self.chosen()
    if not chosen:
      return N_("None selected")
    if chosen >= STATE_TOKENS and not chosen - STATE_TOKENS:
      return N_("Whole U.S.")
    if len(chosen) == 1:
      return self.name(next(iter(chosen)))
    return tn_("{} region", "{} regions", len(chosen))

  def has_selection(self) -> bool:
    return bool(self.chosen())

  def can_clear(self) -> bool:
    return not self.chosen() and bool(self.route_ready) and not jobs.running()

  def downloaded(self) -> bool:
    self.tick()
    return bool(self.road_ready or self.route_ready)

  # ── What's ready ──

  def region_status(self, token: str) -> tuple[str, str]:
    self.tick()
    expanded = self.expand(token)
    covered = set(self.catalog.get("dataset", {}).get("regions", {}))
    covered.update(region for package in self.catalog.get("packages", []) for region in package["regions"])
    return (N_("Road data ready") if expanded <= self.road_ready else N_("Not downloaded"),
            N_("Routes ready") if expanded <= self.route_ready else
            N_("Routes not downloaded") if expanded <= covered else N_("Routes not available yet"))

  def summary(self) -> dict:
    """Road data and routes for the selection, and a note on coverage."""
    chosen = self.chosen()
    packages, missing = self._plan(self._selection())
    clear = self.can_clear()
    route_ready = bool(chosen) and chosen <= self.route_ready
    return {
      "road": N_("Already downloaded") if chosen and chosen <= self.road_ready else N_("Download missing road data"),
      "routes": N_("Removed on update") if clear else N_("Ready") if route_ready else
        N_("Not available for this region") if missing else t_("{} MiB", round(sum(p["bytes"] for p in packages) / 1024**2)),
      "note": N_("Routing coverage is not available for every selected region.") if missing else
        N_("Updates offline routes to match this selection."),
      "route_ready": route_ready,
      "road_ready": bool(chosen) and chosen <= self.road_ready,
      "available": not missing,
    }

  def status(self) -> str:
    chosen = self.chosen()
    if chosen and chosen <= self.road_ready and chosen <= self.route_ready:
      return N_("All maps ready")
    return str(self.summary()["note"]) if chosen else N_("Choose where you drive")

  def routes_size(self) -> float:
    self.tick()
    return self._routes_bytes

  def download_label(self) -> str:
    chosen = self.chosen()
    packages, missing = self._plan(self._selection())
    if self.can_clear() or chosen and chosen <= self.road_ready and chosen <= self.route_ready:
      return N_("Update maps")
    if missing and not packages:
      return N_("Download road data")
    if chosen and chosen <= self.road_ready:
      return t_("Download {} MiB", round(sum(p["bytes"] for p in packages) / 1024**2))
    return N_("Download selected maps")

  # ── The download ──

  def progress(self) -> Progress:
    """The job's progress: road data a region at a time, then offline routes in bytes, installing, and ready."""
    self.tick()
    job = self.job
    phase = job.get("phase", "")
    if phase not in jobs.ACTIVE | {"failed", "ready"} or job.get("selection") == "" and phase != "failed":
      return Progress(False, 0, 0, self.selection_summary())
    selected = sorted(catalog.tokens(job.get("selection", "")))
    current = tuple(job.get("current_regions", []))
    done, total = int(job.get("done", 0)), int(job.get("total", 0))
    common: dict[str, Any] = {"error": job.get("error", ""), "paused": bool(job.get("paused")), "current_regions": current,
                              "stage": job.get("stage", "")}
    if phase == "road":
      regions = tuple(RegionProgress(token, done if token in current else 0, total if token in current else 0,
                                     token in self.road_ready, token in self.road_ready) for token in selected)
      finished = sum(r.finished for r in regions)
      share = max(0.0, min(1.0, done / total)) if total and current else 0.0
      return Progress(True, round((finished + share) * 1000), len(regions) * 1000, self.selection_summary(), regions,
                      phase="road", unit="regions", note=N_("Maps download one region at a time."), **common)
    ready = set(job.get("regions_ready", []))
    regions = tuple(RegionProgress(t, done if t in current else 0, total if t in current else 0,
                                   t in ready or (phase == "ready" and t in self.route_ready), t in self.road_ready)
                    for t in selected)
    note = N_("All selected regions are installed together.") if phase == "install" else \
      N_("Road data and offline routes are ready.") if phase == "ready" else \
      (N_("Some map data is shared between these states.") if len(selected) > 1 else
       N_("Road data ready; offline routes downloading.")) if phase == "download" else ""
    return Progress(phase in jobs.ACTIVE, done, total, self.selection_summary(), regions, phase=phase, unit="bytes", note=note,
                    **common)

  def cancelling(self) -> bool:
    return False

  def checks(self) -> list[tuple[str, bool]]:
    return [(N_("Parked"), bool(self._parked())), (N_("Wi-Fi"), bool(self._wifi()))]

  def download(self) -> None:
    jobs.request(self._selection())
    self.refresh()

  def retry(self) -> None:
    jobs.request(str(self.job.get("selection", self._selection())))
    self.refresh()

  def cancel(self) -> None:
    jobs.cancel()
    self.refresh()

  def can_remove(self) -> bool:
    return self.downloaded() and not self.progress().active and bool(self._parked())

  def remove(self) -> None:
    if self.can_remove():
      self._remove()
      self.refresh()
