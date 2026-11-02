"""Speed & Steering: the everyday driving choices, each one setting several StarPilot params together."""
from __future__ import annotations

from openpilot.starpilot.common.accel_profile import ACCELERATION_PROFILES as ACCEL, DECELERATION_PROFILES as DECEL
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.blocks import Card, Grid, Icon, InfoCard, Label, Rule, Stack
from openpilot.selfdrive.ui.tandem.controls import TILE_CARDS, Button, ChoiceCards, Segmented, Stepper, Switch
from openpilot.selfdrive.ui.tandem.rows import ListPanel, Padded, SectionHeader, SettingRow
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.prefs import MAX_FOLLOWS_LIMIT, WEATHER_HEADS_UP
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate

STYLES = [N_("Relaxed"), N_("Standard"), N_("Sport")]
SPEED_LIMITS = [N_("Off"), N_("Show"), N_("Match")]
LIMIT_CHANGES = [N_("Update automatically"), N_("Tap to confirm")]
LANE_CHANGES = [N_("Nudge"), N_("Auto")]

# Driving Style -> (LongitudinalPersonality, AccelerationProfile, DecelerationProfile). Standard is StarPilot's default.
STYLE_PARAMS = [
  (2, ACCEL["ECO"], DECEL["ECO"]),
  (1, ACCEL["STANDARD"], DECEL["ECO"]),
  (0, ACCEL["SPORT"], DECEL["SPORT"]),
]
OFFSET_KEYS = [f"Offset{i}" for i in range(1, 8)]
SMART_SLOWDOWN_TRIGGERS = ["CECurves", "CEStopLights", "CELead", "CESlowerLead", "CEStoppedLead"]
OFFSET_MAX = 15


class SpeedSteering:
  """Reads and writes the grouped settings; the screen and the hub tile both use it."""

  def __init__(self, store: SettingsStore):
    self._store = store

  @property
  def safe_mode(self) -> bool:
    return self._store.get_bool("SafeMode")

  @property
  def style(self) -> int:
    personality = self._store.get_int("LongitudinalPersonality")
    return next((i for i, (p, _, _) in enumerate(STYLE_PARAMS) if p == personality), 1)

  def set_style(self, index: int) -> None:
    personality, accel, decel = STYLE_PARAMS[index]
    self._store.write({"LongitudinalPersonality": personality, "AccelerationProfile": accel, "DecelerationProfile": decel})

  @property
  def speed_limits(self) -> int:
    if self._store.get_bool("SpeedLimitController"):
      return 2
    return 1 if self._store.get_bool("ShowSpeedLimits") else 0

  def set_speed_limits(self, index: int) -> None:
    """Match runs the speed limit controller, and also sets cruise to the limit when engaging."""
    match = index == 2
    self._store.write({"ShowSpeedLimits": index > 0, "SpeedLimitController": match, "SetSpeedLimit": match})

  @property
  def matching(self) -> bool:
    return self.speed_limits == 2

  @property
  def offset(self) -> float:
    return self._store.get_float(OFFSET_KEYS[0])

  def set_offset(self, value: float) -> None:
    """One offset for every speed range, so a matched limit is always the sign plus the same amount."""
    self._store.write({key: float(value) for key in OFFSET_KEYS})

  @property
  def unit(self) -> str:
    return "km/h" if self._store.get_bool("IsMetric") else "mph"

  @property
  def lane_change_speed(self) -> int:
    return round(self._store.get_float("MinimumLaneChangeSpeed"))

  def _asks(self, key: str) -> int:
    return 1 if self._store.get_bool("SLCConfirmation") and self._store.get_bool(key) else 0

  def _set_asks(self, higher: bool, lower: bool) -> None:
    """StarPilot's Confirm New Limits is on while either direction asks; Confirm Higher and Confirm Lower say which."""
    self._store.write({"SLCConfirmation": higher or lower, "SLCConfirmationHigher": higher, "SLCConfirmationLower": lower})

  @property
  def higher_limits(self) -> int:
    return self._asks("SLCConfirmationHigher")

  def set_higher_limits(self, index: int) -> None:
    self._set_asks(index == 1, bool(self.lower_limits))

  @property
  def lower_limits(self) -> int:
    return self._asks("SLCConfirmationLower")

  def set_lower_limits(self, index: int) -> None:
    self._set_asks(bool(self.higher_limits), index == 1)

  @property
  def max_follows(self) -> bool:
    return MAX_FOLLOWS_LIMIT.get()

  def set_max_follows(self, on: bool) -> None:
    MAX_FOLLOWS_LIMIT.set(on)

  @property
  def lane_changes(self) -> int:
    return 1 if self._store.get_bool("NudgelessLaneChange") else 0

  def set_lane_changes(self, index: int) -> None:
    self._store.write({"LaneChanges": True, "NudgelessLaneChange": index == 1})

  @property
  def smart_slowdowns(self) -> bool:
    return self._store.get_bool("ConditionalExperimental") and self._store.get_bool("CurveSpeedController")

  def set_smart_slowdowns(self, on: bool) -> None:
    """Switches to experimental mode for curves, lights and slower or stopped cars, and slows for curves ahead."""
    values: dict[str, bool | int | float] = {"ConditionalExperimental": on, "CurveSpeedController": on}
    if on:
      values |= {"ConditionalChill": False} | dict.fromkeys(SMART_SLOWDOWN_TRIGGERS, True)
    self._store.write(values)

  @property
  def always_on_steering(self) -> bool:
    return self._store.get_bool("AlwaysOnLateral")

  def set_always_on_steering(self, on: bool) -> None:
    self._store.write({"AlwaysOnLateral": on})

  def summary(self) -> str:
    lanes = N_("Auto lane change") if self.lane_changes else N_("Nudge to change lanes")
    return f"{STYLES[self.style]} · {lanes}"

  def speed_limit_summary(self) -> str:
    return [N_("Speed limits off"), N_("Showing speed limits"), N_("Matching speed limits")][self.speed_limits]


