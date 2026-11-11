"""Weather heads-up: the next 24 hours of forecast, so the drive screen can say when rain, snow or storms start and stop.

Open-Meteo (free, no key; StarPilot's weather presets already use it) gives the weather in 15-minute steps (NOAA's model
in the US). The forecast is kept on the device and fetched again when it's an hour old, every 15 minutes while rain or
snow is falling or due within two hours, or when the car is more than 20 miles from where it was fetched. A failed fetch
is retried after a few minutes; the stored forecast keeps working meanwhile, up to its 24 hours.

Each step's code is the weather at that instant (Open-Meteo's weather_code is "instant", not a sum of the 15 minutes
before), so a step stands for the 7.5 minutes either side of it: weather changes halfway between two steps. A single
15-minute step of rain between dry ones is a blip in the model, not news: weather still to come needs at least
MIN_EVENT_S of steps in a row before it's announced, though a blip shows while it's due.

The chip (onroad/status.py) shows "Snow in 12 min" from 15 minutes before it starts, then "Snow until 8:15 PM" while it
lasts. When an event is first seen within the hour, the chip shows briefly and one soft chime plays.
Steps are 15 minutes, so the times are to the nearest quarter hour, and it's a forecast, not radar.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REFRESH_S = 60 * 60                 # at most once an hour in the same area...
WEATHER_REFRESH_S = 15 * 60         # ...or every 15 minutes while weather is falling or due within WEATHER_NEAR_S
WEATHER_NEAR_S = 2 * 60 * 60
MIN_EVENT_S = 30 * 60               # weather to come is announced only when it lasts at least this long
MOVED_KM = 20 * 1.609344            # ...unless the car is more than 20 miles from where it was fetched
RETRY_S = 5 * 60                    # after a failed fetch
CHECK_S = 30                        # how often the drive screen's tick looks at the location and the setting
LOOKAHEAD_S = 60 * 60               # an event within the hour is announced
SHOW_BEFORE_S = 15 * 60             # the chip stays up from 15 minutes before it starts
FLASH_S = 30.0                      # the brief heads-up when an event is first seen earlier than that

# WMO weather codes (Open-Meteo) -> what the chip calls it, and its icon. Clear and cloudy codes aren't hazards.
HAZARDS: dict[int, tuple[str, str]] = {
  45: (N_("Fog"), "fog"), 48: (N_("Fog"), "fog"),
  51: (N_("Light rain"), "rain"), 53: (N_("Drizzle"), "rain"), 55: (N_("Drizzle"), "rain"),
  56: (N_("Freezing drizzle"), "snow"), 57: (N_("Freezing drizzle"), "snow"),
  61: (N_("Light rain"), "rain"), 63: (N_("Rain"), "rain"), 65: (N_("Heavy rain"), "storm"),
  66: (N_("Freezing rain"), "snow"), 67: (N_("Freezing rain"), "snow"),
  71: (N_("Light snow"), "snow"), 73: (N_("Snow"), "snow"), 75: (N_("Heavy snow"), "snow"), 77: (N_("Fine, icy snow"), "snow"),
  80: (N_("Light rain"), "rain"), 81: (N_("Rain showers"), "rain"), 82: (N_("Heavy rain"), "storm"),
  85: (N_("Light snow flurries"), "snow"), 86: (N_("Heavy snow"), "snow"),
  95: (N_("Thunderstorm"), "storm"), 96: (N_("Storm with hail"), "storm"), 99: (N_("Storm with hail"), "storm"),
}


# The sky when nothing's falling (WMO 0-3), by day and by night: the parked screen's outlook line.
SKY: dict[int, tuple[str, str]] = {0: (N_("Sunny"), N_("Clear")), 1: (N_("Mostly sunny"), N_("Mostly clear")), 2: (N_("Partly cloudy"), N_("Partly cloudy")),
                                   3: (N_("Cloudy"), N_("Cloudy"))}


@dataclass
class Forecast:
  """The hourly steps of a fetched forecast, where and when it was fetched; saved to disk as JSON between restarts."""
  steps: list[tuple[int, int]]      # (unix start, WMO code), in order
  step_s: int                       # 900 for 15-minute steps, 3600 for hourly
  fetched_at: float
  lat: float
  lon: float
  utc_offset: int = 0               # the place's local time, for "until 8:15 PM"
  hours: list[tuple[int, int, float, bool]] = field(default_factory=list)   # (unix hour, WMO code, °C, daytime): the parked screen

  def to_json(self) -> dict:
    return {"steps": self.steps, "step_s": self.step_s, "fetched_at": self.fetched_at, "lat": self.lat, "lon": self.lon,
            "utc_offset": self.utc_offset, "hours": self.hours}

  @staticmethod
  def from_json(data: dict) -> Forecast:
    return Forecast([(int(t), int(c)) for t, c in data["steps"]], int(data["step_s"]), float(data["fetched_at"]),
                    float(data["lat"]), float(data["lon"]), int(data.get("utc_offset", 0)),
                    [(int(t), int(c), float(temp), bool(day)) for t, c, temp, day in data.get("hours", [])])


def parse(data: dict, fetched_at: float, lat: float, lon: float) -> Forecast | None:
  """Open-Meteo's answer (timeformat=unixtime): the 15-minute steps, or the hourly ones where those are missing; and the
  hours with their temperature and whether it's day."""
  hourly = data.get("hourly") or {}
  hours = [(int(t), int(c), float(temp), bool(day)) for t, c, temp, day in
           zip(hourly.get("time") or [], hourly.get("weather_code") or [], hourly.get("temperature_2m") or [],
               hourly.get("is_day") or [], strict=False) if None not in (t, c, temp, day)]
  for key, step_s in (("minutely_15", 900), ("hourly", 3600)):
    block = data.get(key) or {}
    times, codes = block.get("time") or [], block.get("weather_code") or []
    steps = [(int(t), int(c)) for t, c in zip(times, codes, strict=False) if t is not None and c is not None]
    if steps:
      return Forecast(steps, step_s, fetched_at, lat, lon, int(data.get("utc_offset_seconds") or 0), hours)
  return None


