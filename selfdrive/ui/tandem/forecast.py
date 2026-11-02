"""Weather heads-up: the next 24 hours of forecast, so the drive screen can say when rain, snow or storms start and stop.

Open-Meteo (free, no key; StarPilot's weather presets already use it) gives the weather in 15-minute steps (NOAA's HRRR
in the US). The forecast is kept on the device and fetched again only when it's an hour old or the car is more than
20 miles from where it was fetched. A failed fetch is retried after a few minutes; the stored forecast keeps working
meanwhile, up to its 24 hours.

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

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REFRESH_S = 60 * 60                 # at most once an hour in the same area...
MOVED_KM = 20 * 1.609344            # ...unless the car is more than 20 miles from where it was fetched
RETRY_S = 5 * 60                    # after a failed fetch
CHECK_S = 30                        # how often the drive screen's tick looks at the location and the setting
LOOKAHEAD_S = 60 * 60               # an event within the hour is announced
SHOW_BEFORE_S = 15 * 60             # the chip stays up from 15 minutes before it starts
FLASH_S = 30.0                      # the brief heads-up when an event is first seen earlier than that

# WMO weather codes (Open-Meteo) -> what the chip calls it, and its icon. Clear and cloudy codes aren't hazards.
HAZARDS: dict[int, tuple[str, str]] = {
  45: ("Fog", "fog"), 48: ("Fog", "fog"),
  51: ("Light rain", "rain"), 53: ("Drizzle", "rain"), 55: ("Drizzle", "rain"),
  56: ("Freezing drizzle", "snow"), 57: ("Freezing drizzle", "snow"),
  61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "storm"),
  66: ("Freezing rain", "snow"), 67: ("Freezing rain", "snow"),
  71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow", "snow"),
  80: ("Light rain", "rain"), 81: ("Rain showers", "rain"), 82: ("Heavy rain", "storm"),
  85: ("Snow showers", "snow"), 86: ("Heavy snow", "snow"),
  95: ("Thunderstorm", "storm"), 96: ("Thunderstorm with hail", "storm"), 99: ("Thunderstorm with hail", "storm"),
}


@dataclass
class Forecast:
  steps: list[tuple[int, int]]      # (unix start, WMO code), in order
  step_s: int                       # 900 for 15-minute steps, 3600 for hourly
  fetched_at: float
  lat: float
  lon: float
  utc_offset: int = 0               # the place's local time, for "until 8:15 PM"

  def to_json(self) -> dict:
    return {"steps": self.steps, "step_s": self.step_s, "fetched_at": self.fetched_at, "lat": self.lat, "lon": self.lon,
            "utc_offset": self.utc_offset}

  @staticmethod
  def from_json(data: dict) -> Forecast:
    return Forecast([(int(t), int(c)) for t, c in data["steps"]], int(data["step_s"]), float(data["fetched_at"]),
                    float(data["lat"]), float(data["lon"]), int(data.get("utc_offset", 0)))


def parse(data: dict, fetched_at: float, lat: float, lon: float) -> Forecast | None:
  """Open-Meteo's answer (timeformat=unixtime): the 15-minute steps, or the hourly ones where those are missing."""
  for key, step_s in (("minutely_15", 900), ("hourly", 3600)):
    block = data.get(key) or {}
    times, codes = block.get("time") or [], block.get("weather_code") or []
    steps = [(int(t), int(c)) for t, c in zip(times, codes, strict=False) if t is not None and c is not None]
    if steps:
      return Forecast(steps, step_s, fetched_at, lat, lon, int(data.get("utc_offset_seconds") or 0))
  return None


def wall_clock() -> float:
  """Unix time: forecasts are in wall-clock time, unlike the UI's monotonic timers."""
  return datetime.now(UTC).timestamp()


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  p1, p2 = math.radians(lat1), math.radians(lat2)
  a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
  return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, a)))


def needs_fetch(forecast: Forecast | None, now: float, lat: float, lon: float) -> bool:
  if forecast is None:
    return True
  return now - forecast.fetched_at >= REFRESH_S or distance_km(forecast.lat, forecast.lon, lat, lon) > MOVED_KM


def clock(ts: float, utc_offset: int) -> str:
  """8:15 PM, in the forecast place's local time."""
  t = time.gmtime(ts + utc_offset)
  return f"{t.tm_hour % 12 or 12}:{t.tm_min:02d} {'AM' if t.tm_hour < 12 else 'PM'}"


@dataclass
class HeadsUp:
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
      return f"{self.label} in {self.minutes} min"
    return f"{self.label} until {self.until}" if self.until else self.label


def heads_up(forecast: Forecast | None, now: float) -> HeadsUp | None:
  """What's happening now, or the next hazard within the hour."""
  if forecast is None or not forecast.steps:
    return None
  steps, dur = forecast.steps, forecast.step_s
  current = next((i for i, (t, _) in enumerate(steps) if t <= now < t + dur), None)
  if current is not None and steps[current][1] in HAZARDS:
    start = current
    while start > 0 and steps[start - 1][1] in HAZARDS:
      start -= 1
    end = next((t for t, code in steps[current:] if code not in HAZARDS), None)
    label, icon = HAZARDS[steps[current][1]]
    return HeadsUp(label, icon, steps[start][0], 0, clock(end, forecast.utc_offset) if end is not None else "")
  for t, code in steps:
    if now < t <= now + LOOKAHEAD_S and code in HAZARDS:
      label, icon = HAZARDS[code]
      return HeadsUp(label, icon, t, max(1, math.ceil((t - now) / 60)))
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
    except Exception:
      pass
    finally:
      self._busy = False


def fetch_open_meteo(lat: float, lon: float) -> dict | None:
  params = {"latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}", "minutely_15": "weather_code", "hourly": "weather_code",
            "forecast_minutely_15": 96, "forecast_hours": 24, "timezone": "auto", "timeformat": "unixtime"}
  request = urllib.request.Request(f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "tandem/1.0"})
  with urllib.request.urlopen(request, timeout=10) as response:
    return json.loads(response.read().decode())


def last_position(read: Callable[[], object]) -> tuple[float, float] | None:
  """StarPilot's planner keeps the last GPS fix in LastGPSPosition (JSON)."""
  try:
    raw = read()
    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw) if isinstance(raw, (str, bytes)) else raw
    lat, lon = float(data["latitude"]), float(data["longitude"])
  except (TypeError, ValueError, KeyError):
    return None
  return (lat, lon) if (lat or lon) and math.isfinite(lat) and math.isfinite(lon) else None
