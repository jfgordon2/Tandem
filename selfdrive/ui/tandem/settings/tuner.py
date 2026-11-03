"""Tuner Mode: raw values behind the presets, each showing where it comes from, and per-item bundle overrides.

A value is DEFAULT when it equals the car's stock value (StarPilot keeps it in the matching *Stock param) or the
param default, OVERRIDE when it differs, and LEARNED while openpilot learns it (steering delay). FROM STYLE marks
the profiles that Driving Style sets.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Badge, Button, ButtonStyle, Segmented, Switch, Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow
from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW, LEAD_INSIGHTS, Bundle
from openpilot.selfdrive.ui.tandem.settings.editors import NumberSpec, number_sheet
from openpilot.selfdrive.ui.tandem.settings.speed_steering import STYLE_PARAMS, SpeedSteering
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

DEFAULT, OVERRIDE, LEARNED, FROM_STYLE = N_("Default"), N_("Override"), N_("Learned"), N_("From style")
_TONES = {DEFAULT: Tone.NEUTRAL, OVERRIDE: Tone.WARNING, LEARNED: Tone.SUCCESS, FROM_STYLE: Tone.ACCENT}


@dataclass(frozen=True)
class Tunable:
  key: str
  title: str
  subtitle: str
  spec: NumberSpec
  stock_key: str | None = None       # the car's own value; falls back to spec.default
  learned_key: str | None = None     # a switch that, when on, makes openpilot learn the value
  enable: dict = field(default_factory=dict)   # master switches the value needs


def _f(digits: int, unit: str = "") -> Callable[[float], str]:
  return lambda v: f"{v:.{digits}f}{unit}"


LATERAL = {"AdvancedLateralTune": True}
LONGITUDINAL = {"AdvancedLongitudinalTune": True}

STEERING = [
  Tunable("SteerDelay", N_("Steering Delay"), N_("Time from command to wheel response"), NumberSpec(0.01, 1.0, 0.01, 0.1, _f(2, " s")),
          "SteerDelayStock", learned_key="UseAutoSteerDelay", enable=LATERAL),
  Tunable("SteerFriction", N_("Friction"), N_("Extra torque near center"), NumberSpec(0.0, 1.0, 0.01, 0.1, _f(2)), "SteerFrictionStock",
          enable=LATERAL),
  Tunable("SteerLatAccel", N_("Lateral Acceleration"), N_("Torque to cornering scaling"), NumberSpec(0.5, 5.0, 0.05, 2.5, _f(2)),
          "SteerLatAccelStock", enable=LATERAL),
  Tunable("SteerKP", N_("Kp Factor"), N_("Correction strength"), NumberSpec(0.1, 3.0, 0.05, 1.0, _f(2)), "SteerKPStock", enable=LATERAL),
]
GAS_BRAKE = [
  Tunable("MaxDesiredAcceleration", N_("Maximum Acceleration"), N_("The hardest openpilot will accelerate"),
          NumberSpec(0.1, 4.0, 0.1, 4.0, _f(1, " m/s²")), enable=LONGITUDINAL),
  Tunable("StartAccel", N_("Start Acceleration"), N_("How firmly the car pulls away from a stop"), NumberSpec(0.0, 4.0, 0.05, 0.0, _f(2, " m/s²")),
          "StartAccelStock", enable=LONGITUDINAL),
  Tunable("StopAccel", N_("Stop Acceleration"), N_("Braking held while stopped"), NumberSpec(-4.0, 0.0, 0.05, 0.0, _f(2, " m/s²")),
          "StopAccelStock", enable=LONGITUDINAL),
  Tunable("StoppingDecelRate", N_("Stopping Rate"), N_("How quickly braking builds into a stop"), NumberSpec(0.01, 1.0, 0.01, 0.8, _f(2)),
          "StoppingDecelRateStock", enable=LONGITUDINAL),
  Tunable("LongitudinalActuatorDelay", N_("Actuator Delay"), N_("Time from command to gas or brake response"),
          NumberSpec(0.0, 1.0, 0.01, 0.15, _f(2, " s")), "LongitudinalActuatorDelayStock", enable=LONGITUDINAL),
]
FOLLOWING = [
  Tunable("LeadDetectionThreshold", N_("Lead Detection Sensitivity"), N_("Lower notices cars ahead sooner"),
          NumberSpec(25, 50, 1, 35, lambda v: f"{v:.0f}%", (25, 35, 50))),
  Tunable("IncreasedStoppedDistance", N_("Stopped Distance"), N_("Extra room left behind a stopped car"),
          NumberSpec(0, 10, 1, 0, lambda v: f"+{v:.0f}", (0, 3, 5, 10)), enable={"QOLLongitudinal": True}),
]
# Following gap per Driving Style, plus Traffic mode. Seconds behind the car ahead.
GAPS = [(N_("Relaxed"), "RelaxedFollow", 1.6), (N_("Standard"), "StandardFollow", 1.45), (N_("Sport"), "AggressiveFollow", 1.25),
        (N_("Traffic"), "TrafficFollow", 0.75)]
CONTROLLERS = [N_("Auto"), N_("NNFF"), N_("Lite"), N_("Torque")]
DEFAULT_CONTROLLER = 3   # Torque: NNFF and NNFF Lite stay opt-in
_CONTROLLER_PARAMS = [
  {"NNFF": True, "NNFFLite": True, "ForceTorqueController": False},    # NNFF where the car has a model, otherwise Lite
  {"NNFF": True, "NNFFLite": False, "ForceTorqueController": False},
  {"NNFF": False, "NNFFLite": True, "ForceTorqueController": False},
  {"NNFF": False, "NNFFLite": False, "ForceTorqueController": True},
]
ACCEL_PROFILES = [(N_("Eco"), 1), (N_("Standard"), 0), (N_("Sport"), 2), ("Sport+", 3)]
DECEL_PROFILES = [(N_("Eco"), 1), (N_("Standard"), 0), (N_("Sport"), 2)]
CRUISE_STEPS = [1, 5, 10]
# Bundles listed under Bundle Overrides: name, the keys a driver can override, and the value each has with the bundle on.
ITEM_NAMES = {
  "DeveloperSidebar": N_("Developer sidebar"), "FPSCounter": N_("FPS counter"), "ShowCPU": N_("CPU load"), "ShowGPU": N_("GPU load"),
  "NumericalTemp": N_("Numeric temperature"), "ShowMemoryUsage": N_("Memory use"), "AdjacentPathMetrics": N_("Adjacent lane widths"),
  "SpeedLimitSources": N_("Speed limit sources"), "LeadInfo": N_("Lead details on the tag"), "RadarTracksUI": N_("Radar points"),
  "ShowStoppingPoint": N_("Stopping point"), "ShowStoppingPointMetrics": N_("Stopping point distance"), "AdjacentPath": N_("Adjacent paths"),
  "PedalsOnUI": N_("Pedals"),
}
OVERRIDE_BUNDLES = [DEVELOPER_VIEW, LEAD_INSIGHTS]


class Tuner:
  def __init__(self, store: SettingsStore):
    self._store = store
    self._speed = SpeedSteering(store)

  # Single values

  def value(self, t: Tunable) -> float:
    return self._store.get_float(t.key)

  def baseline(self, t: Tunable) -> float:
    if t.stock_key is not None:
      stock = self._store.get_float(t.stock_key)
      if stock:
        return stock
    return t.spec.default

  def status(self, t: Tunable) -> str:
    if t.learned_key is not None and self._store.get_bool(t.learned_key):
      return LEARNED
    return DEFAULT if abs(self.value(t) - self.baseline(t)) < t.spec.step / 2 else OVERRIDE

  def set_value(self, t: Tunable, value: float) -> None:
    values = dict(t.enable) | {t.key: float(value)}
    if t.learned_key is not None:
      values[t.learned_key] = False
    self._store.write(values)

  def reset(self, t: Tunable) -> None:
    values = {t.key: float(self.baseline(t))}
    if t.learned_key is not None:
      values[t.learned_key] = True
    self._store.write(values)

  # Choices

  @property
  def controller(self) -> int:
    nnff, lite, torque = (self._store.get_bool(k) for k in (N_("NNFF"), "NNFFLite", "ForceTorqueController"))
    if torque:
      return 3
    if nnff:
      return 0 if lite else 1
    return 2 if lite else -1

  def set_controller(self, index: int) -> None:
    self._store.write(LATERAL | _CONTROLLER_PARAMS[index])

  def _profile(self, key: str, profiles: list[tuple[str, int]]) -> int:
    value = self._store.get_int(key)
    return next((i for i, (_, v) in enumerate(profiles) if v == value), 1)

  @property
  def accel_profile(self) -> int:
    return self._profile("AccelerationProfile", ACCEL_PROFILES)

  def set_accel_profile(self, index: int) -> None:
    self._store.write({"AccelerationProfile": ACCEL_PROFILES[index][1]})

  @property
  def decel_profile(self) -> int:
    return self._profile("DecelerationProfile", DECEL_PROFILES)

  def set_decel_profile(self, index: int) -> None:
    self._store.write({"DecelerationProfile": DECEL_PROFILES[index][1]})

  def _style_profile(self, key: str) -> int:
    _, accel, decel = STYLE_PARAMS[self._speed.style]
    return accel if key == "AccelerationProfile" else decel

  def profile_status(self, key: str) -> str:
    return FROM_STYLE if self._store.get_int(key) == self._style_profile(key) else OVERRIDE

  def reset_profile(self, key: str) -> None:
    """Back to the profile the Driving Style sets."""
    self._store.write({key: self._style_profile(key)})

  def gap(self, key: str) -> float:
    return self._store.get_float(key)

  def set_gap(self, key: str, seconds: float) -> None:
    self._store.write({"CustomPersonalities": True, key: round(seconds, 2)})

  def switch(self, key: str) -> bool:
    return self._store.get_bool(key)

  def set_switch(self, key: str, on: bool, enable: dict | None = None) -> None:
    self._store.write((enable or {}) | {key: on})

  @property
  def cruise_step(self) -> int:
    step = self._store.get_float("CustomCruise")
    return min(range(len(CRUISE_STEPS)), key=lambda i: abs(CRUISE_STEPS[i] - step))

  def set_cruise_step(self, index: int) -> None:
    self._store.write({"CustomCruise": float(CRUISE_STEPS[index])})

  # Bundle overrides

  def bundle_items(self, bundle: Bundle) -> list[str]:
    return [k for k in bundle.on if k in ITEM_NAMES]

  def bundle_on(self, bundle: Bundle) -> bool:
    return bundle.is_on(self._store)

  def item_differs(self, bundle: Bundle, key: str) -> bool:
    on = self.bundle_on(bundle)
    expected = bundle.on[key] if on else bundle.off.get(key, bundle.on[key])
    return self._store.get_bool(key) != expected

  def bundle_changes(self, bundle: Bundle) -> int:
    return sum(self.item_differs(bundle, k) for k in self.bundle_items(bundle))

  # Developer View's strip: up to STRIP_MAX metrics, kept in STRIP_METRICS order

  def strip(self) -> list[str]:
    from openpilot.selfdrive.ui.tandem.onroad.developer import strip_keys
    from openpilot.selfdrive.ui.tandem.prefs import DEVELOPER_STRIP
    return strip_keys(DEVELOPER_STRIP.get())   # unset reads as the default; picking none saves "none"

  def toggle_strip(self, key: str) -> None:
    """Adds or removes a metric. Adding one past the limit does nothing; the picker shows it as unavailable."""
    from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_MAX, STRIP_METRICS
    picked = self.strip()
    if key in picked:
      picked.remove(key)
    elif len(picked) < STRIP_MAX and key in STRIP_METRICS:
      picked.append(key)
    from openpilot.selfdrive.ui.tandem.prefs import DEVELOPER_STRIP
    DEVELOPER_STRIP.set(",".join(k for k in STRIP_METRICS if k in picked) or "none")

  # Counts and reset

  def changed(self, tunables: list[Tunable]) -> int:
    return sum(self.status(t) == OVERRIDE for t in tunables)

  def gas_brake_changes(self) -> int:
    profiles = sum(self.profile_status(k) == OVERRIDE for k in ("AccelerationProfile", "DecelerationProfile"))
    return self.changed(GAS_BRAKE) + profiles

  def following_changes(self) -> int:
    return self.changed(FOLLOWING) + sum(abs(self.gap(key) - default) > 0.01 for _, key, default in GAPS)

  def reset_all(self) -> None:
    values: dict = {}
    for t in STEERING + GAS_BRAKE + FOLLOWING:
      values[t.key] = float(self.baseline(t))
      if t.learned_key is not None:
        values[t.learned_key] = True
    _, accel, decel = STYLE_PARAMS[self._speed.style]
    values |= {"AccelerationProfile": accel, "DecelerationProfile": decel} | _CONTROLLER_PARAMS[DEFAULT_CONTROLLER]
    values |= {key: default for _, key, default in GAPS} | {"CustomCruise": 1.0}
    for bundle in OVERRIDE_BUNDLES:
      on = bundle.is_on(self._store)
      values |= {k: v for k, v in (bundle.on if on else bundle.off).items() if k in ITEM_NAMES}
    from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_DEFAULT
    from openpilot.selfdrive.ui.tandem.prefs import DEVELOPER_STRIP
    DEVELOPER_STRIP.set(",".join(STRIP_DEFAULT))
    self._store.write(values)


def _changed_label(count: int) -> str:
  return t_("{} changed", count) if count else ""


def tunable_row(tuner: Tuner, t: Tunable, window) -> SettingRow:
  def edit():
    window.present(number_sheet(window, t.title, t.subtitle, NumberSpec(t.spec.minimum, t.spec.maximum, t.spec.step, tuner.baseline(t),
                                                                        t.spec.fmt, t.spec.picks),
                                lambda: tuner.value(t), lambda v: tuner.set_value(t, v)))

  def action():
    if tuner.status(t) == OVERRIDE:
      tuner.reset(t)
    else:
      edit()

  return SettingRow(t.title, t.subtitle, ValueStatus(lambda: t.spec.fmt(tuner.value(t)), lambda: tuner.status(t),
                                                     Button(lambda: N_("Reset") if tuner.status(t) == OVERRIDE else N_("Override"), action,
                                                            height=T.px(40)), on_value=edit))


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

  def _render(self, rect: rl.Rectangle):
    button_w = T.px(108)
    value, badge, button = row(rect, [FILL, T.px(96), button_w], T.px(10))
    draw.text(value, self._value(), T.font_px(18), T.TEXT, T.FONT_SEMIBOLD, h=Align.END)
    bw, bh = self._badge.preferred_size(badge.width)
    self._badge.render(rl.Rectangle(badge.x + (badge.width - bw) / 2, badge.y + (badge.height - bh) / 2, bw, bh))
    self._button.render(rl.Rectangle(button.x, button.y + (button.height - T.px(40)) / 2, button.width, T.px(40)))


def steering_panel(tuner: Tuner, window) -> ListPanel:
  return ListPanel([
    *[tunable_row(tuner, t, window) for t in STEERING],
    SettingRow(N_("Steering Controller"), N_("Auto uses NNFF when your car has a model"),
               Segmented(CONTROLLERS, lambda: tuner.controller, tuner.set_controller)),
  ], title=N_("Steering"), subtitle=N_("Learned values work for most cars. An override replaces the learned value until you reset it."))


def gas_brake_panel(tuner: Tuner, window) -> ListPanel:
  def profile(title: str, subtitle: str, key: str, profiles, get, set_) -> SettingRow:
    """As the mock: the profile, FROM STYLE or OVERRIDE, and Override (a picker) or Reset (back to the style's)."""
    from openpilot.selfdrive.ui.tandem.rows import OptionList

    def pick() -> None:
      def choose(index: int) -> None:
        set_(index)
        window.dismiss()
      window.present(Sheet(title, OptionList([name for name, _ in profiles], get, choose),
                           subtitle=N_("Replaces the profile your Driving Style sets, until you reset it"),
                           actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss))

    def action() -> None:
      if tuner.profile_status(key) == OVERRIDE:
        tuner.reset_profile(key)
      else:
        pick()
    return SettingRow(title, subtitle, ValueStatus(lambda: profiles[get()][0], lambda: tuner.profile_status(key),
                                                   Button(lambda: N_("Reset") if tuner.profile_status(key) == OVERRIDE else N_("Override"), action,
                                                          height=T.px(40)), on_value=pick))

  return ListPanel([
    profile(N_("Acceleration Profile"), N_("How quickly the car speeds up"), "AccelerationProfile", ACCEL_PROFILES, lambda: tuner.accel_profile,
            tuner.set_accel_profile),
    profile(N_("Braking Profile"), N_("How early and firmly it slows down"), "DecelerationProfile", DECEL_PROFILES, lambda: tuner.decel_profile,
            tuner.set_decel_profile),
    *[tunable_row(tuner, t, window) for t in GAS_BRAKE],
  ], title=N_("Gas & Brake"), subtitle=N_("Driving Style and Vehicle Profile set these. An override replaces their value."))


class GapCells(Component):
  """The four following gaps as one row of cells, as in the mock: the style, then its gap. A changed gap shows in amber;
  tapping a cell edits it."""
  grow_touch_target = False
  GAP = T.px(10)

  def __init__(self, tuner: Tuner, window):
    super().__init__()
    self._tuner, self._window = tuner, window
    self._pressed: int | None = None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(14) + draw.line_height(T.font_px(17)) + T.px(10) + T.px(68) + T.px(14)

  def _cells(self, rect: rl.Rectangle) -> list[rl.Rectangle]:
    body = inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(14))
    top = body.y + draw.line_height(T.font_px(17)) + T.px(10)
    return row(rl.Rectangle(body.x, top, body.width, T.px(68)), [FILL] * len(GAPS), self.GAP)

  def _hit(self, pos) -> int | None:
    return next((i for i, cell in enumerate(self._cells(self._rect)) if rl.check_collision_point_rec(pos, cell)), None)

  def _handle_mouse_press(self, mouse_pos) -> None:
    self._pressed = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed:
      self.edit(hit)
    self._pressed = None

  def edit(self, index: int) -> None:
    name, key, default = GAPS[index]
    tuner, window = self._tuner, self._window
    window.present(number_sheet(window, t_("{} gap", name), N_("Seconds behind the car ahead in this Driving Style"),
                                NumberSpec(0.5, 3.0, 0.05, default, lambda v: t_("{} s", f"{v:.2f}")),
                                lambda: tuner.gap(key), lambda v: tuner.set_gap(key, v)))

  def _render(self, rect: rl.Rectangle):
    body = inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(14))
    draw.text(rl.Rectangle(body.x, body.y, body.width, draw.line_height(T.font_px(17))), N_("Following gap by style"), T.font_px(17), T.TEXT,
              T.FONT_BOLD)
    for i, ((name, key, default), cell) in enumerate(zip(GAPS, self._cells(rect), strict=True)):
      draw.fill(cell, T.SURFACE_4, T.px(14))
      if self.is_pressed and i == self._pressed:
        draw.pressed(cell, T.px(14))
      top, bottom = column(inset(cell, x=T.px(16), y=T.px(10)), [draw.line_height(T.font_px(14)), FILL], T.px(2))
      draw.text(top, name, T.font_px(14), T.TEXT_TERTIARY)
      value = self._tuner.gap(key)
      changed = abs(value - default) > 0.01
      draw.text(bottom, t_("{} s", f"{value:.2f}"), T.font_px(22), T.WARNING if changed else T.TEXT, T.FONT_BOLD)


