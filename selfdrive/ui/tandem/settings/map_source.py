"""Combine StarPilot's mapd controller with Tandem routing-data jobs."""
from __future__ import annotations

from dataclasses import replace
import time

from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.starpilot.tandem.routing import bundles, catalog, maps as jobs


class CombinedMaps:
  def __init__(self, road):
    self.road = road
    self._updated = -1.0
    self.job, self.road_ready, self.route_ready = {}, set(), set()
    self.catalog = catalog.load()

  def __getattr__(self, name):
    return getattr(self.road, name)

  def selection(self):
    return self.road._layout._params.get("MapsSelected", encoding="utf-8") or ""

  def selection_summary(self):
    from openpilot.starpilot.common.maps_catalog import MAP_TOKEN_LABELS
    selected = catalog.tokens(self.selection())
    if len(selected) == 1:
      return next(MAP_TOKEN_LABELS.get(t, t) for t in selected)
    return self.road.selection_summary()

  def tick(self):
    self.road.tick()
    if time.monotonic() - self._updated < .5:
      return
    self._updated = time.monotonic()
    self.job = jobs.read()
    self.catalog = catalog.load()
    self.route_ready = catalog.ready_regions()
    from openpilot.starpilot.common.maps_download_progress import load_maps_storage_cache
    cache = load_maps_storage_cache(self.road._layout._params.get("MapsDownloadSizeCache", encoding="utf-8") or "")
    # Upstream has per-selection storage receipts, not per-region tile ownership.
    self.road_ready = set()
    for key in cache._selections:
      if cache.selection_total_files(key) > 0 and cache.selection_updated_at(key):
        self.road_ready.update(catalog.tokens(key))

  def refresh(self):
    self._updated = -1
    self.road.refresh()
    self.tick()

  def expand(self, token):
    spec = self.road._m.REGIONAL_PACKAGES.get(token)
    return set(spec["tokens"]) if spec else catalog.tokens(token)

  def regions(self, tab):
    names = {"pkg:midwest": N_("Midwest"), "pkg:west": N_("West"), "pkg:south": N_("South"), "pkg:northeast": N_("Northeast")}
    return [replace(region, name=names.get(region.token, region.name)) for region in self.road.regions(tab)]

  def region_status(self, token):
    selected = self.expand(token)
    ready = bool(selected) and selected <= self.route_ready
    packages, missing = catalog.plan(",".join(selected), self.catalog)
    return (N_("Road data ready") if selected <= self.road_ready else N_("Not downloaded"),
            N_("Routes ready") if ready else N_("Routes not downloaded") if packages and not missing else N_("Routes not available yet"))

  def summary(self):
    selected = catalog.tokens(self.selection())
    packages, missing = catalog.plan(self.selection(), self.catalog)
    return {
      "road": N_("Already downloaded") if selected and selected <= self.road_ready else N_("Download missing road data"),
      "routes": N_("Ready") if selected and selected <= self.route_ready else
        N_("Not available for this region") if missing else
        t_("{} MiB", round(sum(p["bytes"] for p in packages) / 1024**2)),
      "note": N_("Routing coverage is not available for every selected region.") if missing else
        N_("Downloads all missing map data for this selection."),
      "route_ready": bool(selected) and selected <= self.route_ready,
      "road_ready": bool(selected) and selected <= self.road_ready,
      "available": not missing,
    }

  def downloaded(self):
    return self.road.downloaded() or bool(self.route_ready)

  def status(self):
    selected = catalog.tokens(self.selection())
    if selected and selected <= self.road_ready and selected <= self.route_ready:
      return N_("All maps ready")
    return self.summary()["note"] if selected else N_("Choose where you drive")

  def progress(self):
    from openpilot.selfdrive.ui.tandem.settings.maps import Progress, RegionProgress
    road = self.road.progress()
    job = self.job
    if job.get("phase") == "cancelled":
      return replace(road, phase="road" if road.active else "", unit="files")
    if road.active or job.get("phase") == "road":
      completed = set(job.get("regions_ready", []))
      regions = tuple(replace(r, ready=r.finished and r.location in completed) for r in road.regions)
      return replace(road, active=road.active or job.get("phase") == "road", regions=regions, phase="road", unit="files")
    if job.get("phase") not in jobs.ACTIVE | {"failed", "ready"}:
      return road
    selected = catalog.tokens(job.get("selection", ""))
    done, total = job.get("done", 0), job.get("total", 0)
    phase = job["phase"]
    current = set(job.get("current_regions", []))
    ready = set(job.get("regions_ready", []))
    regions = tuple(RegionProgress(t, done if t in current else 0, total if t in current else 0,
                                   t in ready or (phase == "ready" and t in self.route_ready)) for t in sorted(selected))
    return Progress(phase in jobs.ACTIVE, done, total, self.selection_summary(), regions,
                    phase=phase, unit="bytes", error=job.get("error", ""), paused=job.get("paused", False),
                    note=N_("Road data ready; offline routes downloading.") if phase == "download" else "",
                    current_regions=tuple(current))

  def download(self):
    selected = catalog.tokens(self.selection())
    if selected and selected <= self.road_ready and not selected <= self.route_ready:
      jobs.request(self.selection())  # add routing without redownloading road data
    else:
      self.road.download()  # existing scheduler hook starts the shared job
    self._updated = -1

  def retry(self):
    jobs.request(self.job.get("selection", self.selection()), wait_for_road=not self.job.get("road_ready", False))
    if not self.job.get("road_ready", False):
      self.road.download()
    self._updated = -1

  def cancel(self):
    jobs.cancel()
    if self.road.progress().active:
      self.road.cancel()

  def checks(self):
    from openpilot.selfdrive.ui.ui_state import ui_state
    from cereal import log
    wifi = ui_state.sm.valid.get("deviceState", False) and ui_state.sm["deviceState"].networkType == log.DeviceState.NetworkType.wifi
    return [(name, value) for name, value in self.road.checks() if name != "Online"] + [(N_("Wi-Fi"), bool(wifi))]

  def routes_size(self):
    return sum(r["bytes"] for b in bundles.installed() for r in b.manifest["files"].values())

  def download_label(self):
    selected = catalog.tokens(self.selection())
    packages, missing = catalog.plan(self.selection(), self.catalog)
    if missing and not packages:
      return N_("Download road data")
    if selected and selected <= self.road_ready and selected <= self.route_ready:
      return N_("Update maps")
    if selected and selected <= self.road_ready:
      return t_("Download {} MiB", round(sum(p["bytes"] for p in packages) / 1024**2))
    return N_("Download selected maps")
