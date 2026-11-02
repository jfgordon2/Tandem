"""Offline Maps: what's downloaded, keeping it up to date, choosing regions, and download progress.

The region catalog, selection rules and download requests are StarPilot's (its maps screen controller and the
DownloadMaps / CancelDownloadMaps signals), so mapd sees exactly what it would from StarPilot's own screen.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Grid, IconTitle, Label, Stack, Surface
from openpilot.selfdrive.ui.tandem.chrome import PageHeader, Sidebar, SidebarItem
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ProgressBar, Segmented
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.device_sections import DELETE_MAPS_MESSAGE, StorageBar, confirm
from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding
from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage, body_rect
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate

SCHEDULES = [N_("Off"), N_("Weekly"), N_("Monthly")]   # PreferredSchedule 0, 1, 2


@dataclass(frozen=True)
class Region:
  token: str
  name: str
  detail: str = ""


@dataclass(frozen=True)
class RegionProgress:
  location: str        # mapd's name for it, e.g. "us_state.ID" or "nation.DE"
  done: int
  total: int

  @property
  def code(self) -> str:
    """The short name a tile shows: the state's or country's code ("ID", "DE"), otherwise the name."""
    for prefix in ("us_state.", "nation.", "US_"):   # mapd's selection keys (starpilot/common/maps_selection.py), and older ones
      if self.location.startswith(prefix):
        return self.location[len(prefix):]
    return self.location.replace("_", " ")

  @property
  def finished(self) -> bool:
    return self.total > 0 and self.done >= self.total


def region_tiles(details) -> tuple[RegionProgress, ...]:
  """mapd's per-location (name, files done, files total), sorted by the name a tile shows: mapd lists them in no fixed
  order, so unsorted tiles would trade places as updates arrive."""
  return tuple(sorted((RegionProgress(*d) for d in details), key=lambda r: r.code))


@dataclass(frozen=True)
class Progress:
  active: bool
  done: int
  total: int
  location: str
  regions: tuple[RegionProgress, ...] = ()

  @property
  def fraction(self) -> float:
    return self.done / self.total if self.total else 0.0

  @property
  def step(self) -> int:
    """The mock's steps: 0 Prepare (no file count yet), 1 Download, 2 Install (every file in, still finishing), 3 Ready."""
    if not self.active:
      return 3
    if not self.total:
      return 0
    return 1 if self.done < self.total else 2

  @property
  def current(self) -> RegionProgress | None:
    return next((r for r in self.regions if not r.finished), None)


class MapsSource(Protocol):
  def tick(self) -> None: ...
  def refresh(self) -> None: ...
  def regions(self, tab: int) -> list[Region]: ...     # 0 U.S. regions, 1 U.S. states, 2 other countries
  def selected(self, token: str) -> bool: ...
  def set_selected(self, token: str, on: bool) -> None: ...
  def selection_summary(self) -> str: ...
  def has_selection(self) -> bool: ...
  def downloaded(self) -> bool: ...
  def progress(self) -> Progress: ...
  def cancelling(self) -> bool: ...
  def checks(self) -> list[tuple[str, bool]]: ...      # e.g. ("Parked", True)
  def download(self) -> None: ...
  def cancel(self) -> None: ...
  def remove(self) -> None: ...


class Maps:
  def __init__(self, store: SettingsStore, source: MapsSource):
    self._store = store
    self.source = source

  @property
  def schedule(self) -> int:
    return max(0, min(2, self._store.get_int("PreferredSchedule")))

  def set_schedule(self, index: int) -> None:
    self._store.write({"PreferredSchedule": index})

  def ready(self) -> bool:
    return self.source.has_selection() and all(ok for _, ok in self.source.checks()) and not self.source.progress().active

  def blocked_reason(self) -> str:
    if not self.source.has_selection():
      return N_("Choose at least one region")
    return next((t_("Waiting: {}", name.lower()) for name, ok in self.source.checks() if not ok), "")

  def status(self) -> str:
    progress = self.source.progress()
    if self.source.cancelling():
      return N_("Cancelling…")
    if progress.active:
      return t_("Downloading {} · {}%", progress.location or 'maps', round(progress.fraction * 100))
    return N_("Downloaded") if self.source.downloaded() else N_("Not downloaded yet")

  def summary(self) -> str:
    return f"{self.source.selection_summary()} · {self.status().lower()}"


