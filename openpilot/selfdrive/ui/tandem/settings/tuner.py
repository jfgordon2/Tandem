"""Tuner Mode: StarPilot 7's fine-tuning values, each showing whether it is still StarPilot's default.

StarPilot 7 keeps tuning as settings rows with a range, a step, a unit and a default: lane centering and the car's
steering tune, the acceleration and braking profiles and stops, and each Driving Style's following gap. A value is
DEFAULT at StarPilot's default and OVERRIDE otherwise; FROM STYLE marks the profiles Driving Style sets. Rows StarPilot
doesn't list for this car aren't shown. StarPilot 6's raw gas and brake values, steering controller choice, cruise
step and bundle overrides have no StarPilot 7 setting.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Badge, Button, ButtonStyle, Switch, Tone, ValueButton
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, OptionList, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.editors import NumberSpec, number_sheet
from openpilot.selfdrive.ui.tandem.settings.speed_steering import Rows
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.system.ui.lib.application import MousePos

if TYPE_CHECKING:
  from openpilot.system.ui.widgets import Widget
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

DEFAULT, OVERRIDE, FROM_STYLE = N_("Default"), N_("Override"), N_("From style")
_TONES = {DEFAULT: Tone.NEUTRAL, OVERRIDE: Tone.WARNING, FROM_STYLE: Tone.ACCENT}


@dataclass(frozen=True)
class Tunable:
  """A StarPilot settings row Tuner Mode shows: its page and key."""
  page: str
  key: str


# Each section's StarPilot pages: every row they list for this car, in StarPilot's order.
# StarPilot's "tuning" page (its manual steering tune, dozens of per-side values) stays on StarPilot's own screens.
STEERING_PAGES = ("lane", "torque")
LANE_CENTERING = "LaneCentering"   # StarPilot's switch for its lane centering: a feature, not a tune, so resets leave it
SWITCHES = {LANE_CENTERING}
# Tandem's names and words for StarPilot's lane centering rows (design/tuner-lanecentering.html); the rest keep StarPilot's.
LABELS = {
  LANE_CENTERING: (N_("Lane Centering"), N_("Steers toward the middle of the lane, not just the model's path")),
  "LaneCenteringPauseOnSignal": (N_("Pause on signal"), N_("Lets the car drift while a blinker is on")),
  "LaneCenterOffset": (N_("Lane offset"), N_("Holds left or right of center")),
  "LaneCenteringE2EAuthority": (N_("Model path preference"), N_("How much a confident model path can override the lane center")),
  "LaneCenteringStrength": (N_("Lane Centering Strength"), N_("100% is normal; lower centers less, higher more")),
}
GAS_BRAKE = [Tunable("profiles", key) for key in ("profile:global_acceleration", "profile:global_braking", "ForceStopDistanceOffset",
                                                  "profile:stopped_gap", "FasterLeadTakeoff", "LeadApproachBuffer", "ExperimentalSpeedNudge")]
STYLE_SET = {"profile:global_acceleration", "profile:global_braking"}   # Driving Style sets these (speed_steering.STYLE_PARAMS)
# Following gap per Driving Style, plus Traffic mode: StarPilot's personality page and its low-speed follow row.
GAPS = [(N_("Relaxed"), Tunable("relaxed", "RelaxedFollow")), (N_("Standard"), Tunable("standard", "StandardFollow")),
        (N_("Sport"), Tunable("aggressive", "AggressiveFollow")), (N_("Traffic"), Tunable("traffic", "TrafficFollow"))]
FOLLOWING = [Tunable("profiles", "ForceStops")]


def _number(text: str) -> float | None:
  try:
    return float(text)
  except (TypeError, ValueError):
    return None


class Tuner:
  """Tuner Mode: StarPilot's tuning rows, their defaults, and resetting them."""

  def __init__(self, rows: Rows):
    self._rows = rows

  def row(self, t: Tunable) -> Any | None:
    return self._rows(t.page).row(t.key)

  def steering(self) -> list[Tunable]:
    """The steering rows StarPilot lists for this car."""
    out = []
    for page in STEERING_PAGES:
      out += [Tunable(page, r.key) for r in self._rows(page).state().rows
              if r.key and (r.choices or r.step) and not r.key.endswith("reset")]
    return out

  def present(self, tunables: list[Tunable]) -> list[Tunable]:
    return [t for t in tunables if self.row(t) is not None]

  def value(self, t: Tunable) -> str:
    return self._rows(t.page).value(t.key)

  def number(self, t: Tunable) -> float:
    return self._rows(t.page).number(t.key)

  def label(self, t: Tunable) -> str:
    r = self.row(t)
    if r is None:
      return ""
    unit = f" {r.unit}" if r.unit and r.step else ""
    return f"{r.value}{unit}"

  def status(self, t: Tunable) -> str:
    if t.key in STYLE_SET:
      return FROM_STYLE
    return OVERRIDE if self.changed(t) else DEFAULT

  def changed(self, t: Tunable) -> bool:
    r = self.row(t)
    if r is None or not r.default_value:
      return False
    a, b = _number(str(r.value)), _number(str(r.default_value))
    return abs(a - b) > 1e-6 if a is not None and b is not None else str(r.value) != str(r.default_value)

  def editable(self, t: Tunable) -> bool:
    return self._rows(t.page).available(t.key)

  def set(self, t: Tunable, value: str) -> None:
    self._rows(t.page).set(t.key, value)

  def set_number(self, t: Tunable, value: float) -> None:
    self._rows(t.page).set_number(t.key, value)

  def reset(self, t: Tunable) -> None:
    r = self.row(t)
    if r is not None and r.default_value:
      self.set(t, str(r.default_value))

  def spec(self, t: Tunable) -> NumberSpec:
    r = self.row(t)
    default = _number(str(r.default_value)) if r is not None else None
    minimum, maximum, step = (float(r.minimum), float(r.maximum), float(r.step)) if r is not None else (0.0, 1.0, 0.1)
    unit = f" {r.unit}" if r is not None and r.unit else ""
    digits = max(0, len(f"{step:g}".partition(".")[2]))
    return NumberSpec(minimum, maximum, step, default if default is not None else minimum, lambda v: f"{v:.{digits}f}{unit}")

  def changes(self, tunables: list[Tunable]) -> int:
    return sum(self.changed(t) for t in tunables if t.key not in STYLE_SET | SWITCHES)

  def gas_brake_changes(self) -> int:
    return self.changes(self.present(GAS_BRAKE))

  def following_changes(self) -> int:
    return self.changes(self.present([t for _, t in GAPS] + FOLLOWING))

  def all_tunables(self) -> list[Tunable]:
    return self.steering() + self.present(GAS_BRAKE + [t for _, t in GAPS] + FOLLOWING)

  def reset_all(self) -> None:
    """Every changed value back to StarPilot's default, except what Driving Style sets and the Lane Centering switch."""
    for t in self.all_tunables():
      if t.key not in STYLE_SET | SWITCHES and self.changed(t) and self.editable(t):
        self.reset(t)


