"""Speed & Steering: the everyday driving choices, each one setting several of StarPilot 7's settings together.

The panels are release's. The models read and change StarPilot 7's settings rows (starpilot7.FeatureRows) where StarPilot
keeps a setting behind its owner, and plain openpilot settings through the store. Lane-change choices go through a
confirmation, as StarPilot 7 requires.
"""
from __future__ import annotations
from collections.abc import Callable
from typing import TYPE_CHECKING
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.blocks import Label, Stack
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Segmented, Stepper, Switch, ValueButton
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.prefs import MAX_FOLLOWS_LIMIT, WEATHER_HEADS_UP
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.live import Live
  from openpilot.selfdrive.ui.tandem.settings.starpilot7 import FeatureRows
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

Rows = Callable[[str], "FeatureRows"]   # StarPilot 7's settings page by name (StarPilotOwners.rows)
Confirm = Callable[[str, str, str, Callable[[], None]], None]   # title, message, button, then the action on confirm

STYLES = [N_("Relaxed"), N_("Standard"), N_("Sport")]
SPEED_LIMITS = [N_("Off"), N_("Show"), N_("Match")]
LIMIT_CHANGES = [N_("Update automatically"), N_("Tap to confirm")]
LANE_CHANGES = [N_("Nudge"), N_("Auto")]

# Driving Style -> (LongitudinalPersonality, StarPilot 7's acceleration preset, its braking preset), as the owner decided.
STYLE_PARAMS = [
  (2, "Comfort", "Comfort"),                       # Relaxed
  (1, "StarPilot Default", "StarPilot Default"),   # Standard
  (0, "Sport", "Sport"),                           # Sport (StarPilot's Aggressive personality)
]
OFFSET_KEYS = [f"slc:offset:{i}" for i in range(1, 8)]   # StarPilot 7's offset per speed range; Tandem sets them alike
CONFIRMATION = ("Off", "Both", "Higher only", "Lower only")   # StarPilot 7's SLCConfirmation choices
OFFSET_MAX = 15
# StarPilot 7's speed limit sources, first to third (starpilot/speed_limits/runtime_settings.SOURCE_PRIORITY_KEYS), and its
# choices for them in plain words: the first word as a name, later ones as they read after "then" (design/speedlimitsources.html).
SOURCE_KEYS = ("SLCPriority1", "SLCPriority2", "SLCPriority3")
SOURCES = {
  "Off": (N_("Off"), ""),
  "Maps": (N_("Maps"), N_("maps", context="a speed limit source, after the first in a list")),
  "Vision": (N_("Camera"), N_("camera", context="a speed limit source, after the first in a list")),
  "Dashboard": (N_("Car"), N_("car", context="a speed limit source, after the first in a list")),
}
SOURCE_ROWS = [(N_("First"), N_("Used whenever it has a limit")), (N_("Second"), N_("When the first has none")),
               (N_("Third"), N_("When neither has one"))]