def wall_clock() -> float:
  """Unix time: forecasts are in wall-clock time, unlike the UI's monotonic timers."""
  return datetime.now(UTC).timestamp()


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  p1, p2 = math.radians(lat1), math.radians(lat2)
  a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
  return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, a)))


def weather_near(forecast: Forecast, now: float) -> bool:
  """Rain, snow, storms or fog falling now or due within WEATHER_NEAR_S: the forecast is worth refreshing more often."""
  half = forecast.step_s / 2
  return any(code in HAZARDS and t + half > now and t - half < now + WEATHER_NEAR_S for t, code in forecast.steps)


def needs_fetch(forecast: Forecast | None, now: float, lat: float, lon: float) -> bool:
  if forecast is None or not forecast.hours:   # none yet, or stored before the hours were kept
    return True
  every = WEATHER_REFRESH_S if weather_near(forecast, now) else REFRESH_S
  return now - forecast.fetched_at >= every or distance_km(forecast.lat, forecast.lon, lat, lon) > MOVED_KM


def runs(forecast: Forecast) -> list[tuple[int, int]]:
  """Each stretch of hazard steps in a row, as (first index, index after the last)."""
  found, i, steps = [], 0, forecast.steps
  while i < len(steps):
    if steps[i][1] in HAZARDS:
      j = i
      while j < len(steps) and steps[j][1] in HAZARDS:
        j += 1
      found.append((i, j))
      i = j
    else:
      i += 1
  return found


