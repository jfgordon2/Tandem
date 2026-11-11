"""The route preview's map and arrival estimate (design/routepreview.html).

There are no map tiles on the device, so the map is the mock's stylized one: a quiet grid with the route drawn over
it, fitted to the panel, from the start (a ring) to the destination (a pin). RouteFetcher asks Mapbox for the route
the same way StarPilot's navigationd does (its MapboxRouteEngine, the MapboxSecretKey, and the last GPS fix), in the
background, so the preview can show Arrive, Time and Distance before Start.
"""
from __future__ import annotations

import datetime
import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.layout import Align
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

MAP_FILL = T._hex("111821")
GRID = T._hex("1C2733")
GRID_STEP = T.px(150)
ROUTE_W = T.px(9)
EMPTY = "–"                 # a fact with no route yet (Figtree has no em dash)


@dataclass(frozen=True)
class RoutePlan:
  """A route for the preview map: its path as (latitude, longitude) points, its length in meters and time in seconds."""
  path: tuple[tuple[float, float], ...]   # (latitude, longitude) from the start to the destination
  meters: float
  seconds: float


# ── Words ──

def arrive_text(plan: RoutePlan | None, now: datetime.datetime | None = None) -> str:
  if plan is None:
    return EMPTY
  return ((now or datetime.datetime.now()) + datetime.timedelta(seconds=plan.seconds)).strftime("%-I:%M %p")


