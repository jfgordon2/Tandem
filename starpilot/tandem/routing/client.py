"""One bounded request per local connection. Safe to call from an existing background worker."""
from __future__ import annotations

import json
import errno
import socket
import time
import uuid
from typing import Any

from openpilot.starpilot.tandem.routing import config as C, demand
from openpilot.starpilot.tandem.routing.bundles import capability, for_trip, load


def request(action: str, *, timeout: float = C.DEADLINE, **payload: Any) -> dict:
  """Sends one request to the routing broker and returns its reply.

  A request is retried only before it's sent: one the broker accepted is never replayed.

  Args:
    action: The broker action (route, status, ...).
    timeout: The deadline in seconds.
    payload: The request's fields.

  Raises:
    RoutingError: When the broker can't be reached or doesn't answer in time.
  """
  end = time.monotonic() + timeout
  identity = uuid.uuid4().hex
  message = {"protocol": C.PROTOCOL, "id": identity, "action": action, **payload}
  try:
    if action == "route":
      message["_deadline"] = end
    data = json.dumps(message, allow_nan=False).encode() + b"\n"
    if len(data) > C.MAX_MESSAGE:
      raise C.RoutingError("invalid_request")
    if action == "route" and not demand.wake():
      raise C.RoutingError("worker_failed")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
      # Manager observes the wake on its next tick. Retry only before sending:
      # a request already accepted by the broker must never be replayed.
      startup_end = min(end, time.monotonic() + 5)
      while True:
        connection.settimeout(max(.001, end - time.monotonic()))
        try:
          connection.connect(str(C.socket_path()))
          break
        except OSError as error:
          if action != "route" or error.errno not in (errno.ENOENT, errno.ECONNREFUSED):
            raise
          if not C.enabled():
            raise C.RoutingError("superseded") from None
          remaining = startup_end - time.monotonic()
          if remaining <= 0:
            raise C.RoutingError("timeout") from None
          time.sleep(min(.05, remaining))
      connection.settimeout(max(.001, end - time.monotonic()))
      connection.sendall(data)
      with connection.makefile("rb") as stream:
        raw = stream.readline(C.MAX_MESSAGE + 1)
      if len(raw) > C.MAX_MESSAGE or not raw.endswith(b"\n"):
        raise C.RoutingError("invalid_response")
      response = json.loads(raw)
      if response.get("id") != identity or response.get("protocol") != C.PROTOCOL:
        raise C.RoutingError("invalid_response")
      return dict(response)
  except TimeoutError:
    raise C.RoutingError("timeout") from None
  except (OSError, ValueError, TypeError, AttributeError):
    raise C.RoutingError("worker_failed") from None


def route(start: tuple[float, float, float | None], destination: dict, *, caller: str = "navigation", language: str = "en") -> dict:
  """A route from offline routing, through the broker.

  Args:
    start: (latitude, longitude, heading or None).
    destination: The destination place, with latitude and longitude.
    caller: "navigation" or "preview"; a preview yields to navigation.
    language: The instructions' language.

  Raises:
    RoutingError: Why there's no route (no data, outside coverage, timeout...).
  """
  state = capability()
  if state["status"] != "ready":
    raise C.RoutingError(state["status"])
  bundle = for_trip(start, destination)
  result = request("route", caller=caller, bundle=bundle.id, generation=bundle.generation,
                   start=list(start), destination=destination, language=language)
  if result["status"] != "ok":
    raise C.RoutingError(result["status"])
  if load(bundle.folder).generation != result.get("generation") or not C.enabled():
    raise C.RoutingError("superseded")
  route = result["route"]
  if not isinstance(route, dict):
    raise C.RoutingError("invalid_response")
  return route
