"""Weather heads-up: the forecast's steps, when to fetch, what the chip says, and when it shows and chimes."""
import json

import pytest

from openpilot.selfdrive.ui.tandem import forecast as F

T0 = 1_700_000_000 - 1_700_000_000 % 900       # a quarter-hour boundary
CLEAR, LIGHT_RAIN, SNOW, STORM = 0, 61, 73, 95


def _forecast(codes, offset=0, fetched_at=T0, lat=41.6, lon=-93.6):
  return F.Forecast([(T0 + i * 900, c) for i, c in enumerate(codes)], 900, fetched_at, lat, lon, offset)


def test_parse_prefers_15_minute_steps_and_falls_back_to_hourly():
  data = {"utc_offset_seconds": -18000, "minutely_15": {"time": [T0, T0 + 900], "weather_code": [0, 61]},
          "hourly": {"time": [T0], "weather_code": [3]}}
  fc = F.parse(data, T0, 1.0, 2.0)
  assert fc.step_s == 900 and fc.steps == [(T0, 0), (T0 + 900, 61)] and fc.utc_offset == -18000
  assert F.parse({"hourly": {"time": [T0], "weather_code": [3]}}, T0, 1.0, 2.0).step_s == 3600
  assert F.parse({}, T0, 1.0, 2.0) is None
  assert F.Forecast.from_json(json.loads(json.dumps(fc.to_json()))) == fc


def test_fetch_at_most_hourly_unless_the_car_moved_20_miles():
  fc = _forecast([CLEAR])
  assert F.needs_fetch(None, T0, 41.6, -93.6)
  assert not F.needs_fetch(fc, T0 + 3599, 41.6, -93.6)
  assert F.needs_fetch(fc, T0 + 3600, 41.6, -93.6)
  assert not F.needs_fetch(fc, T0 + 60, 41.6 + 0.25, -93.6)       # about 17 miles north
  assert F.needs_fetch(fc, T0 + 60, 41.6 + 0.35, -93.6)           # about 24 miles


def test_light_rain_is_named_and_says_when_it_stops():
  fc = _forecast([LIGHT_RAIN, LIGHT_RAIN, LIGHT_RAIN, CLEAR], offset=-6 * 3600)
  hint = F.heads_up(fc, T0 + 100)
  assert hint.active and hint.label == "Light rain" and hint.icon == "rain"
  assert hint.text == f"Light rain until {F.clock(T0 + 2700, -6 * 3600)}"
  assert F.clock(T0 + 2700, -6 * 3600).endswith(("AM", "PM"))


def test_upcoming_weather_counts_down_and_past_the_data_has_no_end():
  fc = _forecast([CLEAR, CLEAR, STORM, STORM])
  hint = F.heads_up(fc, T0 + 300)
  assert not hint.active and hint.minutes == 25 and hint.text == "Thunderstorm in 25 min" and hint.icon == "storm"
  assert F.heads_up(fc, T0 + 1900).text == "Thunderstorm"       # falling, and still falling at the end of the data
  assert F.heads_up(_forecast([CLEAR] * 6 + [SNOW]), T0) is None  # 90 minutes away: not yet


def test_clock_reads_like_a_dashboard():
  assert F.clock(20 * 3600 + 15 * 60, 0) == "8:15 PM"
  assert F.clock(0, 0) == "12:00 AM" and F.clock(12 * 3600 + 5 * 60, 0) == "12:05 PM"


def test_chip_from_15_minutes_out_until_it_ends_with_one_chime_and_an_early_heads_up():
  fc = _forecast([CLEAR] * 4 + [SNOW, SNOW, CLEAR])   # snow from T0+3600 to T0+5400
  a = F.Announcer()
  assert a.update(F.heads_up(fc, T0 + 600), T0 + 600) == (True, True)       # first seen 50 min out: heads-up and chime
  assert a.update(F.heads_up(fc, T0 + 620), T0 + 620) == (True, False)      # the brief heads-up...
  assert a.update(F.heads_up(fc, T0 + 640), T0 + 640) == (False, False)     # ...then quiet
  assert a.update(F.heads_up(fc, T0 + 2700), T0 + 2700) == (True, False)    # from 15 min out, no second chime
  assert a.update(F.heads_up(fc, T0 + 4000), T0 + 4000) == (True, False)    # while it snows
  assert a.update(F.heads_up(fc, T0 + 5500), T0 + 5500) == (False, False)   # over