def time_text(plan: RoutePlan | None) -> str:
  if plan is None:
    return EMPTY
  minutes = max(1, round(plan.seconds / 60))
  return t_("{} min", minutes) if minutes < 60 else t_("{} h {} min", minutes // 60, minutes % 60)


def distance_text(plan: RoutePlan | None, metric: bool) -> str:
  if plan is None:
    return EMPTY
  value = plan.meters / 1000 if metric else plan.meters / 1609.344
  return f"{value:.1f} {'km' if metric else 'mi'}" if value < 100 else f"{round(value)} {'km' if metric else 'mi'}"


# ── Drawing ──

def project(path: tuple[tuple[float, float], ...], rect: rl.Rectangle, pad: float) -> list[rl.Vector2]:
  """The path fitted into rect (less pad) with north up, keeping its shape."""
  if not path:
    return []
  lat0 = math.radians(sum(p[0] for p in path) / len(path))
  xs = [lon * math.cos(lat0) for _, lon in path]
  ys = [-lat for lat, _ in path]
  span_x, span_y = max(max(xs) - min(xs), 1e-9), max(max(ys) - min(ys), 1e-9)
  room_w, room_h = rect.width - pad * 2, rect.height - pad * 2
  scale = min(room_w / span_x, room_h / span_y)
  left = rect.x + pad + (room_w - span_x * scale) / 2
  top = rect.y + pad + (room_h - span_y * scale) / 2
  return [rl.Vector2(left + (x - min(xs)) * scale, top + (y - min(ys)) * scale) for x, y in zip(xs, ys, strict=True)]


def _thin(points: list[rl.Vector2], spacing: float) -> list[rl.Vector2]:
  kept = points[:1]
  for p in points[1:-1]:
    if math.hypot(p.x - kept[-1].x, p.y - kept[-1].y) >= spacing:
      kept.append(p)
  return kept + points[-1:] if len(points) > 1 else kept


def _pin(tip: rl.Vector2, color: rl.Color) -> None:
  """The mock's teardrop: a round head over a point at tip."""
  r = T.px(17)
  head = rl.Vector2(tip.x, tip.y - T.px(28))
  rl.draw_circle_v(head, r, color)
  rl.draw_triangle(rl.Vector2(tip.x, tip.y), rl.Vector2(head.x + r * 0.87, head.y + r * 0.5), rl.Vector2(head.x - r * 0.87, head.y + r * 0.5),
                   color)


def draw_route_map(rect: rl.Rectangle, plan: RoutePlan | None, status: str) -> None:
  """The map panel: the grid, then the route with its ends, or the status in the middle while there's no route."""
  draw.fill(rect, MAP_FILL, T.RADIUS_PANEL)
  rl.begin_scissor_mode(int(rect.x), int(rect.y), int(rect.width), int(rect.height))
  edge = T.RADIUS_PANEL
  x = rect.x + GRID_STEP * 0.7
  while x < rect.x + rect.width - edge:
    rl.draw_rectangle_rec(rl.Rectangle(x - T.px(5), rect.y, T.px(10), rect.height), GRID)
    x += GRID_STEP
  y = rect.y + GRID_STEP * 0.6
  while y < rect.y + rect.height - edge:
    rl.draw_rectangle_rec(rl.Rectangle(rect.x, y - T.px(5), rect.width, T.px(10)), GRID)
    y += GRID_STEP
  rl.end_scissor_mode()     # the lines stop short of the rounded corners, so a rectangle clip is enough

  if plan is None or len(plan.path) < 2:
    if status:
      draw.text(rect, status, T.font_px(18), T.TEXT_TERTIARY, T.FONT_SEMIBOLD, Align.CENTER)
    return

  # Room for the pin above the destination and the back button in the corner
  points = _thin(project(plan.path, rect, T.px(80)), T.px(3))
  for a, b in zip(points, points[1:], strict=False):
    rl.draw_line_ex(a, b, ROUTE_W, T.ACCENT)
  for p in points:
    rl.draw_circle_v(p, ROUTE_W / 2, T.ACCENT)
  start, end = points[0], points[-1]
  rl.draw_circle_v(start, T.px(13) + T.px(2.5), T.ACCENT)
  rl.draw_circle_v(start, T.px(13) - T.px(2.5), T.BG)
  _pin(rl.Vector2(end.x, end.y), T.TEXT)


# ── Fetching ──

def gps_fix(raw: str) -> tuple[float, float, float | None] | None:
  """(latitude, longitude, bearing) from StarPilot's LastGPSPosition, as navigationd reads it, or None without a fix."""
  try:
    state = json.loads(raw) if raw else None
  except json.JSONDecodeError:
    return None
  if not isinstance(state, dict) or not state.get("hasFix", False):
    return None
  lat, lon = float(state.get("latitude", 0.0) or 0.0), float(state.get("longitude", 0.0) or 0.0)
  if not (math.isfinite(lat) and math.isfinite(lon)) or (abs(lat) < 1e-6 and abs(lon) < 1e-6):
    return None
  bearing = float(state.get("bearing", 0.0) or 0.0)
  return lat, lon, bearing if math.isfinite(bearing) else None


def start_position(live: str, saved: str) -> tuple[float, float, float | None] | None:
  """Where the route starts: the live fix, else the last position StarPilot saved.

  Parked indoors there's often no live fix, but the car hasn't moved. The saved heading may be old, so it isn't used.

  Args:
    live: Memory LastGPSPosition, kept only while the GPS has a fix.
    saved: Persistent LastGPSPosition, written when the car turns off and while parked.

  Returns:
    (latitude, longitude, heading or None), or None when neither has a position.
  """
  fix = gps_fix(live)
  if fix is not None:
    return fix
  saved_fix = gps_fix(saved)
  return (saved_fix[0], saved_fix[1], None) if saved_fix is not None else None


FINDING = N_("Finding a route…")
NO_FIX = N_("Needs a GPS fix to plan the route")
NO_ROUTE = N_("Couldn't find a route. Check the connection.")
NOT_SET_UP = N_("Routes need the secret Mapbox key: see Settings › Driving › Speed & Steering › Navigation")


class RouteFetcher:
  """One route at a time for the place being previewed; a newer place replaces an older request. Without a route (no
  GPS position yet, no connection), it asks again every RETRY seconds while the preview is open, keeping the reason up."""
  RETRY = 5.0

  def __init__(self, fetch: Callable[[dict], RoutePlan | str], clock: Callable[[], float] = time.monotonic,
               identity: Callable[[dict], tuple] | None = None, max_age: float | None = None, retry_errors: tuple[str, ...] = ()):
    self._fetch = fetch          # runs in the background: a plan, or the reason there isn't one
    self._clock = clock
    self._lock = threading.Lock()
    self._key: tuple | None = None
    self._result: RoutePlan | str = ""
    self._busy = False
    self._done_at = 0.0
    self._identity, self._max_age = identity, max_age
    self._retry_errors = (NO_FIX, NO_ROUTE, *retry_errors)
    self._generation = 0

  def route(self, place: dict | None) -> tuple[RoutePlan | None, str]:
    """The route to place, or why there isn't one yet. Fetches in the background, again when the place changes or a retryable error has waited RETRY seconds."""
    if place is None:
      return None, ""
    key = self._identity(place) if self._identity else (place.get("latitude"), place.get("longitude"))
    with self._lock:
      if key != self._key:
        self._key, self._result = key, FINDING
        self._start(key, place)
      elif (not self._busy and isinstance(self._result, str) and self._result in self._retry_errors
            and self._clock() - self._done_at >= self.RETRY):
        self._start(key, place)
      elif not self._busy and self._max_age is not None and self._clock() - self._done_at >= self._max_age:
        self._result = FINDING
        self._start(key, place)
      result = self._result
    return (result, "") if isinstance(result, RoutePlan) else (None, result)

  def _start(self, key: tuple, place: dict) -> None:
    self._busy = True
    self._generation += 1
    threading.Thread(target=self._run, args=(key, self._generation, dict(place)), daemon=True).start()

  def _run(self, key: tuple, generation: int, place: dict) -> None:
    try:
      result = self._fetch(place)
    except Exception:
      result = NO_ROUTE
    with self._lock:
      if key == self._key and generation == self._generation:
        self._result, self._busy, self._done_at = result, False, self._clock()


def mapbox_route(place: dict) -> RoutePlan | str:
  """StarPilot's own route request, from the last GPS fix to place."""
  from openpilot.common.params import Params
  from openpilot.starpilot.navigation.route_engine import Coordinate, MapboxRouteEngine
  token = Params().get("MapboxSecretKey", encoding="utf-8") or ""
  if not token.strip():
    return NOT_SET_UP
  fix = start_position(Params(memory=True).get("LastGPSPosition", encoding="utf-8") or "",
                       Params().get("LastGPSPosition", encoding="utf-8") or "")
  if fix is None:
    return NO_FIX
  route = MapboxRouteEngine().fetch_route(token, Coordinate(fix[0], fix[1]), place, fix[2])
  if route is None:
    return NO_ROUTE
  return RoutePlan(tuple((c.latitude, c.longitude) for c in route.geometry), route.total_distance, route.total_duration)


def local_start() -> tuple[float, float, float | None] | None:
  from openpilot.common.params import Params
  try:
    return start_position(Params(memory=True).get("LastGPSPosition", encoding="utf-8") or "",
                          Params().get("LastGPSPosition", encoding="utf-8") or "")
  except (ValueError, TypeError, OverflowError):
    return None


def local_identity(place: dict) -> tuple:
  """What a local route preview depends on, so the preview refetches when any of it changes (a move of about 40 m counts)."""
  from openpilot.common.params import Params
  from openpilot.starpilot.tandem.routing.bundles import capability
  state, fix = capability(), local_start()
  # A roughly 40 m grid avoids planning every GPS tick while rejecting a moved parked preview.
  start = (round(fix[0] / .0004), round(fix[1] / .0004), round(fix[2] / 15) if fix[2] is not None else None) if fix else None
  from openpilot.starpilot.tandem.routing.config import policy
  return (place.get("latitude"), place.get("longitude"), place.get("routeId"), state["status"], state.get("generation"), policy(),
          Params().get("MapboxSecretKey", encoding="utf-8") or "",
          start, Params().get("LanguageSetting", encoding="utf-8") or "en")


def local_route(place: dict) -> RoutePlan | str:
  """A route preview from offline routing, or the reason there isn't one."""
  from openpilot.common.params import Params
  from openpilot.starpilot.tandem.routing import client
  from openpilot.starpilot.tandem.routing.config import RoutingError
  from openpilot.starpilot.tandem.routing.normalize import normalize
  from openpilot.selfdrive.ui.tandem.routing_status import status_text
  fix = local_start()
  if fix is None:
    return NO_FIX
  try:
    data = normalize(client.route(fix, place, caller="preview", language=Params().get("LanguageSetting", encoding="utf-8") or "en"))
    return RoutePlan(tuple((c["latitude"], c["longitude"]) for c in data["geometry"]), data["totalDistance"], data["totalDuration"])
  except RoutingError as error:
    return status_text(error.code)


def policy_route(place: dict) -> RoutePlan | str:
  """A route preview from StarPilot's route engine, online or offline as Navigation's preference says, or the reason there isn't one."""
  from openpilot.common.params import Params
  from openpilot.starpilot.navigation.route_engine import Coordinate
  from openpilot.starpilot.tandem.routing.route_engine import PolicyRouteEngine
  from openpilot.selfdrive.ui.tandem.routing_status import status_text
  fix = local_start()
  if fix is None:
    return NO_FIX
  engine = PolicyRouteEngine(caller="preview", language=Params().get("LanguageSetting", encoding="utf-8") or "en")
  route = engine.fetch_route(Params().get("MapboxSecretKey", encoding="utf-8") or "", Coordinate(*fix[:2]), place, fix[2])
  if route is None:
    return status_text(engine.status)
  return RoutePlan(tuple((c.latitude, c.longitude) for c in route.geometry), route.total_distance, route.total_duration)
