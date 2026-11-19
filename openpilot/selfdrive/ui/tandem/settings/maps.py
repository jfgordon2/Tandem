"""Offline Maps (design/valhalla2-maps-home.html): what's downloaded, choosing regions, and download progress.

One map job downloads both map sets for the chosen states: road data from StarPilot 7's map owner, then Tandem's
offline routes (starpilot/tandem/routing/maps.py). settings/map_source.py is the real source. StarPilot 7 has no
scheduled map refresh, so release's Keep up to date card is left out (README, where the code differs from the mocks).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Protocol
from collections.abc import Iterable

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Grid, IconTitle, Label, Stack, Surface
from openpilot.selfdrive.ui.tandem.chrome import PageHeader, Sidebar, SidebarItem
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonRow, ButtonStyle, ProgressBar
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.pages import Rebuilding, TitledPage, body_rect
from openpilot.selfdrive.ui.tandem.settings.storage import StorageBar
from openpilot.selfdrive.ui.tandem.settings.window import confirm
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

DELETE_MAPS_MESSAGE = N_("Remove all downloaded maps from this device. Your regions stay chosen.")   # as Storage & Data


@dataclass(frozen=True)
class Region:
  """A region the maps page offers: its token (e.g. us_state.IA), name and detail."""
  token: str
  name: str
  detail: str = ""


@dataclass(frozen=True)
class RegionProgress:
  """One region's download progress."""
  location: str        # mapd's name for it, e.g. "us_state.ID" or "nation.DE"
  done: int
  total: int
  ready: bool | None = None
  downloaded: bool = False

  @property
  def fraction(self) -> float:
    return max(0.0, min(1.0, self.done / self.total if self.total else float(self.downloaded)))

  @property
  def code(self) -> str:
    """The short name a tile shows: the state's or country's code ("ID", "DE"), otherwise the name."""
    for prefix in ("us_state.", "nation.", "US_"):   # mapd's selection keys (starpilot/common/maps_selection.py), and older ones
      if self.location.startswith(prefix):
        return self.location[len(prefix):]
    return self.location.replace("_", " ")

  @property
  def finished(self) -> bool:
    return self.ready if self.ready is not None else self.total > 0 and self.done >= self.total


def region_tiles(details: Iterable[tuple[str, int, int]]) -> tuple[RegionProgress, ...]:
  """mapd's per-location (name, files done, files total), sorted by the name a tile shows: mapd lists them in no fixed
  order, so unsorted tiles would trade places as updates arrive."""
  return tuple(sorted((RegionProgress(*d) for d in details), key=lambda r: r.code))


@dataclass(frozen=True)
class Progress:
  """A maps download's progress: overall, per region, and its phase."""
  active: bool
  done: int
  total: int
  location: str
  regions: tuple[RegionProgress, ...] = ()
  phase: str = ""
  unit: str = "files"
  error: str = ""
  paused: bool = False
  note: str = ""
  current_regions: tuple[str, ...] = ()
  stage: str = ""
  paired: bool = False

  @property
  def fraction(self) -> float:
    if self.phase == "ready":
      return 1.0
    value = max(0.0, self.done / self.total if self.total else 0.0)
    return min(.99 if self.phase == "install" else 1.0, value)

  def step_complete(self, index: int) -> bool:
    return index < self.step or self.phase == "ready"

  @property
  def step(self) -> int:
    """The mock's steps: 0 Prepare (no file count yet), 1 Download, 2 Install (every file in, still finishing), 3 Ready."""
    if self.phase in ("prepare", "road", "download", "install", "ready", "failed"):
      return {"prepare": 0, "road": 1, "download": 1, "install": 2, "ready": 3, "failed": 1}[self.phase]
    if not self.active:
      return 3
    if not self.total:
      return 0
    return 1 if self.done < self.total else 2

  @property
  def current(self) -> RegionProgress | None:
    pending = [r for r in self.regions if not r.finished and (not self.current_regions or r.location in self.current_regions)]
    if self.phase in ("download", "road", ""):
      return next((r for r in pending if r.fraction < 1), next(iter(pending), None))
    return next(iter(pending), None)