class ProgressCard(Component):
  """Percent and files while a download runs; hidden otherwise."""
  grow_touch_target = False

  def __init__(self, maps: Maps, padding: float = T.PANEL_HEADER_INSET):
    super().__init__()
    self._maps = maps
    self._padding = padding
    self._bar = self._child(ProgressBar(lambda: maps.source.progress().fraction))
    self._cancel = self._child(Button(N_("Cancel download"), maps.source.cancel, ButtonStyle.DANGER_SOFT))
    self.set_visible(lambda: maps.source.progress().active)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(120)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._cancel.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle):
    progress = self._maps.source.progress()
    body = inset(rect, x=self._padding, y=T.px(14))
    top, bar, note = column(body, [T.BUTTON_HEIGHT, T.px(10), FILL], T.px(12))
    text, cancel = row(top, [FILL, self._cancel.preferred_size(top.width)[0]], T.px(12))
    draw.text(text, f"{round(progress.fraction * 100)}%", T.font_px(30), T.TEXT, T.FONT_EXTRABOLD)
    self._cancel.render(cancel)
    self._bar.render(bar)
    draw.text(note, t_("{} of {} files · {}. Pauses if you drive or lose the connection.", progress.done, progress.total, progress.location),
              T.SIZE_SUBTITLE, T.TEXT_TERTIARY)


def maps_page(maps: Maps, open_regions: Callable[[], None], sizes: Callable[[], dict[str, float]], window) -> Widget:
  """Your regions on the left, with the download; keeping up to date and storage on the right."""
  def parked() -> bool:
    return dict(maps.source.checks()).get("Parked", False)

  def label() -> str:
    if not maps.ready():
      return maps.blocked_reason() or N_("Download")
    return N_("Update now") if maps.source.downloaded() else N_("Download")

  download = Button(label, maps.source.download, ButtonStyle.PRIMARY, height=T.px(58))
  download.set_enabled(maps.ready)
  download.set_visible(lambda: not maps.source.progress().active)
  remove = Button(lambda: N_("Park to remove maps") if not parked() else N_("Remove maps"),
                  lambda: confirm(window, N_("Remove offline maps?"), DELETE_MAPS_MESSAGE, N_("Remove"), maps.source.remove),
                  ButtonStyle.DANGER_SOFT, height=T.px(48))
  remove.set_enabled(lambda: maps.source.downloaded() and not maps.source.progress().active and parked())
  downloaded = lambda: maps.status() == "Downloaded"  # noqa: E731
  regions = Card([
    Label(N_("YOUR REGIONS"), color=T.ACCENT_TEXT, caption=True),
    IconTitle("map", maps.source.selection_summary, N_("Change them in Choose regions")),
    Label(maps.status, T.font_px(15), lambda: T.SUCCESS_TEXT if downloaded() else T.TEXT_TERTIARY, T.FONT,
          icon=lambda: "check" if downloaded() else None),
    ProgressCard(maps, padding=0),
    SPACER,
    download,
    Surface(SettingRow(N_("Choose regions"), N_("Add or remove states, regions and countries"), on_click=open_regions),
            T.SURFACE_4, T.px(14)),
  ], gap=T.px(14))
  schedule = Card([
    Label(N_("Keep up to date"), T.font_px(18)),
    Segmented(SCHEDULES, lambda: maps.schedule, maps.set_schedule, height=T.px(52), font_size=T.font_px(16), equal=True),
    Label(N_("Updates download only while parked and online"), T.SIZE_SUBTITLE, T.TEXT_MUTED, T.FONT),
  ], padding=(T.px(20), T.px(18)))
  storage = Card([
    StorageBar(sizes, heading=N_("Storage"), padding=(0, 0)),
    Label(N_("Without maps, speed limits need a connection."), T.SIZE_SUBTITLE, T.TEXT_MUTED, T.FONT),
    SPACER,
    remove,
  ], padding=(T.px(20), T.px(18)), gap=T.px(10))
  return TitledPage(N_("Offline Maps"), N_("Speed limits and curves work without a connection"),
                    Columns([regions, Stack([schedule, storage], gap=T.px(14), grow=1)], [1.25, 1]))