class SpeedSteering:
  """Reads and writes the grouped settings; the screen and the hub tile both use it.

  Args:
    store: Plain openpilot settings (the personality, Safe Mode, units).
    rows: StarPilot 7's settings pages.
    confirm: Asks the driver before a change StarPilot only makes on confirmation (lane changes).
    owns_set: Whether StarPilot runs this car's cruise and can move SET (not the car's own cruise).
  """

  def __init__(self, store: SettingsStore, rows: Rows, confirm: Confirm = lambda title, message, label, action: action(),
               owns_set: Callable[[], bool] = lambda: True):
    self._store = store
    self._rows = rows
    self._confirm = confirm
    self.owns_set = owns_set

  @property
  def safe_mode(self) -> bool:
    return self._store.get_bool("SafeMode")

  @property
  def style(self) -> int:
    personality = self._store.get_int("LongitudinalPersonality")
    return next((i for i, (p, _, _) in enumerate(STYLE_PARAMS) if p == personality), 1)

  def set_style(self, index: int) -> None:
    """The personality, then StarPilot's acceleration and braking presets where the car lets StarPilot control speed."""
    personality, accel, decel = STYLE_PARAMS[index]
    self._store.write({"LongitudinalPersonality": personality})
    profiles = self._rows("profiles")
    profiles.set("profile:global_acceleration", accel)
    profiles.set("profile:global_braking", decel)

  @property
  def speed_limits(self) -> int:
    slc = self._rows("slc")
    if slc.on("SpeedLimitController"):
      return 2
    return 1 if slc.on("ShowSpeedLimits") else 0

  def set_speed_limits(self, index: int) -> None:
    """Match runs the speed limit controller, and also sets cruise to the limit when engaging."""
    slc = self._rows("slc")
    match = index == 2
    slc.set_on("ShowSpeedLimits", index > 0)
    slc.set_on("SpeedLimitController", match)
    slc.set_on("SLCOnEngage", match)

  @property
  def matching(self) -> bool:
    return self.speed_limits == 2

  # Speed limit sources: StarPilot's three, in order (it shows Map Data as "Maps")

  def source_choices(self, index: int) -> list[str]:
    """StarPilot's choices for a source, as it offers them for this car (Maps only with a verified offline map package)."""
    row = self._rows("slc").row(SOURCE_KEYS[index])
    offered = set(row.choices) if row is not None else set()
    return [choice for choice in SOURCES if choice in offered]   # in the sheet's order: Off, Maps, Camera, Car

  def source(self, index: int) -> str:
    value = self._rows("slc").value(SOURCE_KEYS[index], "Off")
    return "Maps" if value == "Map Data" else value

  def set_source(self, index: int, choice: str) -> None:
    """Saves a source through StarPilot's settings owner, which checks it against what it offered."""
    self._rows("slc").set(SOURCE_KEYS[index], choice)

  def source_editable(self, index: int) -> bool:
    return self._rows("slc").available(SOURCE_KEYS[index])

  def sources_summary(self) -> str:
    """The order on one line: "Maps, then camera"."""
    names = [self.source(i) for i in range(len(SOURCE_KEYS))]
    names = [n for n in names if n in SOURCES and n != "Off"]
    if not names:
      return N_("None")
    words = [translate(SOURCES[names[0]][0])] + [translate(SOURCES[n][1]) for n in names[1:]]
    if len(words) == 1:
      return words[0]
    if len(words) == 2:
      return t_("{}, then {}", *words, context="speed limit sources in order")
    return t_("{}, {}, then {}", *words, context="speed limit sources in order")

  @property
  def offset(self) -> float:
    return self._rows("slc").number(OFFSET_KEYS[0])

  def set_offset(self, value: float) -> None:
    """One offset for every speed range, so a matched limit is always the sign plus the same amount."""
    slc = self._rows("slc")
    for key in OFFSET_KEYS:
      slc.set_number(key, value)

  @property
  def unit(self) -> str:
    return "km/h" if self._store.get_bool("IsMetric") else "mph"

  @property
  def lane_change_speed(self) -> int:
    return round(self._rows("lane_change").number("lane_change:speed"))

  def _confirmation(self) -> tuple[bool, bool]:
    choice = self._rows("slc").value("SLCConfirmation", "Off")
    return choice in ("Both", "Higher only"), choice in ("Both", "Lower only")

  def _set_asks(self, higher: bool, lower: bool) -> None:
    self._rows("slc").set("SLCConfirmation", CONFIRMATION[(1 if higher and lower else 2 if higher else 3 if lower else 0)])

  @property
  def higher_limits(self) -> int:
    return int(self._confirmation()[0])

  def set_higher_limits(self, index: int) -> None:
    self._set_asks(index == 1, self._confirmation()[1])

  @property
  def lower_limits(self) -> int:
    return int(self._confirmation()[1])

  def set_lower_limits(self, index: int) -> None:
    self._set_asks(self._confirmation()[0], index == 1)

  @property
  def max_follows(self) -> bool:
    return MAX_FOLLOWS_LIMIT.get()

  def set_max_follows(self, on: bool) -> None:
    MAX_FOLLOWS_LIMIT.set(on)

  @property
  def lane_changes(self) -> int:
    return 1 if self._rows("lane_change").on("lane_change:auto") else 0

  def set_lane_changes(self, index: int) -> None:
    """StarPilot 7 changes lane-change settings only on confirmation, so the driver confirms first."""
    if index == self.lane_changes:
      return

    def apply() -> None:
      lanes = self._rows("lane_change")
      lanes.set_on("lane_change:enabled", True, confirmed=True)
      lanes.set_on("lane_change:auto", index == 1, confirmed=True)
    message = N_("Starts one lane change per signal on its own.") if index == 1 else N_("Changes lanes only when you nudge the wheel.")
    self._confirm(N_("Change lane changes?"), message, LANE_CHANGES[index], apply)

  @property
  def smart_slowdowns(self) -> bool:
    return self._rows("conditional").value("conditional:mode") == "Automatic" and self._rows("curve").on("CurveSpeedController")

  def set_smart_slowdowns(self, on: bool) -> None:
    """Automatic driving mode (experimental for curves, lights and slower or stopped cars) and the curve controller."""
    self._rows("conditional").set("conditional:mode", "Automatic" if on else "Chill")
    self._rows("curve").set_on("CurveSpeedController", on)

  @property
  def always_on_steering(self) -> bool:
    return self._rows("aol").on("AlwaysOnLateral")

  def set_always_on_steering(self, on: bool) -> None:
    self._rows("aol").set_on("AlwaysOnLateral", on)

  def summary(self) -> str:
    lanes = N_("Auto lane change") if self.lane_changes else N_("Nudge to change lanes")
    return f"{STYLES[self.style]} · {lanes}"

  def speed_limit_summary(self) -> str:
    return [N_("Speed limits off"), N_("Showing speed limits"), N_("Matching speed limits")][self.speed_limits]


