"""What the car is doing on its own, read from the driving messages, and which status chip explains it.

Snapshot holds plain values, so the chip rules can be tested without cereal. snapshot() fills one from ui_state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from openpilot.selfdrive.ui.tandem.i18n import N_, t_


class ChipTone(Enum):
  INFO = "info"         # blue: the car is changing speed or steering on its own
  PAUSED = "paused"     # amber: steering paused or a change blocked
  WAITING = "waiting"   # green: waiting on the driver
  ALERT = "alert"       # red: something on the device needs attention, not the drive


@dataclass(frozen=True)
class Chip:
  key: str
  label: str
  tone: ChipTone
  icon: str


@dataclass
class Snapshot:
  engaged: bool = False
  standstill: bool = False
  waiting_for_resume: bool = False         # the car's cruise is held at a stop until the driver resumes
  speed: float = 0.0                       # m/s
  accel: float = 0.0                       # m/s², the car's own
  metric: bool = False
  lateral_paused: bool = False             # paused by hand (a wheel button's Pause steering action)
  steering_held: bool = False              # StarPilot's planner is holding steering off (its lateralCheck) while engaged
  pause_lateral_speed: float = 0.0         # StarPilot's Pause steering below setting, display units; 0 when off
  pause_lateral_ms: float = 0.0            # the same, m/s
  pause_on_signal: bool = False            # ...only while signalling (PauseLateralOnSignal)
  signal_on: bool = False
  signal_direction: str = "none"           # left, right, both, none
  always_on_lateral: bool = False          # steering with cruise off
  speed_paused: bool = False               # Pause speed control from a wheel button: the driver has the pedals
  coasting: bool = False                   # Force coast from a wheel button, until either pedal
  pulse_glide: bool = False                # Pulse and glide from a wheel button
  gliding: bool = False                    # ...in its glide phase
  lane_change: str = "off"                 # off, pre, starting, finishing
  lane_change_direction: str = "none"      # left, right, none
  blindspot: bool = False                  # on the side of the requested lane change
  curve_control: bool = False
  red_light: bool = False
  stop_sign: bool = False
  slowing_for_lead: bool = False
  nav_turn: bool = False
  nav_turn_maneuver: str = ""
  nav_turn_modifier: str = ""
  limit_changed: bool = False
  speed_limit: float = 0.0                 # display units
  weather: str = ""                        # "Rain", "Heavy rain", "Snow", "Fog": the condition Weather presets see
  weather_gap: bool = False                # ...and its preset adds following distance
  forecast: tuple[str, str] | None = None  # Weather heads-up (forecast.py): ("Snow in 12 min" or "Snow until 8:15 PM", icon)
  forecast_active: bool = False            # ...and it's falling now, so it stands in for the longer-gap chip
  memory_percent: int = 0                  # RAM in use, from deviceState
  low_ram: bool = False                    # StarPilot raised Low Memory and RAM hasn't yet fallen to RamWatch.CLEAR
  events: set[str] = field(default_factory=set)
  routing: Chip | None = None


def turn_icon(maneuver: str, modifier: str) -> str:
  """The same maneuver icon for navigation cards and turn-progress chips; unknown directions stay neutral."""
  if maneuver in ("arrive", "depart"):
    return "pin"
  if maneuver in ("roundabout", "rotary", "roundabout turn") or "uturn" in modifier.lower():
    return "restart"
  modifier = modifier.lower()
  if "left" in modifier:
    return "turn_left"
  if "right" in modifier:
    return "turn_right"
  return "shift" if modifier == "straight" else "map"


SLOWING_ACCEL = -0.3     # m/s²: below this the car is braking, not just following
MOVING_SPEED = 0.5       # m/s


def chips_for(s: Snapshot) -> list[Chip]:
  """Every chip that applies now, highest priority first: paused or blocked, stopping, slowing, waiting, then low memory. Reasons that
  exclude each other (the two pauses, blocked or changing lanes, a sign or the model's stop) give one chip."""
  unit = "km/h" if s.metric else "mph"
  out: list[Chip] = []
  # Why steering is off, as StarPilot's planner decides it. The car's own minimum steering speed isn't one of these:
  # openpilot says it in its "Steer Unavailable Under …" alert, with the car's figure.
  below = 0 < s.pause_lateral_ms and s.speed < s.pause_lateral_ms
  if s.lateral_paused:
    out.append(Chip("pause_button", N_("Steering paused"), ChipTone.PAUSED, "wheel_pause"))
  elif s.steering_held and not s.standstill:
    # As StarPilot's planner decides: with Pause on signal, speed alone doesn't pause, only signalling below it, then a
    # short hold once the signal ends (Lateral Resume Delay) so the driver can straighten the wheel after a slow turn.
    if s.pause_on_signal and s.signal_on:
      icon = {"left": "signal", "right": "signal_right", "both": "warning"}.get(s.signal_direction, "wheel_pause")
      out.append(Chip("pause_signal", N_("Steering paused for signal"), ChipTone.PAUSED, icon))
    elif s.pause_on_signal:
      out.append(Chip("pause_turn", N_("Steering paused after turn"), ChipTone.PAUSED, "wheel_pause"))
    elif below:
      out.append(Chip("pause_speed", t_("Steering paused · under {} {}", f"{s.pause_lateral_speed:.0f}", unit), ChipTone.PAUSED, "wheel_pause"))
    else:
      out.append(Chip("pause_held", N_("Steering paused"), ChipTone.PAUSED, "wheel_pause"))
  if s.speed_paused and s.engaged:
    out.append(Chip("speed_paused", N_("Speed control paused"), ChipTone.PAUSED, "gauge_pause"))
  # Also whenever openpilot or StarPilot raises Car Detected in Blindspot (camera blind spot too, and StarPilot's loud
  # version while signalling without steering): the chip stands in for that banner, so it must show whenever it would.
  blocked_alert = bool(s.events & {"laneChangeBlocked", "laneChangeBlockedLoud"})
  if (s.lane_change in ("pre", "starting") and s.blindspot) or blocked_alert:
    out.append(Chip("lane_blocked", N_("Lane change blocked"), ChipTone.PAUSED, "lane_blocked"))
  elif s.lane_change in ("starting", "finishing") and s.lane_change_direction in ("left", "right"):
    out.append(Chip("lane_change", t_("Changing lanes {}", s.lane_change_direction), ChipTone.INFO, f"lane_{s.lane_change_direction}"))
  green = "greenLight" in s.events
  if s.standstill and green:   # at a stop the news is the light changing, not that we're stopped
    out.append(Chip("green_light", N_("Light is green"), ChipTone.WAITING, "light_green"))
  else:
    stop = N_("Stopped") if s.standstill else N_("Stopping")   # once the car is stopped, the chip says so
    if s.stop_sign:
      out.append(Chip("stop_sign", t_("{} for stop sign", stop), ChipTone.INFO, "stop_sign"))
    elif s.red_light:
      # StarPilot's redLight is the model predicting a stop, for a light or a sign alike; only the dashboard confirms a sign.
      out.append(Chip("red_light", N_("Stopped") if s.standstill else N_("Stopping ahead"), ChipTone.INFO, "stop"))
  if s.curve_control:
    out.append(Chip("curve", N_("Slowing for curve"), ChipTone.INFO, "curve"))
  if s.nav_turn:
    out.append(Chip("turn", N_("Slowing for turn"), ChipTone.INFO, turn_icon(s.nav_turn_maneuver, s.nav_turn_modifier)))
  # Turn events stand on their own, including steering-only turns with the driver on the pedals.
  if "turningLeft" in s.events:
    out.append(Chip("turning", N_("Turning left"), ChipTone.INFO, "turn_left"))
  elif "turningRight" in s.events:
    out.append(Chip("turning", N_("Turning right"), ChipTone.INFO, "turn_right"))
  if s.slowing_for_lead and not s.standstill and s.speed > MOVING_SPEED and s.accel < SLOWING_ACCEL:
    out.append(Chip("traffic", N_("Slowing for traffic"), ChipTone.INFO, "car"))
  if s.limit_changed and s.speed_limit:
    out.append(Chip("limit", t_("Matching limit {}", f"{s.speed_limit:.0f}"), ChipTone.INFO, "gauge"))
  if s.coasting and s.engaged and not s.speed_paused:
    out.append(Chip("coasting", N_("Coasting"), ChipTone.INFO, "coast"))
  if s.pulse_glide and s.engaged and not s.speed_paused:
    out.append(Chip("pulse_glide", N_("Pulse & glide · gliding") if s.gliding else N_("Pulse & glide"), ChipTone.INFO, "pulse_glide"))
  if s.forecast:
    out.append(Chip("forecast", s.forecast[0], ChipTone.INFO, s.forecast[1]))
  if s.weather and s.weather_gap and not (s.forecast and s.forecast_active):
    out.append(Chip("weather", t_("{} · longer gap", s.weather), ChipTone.INFO, {"Snow": "snow", "Fog": "fog"}.get(s.weather, "rain")))
  if green and not s.standstill:
    out.append(Chip("green_light", N_("Light is green"), ChipTone.WAITING, "light_green"))
  if "leadDeparting" in s.events:
    out.append(Chip("lead_moved", N_("Car ahead moved"), ChipTone.WAITING, "car_up"))
  if s.engaged and s.standstill and s.waiting_for_resume:   # cars that resume on their own aren't waiting on you
    out.append(Chip("ready", N_("Ready · tap resume"), ChipTone.WAITING, "play"))
  if s.always_on_lateral and not s.engaged:
    out.append(Chip("steering_only", N_("Steering only"), ChipTone.INFO, "wheel"))
  if s.routing is not None:
    out.append(s.routing)  # routing yields to driving reasons; Low on RAM remains last
  # Last, so it's the first to give way when more than MAX apply. StarPilot decides when memory is low (its lowMemory
  # event); this chip stands in for that event's notice. Its disengage and can't-engage forms stay alerts.
  if s.low_ram or "lowMemory" in s.events:
    out.append(Chip("low_memory", t_("Low on RAM · {}% used", s.memory_percent), ChipTone.ALERT, "memory"))
  return out


def routing_chip(state: dict | None, now: float, offline_only: bool = False) -> Chip | None:
  if not isinstance(state, dict):
    return None
  code = state.get("status", "")
  if code in ("idle", "routing", "superseded"):
    label = N_("Recalculating route") if state.get("active") else N_("Finding route")
  elif code == "rerouting":
    label = N_("Recalculating route")
  elif code == "gps_waiting":
    label = N_("Waiting for GPS")
  elif code == "ready":
    try:
      fallback = float(state.get("fallback_at", 0))
    except (ValueError, TypeError):
      return None
    if not 0 < fallback <= now <= fallback + 3:
      return None
    label = N_("Using offline maps") if state.get("provider") == "offline" else N_("Using online maps")
    if offline_only and state.get("provider") != "offline":
      return None
  else:
    return Chip("routing", N_("Offline maps unavailable") if offline_only else N_("Route unavailable"), ChipTone.PAUSED, "warning")
  return Chip("routing", label, ChipTone.INFO, "restart")


def chip_for(s: Snapshot) -> Chip | None:
  """The highest-priority chip, or None."""
  chips = chips_for(s)
  return chips[0] if chips else None


@dataclass
class _Shown:
  chip: Chip
  born: float        # when it joined the stack (its place: newest nearest the bar)
  until: float       # its reason was last seen at until - HOLD
  rank: int          # its priority when last seen


class ChipStack:
  """Up to MAX chips at once, newest nearest the bar. Each keeps its own hold: it stays while its reason holds, renews
  whenever the reason is seen again, then fades over FADE once HOLD has passed. With more reasons than MAX, the
  highest-priority ones show. The whole stack hides while an alert shows."""
  MAX = 4
  HOLD = 2.0
  FADE = 0.3

  def __init__(self):
    self._shown: dict[str, _Shown] = {}

  def update(self, s: Snapshot, now: float, alert_showing: bool) -> list[tuple[Chip, float]]:
    """(chip, opacity) nearest the bar first."""
    for rank, chip in enumerate(chips_for(s)):
      held = self._shown.get(chip.key)
      if held is None:
        self._shown[chip.key] = _Shown(chip, now, now + self.HOLD, rank)
      else:
        held.chip, held.until, held.rank = chip, now + self.HOLD, rank   # renewed; a changed label (Stopping → Stopped) updates
    self._shown = {k: v for k, v in self._shown.items() if now < v.until + self.FADE}
    if alert_showing:
      return []
    visible = sorted(self._shown.values(), key=lambda v: v.rank)[:self.MAX]
    visible.sort(key=lambda v: v.born, reverse=True)
    return [(v.chip, 1.0 if now < v.until else max(0.0, 1.0 - (now - v.until) / self.FADE)) for v in visible]


class ChipPicker:
  """Holds a chip for HOLD seconds after its reason ends, so it doesn't flicker. Hidden while an alert shows."""
  HOLD = 2.0

  def __init__(self):
    self._chip: Chip | None = None
    self._until = 0.0

  def update(self, s: Snapshot, now: float, alert_showing: bool) -> Chip | None:
    chip = chip_for(s)
    if chip is not None:
      self._chip, self._until = chip, now + self.HOLD
    elif now >= self._until:
      self._chip = None
    return None if alert_showing else self._chip


# OpenWeather condition ids, grouped as StarPilot's weather checker groups them (WEATHER_CATEGORIES): (name, preset suffix).
WEATHER_GROUPS = (
  (N_("Rain"), "rain", ((300, 321), (500, 504))),
  (N_("Heavy rain"), "rain_storm", ((200, 232), (511, 511), (520, 531))),
  (N_("Snow"), "snow", ((600, 622),)),
  (N_("Fog"), "low_visibility", ((701, 762),)),
)


def weather_group(weather_id: int) -> tuple[str, str]:
  """(name, StarPilot's preset suffix), or ("", "") for clear and anything StarPilot treats as clear."""
  for name, suffix, ranges in WEATHER_GROUPS:
    if any(lo <= weather_id <= hi for lo, hi in ranges):
      return name, suffix
  return "", ""


def weather_name(weather_id: int) -> str:
  return weather_group(weather_id)[0]


class LimitWatch:
  """Whether the car is matching a new speed limit: after the limit StarPilot drives to changes (accepted, not still
  asking), while the Speed Limit Controller is holding the speed under the set speed, until the speed reaches it."""
  TIMEOUT = 20.0     # s: a change the car never reaches (traffic, hills) stops being news
  CLOSE = 0.5        # m/s

  def __init__(self):
    self._last = 0.0
    self._until = 0.0

  def update(self, limit: float, target: float, limiting: bool, pending: bool, overridden: float, speed: float, now: float) -> bool:
    if limit > 0:
      if self._last > 0 and abs(limit - self._last) >= self.CLOSE:
        self._until = now + self.TIMEOUT
      self._last = limit
    if now >= self._until:
      return False
    if abs(speed - target) <= self.CLOSE:
      self._until = 0.0
      return False
    return limiting and not pending and overridden <= 0


class RamWatch:
  """Holds Low on RAM from StarPilot's Low Memory (above 90%) until RAM falls to CLEAR, so the chip doesn't blink while
  RAM hovers around 90%."""
  CLEAR = 85

  def __init__(self):
    self.on = False

  def update(self, raised: bool, percent: int) -> bool:
    self.on = raised or (self.on and percent > self.CLEAR)
    return self.on


def snapshot(ui_state, nav_active: bool = False, limits: LimitWatch | None = None, now: float = 0.0,
             ram: RamWatch | None = None) -> Snapshot:
  """Fill a Snapshot from upstream's ui_state. Missing messages leave defaults. limits tracks speed limit changes, ram
  holds Low on RAM."""
  sm = ui_state.sm
  valid = sm.valid
  s = Snapshot(engaged=bool(ui_state.engaged), metric=bool(ui_state.is_metric), always_on_lateral=bool(ui_state.always_on_lateral_active))
  speed_conversion = 3.6 if s.metric else 2.236936
  if valid.get("carState", False):
    cs = sm["carState"]
    s.standstill, s.speed, s.accel = bool(cs.standstill), float(cs.vEgo), float(cs.aEgo)
    s.waiting_for_resume = bool(cs.cruiseState.standstill)
    s.signal_on = bool(cs.leftBlinker or cs.rightBlinker)
    if cs.leftBlinker and cs.rightBlinker:
      s.signal_direction = "both"
    elif s.signal_on:
      s.signal_direction = "left" if cs.leftBlinker else "right"
    direction_left = cs.leftBlinker
    s.blindspot = bool(cs.leftBlindspot if direction_left else cs.rightBlindspot)
  if valid.get("modelV2", False):
    meta = sm["modelV2"].meta
    s.lane_change = {1: "pre", 2: "starting", 3: "finishing"}.get(meta.laneChangeState.raw, "off")
    s.lane_change_direction = {1: "left", 2: "right"}.get(meta.laneChangeDirection.raw, "none")
  toggles = ui_state.starpilot_toggles or {}
  steering_on = s.engaged
  if valid.get("starpilotCarState", False):
    spcs = sm["starpilotCarState"]
    s.lateral_paused = bool(spcs.pauseLateral)
    s.speed_paused, s.coasting, s.pulse_glide = bool(spcs.pauseLongitudinal), bool(spcs.forceCoast), bool(spcs.pulseAndGlide)
    # Always On Lateral turns itself off while StarPilot pauses steering, so read whether it would be steering.
    steering_on |= bool(toggles.get("always_on_lateral", False) and spcs.alwaysOnLateralAllowed)
  s.pause_lateral_ms = float(toggles.get("pause_lateral_below_speed", 0) or 0)
  s.pause_lateral_speed = s.pause_lateral_ms * speed_conversion
  s.pause_on_signal = bool(toggles.get("pause_lateral_below_signal", False))
  if valid.get("starpilotPlan", False):
    plan = sm["starpilotPlan"]
    s.steering_held = bool(not plan.lateralCheck and steering_on)
    s.curve_control = bool(plan.cscControllingSpeed)
    s.red_light = bool(plan.redLight or plan.forcingStop)
    s.stop_sign = bool(plan.stopSignConfirmed)
    s.speed_limit = float(plan.slcSpeedLimit) * speed_conversion
    if limits is not None:
      s.limit_changed = limits.update(float(plan.slcSpeedLimit), float(plan.slcSpeedLimit + plan.slcSpeedLimitOffset),
                                      bool(plan.slcIsLimitingMaxSet), bool(plan.speedLimitChanged), float(plan.slcOverriddenSpeed),
                                      s.speed, now)
    s.slowing_for_lead = bool(plan.experimentalMode and plan.trackingLead and not s.red_light)
    from openpilot.starpilot.tandem.navigation import read_turn
    turn = read_turn(now)
    # A route or experimental mode alone does not mean the car is slowing for a turn.
    s.nav_turn = bool(
      nav_active and turn["active"] and valid.get("carState", False)
      and sm["carState"].aEgo < -0.1 and s.speed > max(float(plan.vCruise), 0.1)
    )
    s.nav_turn_maneuver, s.nav_turn_modifier = turn["maneuver"], turn["modifier"]
    if toggles.get("weather_presets"):
      s.weather, suffix = weather_group(int(plan.weatherId))
      s.weather_gap = bool(suffix and float(toggles.get(f"increase_following_distance_{suffix}", 0) or 0) > 0)
    s.events = {str(e.name) for e in plan.starpilotEvents}
    s.gliding = bool(plan.pulseGlideCoasting)
  # StarPilot raises greenLight and leadDeparting for a single planner frame, which the UI can miss; the alerts they start
  # are held for seconds, so their names count too (the chip stands in for the hidden banner).
  for service in ("selfdriveState", "starpilotSelfdriveState"):
    # EmptyAlert can retain an old alertType after a hidden turn banner. Only an
    # actual alert may extend a chip; live planner events above still stand alone.
    if valid.get(service, False) and str(sm[service].alertSize) != "none" and sm[service].alertType:
      s.events.add(str(sm[service].alertType).split("/", 1)[0])
  if valid.get("deviceState", False):
    s.memory_percent = int(sm["deviceState"].memoryUsagePercent)
  if ram is not None:
    s.low_ram = ram.update("lowMemory" in s.events, s.memory_percent)
  return s