class RegionCard(Component):
  """A region to tap on or off; chosen regions have the accent fill and outline."""

  def __init__(self, region: Region, maps: Maps):
    super().__init__()
    self._region = region
    self._maps = maps
    self.set_click_callback(lambda: maps.source.set_selected(region.token, not self.chosen))

  @property
  def chosen(self) -> bool:
    return self._maps.source.selected(self._region.token)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(96)

  def _render(self, rect: rl.Rectangle):
    chosen = self.chosen
    draw.fill(rect, T.ACCENT_SELECTED if chosen else T.SURFACE_3, T.px(16))
    if chosen:
      draw.stroke(rect, T.ACCENT, T.px(16), T.px(2))
    elif self.is_pressed:
      draw.pressed(rect, T.px(16))
    body = inset(rect, x=T.px(16), y=T.px(12))
    if not self._region.detail:
      draw.text(body, self._region.name, T.font_px(17), T.TEXT, T.FONT_BOLD)
      return
    lines = [draw.line_height(T.font_px(17)), draw.line_height(T.SIZE_CAPTION)]
    title, line = column(place(body, body.width, sum(lines) + T.px(4)), lines, T.px(4))
    draw.text(title, self._region.name, T.font_px(17), T.TEXT, T.FONT_BOLD)
    draw.text(line, self._region.detail, T.SIZE_CAPTION, T.TEXT_TERTIARY)


class RegionsPage(Component):
  """Region kinds on the left, the regions as cards in the middle, and the selection with its download on the right."""
  grow_touch_target = False
  TABS = [N_("U.S. regions"), N_("U.S. states"), N_("Other countries")]

  def __init__(self, maps: Maps, on_download: Callable[[], None]):
    super().__init__()
    self._maps = maps
    self._tab = 0
    self._header = self._child(PageHeader(N_("Add map regions"), N_("Pick a region, or switch to states for less storage")))
    self._tabs = self._child(Sidebar(N_("REGIONS"), [SidebarItem(t, on_select=lambda i=i: self._select(i)) for i, t in enumerate(self.TABS)],
                                     selected=lambda: self._tab, width=T.px(220)))

    def build() -> ListPanel:
      cards = [RegionCard(r, maps) for r in maps.source.regions(self._tab)]
      return ListPanel([Grid(cards, columns=2 if self._tab == 0 else 3)] if cards else [Text(N_("No regions available."))],
                       background=T.BG, dividers=False)

    self._list = self._child(Rebuilding(lambda: self._tab, build, maps.source.tick))
    download = Button(N_("Download"), on_download, ButtonStyle.PRIMARY, height=T.px(60))
    download.set_enabled(maps.ready)

    def check(name: str) -> Label:
      ok = lambda: bool(dict(maps.source.checks()).get(name))  # noqa: E731
      return Label(lambda: name if ok() else t_("{}: not yet", name), T.font_px(15), lambda: T.TEXT_SECONDARY if ok() else T.WARNING, T.FONT,
                   icon=lambda: "check" if ok() else "warning", icon_color=lambda: T.SUCCESS_TEXT if ok() else T.WARNING)

    self._side = self._child(Card([
      Label(N_("SELECTED"), color=T.ACCENT_TEXT, caption=True),
      Text(maps.source.selection_summary, T.font_px(22), T.TEXT, T.FONT_EXTRABOLD, padding=(0, 0)),
      Stack([check(name) for name, _ in maps.source.checks()], gap=T.px(8)),
      SPACER,
      download,
    ], padding=(T.px(18), T.px(18))))

  def _select(self, index: int) -> None:
    self._tab = index

  def _render(self, rect: rl.Rectangle):
    body = inset(body_rect(rect), top=T.px(2))
    header, content = column(body, [self._header.preferred_height(body.width), FILL], T.px(14))
    self._header.render(header)
    tabs, grid, side = row(content, [T.px(220), FILL, T.px(330)], T.px(14))
    self._tabs.render(inset(tabs, top=-T.px(8)))
    self._list.render(grid)
    self._side.render(side)