def following_panel(tuner: Tuner, window) -> ListPanel:
  return ListPanel([
    GapCells(tuner, window),
    *[tunable_row(tuner, t, window) for t in FOLLOWING],
    SettingRow(N_("Use Radar for Take-Offs"), N_("Starts moving as soon as the radar sees the car ahead pull away"),
               Switch(lambda: tuner.switch("RadarTakeoffs"), lambda on: tuner.set_switch("RadarTakeoffs", on))),
    SettingRow(N_("Force Stops at Lights"), N_("Comes to a full stop for red lights the model detects"),
               Switch(lambda: tuner.switch("ForceStops"), lambda on: tuner.set_switch("ForceStops", on, {"QOLLongitudinal": True}))),
    SettingRow(N_("Cruise Button Step"), N_("How far one press of + or − moves the set speed"),
               Segmented([str(s) for s in CRUISE_STEPS], lambda: tuner.cruise_step, tuner.set_cruise_step)),
  ], title=N_("Following & Stops"))


class StripPicker(Component):
  """Developer View's bar metrics: a grid of tiles, each picked or not. Once five are picked the rest dim until one is
  taken away."""
  grow_touch_target = False
  COLUMNS, TILE, GAP = 3, T.px(78), T.px(10)

  def __init__(self, tuner: Tuner):
    from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_METRICS
    super().__init__()
    self._tuner = tuner
    self._keys = list(STRIP_METRICS)
    self._pressed: str | None = None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    rows = -(-len(self._keys) // self.COLUMNS)
    return max_width, rows * self.TILE + (rows - 1) * self.GAP

  def _cells(self, rect: rl.Rectangle) -> list[tuple[str, rl.Rectangle]]:
    w = (rect.width - self.GAP * (self.COLUMNS - 1)) / self.COLUMNS
    return [(k, rl.Rectangle(rect.x + (i % self.COLUMNS) * (w + self.GAP), rect.y + (i // self.COLUMNS) * (self.TILE + self.GAP), w, self.TILE))
            for i, k in enumerate(self._keys)]

  def _hit(self, pos) -> str | None:
    return next((k for k, cell in self._cells(self._rect) if rl.check_collision_point_rec(pos, cell)), None)

  def _handle_mouse_press(self, mouse_pos) -> None:
    self._pressed = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed:
      self._tuner.toggle_strip(hit)
    self._pressed = None

  def _render(self, rect: rl.Rectangle):
    from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_MAX, STRIP_METRICS
    picked = self._tuner.strip()
    full = len(picked) >= STRIP_MAX
    for key, cell in self._cells(rect):
      on = key in picked
      draw.fill(cell, T.ACCENT_SELECTED if on else T.SURFACE_4, T.px(14))
      if on:
        draw.stroke(cell, T.ACCENT, T.px(14), T.px(2))
      elif self.is_pressed and key == self._pressed:
        draw.pressed(cell, T.px(14))
      body = inset(cell, x=T.px(16), y=T.px(12))
      label, line = column(body, [draw.line_height(T.font_px(17)), FILL], T.px(2))
      dim = full and not on
      draw.text(label, STRIP_METRICS[key][0], T.font_px(17), T.TEXT_MUTED if dim else T.TEXT, T.FONT_MONO_BOLD)
      draw.text(line, draw.fit(STRIP_METRICS[key][1], T.font_px(14), T.FONT, line.width - T.px(26)), T.font_px(14),
                T.TEXT_MUTED if dim else T.TEXT_TERTIARY, v=Align.START)
      if on:
        draw.check(rl.Rectangle(body.x + body.width - T.px(18), label.y, T.px(18), label.height), T.ACCENT_TEXT, T.px(18))


def strip_sheet(tuner: Tuner, window) -> Sheet:
  from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_MAX
  return Sheet(N_("Bar metrics"), StripPicker(tuner),
               subtitle=lambda: t_("{} of {} picked. They spread evenly across the bar; pick none to hide it.", len(tuner.strip()), STRIP_MAX),
               actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss)


class BundleOverrides(Component):
  """One panel: the bundle tabs and whether that bundle is on, then a switch per param it sets in two columns, marked
  OVERRIDE where it differs from the bundle."""
  grow_touch_target = False
  HEADER = T.px(64)
  ROW = T.px(50)

  def __init__(self, tuner: Tuner, window=None):
    super().__init__()
    self._tuner = tuner
    self._tab = 0
    self._choose = self._child(Button(N_("Choose"), lambda: window.present(strip_sheet(tuner, window)) if window else None,
                                      ButtonStyle.SECONDARY, height=T.px(40), font_size=T.font_px(15), weight=T.FONT_BOLD))
    self._tabs = self._child(Segmented([b.name for b in OVERRIDE_BUNDLES], lambda: self._tab, self._select, height=T.px(48),
                                       font_size=T.font_px(15)))
    self._items = []
    for bundle in OVERRIDE_BUNDLES:
      rows = []
      for key in tuner.bundle_items(bundle):
        badge = self._child(Badge(N_("Override"), Tone.WARNING))
        switch = self._child(Switch(lambda k=key: tuner.switch(k), lambda on, k=key: tuner.set_switch(k, on), width=T.px(52), height=T.px(30)))
        rows.append((key, badge, switch))
      self._items.append(rows)

  def _select(self, index: int) -> None:
    self._tab = index

  def _render(self, rect: rl.Rectangle):
    tab = self._tab   # once: a tap on the tabs lands while they render below, and the rest of this frame must match
    tuner, bundle = self._tuner, OVERRIDE_BUNDLES[tab]
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    header = inset(rl.Rectangle(rect.x, rect.y, rect.width, self.HEADER), left=T.px(22), right=T.px(16), y=T.px(8))
    w, h = self._tabs.preferred_size(header.width)
    self._tabs.render(place(header, w, h, Align.START))
    on = tuner.bundle_on(bundle)
    draw.text(header, N_("Bundle on") if on else N_("Bundle off"), T.SIZE_SUBTITLE, T.SUCCESS_TEXT if on else T.TEXT_MUTED, T.FONT_SEMIBOLD,
              Align.END)
    draw.hline(rect.x, rect.y + self.HEADER, rect.width)

    note_h = draw.line_height(T.SIZE_SUBTITLE) + T.px(28)
    grid = inset(rl.Rectangle(rect.x, rect.y + self.HEADER, rect.width, rect.height - self.HEADER - note_h), x=T.px(10), y=T.px(6))
    col_w = (grid.width - T.px(10)) / 2
    for i, (key, badge, switch) in enumerate(self._items[tab]):
      col, line = i % 2, i // 2
      cell = rl.Rectangle(grid.x + col * (col_w + T.px(10)), grid.y + line * (self.ROW + T.DIVIDER), col_w, self.ROW)
      if line > 0:
        draw.hline(cell.x, cell.y - T.DIVIDER, cell.width)
      body = inset(cell, x=T.px(10))
      sw, sh = switch.preferred_size(body.width)
      switch.render(place(body, sw, sh, Align.END))
      text = inset(body, right=sw + T.px(10))
      if tuner.item_differs(bundle, key):   # only the shown tab's widgets render, so only they take taps
        bw, bh = badge.preferred_size(text.width)
        badge.render(place(text, bw, bh, Align.END))
        text = inset(text, right=bw + T.px(10))
      draw.text(text, ITEM_NAMES[key], T.font_px(16), T.TEXT, T.FONT_SEMIBOLD)
    if bundle is DEVELOPER_VIEW:   # the strip's metrics, under the switches
      lines = -(-len(self._items[tab]) // 2)
      cell = rl.Rectangle(grid.x, grid.y + lines * (self.ROW + T.DIVIDER), grid.width, self.ROW)
      draw.hline(cell.x, cell.y - T.DIVIDER, cell.width)
      body = inset(cell, x=T.px(10))
      bw, bh = self._choose.preferred_size(body.width)
      self._choose.render(place(body, bw, bh, Align.END))
      title_w = draw.text(body, N_("Bar metrics"), T.font_px(16), T.TEXT, T.FONT_SEMIBOLD)
      picked = ", ".join(tuner.strip()) or N_("None: the bar is hidden")
      words = inset(body, left=title_w + T.px(14), right=bw + T.px(14))
      draw.text(words, draw.fit(picked, T.SIZE_SUBTITLE, T.FONT, words.width), T.SIZE_SUBTITLE, T.TEXT_TERTIARY)
    note = t_("{} of {} items differ from the bundle.", tuner.bundle_changes(bundle), len(tuner.bundle_items(bundle)))
    draw.text(rl.Rectangle(rect.x + T.px(22), rect.y + rect.height - note_h, rect.width - T.px(44), note_h), note, T.SIZE_SUBTITLE,
              T.TEXT_TERTIARY)


RESET_TUNING_MESSAGE = N_("Every Tuner Mode change goes back to its default, in every section and bundle. Your other settings stay as they are.")


def tuner_page(tuner: Tuner, window):
  from openpilot.selfdrive.ui.tandem.settings.device_sections import confirm
  from openpilot.selfdrive.ui.tandem.settings.pages import Section, SectionPage

  def reset_all() -> None:
    confirm(window, N_("Reset all tuning?"), RESET_TUNING_MESSAGE, N_("Reset"), tuner.reset_all, icon="restart")

  return SectionPage(N_("TUNER MODE"), [
    Section(N_("Steering"), lambda: steering_panel(tuner, window), lambda: _changed_label(tuner.changed(STEERING)), value_tone=Tone.WARNING),
    Section(N_("Gas & Brake"), lambda: gas_brake_panel(tuner, window), lambda: _changed_label(tuner.gas_brake_changes()),
            value_tone=Tone.WARNING),
    Section(N_("Following & Stops"), lambda: following_panel(tuner, window), lambda: _changed_label(tuner.following_changes()),
            value_tone=Tone.WARNING),
    Section(N_("Bundle Overrides"), lambda: BundleOverrides(tuner, window),
            lambda: _changed_label(sum(tuner.bundle_changes(b) for b in OVERRIDE_BUNDLES)), value_tone=Tone.WARNING),
  ], tone=Tone.WARNING, footer=[Button(N_("Reset all tuning"), reset_all, ButtonStyle.DANGER_SOFT, width=T.SIDEBAR_WIDTH)])