class MapsSource(Protocol):
  """What the maps page needs: regions and the selection, both map sets' readiness, and the download."""

  def tick(self) -> None: ...
  def refresh(self) -> None: ...
  def regions(self, tab: int) -> list[Region]: ...     # 0 U.S. regions, 1 U.S. states, 2 other countries
  def name(self, token: str) -> str: ...
  def selected(self, token: str) -> bool: ...
  def set_selected(self, token: str, on: bool) -> None: ...
  def selection_summary(self) -> str: ...
  def has_selection(self) -> bool: ...
  def can_clear(self) -> bool: ...                     # nothing chosen, and routing data to remove
  def downloaded(self) -> bool: ...
  def progress(self) -> Progress: ...
  def cancelling(self) -> bool: ...
  def checks(self) -> list[tuple[str, bool]]: ...      # e.g. ("Parked", True)
  def download(self) -> None: ...
  def download_label(self) -> str: ...
  def retry(self) -> None: ...
  def cancel(self) -> None: ...
  def remove(self) -> None: ...
  def can_remove(self) -> bool: ...
  def status(self) -> str: ...
  def region_status(self, token: str) -> tuple[str, str]: ...
  def summary(self) -> dict: ...         # road, routes and note lines; road_ready, route_ready and available
  def routes_size(self) -> float: ...    # bytes of installed routing data


class Maps:
  """Navigation › Offline Maps: readiness and summary, over a maps source."""

  def __init__(self, source: MapsSource):
    self.source = source

  def ready(self) -> bool:
    selected = self.source.has_selection() or self.source.can_clear()
    return selected and all(ok for _, ok in self.source.checks()) and not self.source.progress().active

  def blocked_reason(self) -> str:
    if not self.source.has_selection() and not self.source.can_clear():
      return N_("Choose at least one region")
    return next((t_("Waiting: {}", name.lower()) for name, ok in self.source.checks() if not ok), "")

  def status(self) -> str:
    """The maps page's status line."""
    return str(self.source.status())

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

  def _render(self, rect: rl.Rectangle) -> None:
    progress = self._maps.source.progress()
    body = inset(rect, x=self._padding, y=T.px(14))
    top, bar, note = column(body, [T.BUTTON_HEIGHT, T.px(10), FILL], T.px(12))
    text, cancel = row(top, [FILL, self._cancel.preferred_size(top.width)[0]], T.px(12))
    draw.text(text, f"{round(progress.fraction * 100)}%", T.font_px(30), T.TEXT, T.FONT_EXTRABOLD)
    self._cancel.render(cancel)
    self._bar.render(bar)
    draw.text(note, t_("{} of {} files · {}. Pauses if you drive or lose the connection.", progress.done, progress.total, progress.location),
              T.SIZE_SUBTITLE, T.TEXT_TERTIARY)


