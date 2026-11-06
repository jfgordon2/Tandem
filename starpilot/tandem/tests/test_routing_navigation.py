"""Exercise the real upstream daemon/model with transport stand-ins, without publishing to a vehicle."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import config as C
from openpilot.starpilot.tandem.routing.navigationd import navigationd_type

ROOT = Path(__file__).resolve().parents[3]


class Params:
  def __init__(self):
    self.values = {}
  def get(self, key, **kwargs):
    return self.values.get(key)
  def get_bool(self, key):
    return bool(self.values.get(key))
  def remove(self, key):
    self.values.pop(key, None)
  def put_nonblocking(self, key, value):
    self.values[key] = value


@pytest.fixture
def daemon(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  for screen in C.SCREENS:
    monkeypatch.setenv(screen, "1")
  cereal = ModuleType("cereal")
  cereal.__path__ = []
  cereal.log = SimpleNamespace(NavInstruction=SimpleNamespace(SpeedLimitSign=SimpleNamespace(vienna=0, mutcd=1)))
  messaging = ModuleType("cereal.messaging")
  messaging.PubMaster = lambda _: SimpleNamespace(send=lambda *args: None)
  messaging.new_message = lambda *_: SimpleNamespace(valid=False, navInstruction=SimpleNamespace(), navRoute=SimpleNamespace())
  cereal.messaging = messaging
  monkeypatch.setitem(sys.modules, "cereal", cereal)
  monkeypatch.setitem(sys.modules, "cereal.messaging", messaging)
  saved, memory = Params(), Params()
  monkeypatch.setitem(sys.modules, "openpilot.common.params", SimpleNamespace(Params=lambda **kw: memory if kw.get("memory") else saved))
  monkeypatch.setitem(sys.modules, "openpilot.common.realtime", SimpleNamespace(Ratekeeper=lambda _: None))
  monkeypatch.setitem(sys.modules, "openpilot.common.swaglog", SimpleNamespace(cloudlog=SimpleNamespace(warning=lambda *_: None)))
  def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module
  engine = load("openpilot.starpilot.navigation.route_engine", "starpilot/navigation/route_engine.py")
  upstream = load("openpilot.starpilot.navigation.navigationd", "starpilot/navigation/navigationd.py")
  from openpilot.starpilot.tandem.routing import navigationd as local
  monkeypatch.setattr(local, "capability", lambda: {"status": "ready", "generation": "test-graph"})
  route = engine.NavigationRoute.from_mapbox_route({
    "geometry": [{"latitude": 41.5, "longitude": -93.6}, {"latitude": 41.5, "longitude": -93.59},
                 {"latitude": 41.51, "longitude": -93.59}],
    "steps": [{"maneuver": "depart", "instruction": "Head east", "location": {"latitude": 41.5, "longitude": -93.6},
               "distance": 830, "duration": 60},
              {"maneuver": "arrive", "instruction": "Arrive", "location": {"latitude": 41.51, "longitude": -93.59},
               "distance": 0, "duration": 0}], "totalDistance": 1940, "totalDuration": 120})
  return upstream.Navigationd, engine, route, saved, memory


def destination(name):
  return {"name": name, "place_name": name, "latitude": 41.51, "longitude": -93.59}


def finished(nav):
  for _ in range(200):
    if not nav._route_fetch_inflight:
      return
    time.sleep(.005)
  raise AssertionError("fetch stayed inflight")


def test_original_gate_and_local_keyless_fetch(daemon):
  base, engine, route, _, _ = daemon
  calls = []
  provider = SimpleNamespace(fetch_route=lambda *args: calls.append(args) or route, retry_at=0)
  stock = base(provider)
  stock._last_position = engine.Coordinate(41.5, -93.6)
  stock._start_route_fetch(destination("A"))
  assert calls == []
  local = navigationd_type(base)(provider)
  local._last_position = stock._last_position
  local._maybe_update_route(destination("A"))
  finished(local)
  assert len(calls) == 1 and calls[0][0] == ""
  assert local._active_destination["name"] == "A"


def test_destination_replacement_rejects_late_result_and_clears_previous_state(daemon):
  base, engine, route, saved, memory = daemon
  gate, entered = threading.Event(), threading.Event()
  def fetch(_, start, target, bearing):
    if target["name"] == "A":
      entered.set()
      assert gate.wait(2)
      return route
    return None
  local = navigationd_type(base)(SimpleNamespace(fetch_route=fetch, retry_at=0))
  local._last_position = engine.Coordinate(41.5, -93.6)
  memory.values["NavInstructionState"] = {"valid": True, "maneuverType": "turn"}
  local._maybe_update_route(destination("A"))
  assert entered.wait(2)
  local._maybe_update_route(destination("B"))
  assert "NavInstructionState" not in memory.values
  gate.set()
  finished(local)
  assert local._route is None
  local._maybe_update_route(destination("B"))
  finished(local)
  assert local._route is None and local._active_destination is None
  saved.values["NavDestination"] = json.dumps(destination("B"))
  local._maybe_update_route(None)
  assert local._requested_destination_key is None


def test_gps_freshness_and_final_step_arrival(daemon):
  base, engine, route, saved, memory = daemon
  local = navigationd_type(base)(SimpleNamespace(fetch_route=lambda *args: route, retry_at=0))
  state = {"hasFix": True, "latitude": 41.5, "longitude": -93.6, "speed": 0, "updatedAtMonotonic": time.monotonic()}
  memory.values["LastGPSPosition"] = json.dumps(state)
  assert local._update_location()[0]
  state["updatedAtMonotonic"] = time.monotonic() - 3
  memory.values["LastGPSPosition"] = json.dumps(state)
  assert local._update_location() == (False, 0)
  assert local._last_position is None
  state["updatedAtMonotonic"] = time.monotonic() + 100
  memory.values["LastGPSPosition"] = json.dumps(state)
  assert not local._update_location()[0]
  saved.values["NavDestination"] = json.dumps(destination("A"))
  local._route, local._active_destination = route, destination("A")
  progress = route.get_progress(engine.Coordinate(41.51, -93.59))
  assert progress.current_step_index == len(route.steps) - 1
  local._arrival_started_at = time.monotonic() - 6
  local._maybe_recompute(route, destination("A"), progress, {"now": time.monotonic()})
  assert local._route is None and "NavDestination" not in saved.values


def test_off_route_suppresses_actionable_state_without_rewriting_progress(daemon):
  base, engine, route, _, memory = daemon
  local = navigationd_type(base)(SimpleNamespace(fetch_route=lambda *args: route, retry_at=0))
  local._last_position = engine.Coordinate(41.505, -93.7)
  progress, state = local._build_progress(route, True, 10)
  assert state["offRoute"] and progress is not None
  local._last_nav_state = {"valid": True}
  memory.values["NavInstructionState"] = {"valid": True}
  local._publish_nav_state(route, progress, True, {"maneuverType": "turn"})
  assert "NavInstructionState" not in memory.values


def test_owned_cruise_rejects_stale_local_state_and_delegates_valid_targets(monkeypatch):
  from openpilot.starpilot.tandem.navigation import controller_type
  for screen in C.SCREENS:
    monkeypatch.setenv(screen, "1")
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  class Original:
    _nav_instruction_state = {}
    def _update_nav_instruction_state(self):
      pass
    def _get_nav_turn_control_target(self, v_cruise, sm, toggles, on_selected=None):
      on_selected("turn", "right")
      return 7.0
  cruise = controller_type(Original)()
  for stamp in (None, float("nan"), time.monotonic() - 3, time.monotonic() + 5):
    cruise._nav_instruction_state = {"valid": True, "updatedAtMonotonic": stamp}
    assert cruise._get_nav_turn_control_target(20, None, None) == 0
    assert cruise.nav_turn_maneuver == ""
  cruise._nav_instruction_state = {"valid": True, "updatedAtMonotonic": time.monotonic()}
  assert cruise._get_nav_turn_control_target(20, None, None) == 7
  assert cruise.nav_turn_modifier == "right"
  monkeypatch.setenv("TANDEM_ROUTING", "0")
  cruise._nav_instruction_state = {}
  assert cruise._get_nav_turn_control_target(20, None, None) == 7


def test_actual_fixture_uses_existing_route_model_and_banner_timing(daemon):
  _, engine, _, _, _ = daemon
  from openpilot.starpilot.tandem.routing.normalize import normalize
  raw = json.loads((Path(__file__).parent / "fixtures/valhalla-iowa-3.9.1.json").read_text())
  route = engine.NavigationRoute.from_mapbox_route(normalize(raw))
  assert route is not None
  for index in (0, 10, 30, 60, 90):
    payload = route.build_instruction_payload(route.get_progress(route.geometry[index]))
    assert payload["distanceRemaining"] >= 0 and payload["timeRemaining"] >= 0
    assert payload["maneuverType"] and payload["maneuverModifier"]
