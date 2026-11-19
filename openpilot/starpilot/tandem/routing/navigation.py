"""Offline routing as a provider inside StarPilot 7's navigation (starpilot/navigation/runtime.py).

StarPilot's RouteRuntime keeps everything about following a route: GPS, joining, off-route rerouting, arrival and what it
publishes. Tandem only changes where a route comes from. Each request tries the providers in the driver's order
(config.provider_order): StarPilot's own online fetch (Mapbox, or Google with its key) and Valhalla on this device's
routing data. Offline maps only never asks online. A route from Valhalla is StarPilot's own NavigationRoute, made from
Valhalla's OSRM-format answer, so guidance, turn slowing and the screens read it as they read Mapbox's.

routing-status.json says which provider answered and, when none did, why, for the screens.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.starpilot.tandem.routing import client, config as C
from openpilot.starpilot.tandem.routing.bundles import capability
from openpilot.starpilot.tandem.routing.normalize import normalize
from openpilot.starpilot.tandem.state import Snapshot

STATUS = Snapshot("routing-status.json")
Fetch = Callable[..., Any]


def language() -> str:
  """The driver's language for Valhalla's instructions."""
  from openpilot.common.params import Params
  return Params().get("LanguageSetting") or "en"


def offline_ready() -> bool:
  return C.enabled() and capability()["status"] == "ready"


def can_route(settings: dict) -> bool:
  """Whether a route can be asked for: StarPilot's Mapbox key, unless offline maps only; or ready offline data."""
  online = bool(settings.get("token")) and not C.policy()[0]
  return online or offline_ready()


class LocalRouteEngine:
  """Valhalla routes, with StarPilot's route engine signature (MapboxRouteEngine.fetch).

  Args:
    caller: "navigation" or "preview"; a preview yields to navigation in the broker.
    fetch: The broker request (client.route); a stand-in in tests.
  """

  def __init__(self, caller: str = "navigation", fetch: Fetch = client.route):
    self.caller, self._fetch = caller, fetch

  def fetch(self, token: str, position: tuple[float, float], destination: dict, bearing: float | None = None,
            exclusions: tuple[str, ...] = ()) -> Any:
    """A route from this device's routing data.

    Args:
      token: Unused: offline routing needs no key.
      position: (longitude, latitude), as StarPilot passes it.
      destination: StarPilot's destination, with latitude and longitude.
      bearing: The car's heading, or None.
      exclusions: StarPilot's avoidances ("toll", "motorway", "ferry").

    Raises:
      ValidationError: Why there's no route, as StarPilot's runtime expects; its message is the routing code.
    """
    from openpilot.starpilot.navigation.owner import ValidationError
    from openpilot.starpilot.navigation.route_engine import NavigationRoute
    try:
      response = self._fetch((position[1], position[0], bearing), destination, caller=self.caller, language=language(),
                             avoid=tuple(exclusions))
      normalize(response)   # Tandem's checks on Valhalla's answer before StarPilot reads it
      route = NavigationRoute(response["routes"][0])
    except C.RoutingError as error:
      raise ValidationError(error.code) from None
    route.alternatives = [route]  # type: ignore[attr-defined]   # as StarPilot's MapboxRouteEngine marks its routes
    return route


def fetch_by_policy(online: Callable[[], tuple[Fetch, Any]], local: LocalRouteEngine, credentials: tuple[str, str],
                    position: tuple[float, float], destination: dict, bearing: float | None, exclusions: tuple[str, ...],
                    record: bool = True) -> Any:
  """A route from each provider in the driver's order, stopping at the first that answers.

  Args:
    online: StarPilot's own fetch and its first argument (RouteRuntime._fetcher).
    local: The Valhalla engine.
    credentials: (Mapbox key, Google key or "").
    position: (longitude, latitude).
    destination: StarPilot's destination.
    bearing: The car's heading, or None.
    exclusions: StarPilot's avoidances.
    record: Write routing-status.json (navigation does; a preview doesn't).

  Raises:
    ValidationError: When no provider answers; its message is the last provider's reason.
  """
  from openpilot.starpilot.navigation.owner import ValidationError
  policy = C.policy()
  errors: list[str] = []

  def current() -> bool:
    """Still the driver's choice: turning on Offline maps only during an attempt must stop an online fallback."""
    return C.policy() == policy and C.enabled()

  for provider in C.provider_order():
    if not current():
      raise ValidationError("superseded")
    try:
      if provider == "online":
        if not credentials[0]:
          errors.append("online_unavailable")
          continue
        fetch, first = online()
        route = fetch(first, position, destination, bearing, exclusions)
      else:
        state = capability()
        if state["status"] != "ready":
          errors.append(state["status"])
          continue
        route = local.fetch(credentials[0], position, destination, bearing, exclusions)
    except (ValidationError, OSError, ValueError) as error:
      errors.append(str(error) if provider == "offline" else "online_unavailable")
      continue
    if not current():
      raise ValidationError("superseded")
    if record:
      STATUS.write({"status": "ready", "provider": provider, "fallback": bool(errors)})
    return route
  code = errors[-1] if errors else "no_route"
  if record:
    STATUS.write({"status": code, "provider": "", "fallback": False})
  raise ValidationError(code)


def runtime_class(base: type) -> type:
  """StarPilot's RouteRuntime with Valhalla as a provider, or base unchanged when offline routing is off.

  Args:
    base: StarPilot's RouteRuntime (passed in, so this module doesn't import StarPilot's navigation process).
  """
  if not C.enabled():
    return base

  class TandemRouteRuntime(base):  # type: ignore[valid-type, misc]
    """Routes by the driver's order of providers; the rest is StarPilot's."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
      super().__init__(*args, **kwargs)
      self.local = LocalRouteEngine()

    def _can_route(self, settings: dict) -> bool:
      return can_route(settings)

    def _fetcher(self, credentials: tuple[str, str]) -> tuple[Fetch, Any]:
      return self._fetch_by_policy, credentials

    def _fetch_by_policy(self, credentials: tuple[str, str], position: tuple[float, float], destination: dict,
                         bearing: float | None, exclusions: tuple[str, ...]) -> Any:
      online = super()._fetcher   # StarPilot's own choice: Google with its key, else Mapbox
      return fetch_by_policy(lambda: online(credentials), self.local, credentials, position, destination, bearing, exclusions)

  return TandemRouteRuntime