def everyday_panel(model: SpeedSteering) -> ListPanel:
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
  follows = SettingRow(N_("MAX follows limits"), N_("Each new limit sets MAX, so it slows promptly for lower ones"), indent=True,
                       control=Switch(lambda: model.max_follows, model.set_max_follows))
  for row in (offset, higher, lower, follows):
    row.set_visible(lambda: model.matching)

  rows = [
    style,
    SettingRow(N_("Speed Limits"), N_("Match sets cruise to the posted limit"),
               Segmented(SPEED_LIMITS, lambda: model.speed_limits, model.set_speed_limits)),
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


# ── Vehicle Profile ──

PROFILES = [(N_("Car"), N_("Standard tuning for most cars and SUVs")), ("EV", N_("Smoother take-off and regen-aware braking")),
            (N_("Truck"), N_("Gentler acceleration for heavier vehicles")), (N_("Towing"), N_("Truck tuning plus room for a trailer"))]
TRAILER_LOADS = [N_("Light"), N_("Medium"), N_("Heavy")]
TRAILER_POUNDS = [2000, 5000, 8000]   # StarPilot's TrailerLoad is in pounds


class VehicleProfile:
  def __init__(self, store: SettingsStore):
    self._store = store

  @property
  def profile(self) -> int:
    if self._store.get_bool("TruckTuning"):
      return 3 if self._store.get_int("TrailerLoad") > 0 else 2
    return 1 if self._store.get_bool("EVTuning") else 0

  def set_profile(self, index: int) -> None:
    load = TRAILER_POUNDS[self.trailer_load] if index == 3 else 0
    self._store.write({"EVTuning": index == 1, "TruckTuning": index >= 2, "TrailerLoad": load})

  @property
  def towing(self) -> bool:
    return self.profile == 3

  @property
  def trailer_load(self) -> int:
    """Nearest preset to the stored weight; Medium when nothing is set."""
    pounds = self._store.get_int("TrailerLoad") or TRAILER_POUNDS[1]
    return min(range(len(TRAILER_POUNDS)), key=lambda i: abs(TRAILER_POUNDS[i] - pounds))

  def set_trailer_load(self, index: int) -> None:
    self._store.write({"TrailerLoad": TRAILER_POUNDS[index]})

  def summary(self) -> str:
    return PROFILES[self.profile][0]


def vehicle_profile_panel(model: VehicleProfile) -> Widget:
  """The profiles as tiles filling the panel, then Trailer Load. No line under the title, as in the mock."""
  load = SettingRow(N_("Trailer Load"), lambda: N_("Weight of a loaded trailer") if model.towing else N_("Available with Towing"),
                    Segmented(TRAILER_LOADS, lambda: model.trailer_load, model.set_trailer_load, height=T.px(44),
                              font_size=T.font_px(15)), height=T.px(64))
  load.set_enabled(lambda: model.towing)
  return Card([
    Padded(Stack([Label(N_("Vehicle Profile"), T.SIZE_PANEL_TITLE),
                  Label(N_("Adjusts acceleration and braking for what you drive"), T.SIZE_SUBTITLE, T.TEXT_TERTIARY, T.FONT)], gap=T.px(3)),
           x=T.px(22), y=0),
    Padded(ChoiceCards(PROFILES, lambda: model.profile, model.set_profile, large=TILE_CARDS), x=T.px(18), y=0),
    Rule(dim=lambda: not model.towing),
    load,
  ], gap=T.px(12), padding=(0, T.px(16)), background=T.SURFACE_2, grow=1)


# ── Weather ──

WEATHER = [N_("Auto"), N_("Off")]
# Condition -> (param suffix, extra following seconds, % less acceleration, % less curve speed). Placeholders to tune on real drives.
WEATHER_PRESETS = [
  ("LowVisibility", 0.5, 0, 0),
  (N_("Rain"), 0.5, 10, 10),
  ("RainStorm", 1.0, 20, 20),
  (N_("Snow"), 1.5, 30, 25),
]


class Weather:
  def __init__(self, store: SettingsStore):
    self._store = store

  @property
  def mode(self) -> int:
    return 0 if self._store.get_bool("WeatherPresets") else 1

  def set_mode(self, index: int) -> None:
    values: dict = {"WeatherPresets": index == 0}
    if index == 0:
      for suffix, following, accel, lateral in WEATHER_PRESETS:
        values |= {f"IncreaseFollowing{suffix}": following, f"ReduceAcceleration{suffix}": accel,
                   f"ReduceLateralAcceleration{suffix}": lateral}
    self._store.write(values)

  def summary(self) -> str:
    return WEATHER[self.mode]

  @property
  def heads_up(self) -> bool:
    return WEATHER_HEADS_UP.get()

  def set_heads_up(self, on: bool) -> None:
    WEATHER_HEADS_UP.set(on)


def weather_panel(model: Weather) -> ListPanel:
  conditions = [(N_("Fog or low visibility"), N_("Longer following gap"), "fog"), (N_("Rain"), N_("Longer gap, earlier braking"), "rain"),
                (N_("Heavy rain or storms"), N_("More gap, softer acceleration"), "storm"),
                (N_("Snow or ice"), N_("Most gap, gentlest starts and stops"), "snow")]
  cards = [InfoCard(title, line, icon) for title, line, icon in conditions]
  for card in cards:
    card.set_enabled(lambda: model.mode == 0)
  heads_up = SettingRow(N_("Weather heads-up"), N_("Warns before rain, snow or storms start, and says when they should stop"),
                        Switch(lambda: model.heads_up, model.set_heads_up))
  return ListPanel([SectionHeader(N_("WHAT CHANGES")), Padded(Grid(cards), x=T.px(16), y=T.px(6)), heads_up], title=N_("Weather"),
                   subtitle=N_("Drives more cautiously in bad conditions, using local weather"),
                   header_control=Segmented(WEATHER, lambda: model.mode, model.set_mode),
                   footnote=N_("Needs an internet connection. Chips show it ahead and while it lasts."), footnote_divider=True)


# ── Assistance: openpilot's own switches ──

# sentryd's motion threshold (m/s² of change): lower notices smaller bumps. Standard is StarPilot's default.
SENTRY_SENSITIVITY = [(N_("Low"), 0.08), (N_("Standard"), 0.04), (N_("High"), 0.02)]

class Assistance:
  def __init__(self, store: SettingsStore, live):
    self._store = store
    self._live = live

  def get(self, key: str) -> bool:
    return self._store.get_bool(key)

  def setter(self, key: str):
    return lambda on: self._store.write({key: on})

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

  @property
  def sentry(self) -> bool:
    return self.get("SentryModeEnabled")

  def set_sentry(self, on: bool) -> None:
    self._store.write({"SentryModeEnabled": on})

  @property
  def sentry_sensitivity(self) -> int:
    """Index into SENTRY_SENSITIVITY, or -1 for a value set elsewhere (Galaxy's slider)."""
    value = self._store.get_float("SentryModeSensitivity") or SENTRY_SENSITIVITY[1][1]
    return next((i for i, (_, threshold) in enumerate(SENTRY_SENSITIVITY) if abs(value - threshold) < 1e-6), -1)

  def set_sentry_sensitivity(self, index: int) -> None:
    self._store.write({"SentryModeSensitivity": SENTRY_SENSITIVITY[index][1]})

  def monitoring_summary(self) -> str:
    return N_("Driver monitoring always on") if self.get("AlwaysOnDM") else N_("Driver monitoring while engaged")


def assistance_panel(model: Assistance) -> ListPanel:
  def switch(title: str, subtitle: str, key: str, on_change=None, restarts: bool = False) -> SettingRow:
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
    SettingRow(N_("Sentry Mode"), N_("Pictures in Galaxy if the parked car is bumped"),
               Switch(lambda: model.sentry, model.set_sentry)),
    SettingRow(N_("Sensitivity"), N_("High notices smaller bumps"), indent=True,
               control=Segmented([name for name, _ in SENTRY_SENSITIVITY], lambda: model.sentry_sensitivity, model.set_sentry_sensitivity,
                                 height=T.px(42), font_size=T.font_px(15))),   # as the other sub-rows' choices
  ], title=N_("Driver Monitoring"), subtitle=N_("Watches that you're paying attention"))