def _edges(forecast: Forecast, run: tuple[int, int]) -> tuple[float, float | None]:
  """When a run starts and ends: halfway to the steps either side. None past the end of the data."""
  half, steps = forecast.step_s / 2, forecast.steps
  first, after = run
  return steps[first][0] - half, (steps[after][0] - half if after < len(steps) else None)


def _lasting(forecast: Forecast, run: tuple[int, int]) -> bool:
  return (run[1] - run[0]) * forecast.step_s >= MIN_EVENT_S


def hour_label(ts: float, utc_offset: int) -> str:
  """3 PM."""
  hour = time.gmtime(ts + utc_offset).tm_hour
  return f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"


def clock(ts: float, utc_offset: int) -> str:
  """8:15 PM, in the forecast place's local time."""
  t = time.gmtime(ts + utc_offset)
  return f"{t.tm_hour % 12 or 12}:{t.tm_min:02d} {'AM' if t.tm_hour < 12 else 'PM'}"


def event_clock(ts: float, utc_offset: int) -> str:
  """When weather starts or stops, to the nearest 5 minutes: halfway between steps falls on 7.5 minutes past, and a
  forecast isn't that precise."""
  return clock(math.floor(ts / 300 + 0.5) * 300, utc_offset)


@dataclass
class HeadsUp:
  """Weather heads-up for the drive screen: what's coming (rain, snow, storms or fog), its icon, and when it starts."""
  label: str                        # "Light rain"
  icon: str                         # rain, snow, storm, fog
  start: int                        # when it starts (unix), for telling events apart
  minutes: int = 0                  # until it starts; 0 when it's already happening
  until: str = ""                   # when it should stop, "8:15 PM"; "" past the forecast's end

  @property
  def active(self) -> bool:
    return self.minutes == 0

  @property
  def text(self) -> str:
    if not self.active:
      return t_("{} in {} min", self.label, self.minutes)
    return t_("{} until {}", self.label, self.until) if self.until else self.label


def heads_up(forecast: Forecast | None, now: float) -> HeadsUp | None:
  """What's happening now, or the next hazard within the hour."""
  if forecast is None or not forecast.steps:
    return None
  steps, half = forecast.steps, forecast.step_s / 2
  for run in runs(forecast):
    start, end = _edges(forecast, run)
    if end is not None and end <= now:
      continue
    if start <= now:   # falling now, the step we're in named by its own strength
      current = next(i for i in range(*run) if steps[i][0] - half <= now < steps[i][0] + half)
      label, icon = HAZARDS[steps[current][1]]
      return HeadsUp(label, icon, int(start), 0, event_clock(end, forecast.utc_offset) if end is not None else "")
    if start > now + LOOKAHEAD_S:
      return None
    if _lasting(forecast, run):
      label, icon = HAZARDS[steps[run[0]][1]]
      return HeadsUp(label, icon, int(start), max(1, math.ceil((start - now) / 60)))
  return None


@dataclass
class Announcer:
  """When the chip shows, and the one chime: from 15 minutes before an event until it ends; and when an event is first
  seen earlier in the hour, a brief heads-up with the chime."""
  first_seen: dict[tuple[int, str], float] = field(default_factory=dict)

  def update(self, hint: HeadsUp | None, now: float) -> tuple[bool, bool]:
    """Returns (show the chip, chime now)."""
    if hint is None:
      return False, False
    key = (hint.start, hint.label)
    chime = False
    if key not in self.first_seen:
      self.first_seen = {k: v for k, v in self.first_seen.items() if k[0] > now - 2 * 86400}
      self.first_seen[key] = now
      chime = not hint.active          # a warning; weather already falling when first seen isn't news
    show = hint.active or hint.minutes * 60 <= SHOW_BEFORE_S or now - self.first_seen[key] < FLASH_S
    return show, chime