def test_turning_on_close_to_the_weather_still_warns_and_already_falling_does_not_chime():
  fc = _forecast([CLEAR, SNOW, SNOW])
  assert F.Announcer().update(F.heads_up(fc, T0 + 300), T0 + 300) == (True, True)   # 10 minutes away at start
  assert F.Announcer().update(F.heads_up(fc, T0 + 1000), T0 + 1000) == (True, False)


def test_status_chip_stands_in_for_the_longer_gap_chip_while_falling():
  from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chips_for
  s = Snapshot(weather="Rain", weather_gap=True, forecast=("Light rain until 8:15 PM", "rain"), forecast_active=True)
  assert [c.label for c in chips_for(s)] == ["Light rain until 8:15 PM"]
  s.forecast, s.forecast_active = ("Snow in 12 min", "snow"), False
  assert [c.label for c in chips_for(s)] == ["Snow in 12 min", "Rain · longer gap"]


def test_service_fetches_when_due_stores_it_and_backs_off(tmp_path, monkeypatch):
  monkeypatch.setattr(F.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
  now = [float(T0)]
  calls = []

  def fetch(lat, lon):
    calls.append((lat, lon))
    return {"minutely_15": {"time": [T0], "weather_code": [SNOW]}} if len(calls) > 1 else None
  store = tmp_path / "forecast.json"
  svc = F.ForecastService(store, lambda: (41.6, -93.6), lambda: True, fetch, lambda: now[0])
  svc.tick()
  assert calls and svc.forecast is None                  # failed: nothing stored
  now[0] += 60
  svc.tick()
  assert len(calls) == 1                                 # backs off
  now[0] += F.RETRY_S
  svc.tick()
  assert len(calls) == 2 and svc.forecast.steps == [(T0, SNOW)] and store.exists()
  now[0] += 600
  svc.tick()
  assert len(calls) == 2                                 # fresh: no refetch
  assert F.ForecastService(store, lambda: None, lambda: True, fetch).forecast.steps == [(T0, SNOW)]   # loads the stored one


@pytest.mark.parametrize("raw, where", [
  (json.dumps({"latitude": 41.6, "longitude": -93.6}), (41.6, -93.6)),
  (b'{"latitude": 0, "longitude": 0}', None), (None, None), ("not json", None),
])
def test_location_comes_from_starpilots_last_gps_fix(raw, where):
  assert F.last_position(lambda: raw) == where


def test_the_switch_is_a_marker_file(tandem_prefs):
  from openpilot.selfdrive.ui.tandem.prefs import WEATHER_HEADS_UP
  assert WEATHER_HEADS_UP.get()
  WEATHER_HEADS_UP.set(False)
  assert not WEATHER_HEADS_UP.get() and list(tandem_prefs.iterdir())


def test_the_weather_chime_is_its_own_switch_on_the_alerts_page(tandem_prefs):
  from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore

  class Cache:
    values: dict = {}

    def get_bool(self, key):
      return bool(self.values.get(key))

    def put_bool(self, key, value):
      self.values[key] = value

    def invalidate(self):
      pass
  cache = Cache()
  alerts = Alerts(SettingsStore(cache, lambda: None))
  assert alerts.chime("WeatherChime") and "Weather heads-up" in alerts.chimes_summary()
  alerts.set_chime("WeatherChime", False)
  assert not alerts.chime("WeatherChime") and "WeatherChime" not in cache.values   # a marker file, not a param


@pytest.mark.parametrize("code, name", [(71, "Light snow"), (73, "Snow"), (75, "Heavy snow"), (77, "Snow grains"),
                                        (85, "Light snow showers"), (86, "Heavy snow"), (61, "Light rain"), (65, "Heavy rain")])
def test_snow_and_rain_are_named_by_strength(code, name):
  assert F.HAZARDS[code][0] == name
