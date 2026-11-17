"""Display: the driving screen and the path's look.

StarPilot 7 keeps the camera, driver camera, style banner, blind spot border and power-user switches in its Appearance
owner, and the path in its onroad layout; both change only while parked. Text size, reduce motion and the lead car tag
are Tandem's own. StarPilot 7 dropped its compass, so the compass is Tandem's own; it also dropped turn signal animations, boot logos and
the startup message, so those rows are gone; the map rows wait for routing.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Segmented, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.prefs import COMPASS, LARGER_TEXT, LEAD_TAG, REDUCE_MOTION
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow
from openpilot.selfdrive.ui.tandem.settings.bundles import APPEARANCE, DEVELOPER_VIEW, LEAD_INSIGHTS, Bundle
from openpilot.selfdrive.ui.tandem.settings.speed_steering import Rows
from openpilot.selfdrive.ui.tandem.settings.starpilot7 import RoadStyle
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.system.ui.lib.application import MousePos

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

PATH_COLOR = "#5AAAF880"   # Essentials blue at 50%, as release's Standard path
# Path Style -> StarPilot's path mode (and color). Acceleration is openpilot's own path, colored by gas and braking.
PATH_STYLES = [
  (N_("Standard"), N_("A calm blue path"), {"pathMode": "color", "path": PATH_COLOR}),
  (N_("Rainbow"), N_("A rainbow path"), {"pathMode": "rainbow"}),
  (N_("Acceleration"), N_("openpilot's path, colored by gas and braking"), {"pathMode": "acceleration"}),
]
PATH_MODES = ["color", "rainbow", "acceleration"]
# StarPilot's camera choices this offers; Driver and None are left to StarPilot's own screens.
CAMERA_VIEWS = [(N_("Auto"), "Auto"), (N_("Standard"), "Standard"), (N_("Wide"), "Wide")]
TEXT_SIZES = [N_("Standard"), N_("Larger")]   # the driving screen's text, icons and touch targets (onroad/size.py)


class Display:
  """Display settings: StarPilot's appearance rows and path style, and Tandem's own driving screen preferences."""

  def __init__(self, rows: Rows, road: RoadStyle):
    self._rows = rows
    self._road = road

  def _appearance(self, key: str) -> bool:
    return self._rows(APPEARANCE).on(key)

  def _set_appearance(self, key: str, on: bool) -> None:
    self._rows(APPEARANCE).set_on(key, on)

  def editable(self, key: str) -> bool:
    """Whether StarPilot would change this appearance row now (parked, and the saved value readable)."""
    return self._rows(APPEARANCE).available(key)

  # Driving screen

  @property
  def path_style(self) -> int:
    from openpilot.starpilot.ui.road_colors import path_mode
    mode = path_mode(self._road.get())
    return PATH_MODES.index(mode) if mode in PATH_MODES else 0

  def set_path_style(self, index: int) -> None:
    self._road.set(PATH_STYLES[index][2])

  def path_editable(self) -> bool:
    return self._road.editable()

  @property
  def driving_style_banner(self) -> bool:
    return not self._appearance("HidePersonalityAlerts")

  def set_driving_style_banner(self, on: bool) -> None:
    self._set_appearance("HidePersonalityAlerts", not on)

  @property
  def blind_spot(self) -> bool:
    return self._appearance("BlindSpotMetrics")

  def set_blind_spot(self, on: bool) -> None:
    self._set_appearance("BlindSpotMetrics", on)

  @property
  def compass(self) -> bool:
    """Tandem's compass: the heading beside the street name in the onroad bar (prefs.COMPASS, onroad/compass.py)."""
    return COMPASS.get()

  def set_compass(self, on: bool) -> None:
    COMPASS.set(on)

  @property
  def lead_tag(self) -> bool:
    """Tandem's tag above the car ahead (prefs.LEAD_TAG); off leaves only the bar under it."""
    return LEAD_TAG.get()

  def set_lead_tag(self, on: bool) -> None:
    LEAD_TAG.set(on)

  @property
  def text_size(self) -> int:
    """0 Standard, 1 Larger: about 30% larger text and icons on the driving screen (prefs.LARGER_TEXT)."""
    return 1 if LARGER_TEXT.get() else 0

  def set_text_size(self, index: int) -> None:
    LARGER_TEXT.set(index == 1)

  @property
  def reduce_motion(self) -> bool:
    """Long street names and turn instructions end in an ellipsis instead of scrolling (prefs.REDUCE_MOTION)."""
    return REDUCE_MOTION.get()

  def set_reduce_motion(self, on: bool) -> None:
    REDUCE_MOTION.set(on)

  def bundle(self, bundle: Bundle) -> tuple[Callable[[], bool], Callable[[bool], None]]:
    return (lambda: bundle.is_on(self._rows)), (lambda on: bundle.set(self._rows, on))

  def bundle_editable(self, bundle: Bundle) -> bool:
    return bundle.editable(self._rows)

  @property
  def camera_view(self) -> int:
    value = self._rows(APPEARANCE).value("CameraView")
    return next((i for i, (_, v) in enumerate(CAMERA_VIEWS) if v == value), 1)

  def set_camera_view(self, index: int) -> None:
    self._rows(APPEARANCE).set("CameraView", CAMERA_VIEWS[index][1])

  @property
  def driver_camera_in_reverse(self) -> bool:
    return self._appearance("DriverCamera")

  def set_driver_camera_in_reverse(self, on: bool) -> None:
    self._set_appearance("DriverCamera", on)

  def summary(self) -> str:
    return N_("Style banner shown") if self.driving_style_banner else N_("Style banner hidden")

  def path_summary(self) -> str:
    return t_("{} path", PATH_STYLES[self.path_style][0])