class ForecastService:
  """Keeps the forecast: loads the stored one, and fetches in the background when it's due."""

  def __init__(self, store: Path, location: Callable[[], tuple[float, float] | None], enabled: Callable[[], bool],
               fetch: Callable[[float, float], dict | None] | None = None, now: Callable[[], float] = wall_clock):
    self._store, self._location, self._enabled, self._now = store, location, enabled, now
    self._fetch = fetch or fetch_open_meteo
    self._next_try = 0.0
    self._next_check = 0.0
    self._busy = False
    self.forecast: Forecast | None = None
    try:
      self.forecast = Forecast.from_json(json.loads(store.read_text()))
    except (OSError, ValueError, KeyError, TypeError):
      pass

  def tick(self) -> None:
    """Called often; fetches at most when due, never more than one at a time."""
    now = self._now()
    if self._busy or now < max(self._next_try, self._next_check):
      return
    self._next_check = now + CHECK_S
    if not self._enabled():
      return
    where = self._location()
    if where is None or not needs_fetch(self.forecast, now, *where):
      return
    self._busy = True
    self._next_try = now + RETRY_S
    threading.Thread(target=self._fetch_now, args=(now, *where), daemon=True).start()

  def _fetch_now(self, now: float, lat: float, lon: float) -> None:
    try:
      data = self._fetch(lat, lon)
      forecast = parse(data, now, lat, lon) if data else None
      if forecast is not None:
        self.forecast = forecast
        try:
          self._store.write_text(json.dumps(forecast.to_json()))
        except OSError:
          pass
      elif data is not None:
        _log("weather forecast: Open-Meteo's answer had no forecast steps")
    except Exception as e:
      _log(f"weather forecast fetch failed: {e!r}")
    finally:
      self._busy = False


def _log(message: str) -> None:
  """To openpilot's log (swaglog) on the device; nowhere in tests and renders."""
  try:
    from openpilot.common.swaglog import cloudlog
    cloudlog.warning(message)
  except Exception:
    pass


def fetch_open_meteo(lat: float, lon: float) -> dict | None:
  params = {"latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}", "minutely_15": "weather_code",
            "hourly": "weather_code,temperature_2m,is_day",
            "forecast_minutely_15": 96, "forecast_hours": 24, "timezone": "auto", "timeformat": "unixtime"}
  request = urllib.request.Request(f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "tandem/1.0"})
  with urllib.request.urlopen(request, timeout=10) as response:
    data = json.loads(response.read().decode())
  return data if isinstance(data, dict) else None


def where_now(memory: Callable[[str], object], saved: Callable[[str], object]) -> tuple[float, float] | None:
  """StarPilot's live GPS position (in memory, cleared on restart), else the one it saved when the car last turned off or
  while parked with a fix, as Galaxy finds the car. Parked after a restart, only the saved one is there."""
  return last_position(lambda: memory("LastGPSPosition")) or last_position(lambda: saved("LastGPSPosition"))


def last_position(read: Callable[[], object]) -> tuple[float, float] | None:
  """StarPilot's planner keeps the last GPS fix in LastGPSPosition (JSON)."""
  try:
    raw = read()
    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw) if isinstance(raw, (str, bytes)) else raw
    if not isinstance(data, dict):
      return None
    lat, lon = float(data["latitude"]), float(data["longitude"])
  except (TypeError, ValueError, KeyError):
    return None
  return (lat, lon) if (lat or lon) and math.isfinite(lat) and math.isfinite(lon) else None


# ---- the parked screen's outlook ----

OUTLOOK_HOURS = 12


@dataclass
class HourTile:
  """One hour on the parked screen's forecast strip."""
  time: str                         # "3 PM"
  icon: str                         # sun, moon, partly, cloud, rain, snow, storm, fog
  temp: int                         # in the driver's units
  hazard: bool


@dataclass
class Outlook:
  """The parked screen's forecast: one line saying what matters, and a tile an hour."""
  summary: str                      # "Light snow from 5:45 to 8:30 PM", or "Mostly sunny"
  icon: str
  hazard: bool
  updated: str                      # "2:10 PM", when it was fetched
  tiles: list[HourTile]


