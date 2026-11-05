"""Approved routing preferences, shared map flow and existing status chips."""
import os
from pathlib import Path
import tempfile

import pyray as rl

from openpilot.selfdrive.ui.tandem.destinations import DestinationsScreen
from openpilot.selfdrive.ui.tandem.settings.maps import Maps, MapsPage, Progress, Region, RegionProgress, RegionsPage
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.tests.fakes import (FakeBluetooth, FakeBootLogos, FakeCars, FakeData, FakeMaps, FakeModels, FakePlaces,
                                                     FakeUpdates, FakeWheel, FakeWifi)
from openpilot.starpilot.tandem.routing import config as C


class SampleMaps(FakeMaps):
  def __init__(self):
    super().__init__()
    self.picked = {"us_state.IA"}
    self.missing = False
    self.ready = True
    self._regions = [
      [Region("pkg:midwest", "Midwest", "12 states"), Region("pkg:west", "West", "13 states"),
       Region("pkg:south", "South", "17 states"), Region("pkg:northeast", "Northeast", "9 states")],
      [Region("us_state." + c, n) for c, n in (("IA", "Iowa"), ("IL", "Illinois"), ("MN", "Minnesota"),
       ("MO", "Missouri"), ("NE", "Nebraska"), ("SD", "South Dakota"))],
      [Region("nation." + c, n) for c, n in (("LI", "Liechtenstein"), ("AT", "Austria"), ("FR", "France"),
       ("DE", "Germany"), ("NL", "Netherlands"), ("CH", "Switzerland"))],
    ]

  def selection_summary(self):
    return "Midwest" if "pkg:midwest" in self.picked else "Liechtenstein" if "nation.LI" in self.picked else \
      "2 regions" if len(self.picked) == 2 else "Iowa"

  def status(self):
    return "All maps ready · Updated today"

  def summary(self):
    group, country = "pkg:midwest" in self.picked, "nation.LI" in self.picked
    return {"road": "Download missing road data" if self.missing or group else "Already downloaded",
            "routes": "Not available for this region" if self.missing else
              "Size checked before download" if group else "5 MiB" if country else "280 MiB",
            "note": "Speed limits and street names can still download." if self.missing else
              "Downloads all missing map data for this selection.", "route_ready": self.ready,
            "road_ready": not self.missing and not group, "available": not self.missing}

  def download_label(self):
    return "Download road data" if self.missing else "Download selected maps" if "pkg:midwest" in self.picked else \
      "Download 5 MiB" if "nation.LI" in self.picked else "Download 280 MiB"

  def region_status(self, token):
    return ("Road data ready", "Routes not available yet" if self.missing else "Routes not downloaded") if token in self.picked else \
      ("Not downloaded", "Offline routes available")

  def routes_size(self):
    return 293140480

  def checks(self):
    return [("Parked", True), ("Wi-Fi", True)]

  def retry(self):
    pass


class StateSelectionMaps(SampleMaps):
  catalog = {"schema": 2}

  def can_clear(self):
    return not self.picked

  def selection_summary(self):
    return "Iowa" if self.picked else "None selected"

  def summary(self):
    return {"road": "Already downloaded", "routes": "Ready" if self.picked else "Removed on update",
            "note": "Updates offline routes to match this selection.", "route_ready": bool(self.picked),
            "road_ready": True, "available": True}

  def download_label(self):
    return "Update maps"

  def checks(self):
    return [("Parked", True), ("Wi-Fi", True), ("Enough storage", True)]

  def region_status(self, token):
    if token in {"us_state.IA", "us_state.IL", "us_state.MN", "us_state.NE"}:
      return "Road data ready", "Routes ready"
    return "Not downloaded", "Offline routes available"