def sources_sheet(model: SpeedSteering, window: SettingsWindow) -> Sheet:
  """Speed limit sources (design/speedlimitsources.html): StarPilot's three sources, each one of the choices it offers."""
  def source_row(index: int, title: str, subtitle: str) -> SettingRow:
    choices = model.source_choices(index)

    def selected() -> int:
      current = model.source(index)
      return choices.index(current) if current in choices else 0

    def chosen(i: int) -> None:
      model.set_source(index, choices[i])

    def editable() -> bool:
      return model.source_editable(index)
    line = SettingRow(title, subtitle, Segmented([SOURCES[c][0] for c in choices], selected, chosen, height=T.px(44),
                                                 font_size=T.font_px(16)), height=T.px(66))
    line.set_enabled(editable)
    return line

  rows: list[Widget] = [source_row(i, title, subtitle) for i, (title, subtitle) in enumerate(SOURCE_ROWS)]
  rows.append(Text(N_("Maps reads your offline maps. Camera reads signs as you pass them. Car uses its own sign reading."),
                   T.SIZE_SUBTITLE, T.TEXT_MUTED, padding=(T.px(8), T.px(10))))
  return Sheet(N_("Speed limit sources"), Stack(rows, gap=0), subtitle=N_("When more than one has a limit, the first one wins"),
               actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss)