class UpstreamMaps:
  """MapsSource backed by StarPilot's maps screen controller."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.starpilot import maps as m
    self._m = m
    self._layout = m.StarPilotMapsLayout()

  def tick(self) -> None:
    self._layout._update_state()

  def refresh(self) -> None:
    self._layout.show_event()

  def regions(self, tab: int) -> list[Region]:
    m = self._m
    if tab == 0:
      packages = [Region(token, m.tr(spec["title"]), m.tr(spec["subtitle"])) for token, spec in m.REGIONAL_PACKAGES.items()]
      return [Region(m.US_COUNTRY_TOKEN, N_("Whole U.S."), N_("Every state and territory")), *packages]
    regions = self._layout._all_us_states_regions() if tab == 1 else self._layout._all_country_regions()
    return [Region(r["token"], m.tr(r["label"])) for r in regions]

  def selected(self, token: str) -> bool:
    return self._layout._get_map_state(token)

  def set_selected(self, token: str, on: bool) -> None:
    self._layout._set_map_state(token, on)

  def selection_summary(self) -> str:
    return self._layout._selected_summary_text()

  def has_selection(self) -> bool:
    return self._layout._selected_count() > 0

  def downloaded(self) -> bool:
    return self._layout._has_downloaded_data

  def progress(self) -> Progress:
    state = self._layout._download_state
    regions: tuple[RegionProgress, ...] = ()
    sm = self._layout._map_sm
    if sm.valid.get("mapdExtendedOut", False):   # mapd's per-location counts, already received by the layout's own update
      regions = region_tiles((str(d.location), int(d.downloadedFiles), int(d.totalFiles))
                             for d in sm["mapdExtendedOut"].downloadProgress.locationDetails)
    return Progress(state.active or self._layout._download_requested(), state.downloaded_files, state.total_files, state.primary_location,
                    regions)

  def cancelling(self) -> bool:
    return self._layout._is_visually_cancelling()

  def checks(self) -> list[tuple[str, bool]]:
    return [(N_("Parked"), self._layout._is_parked()), (N_("Online"), self._layout._is_online())]

  def download(self) -> None:
    self._layout._params_memory.remove("CancelDownloadMaps")
    self._layout._params_memory.put_bool("DownloadMaps", True)

  def cancel(self) -> None:
    self._layout._params_memory.put_bool("CancelDownloadMaps", True)
    self._layout._params_memory.remove("DownloadMaps")

  def remove(self) -> None:
    def done():
      self._layout._storage_updated_at = 0.0   # re-read what's downloaded, as upstream does after removing
    remove_offline_maps(done)


_memory_params = None


def removal_blocked() -> str:
  """Why offline maps can't be deleted now, or "": StarPilot's rule is parked, and not while a download runs."""
  global _memory_params
  from openpilot.selfdrive.ui.ui_state import ui_state
  sm = ui_state.sm
  parked = ui_state.is_offroad() or (sm.valid.get("starpilotCarState", False) and bool(sm["starpilotCarState"].isParked))
  if not parked:
    return N_("Park to delete offline maps")
  if _memory_params is None:
    from openpilot.common.params import Params
    _memory_params = Params(memory=True)
  if _memory_params.get_bool("DownloadMaps"):
    return N_("Wait for the download to finish")
  return ""


def remove_offline_maps(on_done: Callable[[], None] | None = None) -> None:
  """Deletes downloaded map data in the background, as StarPilot's Remove Maps does; the chosen regions are kept."""
  if removal_blocked():
    return
  import shutil
  import threading
  from openpilot.common.params import Params
  from openpilot.selfdrive.ui.tandem.settings.device_sections import STORAGE
  from openpilot.starpilot.common.maps_download_progress import MAPS_STORAGE_CACHE_PARAM, load_maps_storage_cache
  from openpilot.starpilot.common.starpilot_variables import MAPS_PATH

  def worker():
    if MAPS_PATH.exists():
      shutil.rmtree(MAPS_PATH, ignore_errors=True)
      MAPS_PATH.mkdir(parents=True, exist_ok=True)
    params = Params()
    cache = load_maps_storage_cache(params.get(MAPS_STORAGE_CACHE_PARAM, encoding="utf-8") or "")
    cache.clear()
    params.put(MAPS_STORAGE_CACHE_PARAM, cache.to_json())
    STORAGE.forget()
    if on_done is not None:
      on_done()
  threading.Thread(target=worker, daemon=True).start()