def hour_icon(code: int, day: bool) -> str:
  if code in HAZARDS:
    return HAZARDS[code][1]
  if code in (0, 1):
    return "sun" if day else "moon"
  return "partly" if code == 2 and day else "cloud"


def _next_event(forecast: Forecast, now: float, horizon: float) -> tuple[str, str, int, int | None] | None:
  """The first hazard falling now or starting before horizon: (label, icon, start, end or None past the data)."""
  for run in runs(forecast):
    start, end = _edges(forecast, run)
    if (end is not None and end <= now) or start >= horizon or (start > now and not _lasting(forecast, run)):
      continue
    label, icon = HAZARDS[forecast.steps[run[0]][1]]
    return label, icon, int(start), None if end is None else int(end)
  return None


def outlook(forecast: Forecast | None, now: float, metric: bool, hours: int = OUTLOOK_HOURS) -> Outlook | None:
  """The next 12 hours for the parked screen: a tile an hour, and one line saying what matters.

  Args:
    forecast: The latest forecast, if any.
    now: The wall-clock time.
    metric: Temperatures in °C (prefs.celsius, General › Temperature).
    hours: How many hours to show.

  Returns:
    The outlook, or None without enough forecast left (fewer than 3 hours ahead).
  """
  if forecast is None:
    return None
  ahead = [h for h in forecast.hours if h[0] > now][:hours]
  if len(ahead) < 3:
    return None
  off = forecast.utc_offset
  tiles = [HourTile(hour_label(t, off), hour_icon(code, day), round(temp if metric else temp * 9 / 5 + 32), code in HAZARDS)
           for t, code, temp, day in ahead]
  event = _next_event(forecast, now, ahead[-1][0] + 3600)
  if event is not None:
    label, icon, start, end = event
    if start <= now:
      summary = t_("{} until {}", label, event_clock(end, off)) if end is not None else label
    else:
      summary = t_("{} from {}", label, event_clock(start, off)) + (t_(" to {}", event_clock(end, off)) if end is not None else "")
    return Outlook(summary, icon, True, clock(forecast.fetched_at, off), tiles)
  skies = [(code, day) for _, code, _, day in ahead if code in SKY]
  if not skies:
    return Outlook(N_("No rain or snow ahead"), "cloud", False, clock(forecast.fetched_at, off), tiles)
  codes = [c for c, _ in skies]
  sky = max(set(codes), key=lambda c: (codes.count(c), c))       # the most hours; a tie goes to the cloudier
  day = sum(d for c, d in skies if c == sky) * 2 >= codes.count(sky)
  return Outlook(SKY[sky][0 if day else 1], hour_icon(sky, day), False, clock(forecast.fetched_at, off), tiles)


def now_conditions(forecast: Forecast | None, now: float, metric: bool) -> tuple[str, str] | None:
  """The hour we're in, for the drive screen's bar: (icon, "34°"). metric: °C (prefs.celsius)."""
  if forecast is None:
    return None
  hour = next(((code, temp, day) for t, code, temp, day in forecast.hours if t <= now < t + 3600), None)
  if hour is None:
    return None
  code, temp, day = hour
  return hour_icon(code, day), f"{round(temp if metric else temp * 9 / 5 + 32)}°"


_shared: list[ForecastService] = []


def shared_service() -> ForecastService:
  """One forecast for the drive screen and the parked screen, kept beside the params folder."""
  if not _shared:
    from openpilot.common.params import Params
    from openpilot.selfdrive.ui.tandem.prefs import WEATHER_HEADS_UP, prefs_dir
    memory, saved = Params(memory=True), Params()
    _shared.append(ForecastService(prefs_dir() / ".tandem_forecast.json", lambda: where_now(memory.get, saved.get), WEATHER_HEADS_UP.get))
  return _shared[0]
