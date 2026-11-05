"""Validate a local OSRM response before it reaches StarPilot's instruction consumers."""
from __future__ import annotations

import math

from openpilot.starpilot.tandem.routing.config import RoutingError

TYPES = {"depart", "arrive", "turn", "continue", "new name", "merge", "on ramp", "off ramp", "fork", "end of road",
         "roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary", "notification", "use lane"}
DIRECTIONS = {"none", "straight", "left", "right", "slight left", "slight right", "sharp left", "sharp right", "uturn"}


def number(value, *, minimum: float = 0.0) -> float:
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
    raise RoutingError("invalid_response")
  return float(value)


def coordinate(value) -> dict:
  if not isinstance(value, (list, tuple)) or len(value) != 2:
    raise RoutingError("invalid_response")
  lon, lat = number(value[0], minimum=-180), number(value[1], minimum=-90)
  if lon > 180 or lat > 90:
    raise RoutingError("invalid_response")
  return {"latitude": lat, "longitude": lon}


def banners(raw) -> list:
  result = []
  for banner in raw or []:
    primary = banner["primary"]
    if not isinstance(primary.get("text"), str) or primary.get("type", "turn") not in TYPES:
      raise RoutingError("invalid_response")
    if primary.get("modifier", "none") not in DIRECTIONS:
      raise RoutingError("invalid_response")
    item = {"distanceAlongGeometry": number(banner["distanceAlongGeometry"]), "primary": dict(primary)}
    if banner.get("secondary") is not None:
      text = banner["secondary"].get("text", "")
      if not isinstance(text, str):
        raise RoutingError("invalid_response")
      item["secondary"] = {"text": text}
    lanes = []
    for lane in (banner.get("sub") or {}).get("components", []):
      if lane.get("type") != "lane":
        continue
      directions = lane.get("directions", [])
      if (not isinstance(directions, list) or any(d not in DIRECTIONS for d in directions)
          or not isinstance(lane.get("active"), bool) or lane.get("active_direction", "none") not in DIRECTIONS):
        raise RoutingError("invalid_response")
      lanes.append(dict(lane))
    if lanes:
      item["sub"] = {"components": lanes}
    result.append(item)
  return result


def normalize(response: dict) -> dict:
  try:
    if response["code"] != "Ok" or not response["routes"]:
      raise RoutingError("no_route")
    route = response["routes"][0]
    if len(route["legs"]) != 1 or route["geometry"]["type"] != "LineString":
      raise RoutingError("invalid_response")
    geometry = [coordinate(c) for c in route["geometry"]["coordinates"]]
    if not 2 <= len(geometry) <= 200_000:
      raise RoutingError("invalid_response")
    leg = route["legs"][0]
    steps = []
    for step in leg["steps"]:
      maneuver = step["maneuver"]
      if maneuver["type"] not in TYPES or maneuver.get("modifier", "none") not in DIRECTIONS:
        raise RoutingError("invalid_response")
      instruction = maneuver.get("instruction")
      if not isinstance(instruction, str) or not instruction:
        raise RoutingError("invalid_response")
      steps.append({"maneuver": maneuver["type"], "modifier": maneuver.get("modifier", "none"), "instruction": instruction,
                    "location": coordinate(maneuver["location"]), "distance": number(step["distance"]),
                    "duration": number(step["duration"]), "bannerInstructions": banners(step.get("bannerInstructions", []))})
    if not steps or steps[0]["maneuver"] != "depart" or steps[-1]["maneuver"] != "arrive":
      raise RoutingError("invalid_response")
    speeds = []
    for entry in (leg.get("annotation") or {}).get("maxspeed", []):
      speed = 0.0 if entry.get("unknown") or entry.get("none") else number(entry.get("speed", 0))
      unit = entry.get("unit", "km/h")
      if unit not in ("km/h", "mph"):
        raise RoutingError("invalid_response")
      speeds.append({"speed": speed, "unit": unit})
    if speeds and len(speeds) not in (len(geometry) - 1, len(geometry)):
      raise RoutingError("invalid_response")
    return {"geometry": geometry, "steps": steps, "maxspeed": speeds,
            "totalDistance": number(route["distance"]), "totalDuration": number(route["duration"])}
  except (KeyError, TypeError, IndexError, AttributeError, ValueError):
    raise RoutingError("invalid_response") from None
