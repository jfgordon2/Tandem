"""Where to?'s places on StarPilot 7's navigation owner (starpilot/navigation/owner.py).

StarPilotPlaces is the Places source destinations.py draws. StarPilot keeps the destination, favorites (with Home and
Work as labels), recents and keys, and checks each change against the revision it was read at. Search runs StarPilot's
own place search in the background. A picked place is a local draft until Start; its preview route comes from
StarPilot's own route engine for the chosen provider (Mapbox, or Google with its key), from the last saved position,
with the driver's avoidances. Start sets the destination, and StarPilot's navigation process routes and guides from
there. StarPilot's navigation has its own on/off setting; Start turns it on, since the driver asked for a route.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.routemap import NO_FIX, NO_ROUTE, NOT_SET_UP, RouteFetcher, RoutePlan

REFRESH_S = 1.0


def _owner() -> Any:
  from openpilot.starpilot.navigation.owner import NavigationOwner
  return NavigationOwner()


class StarPilotPlaces:
  """Places over StarPilot's navigation owner.

  Args:
    owner: Makes StarPilot's NavigationOwner.
    allowed: Whether navigation changes are allowed now (not in replay or projection).
    metric: Whether to show metric units.
    clock: Monotonic seconds.
    executor: Runs searches; one worker by default.
  """

  def __init__(self, owner: Callable[[], Any] = _owner, allowed: Callable[[], bool] = lambda: True, metric: Callable[[], bool] = lambda: False,
               clock: Callable[[], float] = time.monotonic, executor: Callable[[], Any] = lambda: ThreadPoolExecutor(max_workers=1,
                                                                                                                 thread_name_prefix="tandem-places")):
    self._make_owner, self._allowed, self._metric, self._clock, self._make_executor = owner, allowed, metric, clock, executor
    self._owner: Any = None
    self._executor: Any = None
    self._snap: dict = {}
    self._read_at = -1e9
    self._draft: dict | None = None
    self._results: list[dict] = []
    self._search: Future | None = None
    self._query = ""
    self._error = ""
    self._routes = RouteFetcher(self._fetch_route)

  # ── Reading ──

  def owner(self) -> Any:
    if self._owner is None:
      self._owner = self._make_owner()
    return self._owner

  def refresh(self) -> None:
    try:
      self._snap = self.owner().snapshot()
    except (OSError, ValueError, RuntimeError):
      pass
    self._read_at = self._clock()

  def _snapshot(self) -> dict:
    if self._clock() - self._read_at >= REFRESH_S:
      self.refresh()
    return self._snap

  def snapshot(self) -> dict:
    """StarPilot's navigation state, read at most every REFRESH_S."""
    return self._snapshot()

  def configure(self, patch: dict) -> bool:
    """Changes StarPilot's navigation settings (configure); False when StarPilot refuses or the state moved on."""
    return self._change(lambda o, r: o.configure(patch, r, self._allowed))

  def tick(self) -> None:
    search = self._search
    if search is not None and search.done():
      self._search = None
      try:
        self._results = list(search.result())
        self._error = ""
      except Exception as error:   # StarPilot's own message: a missing key, the monthly budget, no connection
        self._results, self._error = [], str(error)
    self._snapshot()

  def active(self) -> dict | None:
    return self._snapshot().get("destination")

  def favorites(self) -> list[dict]:
    """Home, Work, then the rest in the order they were saved (StarPilot's order), each with is_home and is_work."""
    return [dict(f, is_home=f.get("label") == "home", is_work=f.get("label") == "work") for f in self._snapshot().get("favorites", [])]

  def recents(self) -> list[dict]:
    return list(self._snapshot().get("recents", []))

  def _identity(self, place: dict | None) -> str | None:
    if not place:
      return None
    if place.get("id"):
      return str(place["id"])
    from openpilot.starpilot.navigation.owner import ValidationError, destination
    try:
      return str(destination(place)["id"])
    except ValidationError:
      return None

  def _favorite(self, place: dict | None) -> dict | None:
    identity = self._identity(place)
    return next((f for f in self._snapshot().get("favorites", []) if f["id"] == identity), None) if identity else None

  def is_favorite(self, place: dict) -> bool:
    return self._favorite(place) is not None

  # ── Changing ──

  def _change(self, change: Callable[[Any, str], Any]) -> bool:
    """One change at the revision last read; on a conflict or refusal, read again and report False."""
    try:
      change(self.owner(), str(self._snapshot().get("revision", "")))
      return True
    except (ValueError, PermissionError, OSError):
      return False
    finally:
      self.refresh()

  def toggle_saved(self, place: dict) -> None:
    favorite = self._favorite(place)
    if favorite is not None:
      self._change(lambda o, r: o.remove_favorite(favorite["id"], r, self._allowed))
    else:
      self._change(lambda o, r: o.favorite(place, r, self._allowed))

  def search(self, query: str) -> None:
    self._query = query
    if self._search is not None and not self._search.done():
      self._search.cancel()
    if self._executor is None:
      self._executor = self._make_executor()
    owner = self.owner()
    self._search = self._executor.submit(owner.search, query)

  def results(self) -> list[tuple[str, str]]:
    return [(r["name"], r.get("address", "")) for r in self._results]

  def status(self) -> tuple[str, str] | None:
    if self._search is not None:
      return N_("Searching…"), N_("Looking up places")
    if self._error:
      return N_("Search unavailable"), self._error
    if self._query and not self._results:
      return N_("Nothing found"), N_("Try a different place or address")
    return None

  def pick_result(self, index: int) -> None:
    if 0 <= index < len(self._results):
      self._draft = self._results[index]

  def pick(self, place: dict) -> None:
    self._draft = dict(place)

  def draft(self) -> dict | None:
    return self._draft

  def clear_draft(self) -> None:
    self._draft = None

  def saved_as(self) -> tuple[bool, bool, bool]:
    favorite = self._favorite(self._draft)
    if favorite is None:
      return False, False, False
    return True, favorite.get("label") == "home", favorite.get("label") == "work"

  def toggle(self, kind: str) -> None:
    """Saves or forgets the draft ("favorite"), or makes it Home or Work, or takes that label away."""
    draft = self._draft
    if draft is None:
      return
    favorite = self._favorite(draft)
    if kind == "favorite":
      self.toggle_saved(draft)
      return
    label = "home" if kind == "home" else "work"
    if favorite is None:
      self._change(lambda o, r: o.favorite(draft, r, self._allowed, label=label))
    else:
      self._change(lambda o, r: o.label_favorite(favorite["id"], None if favorite.get("label") == label else label, r, self._allowed))

  def can_search(self) -> bool:
    return bool(self._snapshot().get("hasKey"))

  def can_start(self) -> bool:
    return bool(self._snapshot().get("hasKey")) and self._draft is not None

  def start(self) -> bool:
    """Sets the draft as StarPilot's destination, turning its navigation on first if it's off."""
    draft = self._draft
    if draft is None or not self.can_start():
      return False
    if not self._snapshot().get("enabled") and not self._change(lambda o, r: o.configure({"enabled": True}, r, self._allowed)):
      return False
    if not self._change(lambda o, r: o.select(draft, r, self._allowed)):
      return False
    self._draft = None
    return True

  def end_route(self) -> None:
    self._change(lambda o, r: o.clear(r, self._allowed))

  def maps_ready(self) -> bool:
    return True   # StarPilot 7 routes online; its offline road maps are for the map's background

  def route(self) -> tuple[RoutePlan | None, str]:
    if not self._snapshot().get("hasKey"):
      return None, NOT_SET_UP
    return self._routes.route(self._draft)

  def metric(self) -> bool:
    return bool(self._metric())

  # ── The preview route ──

  def _fetch_route(self, place: dict) -> RoutePlan | str:
    """StarPilot's own route request for the preview, from the last saved position, in the background."""
    owner = self.owner()
    settings = owner.read_routing()
    position = owner.position_store.read()
    if not position:
      return NO_FIX
    from openpilot.starpilot.navigation.owner import ROUTE_AVOIDANCES
    exclusions = tuple(value for key, value in ROUTE_AVOIDANCES.items() if settings.get(key))
    origin, bearing = (position["longitude"], position["latitude"]), position.get("bearing")
    try:
      if settings.get("routeProvider") == "google" and settings.get("googleKey"):
        from openpilot.starpilot.navigation.google_routes import GoogleRouteEngine, essentials_budget, route_budget
        engine: Any = GoogleRouteEngine(owner.session, route_budget(owner.google_root), essentials_budget(owner.google_root))
        route = engine.fetch(settings["googleKey"], origin, place, bearing, exclusions)
      else:
        from openpilot.starpilot.navigation.mapbox_budget import MonthlyBudget
        from openpilot.starpilot.navigation.route_engine import MapboxRouteEngine
        route = MapboxRouteEngine(owner.session, MonthlyBudget("directions", owner.root / "mapbox-usage")).fetch(
          settings["token"], origin, place, bearing, exclusions)
    except Exception:
      return NO_ROUTE
    return RoutePlan(tuple((lat, lon) for lon, lat in route.points), float(route.total_distance), float(route.total_duration))