def _changed_label(count: int) -> str:
  return t_("{} changed", count) if count else ""


def tunable_row(tuner: Tuner, t: Tunable, window: SettingsWindow) -> SettingRow:
  """A row for one StarPilot value: a switch, a choice, or a number with its source and Override or Reset."""
  r = tuner.row(t)
  title, subtitle = (r.label, r.reason) if r is not None else (t.key, "")
  title, subtitle = LABELS.get(t.key, (title, subtitle))
  if r is not None and tuple(r.choices) == ("Off", "On"):
    line = SettingRow(title, subtitle, Switch(lambda: tuner.value(t) == "On", lambda on: tuner.set(t, "On" if on else "Off")))
  elif r is not None and r.choices and not r.step:
    def pick() -> None:
      current = tuner.row(t)
      choices = list(current.choices) if current is not None else []

      def select(index: int) -> None:
        tuner.set(t, choices[index])
        window.dismiss()
      window.present(Sheet(title, OptionList(choices, lambda: choices.index(tuner.value(t)) if tuner.value(t) in choices else 0, select),
                           subtitle=subtitle, on_dismiss=window.dismiss))
    line = SettingRow(title, subtitle, ValueStatus(lambda: tuner.value(t), lambda: tuner.status(t), ValueButton(N_("Change"), pick),
                                                   on_value=pick))
  else:
    def edit() -> None:
      window.present(number_sheet(window, title, subtitle, tuner.spec(t), lambda: tuner.number(t), lambda v: tuner.set_number(t, v)))

    def action() -> None:
      if tuner.status(t) == OVERRIDE:
        tuner.reset(t)
      else:
        edit()
    line = SettingRow(title, subtitle, ValueStatus(lambda: tuner.label(t), lambda: tuner.status(t),
                                                   Button(lambda: N_("Reset") if tuner.status(t) == OVERRIDE else N_("Override"), action,
                                                          height=T.px(40)), on_value=edit))
  line.set_enabled(lambda: tuner.editable(t))
  return line


class ValueStatus(Component):
  """Value, then its source badge, then an action button."""
  grow_touch_target = False

  def __init__(self, value: Callable[[], str], status: Callable[[], str], button: Button, on_value: Callable[[], None] | None = None):
    super().__init__()
    self._value = value
    self._status = status
    self._badge = self._child(Badge(status, lambda: _TONES.get(status(), Tone.NEUTRAL)))
    self._button = self._child(button)
    self.set_click_callback(on_value)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return T.px(330), T.px(44)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._badge.set_parent_rect(parent_rect)
    self._button.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle) -> None:
    button_w = T.px(108)
    value, badge, button = row(rect, [FILL, T.px(96), button_w], T.px(10))
    draw.text(value, self._value(), T.font_px(18), T.TEXT, T.FONT_SEMIBOLD, h=Align.END)
    bw, bh = self._badge.preferred_size(badge.width)
    self._badge.render(rl.Rectangle(badge.x + (badge.width - bw) / 2, badge.y + (badge.height - bh) / 2, bw, bh))
    self._button.render(rl.Rectangle(button.x, button.y + (button.height - T.px(40)) / 2, button.width, T.px(40)))