def everyday_panel(model: SpeedSteering, window: SettingsWindow | None = None) -> ListPanel:
  """Driving › Everyday: driving style, speed limits and lane changes. With the window, Limit sources opens its sheet."""
  style = SettingRow(N_("Driving Style"), lambda: N_("Relaxed while Safe Mode is on") if model.safe_mode else
                     N_("Sets following gap, acceleration and braking together"), Segmented(STYLES, lambda: model.style, model.set_style))
  style.set_enabled(lambda: not model.safe_mode)
  offset = SettingRow(N_("Offset"), N_("Added to every matched limit"), indent=True,
                      control=Stepper(lambda: model.offset, model.set_offset, 0, OFFSET_MAX,
                                      fmt=lambda v: f"+{v:g} {model.unit}", value_width=T.px(104)))
  higher = SettingRow(N_("Higher limits"), N_("When a posted limit goes up"), indent=True,
                      control=Segmented(LIMIT_CHANGES, lambda: model.higher_limits, model.set_higher_limits,
                                        height=T.px(42), font_size=T.font_px(15)))
  lower = SettingRow(N_("Lower limits"), N_("When a posted limit goes down"), indent=True,
                     control=Segmented(LIMIT_CHANGES, lambda: model.lower_limits, model.set_lower_limits,
                                       height=T.px(42), font_size=T.font_px(15)))
  follows = SettingRow(N_("MAX follows limits"), lambda: N_("Each new limit sets MAX, so it slows promptly for lower ones") if model.owns_set() else
                       N_("Your car's cruise sets MAX on this car; the limit still caps the speed"), indent=True,
                       control=Switch(lambda: model.max_follows, model.set_max_follows))
  follows.set_enabled(model.owns_set)
  for row in (offset, higher, lower, follows):
    row.set_visible(lambda: model.matching)
  sources = SettingRow(N_("Limit sources"), N_("Where limits come from, in order"), indent=True,
                       control=ValueButton(model.sources_summary, lambda: window.present(sources_sheet(model, window)) if window else None))
  sources.set_visible(lambda: model.speed_limits > 0 and window is not None)   # StarPilot uses them to show and to match

  rows = [
    style,
    SettingRow(N_("Speed Limits"), N_("Match sets cruise to the posted limit"),
               Segmented(SPEED_LIMITS, lambda: model.speed_limits, model.set_speed_limits)),
    sources,
    offset,
    higher,
    lower,
    follows,
    SettingRow(N_("Lane Changes"), lambda: t_("Auto starts one change per signal, above {} {}", model.lane_change_speed, model.unit),
               Segmented(LANE_CHANGES, lambda: model.lane_changes, model.set_lane_changes)),
    SettingRow(N_("Smart Slowdowns"), N_("Slows for curves, stop lights and stopped traffic on its own"),
               Switch(lambda: model.smart_slowdowns, model.set_smart_slowdowns)),
    SettingRow(N_("Always-On Steering"), N_("Keeps steering with cruise off."),
               Switch(lambda: model.always_on_steering, model.set_always_on_steering)),
  ]
  count = Label(lambda: t_("{} settings", sum(r.is_visible for r in rows)), T.SIZE_CAPTION, T.TEXT_MUTED, T.FONT, fit=True)
  return ListPanel(rows, title=N_("Everyday"), subtitle=N_("Driving style, speed limits, lane changes and steering"), header_control=count)


# ── Weather ──

class Weather:
  """Driving › Weather: Weather heads-up. StarPilot 7 has no weather driving presets, so that part of release's page is gone."""

  @property
  def heads_up(self) -> bool:
    return WEATHER_HEADS_UP.get()

  def set_heads_up(self, on: bool) -> None:
    WEATHER_HEADS_UP.set(on)

  def summary(self) -> str:
    return N_("Heads-up on") if self.heads_up else N_("Off")


def weather_panel(model: Weather) -> ListPanel:
  """Driving › Weather's panel: release's, without the driving presets StarPilot 7 dropped."""
  heads_up = SettingRow(N_("Weather heads-up"), N_("Warns before rain, snow or storms start, and says when they should stop"),
                        Switch(lambda: model.heads_up, model.set_heads_up))
  return ListPanel([heads_up], title=N_("Weather"), subtitle=N_("Rain, snow and storms ahead, from local weather"),
                   footnote=N_("Needs an internet connection. Chips show it ahead and while it lasts."), footnote_divider=True)


# ── Assistance: openpilot's own switches ──

# sentryd's motion threshold (m/s² of change): lower notices smaller bumps. Standard is StarPilot's default.
SENTRY_SENSITIVITY = [(N_("Low"), 0.08), (N_("Standard"), 0.04), (N_("High"), 0.02)]

