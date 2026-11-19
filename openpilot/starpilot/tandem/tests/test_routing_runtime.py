"""Offline routing inside StarPilot 7's navigation (routing/navigation.py): a real Valhalla answer becomes StarPilot's own
NavigationRoute, providers are tried in the driver's order, and StarPilot's RouteRuntime routes without a Mapbox key
when offline data is ready."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from openpilot.starpilot.navigation.owner import NavigationOwner, ValidationError
from openpilot.starpilot.navigation.route_engine import NavigationRoute
from openpilot.starpilot.navigation.runtime import RouteRuntime
from openpilot.starpilot.tandem.routing import config as C, navigation as N

IOWA = json.loads((Path(__file__).parent / "fixtures/valhalla-iowa-3.9.1.json").read_text())
START, END = (-93.6091, 41.6005), {"name": "Ankeny", "latitude": 41.7318, "longitude": -93.6001}


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path / "state"))
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  for name in C.SCREENS:
    monkeypatch.setenv(name, "1")
  monkeypatch.setattr(N, "language", lambda: "en")


def ready(monkeypatch: pytest.MonkeyPatch, status: str = "ready") -> None:
  monkeypatch.setattr(N, "capability", lambda: {"status": status, "generation": "g"})


def test_a_valhalla_answer_is_starpilots_own_route() -> None:
  asked: list[tuple] = []

  def fetch(start: tuple, destination: dict, **options: Any) -> dict:
    asked.append((start, options["avoid"], options["caller"]))
    return IOWA
  route = N.LocalRouteEngine(fetch=fetch).fetch("", START, END, 90.0, ("toll",))
  assert isinstance(route, NavigationRoute) and route.alternatives == [route]
  assert asked == [((41.6005, -93.6091, 90.0), ("toll",), "navigation")]
  assert route.total_distance > 1000 and route.steps[0].text and route.preview()
  progress = route.progress(route.points[0], 10.0, None)
  assert progress.instruction and not progress.arrived


def test_a_routing_failure_reaches_starpilot_as_its_reason() -> None:
  def fail(*_: Any, **__: Any) -> dict:
    raise C.RoutingError("outside_coverage")
  with pytest.raises(ValidationError, match="outside_coverage"):
    N.LocalRouteEngine(fetch=fail).fetch("", START, END)


@pytest.mark.parametrize("only,first,answers,expected", [
  (False, "online", "online", ["online"]), (False, "offline", "offline", ["offline"]),
  (False, "online", "offline", ["online", "offline"]), (False, "offline", "online", ["offline", "online"]),
  (True, "online", "online", ["offline"]), (False, "online", "neither", ["online", "offline"]),
])
def test_providers_are_tried_once_each_in_the_drivers_order(monkeypatch: pytest.MonkeyPatch, only: bool, first: str, answers: str,
                                                            expected: list[str]) -> None:
  ready(monkeypatch)
  C.set_policy(offline_only=only, preferred=first)
  calls: list[str] = []
  route = object()

  def provider(name: str) -> Any:
    def fetch(*_: Any) -> Any:
      calls.append(name)
      if name != answers:
        raise ValidationError("no_route")
      return route
    return fetch

  class Local:
    def fetch(self, *args: Any) -> Any:
      return provider("offline")(*args)
  try:
    result = N.fetch_by_policy(lambda: (provider("online"), "key"), Local(), ("key", ""), START, END, None, ())  # type: ignore[arg-type]
  except ValidationError:
    result = None
  assert calls == expected and (result is route) == (answers in expected)
  assert N.STATUS.read(60) == ({"status": "ready", "provider": answers, "fallback": len(expected) > 1} if result else
                               {"status": "no_route", "provider": "", "fallback": False})


def test_turning_on_offline_maps_only_during_an_attempt_stops_the_online_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
  ready(monkeypatch)
  C.set_policy(preferred="offline")
  calls: list[str] = []

  class Local:
    def fetch(self, *_: Any) -> Any:
      C.set_policy(offline_only=True)
      raise ValidationError("no_route")
  with pytest.raises(ValidationError, match="superseded"):
    N.fetch_by_policy(lambda: (lambda *_: calls.append("online"), "key"), Local(), ("key", ""), START, END, None, ())  # type: ignore[arg-type]
  assert calls == []


def test_without_a_mapbox_key_offline_data_still_routes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  owner = NavigationOwner(tmp_path / "navigation", transient_root=tmp_path / "transient")
  owner._is_metric = lambda: False   # type: ignore[method-assign]   # its IsMetric param needs the device's Params
  revision = owner.configure({"enabled": True}, owner.read()["revision"], True)["revision"]
  owner.select(END, revision, True)
  runtime = N.runtime_class(RouteRuntime)(owner, executor=Now())
  runtime.local = N.LocalRouteEngine(fetch=lambda *_, **__: IOWA)
  assert runtime.update(1_000, None, 0)["status"] == "needsKey"   # no offline data yet
  ready(monkeypatch)
  status = runtime.update(2_000, (1_500, START, 10.0, 0.0), 1_000)
  assert status["status"] == "routing"
  status = runtime.update(3_000, (2_500, START, 10.0, 0.0), 1_000)
  assert status["status"] == "guiding" and status["instruction"]
  assert N.STATUS.read(60) == {"status": "ready", "provider": "offline", "fallback": True}


def test_with_offline_routing_off_starpilots_runtime_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("TANDEM_ROUTING", "0")
  assert N.runtime_class(RouteRuntime) is RouteRuntime


class Now:
  """Runs a fetch at once, as StarPilot's route thread would."""

  def submit(self, work: Any, *args: Any) -> Any:
    from concurrent.futures import Future
    future: Future = Future()
    try:
      future.set_result(work(*args))
    except Exception as error:
      future.set_exception(error)
    return future