def main(frame, save, out, tap, gui_app):
  from scene_compare import FakeCache, FakeDevice, VALUES
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow
  from openpilot.selfdrive.ui.tandem.settings.live import FakeLive
  from openpilot.selfdrive.ui.tandem.routing_status import status_text
  from openpilot.selfdrive.ui.tandem.onroad.status import Chip, ChipTone, Snapshot, chips_for, routing_chip
  from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState
  from scene_onroad import scene
  previous = {k: os.environ.get(k) for k in ("TANDEM_ROUTING", "TANDEM_PREFS_DIR", "TANDEM_ROUTING_DIR")}
  with tempfile.TemporaryDirectory() as folder:
    os.environ.update(TANDEM_ROUTING="1", TANDEM_PREFS_DIR=folder, TANDEM_ROUTING_DIR=folder)
    source = SampleMaps()
    cache = FakeCache(dict(VALUES))
    store = SettingsStore(cache, lambda: None)
    window = SettingsWindow(store=store, live=FakeLive(), model_source=FakeModels, car_catalog=FakeCars, device_data=FakeData,
      device=FakeDevice, wifi=FakeWifi, wheel=FakeWheel, bluetooth=FakeBluetooth, updates=FakeUpdates,
      maps_source=lambda: source, boot_logos=FakeBootLogos)
    window.show_event()
    rect = rl.Rectangle(0, 0, 2160, 1080)
    def shot(name, render=None, prefix="valhalla2"):
      for _ in range(5):
        frame(render or (lambda: window.render(rect)))
      save(str(Path(out) / (prefix + "-" + name + ".png")))
    for name, only, preferred in (("prefer-online", False, "online"), ("prefer-offline", False, "offline"),
                                  ("offline-only", True, "online"), ("offline-only-missing", True, "offline")):
      C.set_policy(offline_only=only, preferred=preferred)
      window.open_at(0, "speed_steering", 3)
      shot(name)
      panel = window.top.current
      last, viewport = panel._items[-1].rect, panel.rect
      panel._scroll.set_offset(min(0, viewport.y + viewport.height - last.y - last.height))
      shot(name)
    model = Maps(store, source)
    window.open_at(0)
    window.push(MapsPage(model, lambda: None, FakeData().storage, window))
    shot("maps-home")
    source.ready = False
    for name, tab in (("regions-a", 1), ("regions-groups", 0), ("regions-countries", 2), ("regions-unavailable", 1)):
      source.missing = name == "regions-unavailable"
      source.picked = {"pkg:midwest"} if tab == 0 else {"nation.LI"} if tab == 2 else {"us_state.IA"}
      pane = RegionsPage(model, lambda: None)
      pane._select(tab)
      window.push(pane)
      shot(name)
      window.pop()
    state_source = StateSelectionMaps()
    state_model = Maps(store, state_source)
    for name, picked in (("regions-update", {"us_state.IA"}), ("regions-empty", set())):
      state_source.picked = picked
      pane = RegionsPage(state_model, lambda: None)
      pane._select(1)
      window.push(pane)
      shot(name, prefix="valhalla3")
      window.pop()
    source.picked, source.missing = {"us_state.IA"}, False
    for name, phase, unit in (("download-prepare", "prepare", "bytes"), ("download-progress", "download", "bytes"),
                              ("download-road", "road", "files"), ("download-group", "download", "bytes"),
                              ("download-install", "install", "bytes"), ("download-failed", "failed", "bytes"),
                              ("download-ready", "ready", "bytes")):
      total = 50 if unit == "files" else 280 * 1024**2
      done = 21 if unit == "files" else int(total * .42)
      if phase == "prepare":
        done = total = 0
      if phase in ("install", "ready"):
        done = total
      regions = (RegionProgress("us_state.IA", done, total, phase == "ready"),)
      if name == "download-group":
        codes = ("IA", "IL", "IN", "KS", "MI", "MN", "MO", "ND", "NE", "OH", "SD", "WI")
        regions = tuple(RegionProgress("us_state." + code, 60 if i == 5 else 0, 100, i < 5) for i, code in enumerate(codes))
      source.picked = {"pkg:midwest"} if name == "download-group" else {"us_state.IA"}
      source.state = Progress(phase not in ("failed", "ready"), done, total, source.selection_summary(), regions, phase=phase, unit=unit,
        error="download_failed" if phase == "failed" else "", note="Iowa: road data ready; offline routes downloading." if phase == "download" else "")
      shot(name)
    source.state = Progress(True, 0, 0, "Iowa", (RegionProgress("us_state.IA", 0, 0, False),),
                            phase="install", unit="bytes", current_regions=("us_state.IA",))
    shot("local-rebuild", prefix="valhalla3")
    source.picked = {"us_state.IA", "us_state.IL"}
    for name, phase, stage, pct in (("queued", "download", "", 0), ("download", "download", "", 42),
                                   ("install", "install", "build", 38), ("check", "install", "check", 94),
                                   ("ready", "ready", "", 100)):
      total = 345 * 1024**2
      region_counts = (64, 35) if name == "download" else (pct, pct)
      regions = tuple(RegionProgress(token, count, 100, phase == "ready")
                      for token, count in zip(sorted(source.picked), region_counts, strict=True))
      note = "Some map data is shared between these states." if phase == "download" else \
        "All selected regions are installed together." if phase == "install" else "Road data and offline routes are ready."
      source.state = Progress(phase != "ready", round(total * pct / 100), total, "2 regions", regions, phase=phase, unit="bytes",
                              note=note, current_regions=tuple(sorted(source.picked)), stage=stage)
      shot("shared-" + name, prefix="valhalla4")
    for name, counts, current in (("queued", (0, 0), "us_state.IA"), ("iowa", (260, 0), "us_state.IA"),
                                  ("illinois", (1000, 180), "us_state.IL"), ("ready", (1000, 1000), None)):
      ready = name == "ready"
      regions = tuple(RegionProgress(token, count, 1000, ready, count == 1000)
                      for token, count in zip(sorted(source.picked), counts, strict=True))
      source.state = Progress(not ready, sum(counts), 2000, "2 regions", regions,
                              phase="ready" if ready else "download", unit="regions", paired=True,
                              current_regions=(current,) if current else (),
                              note="All selected regions are ready." if ready else "Maps download one region at a time.")
      shot("paired-" + name, prefix="valhalla5")
    source.state = Progress(False, 0, 0, "")
    window.dismiss()
    from openpilot.selfdrive.ui.tandem.settings.device_sections import confirm, DELETE_MAPS_MESSAGE
    confirm(window, "Remove offline maps?", DELETE_MAPS_MESSAGE, "Remove", lambda: None)
    shot("remove-region")
    window.dismiss()
    for name, code, first, strict in (("chip-recalculate", "rerouting", False, False),
      ("chip-first-route", "routing", True, False), ("chip-gps", "gps_waiting", False, False),
      ("chip-offline-fallback", "ready", False, False), ("chip-online-fallback", "ready", False, False),
      ("chip-strict-unavailable", "data_missing", True, True), ("chip-stack", "rerouting", False, False)):
      chip = routing_chip({"status": code, "active": not first, "provider": "online" if name == "chip-online-fallback" else "offline",
                           "fallback_at": 100}, 101, strict)
      chips = [(chip, 1)] if chip else []
      if name == "chip-stack":
        chips.append((Chip("signal", "Steering paused for signal", ChipTone.PAUSED, "signal"), 1))
      state = BarState(False, True, 48, "mph", "Market Street", True, "" if first else "5:18 PM", "" if first else "12 min · 8.4 mi")
      shot(name, scene(state, ArcState(), chips, speed=44, limit="45",
        turn=("0.4 mi", "Turn right onto Market St", "turn", "right") if code == "ready" else None))
    # Both approved chips together after merging release: RAM is lowest priority.
    reason = routing_chip({"status": "rerouting", "active": True}, 101)
    chips = [(chip, 1) for chip in chips_for(Snapshot(routing=reason, low_ram=True, memory_percent=91))]
    shot("chip-ram", scene(state, ArcState(), chips, speed=44, limit="45"))
    places = FakePlaces()
    screen = DestinationsScreen(places, lambda: None, lambda: None)
    shot("places", lambda: screen.render(rect))
    places.route = lambda: (None, status_text("data_missing"))
    places.can_start = lambda: False
    C.set_policy(offline_only=True)
    screen = DestinationsScreen(places, lambda: None, lambda: None)
    screen._pick(places.recents()[0])
    shot("preview-strict-missing", lambda: screen.render(rect))
  for key, value in previous.items():
    if value is None:
      os.environ.pop(key, None)
    else:
      os.environ[key] = value