def maps_page(maps: Maps, open_regions: Callable[[], None], sizes: Callable[[], dict[str, float]], window: SettingsWindow) -> Widget:
  """The Offline Maps page: road data and offline routes for the chosen regions on the left, storage on the right."""
  source = maps.source
  update = Button(N_("Update maps"), source.download)
  update.set_enabled(maps.ready)
  remove = Button(N_("Remove maps"), lambda: confirm(window, N_("Remove offline maps?"), DELETE_MAPS_MESSAGE, N_("Remove"), source.remove),
                  ButtonStyle.DANGER_SOFT)
  remove.set_enabled(source.can_remove)
  choose = Button(N_("Choose regions"), open_regions, ButtonStyle.PRIMARY, height=T.px(60))
  regions = Card([
    Label(N_("DOWNLOADED REGIONS"), color=T.ACCENT_TEXT, caption=True),
    IconTitle("map", source.selection_summary, source.status),
    Surface(SettingRow(N_("Road data"), N_("Speed limits and street names"),
                       Label(lambda: source.summary()["road"], T.SIZE_SUBTITLE,
                             lambda: T.SUCCESS_TEXT if source.summary().get("road_ready", True) else T.TEXT_TERTIARY,
                             T.FONT, fit=True), height=T.px(54)), T.SURFACE_2),
    Surface(SettingRow(N_("Offline routes"), lambda: t_("{} MiB", round(source.routes_size() / 1024**2)),
                       Label(lambda: N_("Ready") if source.summary()["route_ready"] else source.summary()["routes"],
                             T.SIZE_SUBTITLE, lambda: T.SUCCESS_TEXT if source.summary()["route_ready"] else T.ACCENT_TEXT,
                             T.FONT, fit=True), height=T.px(54)), T.SURFACE_2),
    ButtonRow([update, remove], height=T.px(44)), SPACER, choose,
  ], gap=T.px(10), padding=(T.px(20), T.px(18)))
  storage = Card([StorageBar(sizes, heading=N_("Storage"), padding=(0, 0)), SPACER,
                  Label(N_("Updates keep the current maps until the new maps are ready."), T.SIZE_SUBTITLE, T.TEXT_MUTED, T.FONT)],
                 padding=(T.px(20), T.px(18)), grow=1)
  return TitledPage(N_("Offline Maps"), N_("Routes, speed limits and street names without a connection"),
                    Columns([regions, storage], [1.25, 1]))


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
    return max_width, T.px(104)

  def _render(self, rect: rl.Rectangle) -> None:
    chosen = self.chosen
    draw.fill(rect, T.ACCENT_SELECTED if chosen else T.SURFACE_3, T.px(16))
    if chosen:
      draw.stroke(rect, T.ACCENT, T.px(16), T.px(2))
    elif self.is_pressed:
      draw.pressed(rect, T.px(16))
    body = inset(rect, x=T.px(16), y=T.px(12))
    road, routes = self._maps.source.region_status(self._region.token)
    title, line, routing = column(body, [T.px(23), T.px(19), FILL], T.px(3))
    draw.text(title, draw.fit(self._region.name, T.font_px(17), T.FONT_BOLD, title.width), T.font_px(17), T.TEXT, T.FONT_BOLD)
    draw.text(line, road, T.font_px(12), T.TEXT_TERTIARY)
    draw.paragraph(routing, routes, T.font_px(12), T.SUCCESS_TEXT if routes == N_("Routes ready") else T.TEXT_MUTED,
                   spacing=1.0, max_lines=2)


class RegionsPage(Component):
  """Region kinds on the left, the regions as cards in the middle, and the selection with its download on the right."""
  grow_touch_target = False
  TABS = [N_("U.S. regions"), N_("U.S. states"), N_("Other countries")]

  def __init__(self, maps: Maps, on_download: Callable[[], None]):
    super().__init__()
    self._maps = maps
    self._tab = 0
    self._header = self._child(PageHeader(N_("Add map regions"), N_("Pick where you drive. Maps for routes, speed limits and street names.")))
    self._tabs = self._child(Sidebar(N_("REGIONS"), [SidebarItem(t, on_select=partial(self._select, i)) for i, t in enumerate(self.TABS)],
                                     selected=lambda: self._tab, width=T.px(220)))

    def build() -> ListPanel:
      cards = [RegionCard(r, maps) for r in maps.source.regions(self._tab)]
      return ListPanel([Grid(cards, columns=2 if self._tab == 0 else 3)] if cards else [Text(N_("No regions available."))],
                       background=T.BG, dividers=False)

    self._list = self._child(Rebuilding(lambda: self._tab, build, maps.source.tick))
    download = Button(maps.source.download_label, on_download, ButtonStyle.PRIMARY, height=T.px(60))
    download.set_enabled(maps.ready)
    summary = maps.source.summary
    details: list[Widget] = [Label(N_("Road data"), T.font_px(16)),
                 Label(lambda: summary()["road"], T.SIZE_SUBTITLE,
                       lambda: T.SUCCESS_TEXT if summary().get("road_ready", True) else T.TEXT_TERTIARY, T.FONT),
                 Label(N_("Offline routes"), T.font_px(16)),
                 Label(lambda: summary()["routes"], T.SIZE_SUBTITLE,
                       lambda: T.ACCENT_TEXT if summary().get("available", True) else T.WARNING, T.FONT),
                 Text(lambda: summary()["note"], T.SIZE_SUBTITLE, T.TEXT_TERTIARY, T.FONT, padding=(0, 0))]
    checks = Label(lambda: " · ".join(translate(n) for n, ok in maps.source.checks()) if maps.ready() else maps.blocked_reason(),
                   T.font_px(15), T.TEXT_SECONDARY, T.FONT, icon="check", icon_color=T.SUCCESS_TEXT)
    heading = [Label(N_("SELECTED"), color=T.ACCENT_TEXT, caption=True),
               Text(maps.source.selection_summary, T.font_px(22), T.TEXT, T.FONT_EXTRABOLD, padding=(0, 0))]
    # Keep the action pinned as in the approved mock; long translations and
    # large geographic selections scroll only the middle of this summary.
    items = [Stack(heading, gap=T.px(4)),
             ListPanel([Stack(details, gap=T.px(12))], background=T.SURFACE_2, dividers=False),
             Stack([checks, download], gap=T.px(12))]
    self._side = self._child(Card(items, grow=1, padding=(T.px(18), T.px(18))))

  def _select(self, index: int) -> None:
    self._tab = index

  def _render(self, rect: rl.Rectangle) -> None:
    body = inset(body_rect(rect), top=T.px(2))
    header, content = column(body, [self._header.preferred_height(body.width), FILL], T.px(14))
    self._header.render(header)
    tabs, grid, side = row(content, [T.px(220), FILL, T.px(330)], T.px(14))
    self._tabs.render(inset(tabs, top=-T.px(8)))
    self._list.render(grid)
    self._side.render(side)