def steering_panel(tuner: Tuner, window: SettingsWindow) -> ListPanel:
  rows: list[Widget] = [tunable_row(tuner, t, window) for t in tuner.steering()]
  return ListPanel(rows or [Text(N_("StarPilot lists your car's steering values once it's detected."))], title=N_("Steering"),
                   subtitle=N_("StarPilot's defaults suit most cars. An override stays until you reset it."))


def gas_brake_panel(tuner: Tuner, window: SettingsWindow) -> ListPanel:
  rows: list[Widget] = [tunable_row(tuner, t, window) for t in tuner.present(GAS_BRAKE)]
  return ListPanel(rows or [Text(N_("Gas and brake tuning needs openpilot's speed control."))], title=N_("Gas & Brake"),
                   subtitle=N_("Driving Style sets the acceleration and braking profiles."))


class GapCells(Component):
  """The four following gaps as one row of cells, as in the mock: the style, then its gap. A changed gap shows in amber;
  tapping a cell edits it."""
  grow_touch_target = False
  GAP = T.px(10)

  def __init__(self, tuner: Tuner, window: SettingsWindow) -> None:
    super().__init__()
    self._tuner, self._window = tuner, window
    self._pressed: int | None = None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(14) + draw.line_height(T.font_px(17)) + T.px(10) + T.px(68) + T.px(14)

  def _cells(self, rect: rl.Rectangle) -> list[rl.Rectangle]:
    body = inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(14))
    top = body.y + draw.line_height(T.font_px(17)) + T.px(10)
    return row(rl.Rectangle(body.x, top, body.width, T.px(68)), [FILL] * len(GAPS), self.GAP)

  def _hit(self, pos: MousePos) -> int | None:
    return next((i for i, cell in enumerate(self._cells(self._rect)) if rl.check_collision_point_rec(pos, cell)), None)

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    self._pressed = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed:
      self.edit(hit)
    self._pressed = None

  def edit(self, index: int) -> None:
    name, t = GAPS[index]
    tuner = self._tuner
    if not tuner.editable(t):
      return
    self._window.present(number_sheet(self._window, t_("{} gap", name), N_("Seconds behind the car ahead in this Driving Style"),
                                      tuner.spec(t), lambda: tuner.number(t), lambda v: tuner.set_number(t, v)))

  def _render(self, rect: rl.Rectangle) -> None:
    body = inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(14))
    draw.text(rl.Rectangle(body.x, body.y, body.width, draw.line_height(T.font_px(17))), N_("Following gap by style"), T.font_px(17), T.TEXT,
              T.FONT_BOLD)
    for i, ((name, t), cell) in enumerate(zip(GAPS, self._cells(rect), strict=True)):
      draw.fill(cell, T.SURFACE_4, T.px(14))
      if self.is_pressed and i == self._pressed:
        draw.pressed(cell, T.px(14))
      top, bottom = column(inset(cell, x=T.px(16), y=T.px(10)), [draw.line_height(T.font_px(14)), FILL], T.px(2))
      draw.text(top, name, T.font_px(14), T.TEXT_TERTIARY)
      shown = self._tuner.row(t) is not None
      value = t_("{} s", f"{self._tuner.number(t):.2f}") if shown else "–"
      draw.text(bottom, value, T.font_px(22), T.WARNING if self._tuner.changed(t) else T.TEXT if shown else T.TEXT_MUTED, T.FONT_BOLD)


def following_panel(tuner: Tuner, window: SettingsWindow) -> ListPanel:
  """Tuner Mode › Following: the following gaps, then stops."""
  return ListPanel([
    GapCells(tuner, window),
    *[tunable_row(tuner, t, window) for t in tuner.present(FOLLOWING)],
  ], title=N_("Following & Stops"))


RESET_TUNING_MESSAGE = N_("Every Tuner Mode change goes back to StarPilot's default. Your other settings stay as they are.")


def tuner_page(tuner: Tuner, window: SettingsWindow) -> Widget:
  """Tuner Mode's page: each section's values and Reset all."""
  from openpilot.selfdrive.ui.tandem.settings.window import confirm
  from openpilot.selfdrive.ui.tandem.settings.pages import Section, SectionPage

  def reset_all() -> None:
    confirm(window, N_("Reset all tuning?"), RESET_TUNING_MESSAGE, N_("Reset"), tuner.reset_all, icon="restart")

  return SectionPage(N_("TUNER MODE"), [
    Section(N_("Steering"), lambda: steering_panel(tuner, window), lambda: _changed_label(tuner.changes(tuner.steering())),
            value_tone=Tone.WARNING),
    Section(N_("Gas & Brake"), lambda: gas_brake_panel(tuner, window), lambda: _changed_label(tuner.gas_brake_changes()),
            value_tone=Tone.WARNING),
    Section(N_("Following & Stops"), lambda: following_panel(tuner, window), lambda: _changed_label(tuner.following_changes()),
            value_tone=Tone.WARNING),
  ], tone=Tone.WARNING, footer=[Button(N_("Reset all tuning"), reset_all, ButtonStyle.DANGER_SOFT, width=T.SIDEBAR_WIDTH)])
