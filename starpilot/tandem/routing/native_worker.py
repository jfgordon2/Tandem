"""Dedicated native process. Local graph only; Linux socket syscalls are denied before loading it."""
from __future__ import annotations

import ctypes
import fcntl
import json
import math
import os
import platform
import signal
import resource
import socket
import sys

from openpilot.starpilot.tandem.routing import config as C, images, verified
from openpilot.starpilot.tandem.routing.bundles import selected as selected_bundle
from openpilot.starpilot.tandem.routing.metrics import memory


def isolate_network() -> str:
  if sys.platform != "linux":
    return "not_enforced_on_desktop"
  machine = platform.machine()
  calls = {"aarch64": (198, 203), "x86_64": (41, 42)}.get(machine)
  if calls is None:
    raise C.RoutingError("data_incompatible")

  class Filter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]

  class Program(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

  # Load syscall number; deny socket/connect with EPERM; allow other syscalls.
  program = (Filter * 5)(Filter(0x20, 0, 0, 0), Filter(0x15, 2, 0, calls[0]), Filter(0x15, 1, 0, calls[1]),
                         Filter(0x06, 0, 0, 0x7FFF0000), Filter(0x06, 0, 0, 0x00050001))
  libc = ctypes.CDLL(None, use_errno=True)
  if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(Program(5, program)), 0, 0):
    raise C.RoutingError("network_isolation_failed")
  # A manager kill must not leave the child running after its broker is gone.
  if libc.prctl(1, signal.SIGTERM, 0, 0, 0) or os.getppid() == 1:
    raise C.RoutingError("worker_failed")
  try:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  except PermissionError:
    return "seccomp_socket_connect_denied"
  connection.close()
  raise C.RoutingError("network_isolation_failed")


def route_options(message: dict) -> dict:
  start = message["start"]
  destination = message["destination"]
  lat, lon, heading = start
  end_lat, end_lon = destination["latitude"], destination["longitude"]
  for latitude, longitude in ((lat, lon), (end_lat, end_lon)):
    if (isinstance(latitude, bool) or isinstance(longitude, bool) or not math.isfinite(latitude) or not math.isfinite(longitude)
        or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
      raise C.RoutingError("invalid_request")
  origin = {"lat": lat, "lon": lon}
  if heading is not None:
    if not math.isfinite(heading):
      raise C.RoutingError("invalid_request")
    origin.update(heading=heading % 360, heading_tolerance=90)
  # An old Mapbox alt-N is not the same alternative in this provider. Always recalculate main.
  language = str(message.get("language", "en")).replace("main_", "").replace("_", "-")
  supported = {"en", "de", "es", "fr", "it", "ja", "nl", "pl", "pt", "ru", "sv", "tr", "uk", "cs", "da", "fi", "ko", "nb"}
  if language.split("-")[0] not in supported:
    language = "en"
  return {"locations": [origin, {"lat": end_lat, "lon": end_lon}], "costing": "auto", "format": "osrm",
          "shape_format": "geojson", "banner_instructions": True, "directions_type": "instructions", "language": language,
          "filters": {"action": "include", "attributes": ["shape_attributes.speed_limit"]}}


def actor_config(graph):
  from valhalla import get_config
  config = get_config(tile_dir="", tile_extract=str(graph))
  config["mjolnir"].update(tile_dir="", tile_url="", max_cache_size=64 * 1024**2,
                          use_simple_mem_cache=True, use_lru_mem_cache=False)
  config["mjolnir"]["data_processing"]["scan_tar"] = False
  config["thor"].update(clear_reserved_memory=True, max_reserved_labels_count_astar=100_000,
                       max_reserved_labels_count_bidir_astar=100_000)
  return config


def release_heap():
  if sys.platform == "linux":
    try:
      ctypes.CDLL(None).malloc_trim(0)
    except AttributeError:
      pass


def compact_response(raw):
  """Keep the existing provider contract, without unused intersection/waypoint trees."""
  if raw.get("code") != "Ok":
    return raw
  route = raw["routes"][0]
  leg = route["legs"][0]
  if len(route["legs"]) != 1:
    raise C.RoutingError("invalid_response")
  steps = [{key: step[key] for key in ("maneuver", "distance", "duration", "bannerInstructions") if key in step}
           for step in leg["steps"]]
  return {"code": "Ok", "routes": [{"geometry": route["geometry"], "distance": route["distance"], "duration": route["duration"],
    "legs": [{"steps": steps, "annotation": {"maxspeed": (leg.get("annotation") or {}).get("maxspeed", [])}}]}]}


def main():
  isolation = isolate_network()
  from valhalla import Actor
  actor = bundle = lease = None
  for raw in sys.stdin.buffer:
    try:
      if len(raw) > C.MAX_MESSAGE:
        raise C.RoutingError("invalid_request")
      message = json.loads(raw)
      selected = selected_bundle(message)
      verified.require(selected)
      if selected.generation != message["generation"]:
        raise C.RoutingError("superseded")
      if bundle is None or actor is None or selected.generation != bundle.generation:
        actor = None
        if lease is not None:
          lease.close()
        bundle = selected
        lease = (bundle.folder / ".lease").open("a")
        fcntl.flock(lease, fcntl.LOCK_SH)
        # Recheck after acquiring the lease to close a removal/selection race.
        if selected_bundle(message).generation != bundle.generation:
          raise C.RoutingError("superseded")
        verified.require(selected_bundle(message))
        config = actor_config(images.require_mounted(bundle))
        try:
          actor = Actor(config)
        except Exception:
          raise C.RoutingError("data_incompatible") from None
      options = route_options(message)
      for location in options["locations"]:
        if not bundle.covers(location["lat"], location["lon"]):
          raise C.RoutingError("outside_coverage")
      routed = compact_response(actor.route(options))
      usage = resource.getrusage(resource.RUSAGE_SELF)
      result = {"status": "ok", "route": routed, "generation": bundle.generation, "network_isolation": isolation,
                **{"worker_" + key: value for key, value in memory().items()},
                "worker_cpu_seconds": usage.ru_utime + usage.ru_stime}
    except C.RoutingError as error:
      result = {"status": error.code}
    except (KeyError, TypeError, ValueError, OverflowError):
      result = {"status": "invalid_request"}
    except Exception:
      result = {"status": "no_route"}
    encoded = json.dumps(result, allow_nan=False)
    if len(encoded.encode()) > C.MAX_MESSAGE - 1024:
      encoded = '{"status":"invalid_response"}'
    print(encoded, flush=True)
    result = routed = encoded = None
    release_heap()


if __name__ == "__main__":
  main()
