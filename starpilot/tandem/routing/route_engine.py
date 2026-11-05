"""Local provider implementing StarPilot's existing route-engine interface."""
from __future__ import annotations

import time

from openpilot.starpilot.tandem.routing import client
from openpilot.starpilot.tandem.routing.config import RoutingError
from openpilot.starpilot.tandem.routing.normalize import normalize
from openpilot.starpilot.tandem.routing import config as C


class PolicyRouteEngine:
  """One ordered, finite attempt per provider, shared by previews and navigation.

  The existing online engine has a five-second request timeout, and the local
  client has a fifteen-second deadline. A failed attempt therefore has a finite
  twenty-second transport budget, with no provider alternation loop.
  """
  def __init__(self, caller="navigation", language="en", online=None, offline=None, clock=time.monotonic):
    self.online, self.offline = online, offline or LocalRouteEngine(caller, language)
    self.clock = clock
    self.retry_at = 0.0
    self.status, self.provider, self.fallback_at = "idle", "", 0.0

  def available(self, token):
    from openpilot.starpilot.tandem.routing.bundles import capability
    return ("online" in C.provider_order() and bool(token.strip())) or capability()["status"] == "ready"

  def fetch_route(self, token, start, destination, bearing=None):
    if self.clock() < self.retry_at:
      return None
    policy = C.policy()
    self.status = "routing"
    errors = []
    for provider in C.provider_order():
      # Re-read before every network attempt: turning strict mode on during a
      # local attempt must prevent a subsequent online fallback.
      if C.policy() != policy or not C.enabled():
        self.status = "superseded"
        return None
      try:
        if provider == "online":
          if not token.strip():
            errors.append("online_unavailable")
            continue
          if self.online is None:
            from openpilot.starpilot.navigation.route_engine import MapboxRouteEngine
            self.online = MapboxRouteEngine()
          result = self.online.fetch_route(token, start, destination, bearing)
          error = "online_unavailable"
        else:
          result = self.offline.fetch_route(token, start, destination, bearing)
          error = self.offline.status
        if result is not None:
          if C.policy() != policy or not C.enabled():
            self.status = "superseded"
            return None
          self.provider, self.status, self.retry_at = provider, "ready", 0.0
          self.fallback_at = self.clock() if errors else 0.0
          return result
        errors.append(error)
      except Exception:
        errors.append("worker_failed" if provider == "offline" else "online_unavailable")
    self.status = errors[-1] if errors else "no_route"
    self.retry_at = self.clock() + 3
    return None


class LocalRouteEngine:
  def __init__(self, caller: str = "navigation", language: str = "en", fetch=None, clock=time.monotonic):
    self.caller, self.language = caller, language
    self.fetch = fetch or client.route
    self.clock = clock
    self.retry_at = 0.0
    self.status = "idle"

  def fetch_route(self, token, start, destination, bearing=None):
    if self.clock() < self.retry_at:
      return None
    self.status = "routing"
    try:
      from openpilot.starpilot.navigation.route_engine import NavigationRoute
      response = self.fetch((start.latitude, start.longitude, bearing), destination, caller=self.caller, language=self.language)
      route = NavigationRoute.from_mapbox_route(normalize(response))
      if route is None:
        raise RoutingError("invalid_response")
      self.status, self.retry_at = "ready", 0.0
      return route
    except RoutingError as error:
      self.status = error.code
    except Exception:
      # The upstream fetch thread has no exception finalizer; always return so it releases its inflight flag.
      self.status = "worker_failed"
    self.retry_at = self.clock() + (30 if self.status in ("data_incompatible", "outside_coverage", "no_route") else 3)
    return None