# ── Navigation ──

class Navigation:
  """Home, Work and favorites are StarPilot's FavoriteDestinations; picking a place uses its destination search."""

  def __init__(self, store: SettingsStore):
    self._store = store

  def _favorites(self) -> list[dict]:
    value = self._store.get_json("FavoriteDestinations")
    return value if isinstance(value, list) else []

  def _place(self, flag: str) -> str | None:
    place = next((f for f in self._favorites() if f.get(flag)), None)
    return str(place.get("name") or N_("Saved place")) if place else None

  def home(self) -> str | None:
    return self._place("is_home")

  def work(self) -> str | None:
    return self._place("is_work")

  def others(self) -> int:
    return sum(1 for f in self._favorites() if not f.get("is_home") and not f.get("is_work"))

  @property
  def end_when_parked(self) -> bool:
    return self._store.get_bool("ClearNavOnOffroad")

  def set_end_when_parked(self, on: bool) -> None:
    self._store.write({"ClearNavOnOffroad": on})

  def mapbox_status(self) -> tuple[str, bool]:
    """The Mapbox Key row's line, and whether both keys are saved."""
    from openpilot.selfdrive.ui.tandem.mapbox_help import status
    return status(self._store.get_str)


def navigation_panel(model: Navigation, open_destinations, open_offline_maps, open_mapbox_help=lambda: None) -> ListPanel:

  def place(title: str, icon: str, get) -> SettingRow:
    return SettingRow(title, lambda: get() or N_("Not set"), Button(lambda: N_("Change") if get() else N_("Set"), open_destinations),
                      leading=Icon(icon))

  return ListPanel([
    place(N_("Home"), "home", model.home),
    place(N_("Work"), "work", model.work),
    SettingRow(N_("Other favorites"), lambda: t_("{} saved", model.others()), on_click=open_destinations, leading=Icon("star")),
    SettingRow(N_("End Route When Parked"), N_("Clears the destination when you turn off the car"),
               Switch(lambda: model.end_when_parked, model.set_end_when_parked)),
    SettingRow(N_("Mapbox Keys"), lambda: model.mapbox_status()[0],
               Button(lambda: N_("How to change") if model.mapbox_status()[1] else N_("How to add"), open_mapbox_help),
               subtitle_color=lambda: T.SUCCESS_TEXT if model.mapbox_status()[1] else T.WARNING),
    SettingRow(N_("Offline Maps"), N_("Speed limits and routing without a connection"), on_click=open_offline_maps),
  ], title=N_("Navigation"), subtitle=N_("While a route is active, the car slows for turns and uses route speed limits"))