BUNDLE_LINES = {"Developer View": N_("Side panel with system and controls data."),
                "Lead Insights": N_("Distance to the car ahead, and the pedals on screen.")}


def bundle_items(bundle: Bundle) -> list[tuple[str, str]]:
  """(name, StarPilot's setting) for every option a bundle sets."""
  return [(item.name, item.key) for item in bundle.items]


class BundleGrid(Component):
  """The options a bundle sets, as tiles of name and param, four across (design/bundlesheet.html)."""
  grow_touch_target = False
  COLUMNS, TILE, GAP = 4, T.px(64), T.px(10)

  def __init__(self, bundle: Callable[[], Bundle]):
    super().__init__()
    self._bundle = bundle

  def _rows(self) -> int:
    return -(-len(bundle_items(self._bundle())) // self.COLUMNS)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    rows = self._rows()
    return max_width, rows * self.TILE + (rows - 1) * self.GAP + T.px(16) + draw.line_height(T.SIZE_SUBTITLE)

  def _render(self, rect: rl.Rectangle) -> None:
    items = bundle_items(self._bundle())
    w = (rect.width - self.GAP * (self.COLUMNS - 1)) / self.COLUMNS
    for i, (name, key) in enumerate(items):
      tile = rl.Rectangle(rect.x + (i % self.COLUMNS) * (w + self.GAP), rect.y + (i // self.COLUMNS) * (self.TILE + self.GAP), w, self.TILE)
      draw.fill(tile, T.SURFACE_4, T.px(14))
      top, bottom = column(place(inset(tile, x=T.px(14)), w - T.px(28), T.px(44)), [T.px(24), FILL], T.px(2))
      draw.text(top, name, T.font_px(16), T.TEXT, T.FONT_SEMIBOLD)
      draw.text(bottom, key, T.font_px(12), T.TEXT_TERTIARY, T.FONT_MONO)
    note_y = rect.y + self._rows() * (self.TILE + self.GAP) + T.px(6)
    note = rl.Rectangle(rect.x, note_y, rect.width, draw.line_height(T.SIZE_SUBTITLE))
    draw.icon(rl.Rectangle(note.x, note.y, T.px(18), note.height), "info", T.ACCENT_TEXT, T.px(18))
    draw.text(inset(note, left=T.px(28)), N_("Switching off turns these back off."),
              T.SIZE_SUBTITLE, T.TEXT_SECONDARY)


def bundle_sheet(window: SettingsWindow, start: int = 0) -> Sheet:
  """What Developer View and Lead Insights each set, with tabs to switch between them."""
  bundles = [DEVELOPER_VIEW, LEAD_INSIGHTS]
  tab = [start]
  tabs = Segmented([b.name for b in bundles], lambda: tab[0], lambda i: tab.__setitem__(0, i), height=T.px(52), font_size=T.font_px(16))
  return Sheet(lambda: t_("{} sets", bundles[tab[0]].name), BundleGrid(lambda: bundles[tab[0]]),
               subtitle=N_("One switch for the details most drivers never need"),
               actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss, header=tabs)


def driving_screen_panel(model: Display, window: SettingsWindow) -> ListPanel:
  """Display › Driving Screen: text size, and what the drive screen shows, by bundle and by switch."""
  dev_get, dev_set = model.bundle(DEVELOPER_VIEW)
  lead_get, lead_set = model.bundle(LEAD_INSIGHTS)

  def appearance(row: SettingRow, key: str) -> SettingRow:
    row.set_enabled(lambda: model.editable(key))
    return row

  developer = SettingRow(DEVELOPER_VIEW.name, BUNDLE_LINES[DEVELOPER_VIEW.name], Switch(dev_get, dev_set),
                         link=(t_("Sets {} options", len(bundle_items(DEVELOPER_VIEW))), lambda: window.present(bundle_sheet(window, 0))))
  developer.set_enabled(lambda: model.bundle_editable(DEVELOPER_VIEW))
  lead = SettingRow(LEAD_INSIGHTS.name, BUNDLE_LINES[LEAD_INSIGHTS.name], Switch(lead_get, lead_set),
                    link=(t_("Sets {} options", len(bundle_items(LEAD_INSIGHTS))), lambda: window.present(bundle_sheet(window, 1))))
  lead.set_enabled(lambda: model.bundle_editable(LEAD_INSIGHTS))
  return ListPanel([
    SettingRow(N_("Text Size"), N_("Larger text and icons on the driving screen"),
               Segmented(TEXT_SIZES, lambda: model.text_size, model.set_text_size)),
    SettingRow(N_("Reduce Motion"), N_("Long street names end in … instead of scrolling"),
               Switch(lambda: model.reduce_motion, model.set_reduce_motion)),
    appearance(SettingRow(N_("Camera View"), N_("Wide shows more of the road at low speed"),
                          Segmented([name for name, _ in CAMERA_VIEWS], lambda: model.camera_view, model.set_camera_view)), "CameraView"),
    appearance(SettingRow(N_("Driver Camera in Reverse"), N_("Shows the inside camera while backing up"),
                          Switch(lambda: model.driver_camera_in_reverse, model.set_driver_camera_in_reverse)), "DriverCamera"),
    appearance(SettingRow(N_("Driving Style Banner"), N_("Shows the current style when it changes"),
                          Switch(lambda: model.driving_style_banner, model.set_driving_style_banner)), "HidePersonalityAlerts"),
    SettingRow(N_("Compass"), N_("Heading beside the street name, like NE"), Switch(lambda: model.compass, model.set_compass)),
    appearance(SettingRow(N_("Blind Spot Highlights"), N_("Colors the screen edge when a car is beside you"),
                          Switch(lambda: model.blind_spot, model.set_blind_spot)), "BlindSpotMetrics"),
    SettingRow(N_("Lead Car Tag"), N_("Numbers above the car ahead. Off keeps only the bar under it"), Switch(lambda: model.lead_tag, model.set_lead_tag)),
    SectionHeader(N_("POWER USER")),
    developer,
    lead,
  ], title=N_("Driving Screen"), footnote=N_("StarPilot changes the camera, banner and highlights only while parked."))


def path_panel(model: Display, window: SettingsWindow) -> ListPanel:
  """The path's look, as one preset from pictures."""
  def path_sheet() -> None:
    window.present(Sheet(N_("Path Style"), PathStylePicker(lambda: model.path_style, model.set_path_style),
                         subtitle=N_("How the path ahead is drawn"),
                         actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

  style = SettingRow(N_("Path Style"), N_("How the path ahead is drawn"), ValueButton(lambda: PATH_STYLES[model.path_style][0], path_sheet))
  style.set_enabled(model.path_editable)
  return ListPanel([style], title=N_("Path"), end_divider=True)


def _hex(value: str, alpha: float = 1.0) -> rl.Color:
  return rl.Color(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), round(255 * alpha))


# Each style's preview, from the mock (a 220 x 150 picture): path corners at the top and bottom, lane line width, and the
# path's colors from the bottom of the path to the top, with its opacity.
PREVIEWS = [
  ((104, 116, 70, 150), 3, [(0.0, "3A73B3"), (1.0, "3A73B3")], 0.65),
  ((104, 116, 70, 150), 3, [(0.0, "E5484D"), (0.25, "F5A524"), (0.5, "F5E06B"), (0.75, "3FD08A"), (1.0, "5AAAF8")], 0.75),
  ((104, 116, 70, 150), 3, [(0.0, "3FD08A"), (0.6, "3FD08A"), (1.0, "F0B35A")], 0.6),
]
PREVIEW_W, PREVIEW_H = 220, 150
ROAD = _hex("132231")
LANE = _hex("5C6B7A")


def _gradient(stops: list[tuple[float, str]], t: float, alpha: float) -> rl.Color:
  for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
    if t <= t1:
      f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
      a, b = _hex(c0), _hex(c1)
      return rl.Color(round(a.r + (b.r - a.r) * f), round(a.g + (b.g - a.g) * f), round(a.b + (b.b - a.b) * f), round(255 * alpha))
  return _hex(stops[-1][1], alpha)


def draw_path_preview(rect: rl.Rectangle, index: int) -> None:
  """The mock's little road picture: two lane lines and the path in this style, scaled to cover rect."""
  (top_l, top_r, bottom_l, bottom_r), lane_w, stops, alpha = PREVIEWS[index]
  scale = max(rect.width / PREVIEW_W, rect.height / PREVIEW_H)
  ox = rect.x + (rect.width - PREVIEW_W * scale) / 2
  oy = rect.y + (rect.height - PREVIEW_H * scale) / 2

  def at(x: float, y: float) -> rl.Vector2:
    return rl.Vector2(ox + x * scale, oy + y * scale)

  draw.fill(rect, ROAD, T.px(12))
  rl.begin_scissor_mode(int(rect.x), int(rect.y), int(rect.width), int(rect.height))
  for a, b in (((100, 10), (30, 150)), ((120, 10), (190, 150))):
    rl.draw_line_ex(at(*a), at(*b), lane_w * scale, LANE)
  y0, y1 = at(0, 10).y, at(0, 150).y
  for i in range(int(y1 - y0)):   # the path, one pixel row at a time, so the color can change along it
    t = i / max(1.0, y1 - y0)
    left = top_l + (bottom_l - top_l) * t
    right = top_r + (bottom_r - top_r) * t
    x0 = at(left, 0).x
    rl.draw_rectangle_rec(rl.Rectangle(x0, y0 + i, at(right, 0).x - x0, 1), _gradient(stops, 1 - t, alpha))
  rl.end_scissor_mode()


class PathStylePicker(Component):
  """The path styles side by side, each a picture of the path in that style, with its name under it."""
  GAP = T.px(14)

  def __init__(self, selected: Callable[[], int], on_change: Callable[[int], None]):
    super().__init__()
    self._selected = selected
    self._on_change = on_change
    self._pressed: int | None = None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(214) + T.px(14) + draw.line_height(T.SIZE_SUBTITLE)

  def _cards(self) -> list[rl.Rectangle]:
    w = (self._rect.width - self.GAP * (len(PATH_STYLES) - 1)) / len(PATH_STYLES)
    return [rl.Rectangle(self._rect.x + i * (w + self.GAP), self._rect.y, w, T.px(214)) for i in range(len(PATH_STYLES))]

  def _hit(self, pos: MousePos) -> int | None:
    return next((i for i, r in enumerate(self._cards()) if rl.check_collision_point_rec(pos, r)), None)

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    self._pressed = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed and hit != self._selected():
      self._on_change(hit)
    self._pressed = None

  def _render(self, rect: rl.Rectangle) -> None:
    selected = self._selected()
    for i, card in enumerate(self._cards()):
      chosen = i == selected
      draw.fill(card, T.SURFACE_4, T.px(20))
      if chosen:
        draw.stroke(card, T.ACCENT, T.px(20), T.px(2))
      elif self.is_pressed and i == self._pressed:
        draw.pressed(card, T.px(20))
      body = inset(card, T.px(12))
      label_h = draw.line_height(T.font_px(18))
      draw_path_preview(rl.Rectangle(body.x, body.y, body.width, body.height - label_h - T.px(12)), i)
      draw.text(rl.Rectangle(body.x, body.y + body.height - label_h, body.width, label_h), PATH_STYLES[i][0], T.font_px(18), T.TEXT,
                T.FONT_BOLD if chosen else T.FONT_SEMIBOLD, Align.CENTER)
    note = rl.Rectangle(rect.x, rect.y + T.px(214) + T.px(14), rect.width, draw.line_height(T.SIZE_SUBTITLE))
    draw.text(note, N_("Acceleration is openpilot's own path, colored by gas and braking."),
              T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