class Assistance:
  """Driving › Assistance: StarPilot's safety switches, Sentry Mode and driver monitoring.

  openpilot's own switches are plain settings; Disengage on Gas Pedal and Sentry are behind StarPilot 7's owners.
  """
  OWNED = {"DisengageOnAccelerator": "profiles"}   # setting -> StarPilot 7 page holding it

  def __init__(self, store: SettingsStore, live: Live, rows: Rows) -> None:
    self._store = store
    self._live = live
    self._rows = rows

  def get(self, key: str) -> bool:
    page = self.OWNED.get(key)
    return self._rows(page).on(key) if page else self._store.get_bool(key)

  def setter(self, key: str) -> Callable[[bool], None]:
    page = self.OWNED.get(key)

    def set_value(on: bool) -> None:
      if page:
        self._rows(page).set_on(key, on)
      else:
        self._store.write({key: on})
    return set_value

  def set_safe_mode(self, on: bool) -> None:
    """Safe Mode turns off experimental mode and drives Relaxed, as upstream's toggle screen does."""
    values: dict = {"SafeMode": on}
    if on:
      values |= {"ExperimentalMode": False, "LongitudinalPersonality": STYLE_PARAMS[0][0]}
    self._store.write(values)

  def parked_or_disengaged(self) -> bool:
    return not self._live.engaged()

  def summary(self) -> str:
    return N_("Gas pedal disengages") if self.get("DisengageOnAccelerator") else N_("Gas pedal doesn't disengage")

  # Sentry (StarPilot's sentryd): pictures when the parked car is bumped, viewed in Galaxy › Tools › Sentry

  # StarPilot 7's Sentry owner changes its settings only while parked, and only as an explicit action: a tap here is one.

  @property
  def sentry(self) -> bool:
    return self._rows("sentry").on("sentry:enabled")

  def set_sentry(self, on: bool) -> None:
    self._rows("sentry").set_on("sentry:enabled", on, confirmed=True)

  @property
  def sentry_sensitivity(self) -> int:
    """Index into SENTRY_SENSITIVITY, or -1 for a value set elsewhere (Galaxy's slider)."""
    value = self._rows("sentry").number("sentry:sensitivity", SENTRY_SENSITIVITY[1][1])
    return next((i for i, (_, threshold) in enumerate(SENTRY_SENSITIVITY) if abs(value - threshold) < 1e-6), -1)

  def set_sentry_sensitivity(self, index: int) -> None:
    self._rows("sentry").set("sentry:sensitivity", f"{SENTRY_SENSITIVITY[index][1]:.3f}", confirmed=True)

  def sentry_available(self) -> bool:
    return self._rows("sentry").available("sentry:enabled")

  def monitoring_summary(self) -> str:
    return N_("Driver monitoring always on") if self.get("AlwaysOnDM") else N_("Driver monitoring while engaged")


def assistance_panel(model: Assistance) -> ListPanel:
  """Driving › Assistance's panel."""
  def switch(title: str, subtitle: str, key: str, on_change: Callable[[bool], None] | None = None, restarts: bool = False) -> SettingRow:
    row = SettingRow(title, translate(subtitle) + (translate(N_(" Restarts openpilot if the car is on.")) if restarts else ""),
                     Switch(lambda: model.get(key), on_change or model.setter(key)))
    if restarts:
      row.set_enabled(model.parked_or_disengaged)
    return row

  return ListPanel([
    switch("openpilot", N_("Adaptive cruise and lane keeping. Your attention is required at all times."), "OpenpilotEnabledToggle",
           restarts=True),
    switch(N_("Disengage on Gas Pedal"), N_("Pressing the accelerator turns openpilot off"), "DisengageOnAccelerator"),
    switch(N_("Lane Departure Warnings"), N_("Alerts when you drift over a lane line without signaling, above 31 mph (50 km/h)"), "IsLdwEnabled"),
    switch(N_("Safe Mode"), N_("Uses stock tuning, the default model and Relaxed until turned off."), "SafeMode", model.set_safe_mode,
           restarts=True),
  ], title=N_("Assistance"), subtitle=N_("openpilot's core switches"))


def driver_monitoring_panel(model: Assistance, rows: list) -> ListPanel:
  """Driver monitoring in one place: Always-On, then the camera preview and reset (settings.device.driver_monitoring_rows)."""
  return ListPanel([
    SettingRow(N_("Always-On Driver Monitoring"), N_("Watches for distraction even when openpilot is off"),
               Switch(lambda: model.get("AlwaysOnDM"), model.setter("AlwaysOnDM"))),
    *rows,
    SectionHeader(N_("WHILE PARKED")),
    SettingRow(N_("Sentry Mode"), lambda: N_("Pictures in Galaxy if the parked car is bumped") if model.sentry_available() else
               N_("Turn off the car to change Sentry Mode"), Switch(lambda: model.sentry, model.set_sentry)),
    SettingRow(N_("Sensitivity"), N_("High notices smaller bumps"), indent=True,
               control=Segmented([name for name, _ in SENTRY_SENSITIVITY], lambda: model.sentry_sensitivity, model.set_sentry_sensitivity,
                                 height=T.px(42), font_size=T.font_px(15))),   # as the other sub-rows' choices
  ], title=N_("Driver Monitoring"), subtitle=N_("Watches that you're paying attention"))