STEPS = [N_("Prepare"), N_("Download"), N_("Install"), N_("Ready")]
DOWNLOAD_NOTE = N_("Pauses if you start driving or lose Wi-Fi, and picks up where it stopped. Keep the device powered.")


def tile_window(count: int, current: int | None, capacity: int) -> tuple[int, int, int]:
  """(start, end, more) when count tiles may not fit in capacity: a run that keeps the current one in view, and how many
  are left out (drawn as one "+N more" tile)."""
  if count <= capacity:
    return 0, count, 0
  shown = capacity - 1
  start = 0 if current is None else max(0, min(current - shown // 2, count - shown))
  return start, start + shown, count - shown


def minutes_left(started: tuple[float, int] | None, now: float, done: int, total: int) -> int | None:
  """Minutes to go at the rate since started (time, files done then), once there's a rate to go by."""
  if started is None or total <= 0 or done >= total:
    return None
  t0, d0 = started
  if done <= d0 or now - t0 < 5.0:
    return None
  rate = (done - d0) / (now - t0)
  return max(1, round((total - done) / rate / 60))


class DownloadView(Component):
  """A download in progress (design/mapdownloading.html): percent and steps, then each region as a tile, done, current or
  waiting. Shown in place of the Offline Maps page while it runs."""
  grow_touch_target = False
  COLUMNS = 7

  def __init__(self, maps: Maps):
    super().__init__()
    self._maps = maps
    self._cancel = self._child(Button(N_("Cancel download"), maps.source.cancel, ButtonStyle.DANGER_SOFT, height=T.px(52)))
    self._bar = self._child(ProgressBar(lambda: maps.source.progress().fraction))
    self._started: tuple[float, int] | None = None

  def _update_state(self):
    progress = self._maps.source.progress()
    if progress.active and progress.total and self._started is None:
      self._started = (rl.get_time(), progress.done)
    elif not progress.active:
      self._started = None

  def _render(self, rect: rl.Rectangle):
    from openpilot.selfdrive.ui.tandem.settings.pages import body_rect
    progress = self._maps.source.progress()
    body = body_rect(rect)
    header, top, grid = column(body, [T.px(60), T.px(136), FILL], T.px(12))
    # Header: title and line, Cancel at the right
    w, _ = self._cancel.preferred_size(header.width)
    words, cancel = row(header, [FILL, w], T.px(14))
    self._cancel.render(place(cancel, w, T.px(52)))
    title, line = column(place(words, words.width, T.px(60)), [T.px(34), FILL], T.px(2))
    what = self._maps.source.selection_summary().removesuffix(" selected")   # "13 regions", "Whole U.S. (56 states)"
    draw.text(title, t_("Downloading {}", what), T.font_px(26), T.TEXT, T.FONT_EXTRABOLD)
    draw.text(line, N_("You can leave this screen. It keeps going in the background."), T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
    # Percent, bar and steps
    draw.fill(top, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(top, x=T.px(22), y=T.px(16))
    figure, bar, steps = column(inner, [T.px(50), T.px(12), FILL], T.px(10))
    pct = f"{round(progress.fraction * 100)}%"
    pw = draw.text(figure, pct, T.font_px(44), T.TEXT, T.FONT_EXTRABOLD)
    left = minutes_left(self._started, rl.get_time(), progress.done, progress.total)
    detail = t_("{} of {} files", progress.done, progress.total) if progress.total else N_("Getting ready")
    if left is not None:
      detail += t_(" · about {} min left", left)
    draw.text(inset(figure, left=pw + T.px(16)), detail, T.font_px(17), T.TEXT_SECONDARY)
    self._bar.render(bar)
    for i, (name, cell) in enumerate(zip(STEPS, row(steps, [FILL] * len(STEPS), T.px(12)), strict=True)):
      done, now = i < progress.step, i == progress.step
      ink = T.SUCCESS_TEXT if done else (T.TEXT if now else T.TEXT_MUTED)
      mark = rl.Rectangle(cell.x, cell.y, T.px(18), cell.height)
      if done:
        draw.icon(mark, "check", T.SUCCESS_TEXT, T.px(16))
      elif now:
        rl.draw_circle_v(rl.Vector2(mark.x + T.px(7), mark.y + mark.height / 2), T.px(5), T.ACCENT)
      else:
        rl.draw_circle_lines_v(rl.Vector2(mark.x + T.px(7), mark.y + mark.height / 2), T.px(5), T.TEXT_MUTED)
      draw.text(inset(cell, left=T.px(26)), f"{i + 1} {translate(name)}", T.font_px(16), ink, T.FONT_SEMIBOLD if now or done else T.FONT)
    # Regions
    draw.fill(grid, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(grid, x=T.px(22), y=T.px(14))
    regions = progress.regions
    finished = sum(r.finished for r in regions)
    caption, tiles, note = column(inner, [draw.line_height(T.SIZE_CAPTION), FILL, draw.line_height(T.SIZE_SUBTITLE)], T.px(12))
    draw.caption(caption, t_("REGIONS · {} OF {} DONE", finished, len(regions)) if regions else N_("REGIONS"))
    current = progress.current
    tile_w = (tiles.width - T.px(10) * (self.COLUMNS - 1)) / self.COLUMNS
    rows = max(1, int((tiles.height + T.px(8)) // T.px(56)))
    start, end, more = tile_window(len(regions), regions.index(current) if current is not None else None, rows * self.COLUMNS)
    cell = lambda i: rl.Rectangle(tiles.x + (i % self.COLUMNS) * (tile_w + T.px(10)), tiles.y + (i // self.COLUMNS) * T.px(56),  # noqa: E731
                                  tile_w, T.px(48))
    if more:
      tile = cell(end - start)
      draw.fill(tile, T.SURFACE_4, T.px(12))
      draw.text(tile, t_("+{} more", more), T.font_px(15), T.TEXT_TERTIARY, T.FONT_SEMIBOLD, Align.CENTER)
    for i, region in enumerate(regions[start:end]):
      tile = cell(i)
      is_current = region is current
      if region.finished:
        draw.fill(tile, T.SUCCESS_SURFACE, T.px(12))
        label, ink = region.code, T.SUCCESS_CHIP_TEXT
      elif is_current:
        draw.fill(tile, T.ACCENT_SELECTED, T.px(12))
        draw.stroke(tile, T.ACCENT, T.px(12), T.px(2))
        label, ink = region.code, T.TEXT
      else:
        draw.fill(tile, T.SURFACE_4, T.px(12))
        label, ink = region.code, T.TEXT_TERTIARY
      extra = ""
      if is_current and region.total:
        extra = f"{round(region.done * 100 / region.total)}%"
      lw = draw.text_width(label, T.font_px(17), T.FONT_BOLD)
      ew = draw.text_width(extra, T.font_px(13), T.FONT_BOLD) + T.px(8) if extra else 0
      cw = T.px(22) if region.finished else 0
      x = tile.x + (tile.width - (cw + lw + ew)) / 2
      if region.finished:
        draw.icon(rl.Rectangle(x, tile.y, T.px(16), tile.height), "check", T.SUCCESS_TEXT, T.px(16))
      draw.text(rl.Rectangle(x + cw, tile.y, lw, tile.height), label, T.font_px(17), ink, T.FONT_BOLD)
      if extra:
        draw.text(rl.Rectangle(x + cw + lw + T.px(8), tile.y, ew, tile.height), extra, T.font_px(13), T.ACCENT_TEXT, T.FONT_BOLD)
    draw.icon(rl.Rectangle(note.x, note.y, T.px(18), note.height), "info", T.ACCENT_TEXT, T.px(18))
    draw.text(inset(note, left=T.px(28)), DOWNLOAD_NOTE, T.SIZE_SUBTITLE, T.TEXT_SECONDARY)


class MapsPage(Component):
  """The Offline Maps panel; tracks the download while open, showing the download view in its place while one runs."""
  grow_touch_target = False

  def __init__(self, maps: Maps, open_regions: Callable[[], None], sizes: Callable[[], dict[str, float]], window):
    super().__init__()
    self._maps = maps
    self._page = self._child(maps_page(maps, open_regions, sizes, window))
    self._download = self._child(DownloadView(maps))

  def show_event(self):
    self._maps.source.refresh()
    super().show_event()

  def _update_state(self):
    self._maps.source.tick()

  def _render(self, rect: rl.Rectangle):
    (self._download if self._maps.source.progress().active else self._page).render(rect)