STEPS = [N_("Prepare"), N_("Download"), N_("Install"), N_("Ready")]
DOWNLOAD_NOTE = N_("Pauses if you start driving or lose Wi-Fi, and picks up where it stopped. Keep the device powered.")


def tile_window(count: int, current: int | None, capacity: int) -> tuple[int, int, int]:
  """Which tiles to show when count may not fit in capacity.

  Returns:
    (start, end, more): a run that keeps the current tile in view, and how many are left out (drawn as one "+N more"
    tile).
  """
  if count <= capacity:
    return 0, count, 0
  shown = capacity - 1
  start = 0 if current is None else max(0, min(current - shown // 2, count - shown))
  return start, start + shown, count - shown


def minutes_left(started: tuple[float, int] | None, now: float, done: int, total: int) -> int | None:
  """Minutes to go at the rate since started.

  Args:
    started: (time, files done then).
    now: The time now.
    done: Files done now.
    total: Files in all.

  Returns:
    The minutes, once there's a rate to go by (5 seconds and some progress); else None.
  """
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
    self._retry = self._child(Button(N_("Retry download"), maps.source.retry,
                                     ButtonStyle.PRIMARY, height=T.px(52)))
    self._done = self._child(Button(N_("Done"), lambda: setattr(self, "_dismissed", True), ButtonStyle.PRIMARY, height=T.px(52)))
    self._dismissed = False
    self._bar = self._child(ProgressBar(lambda: maps.source.progress().fraction))
    self._started: tuple[float, int] | None = None
    self._counter: tuple[str, str, int] | None = None

  def _update_state(self) -> None:
    progress = self._maps.source.progress()
    counter = (progress.phase, progress.unit, progress.total)
    transfer = progress.active and progress.phase not in ("prepare", "install") and not progress.paused and progress.unit != "regions"
    if transfer and progress.total:
      if self._started is None or counter != self._counter or progress.done < self._started[1]:
        self._started = (rl.get_time(), progress.done)
    else:
      self._started = None
    self._counter = counter

  def _render(self, rect: rl.Rectangle) -> None:
    from openpilot.selfdrive.ui.tandem.settings.pages import body_rect
    progress = self._maps.source.progress()
    body = body_rect(rect)
    header, top, grid = column(body, [T.px(60), T.px(136), FILL], T.px(12))
    # Header: title and line, Cancel at the right
    action = self._retry if progress.error else self._done if progress.phase == "ready" else self._cancel
    w, _ = action.preferred_size(header.width)
    words, cancel = row(header, [FILL, w], T.px(14))
    action.render(place(cancel, w, T.px(52)))
    title, line = column(place(words, words.width, T.px(60)), [T.px(34), FILL], T.px(2))
    what = self._maps.source.selection_summary().removesuffix(" selected")   # "13 regions", "Whole U.S. (56 states)"
    heading = t_("{} download stopped", what) if progress.error else t_("{} maps ready", what) if progress.phase == "ready" else \
      t_("Preparing {} maps", what) if progress.phase == "prepare" else t_("Installing {}", what) if progress.phase == "install" else \
      t_("Downloading {}", what)
    if progress.phase == "ready" and len(progress.regions) > 1:
      heading = t_("{} ready", what)
    draw.text(title, heading, T.font_px(26), T.TEXT, T.FONT_EXTRABOLD)
    explanation = N_("You can leave this screen. It keeps going in the background.")
    if progress.error:
      from openpilot.selfdrive.ui.tandem.routing_status import status_text
      explanation = status_text(progress.error)
    elif progress.phase == "ready":
      explanation = N_("All maps ready") if progress.paired else N_("Both map sets ready")
    draw.text(line, explanation, T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
    # Percent, bar and steps
    draw.fill(top, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(top, x=T.px(22), y=T.px(16))
    figure, bar, steps = column(inner, [T.px(50), T.px(12), FILL], T.px(10))
    pct = f"{round(progress.fraction * 100)}%"
    pw = draw.text(figure, pct, T.font_px(44), T.TEXT, T.FONT_EXTRABOLD)
    left = minutes_left(self._started, rl.get_time(), progress.done, progress.total)
    if progress.phase == "install":
      detail = N_("Download complete · Building maps") if progress.stage == "build" else \
        N_("Download complete · Checking maps") if progress.stage == "check" else N_("Download complete · Installing maps")
    elif progress.phase == "ready":
      detail = N_("All maps ready") if progress.paired else N_("Both map sets ready")
    elif progress.unit == "regions":
      current = progress.current
      detail = t_("{} · {} of {}", self._maps.source.name(current.location),
                  progress.regions.index(current) + 1, len(progress.regions)) if current else N_("Getting ready")
    elif progress.unit == "bytes" and progress.total:
      detail = t_("Offline routes · {} of {} MiB", round(progress.done / 1024**2), round(progress.total / 1024**2))
    else:
      detail = t_("Road data · {} of {} files", progress.done, progress.total) if progress.total else N_("Getting ready")
    if progress.error:
      detail += N_(" · Download stopped")
    if left is not None and not progress.error and not progress.paused:
      detail += t_(" · about {} min left", left)
    draw.text(inset(figure, left=pw + T.px(16)), detail, T.font_px(17), T.TEXT_SECONDARY)
    self._bar.render(bar)
    for i, (name, cell) in enumerate(zip(STEPS, row(steps, [FILL] * len(STEPS), T.px(12)), strict=True)):
      done, now = progress.step_complete(i), i == progress.step
      ink = T.SUCCESS_TEXT if done else (T.TEXT if now else T.TEXT_MUTED)
      mark = rl.Rectangle(cell.x, cell.y, T.px(18), cell.height)
      if done:
        draw.icon(mark, "check", T.SUCCESS_TEXT, T.px(16))
      elif now:
        rl.draw_circle_v(rl.Vector2(mark.x + T.px(7), mark.y + mark.height / 2), T.px(5), T.ACCENT)
      else:
        rl.draw_circle_lines(int(mark.x + T.px(7)), int(mark.y + mark.height / 2), T.px(5), T.TEXT_MUTED)
      draw.text(inset(cell, left=T.px(26)), f"{i + 1} {translate(name)}", T.font_px(16), ink, T.FONT_SEMIBOLD if now or done else T.FONT)
    # Regions
    draw.fill(grid, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(grid, x=T.px(22), y=T.px(14))
    regions = progress.regions
    finished = sum(r.finished for r in regions)
    caption, tiles, note = column(inner, [draw.line_height(T.SIZE_CAPTION), FILL, draw.line_height(T.SIZE_SUBTITLE)], T.px(12))
    downloading = progress.paired and progress.phase == "download"
    downloaded = sum(r.downloaded for r in regions)
    draw.caption(caption, t_("REGIONS · {} OF {} DOWNLOADED", downloaded, len(regions)) if downloading else
                 t_("REGIONS · {} OF {} DONE", finished, len(regions)) if regions else N_("REGIONS"))
    current = progress.current
    tile_w = (tiles.width - T.px(10) * (self.COLUMNS - 1)) / self.COLUMNS
    rows = max(1, int((tiles.height + T.px(8)) // T.px(56)))
    start, end, more = tile_window(len(regions), regions.index(current) if current is not None else None, rows * self.COLUMNS)
    tile_at = lambda i: rl.Rectangle(tiles.x + (i % self.COLUMNS) * (tile_w + T.px(10)), tiles.y + (i // self.COLUMNS) * T.px(56),  # noqa: E731
                                  tile_w, T.px(48))
    if more:
      tile = tile_at(end - start)
      draw.fill(tile, T.SURFACE_4, T.px(12))
      draw.text(tile, t_("+{} more", more), T.font_px(15), T.TEXT_TERTIARY, T.FONT_SEMIBOLD, Align.CENTER)
    for i, region in enumerate(regions[start:end]):
      tile = tile_at(i)
      is_current = not region.finished and (region is current or region.location in progress.current_regions)
      if region.finished:
        draw.fill(tile, T.SUCCESS_SURFACE, T.px(12))
        label, ink = region.code, T.SUCCESS_CHIP_TEXT
      elif is_current:
        draw.fill(tile, T.WARNING_SURFACE if progress.error else T.ACCENT_SELECTED, T.px(12))
        draw.stroke(tile, T.WARNING if progress.error else T.ACCENT, T.px(12), T.px(2))
        label, ink = region.code, T.TEXT
      else:
        draw.fill(tile, T.SURFACE_4, T.px(12))
        label, ink = region.code, T.TEXT_TERTIARY
      extra = ""
      if not region.finished and not progress.error:
        extra = f"{round((progress.fraction if progress.phase == 'install' else region.fraction) * 100)}%"
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
    message = N_("Paused. Downloads continue when parked on Wi-Fi.") if progress.paused else DOWNLOAD_NOTE
    if progress.phase == "ready":
      message = N_("Maps are ready. Existing saved places stay saved.") if progress.paired else \
        N_("Both map sets are ready. Existing saved places stay saved.")
    if progress.error:
      from openpilot.selfdrive.ui.tandem.routing_status import status_text
      message = status_text(progress.error)
    draw.text(inset(note, left=T.px(28)), message, T.SIZE_SUBTITLE, T.WARNING if progress.error else T.TEXT_SECONDARY)
    if progress.note:
      note_y = tiles.y + T.px(56) * ((len(regions) + self.COLUMNS - 1) // self.COLUMNS) + T.px(8)
      if note_y + draw.line_height(T.SIZE_CAPTION) < note.y:
        draw.text(rl.Rectangle(tiles.x, note_y, tiles.width, T.px(20)), progress.note, T.SIZE_CAPTION, T.TEXT_SECONDARY)


class MapsPage(Component):
  """The Offline Maps panel; tracks the download while open, showing the download view in its place while one runs."""
  grow_touch_target = False

  def __init__(self, maps: Maps, open_regions: Callable[[], None], sizes: Callable[[], dict[str, float]], window: SettingsWindow) -> None:
    super().__init__()
    self._maps = maps
    self._page = self._child(maps_page(maps, open_regions, sizes, window))
    self._download = self._child(DownloadView(maps))

  def show_event(self) -> None:
    self._maps.source.refresh()
    if self._maps.source.progress().phase == "ready":
      self._download._dismissed = True
    super().show_event()

  def _update_state(self) -> None:
    self._maps.source.tick()

  def _render(self, rect: rl.Rectangle) -> None:
    progress = self._maps.source.progress()
    if progress.active:
      self._download._dismissed = False
    visible = progress.active or (progress.error or progress.phase == "ready") and not self._download._dismissed
    (self._download if visible else self._page).render(rect)
