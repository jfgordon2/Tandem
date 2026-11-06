"""Owned readiness and lifecycle changes around the original navigation progress/publish loop."""
from __future__ import annotations

import json
import math
from time import monotonic

from openpilot.starpilot.tandem.routing.config import enabled, policy
from openpilot.starpilot.tandem.routing.bundles import capability
from openpilot.starpilot.tandem.state import Snapshot

STATUS = Snapshot("routing-status.json")


def navigationd_type(base):
  if not enabled():
    return base

  class LocalNavigationd(base):
    def __init__(self, route_engine=None):
      from openpilot.starpilot.tandem.routing.route_engine import PolicyRouteEngine
      super().__init__(route_engine=route_engine or PolicyRouteEngine(language=self_language()))
      self._local_destination_key = None
      self._local_generation = None
      self._local_unreliable = False
      self._display_estimate = None

    def _can_fetch_route(self, token):
      return enabled() and ((not policy()[0] and bool(token)) or capability()["status"] == "ready")

    def _clear_route(self, *, remove_destination=False):
      self._display_estimate = None
      super()._clear_route(remove_destination=remove_destination)
      # The previous producer's memory may exist before this instance publishes its first state.
      self.params_memory.remove("NavInstructionState")

    def _update_location(self):
      try:
        valid, speed = super()._update_location()
        state = json.loads(self.params_memory.get("LastGPSPosition", encoding="utf-8") or "{}")
        stamp = float(state.get("updatedAtMonotonic", 0))
        valid &= math.isfinite(stamp) and 0 < stamp <= monotonic() and monotonic() - stamp <= 2.5 and math.isfinite(speed)
      except (ValueError, TypeError, AttributeError):
        valid, speed = False, 0.0
      if not valid:
        self._last_position = self._last_bearing = None
      return valid, speed if valid else 0.0

    def _maybe_update_route(self, destination):
      state = capability()
      key = self._destination_key(destination)
      generation = (state.get("generation"), policy(), self._route_token(), enabled())
      if key != self._local_destination_key or generation != self._local_generation or not enabled():
        # _clear_route invalidates the requested key. A late old fetch then fails upstream's still_current check.
        self._clear_route()
        self._local_destination_key, self._local_generation = key, generation
        self.route_engine.retry_at = 0.0
      return super()._maybe_update_route(destination)

    def _build_progress(self, route, location_valid, v_ego):
      progress, state = super()._build_progress(route, location_valid, v_ego)
      self._local_unreliable = bool(state and (state["offRoute"] or state["misaligned"]))
      return progress, state

    def _maybe_recompute(self, route, destination, progress, state):
      from openpilot.starpilot.navigation.navigationd import ARRIVAL_CLEAR_SECONDS
      if state and self._timer_expired(self._arrival_started_at, ARRIVAL_CLEAR_SECONDS, float(state["now"])):
        self._clear_route(remove_destination=True)
        return
      super()._maybe_recompute(route, destination, progress, state)

    def _publish_nav_instruction(self, route, progress, location_valid, payload=None):
      super()._publish_nav_instruction(route, progress, location_valid and not self._local_unreliable, payload)

    def _publish_nav_state(self, route, progress, location_valid, payload=None):
      super()._publish_nav_state(route, progress, location_valid and not self._local_unreliable, payload)
      status = getattr(self.route_engine, "status", "idle")
      if route is None and status == "ready":
        status = "routing"
      state = capability()
      if policy()[0] and state["status"] != "ready":
        status = state["status"]
      elif route is None and not self._can_fetch_route(self._route_token()):
        status = "route_unavailable"
      if self._last_position is None:
        status = "gps_waiting"
      elif self._local_unreliable and status in ("ready", "idle", "routing"):
        status = "rerouting"
      if route is not None and progress is not None and location_valid and not self._local_unreliable:
        self._display_estimate = {"seconds": float(progress.time_remaining), "meters": float(progress.distance_remaining),
                                  "at": monotonic()}
      estimate = getattr(self, "_display_estimate", None)
      # Display-only grace. Never feed these retained values into navInstruction
      # or NavInstructionState, and expire them during a long GPS/reroute outage.
      if estimate is not None and monotonic() - estimate["at"] > 20:
        estimate = None
      STATUS.write({"status": status, "active": route is not None, "estimate": estimate,
                    "provider": getattr(self.route_engine, "provider", ""),
                    "fallback_at": getattr(self.route_engine, "fallback_at", 0)})

    def run(self):
      try:
        super().run()
      finally:
        self._clear_route()
        self._publish_nav_route_if_needed()
        STATUS.write({"status": "idle", "active": False})

  return LocalNavigationd


def self_language() -> str:
  from openpilot.common.params import Params
  return Params().get("LanguageSetting", encoding="utf-8") or "en"
