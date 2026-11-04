"""One bounded request per local connection. Safe to call from an existing background worker."""
from __future__ import annotations

import json
import socket
import uuid

from openpilot.starpilot.tandem.routing import config as C
from openpilot.starpilot.tandem.routing.bundles import capability, for_trip, load


def request(action: str, *, timeout: float = C.DEADLINE, **payload) -> dict:
  identity = uuid.uuid4().hex
  message = {"protocol": C.PROTOCOL, "id": identity, "action": action, **payload}
  try:
    data = json.dumps(message, allow_nan=False).encode() + b"\n"
    if len(data) > C.MAX_MESSAGE:
      raise C.RoutingError("invalid_request")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
      connection.settimeout(timeout + 1)
      connection.connect(str(C.socket_path()))
      connection.sendall(data)
      with connection.makefile("rb") as stream:
        raw = stream.readline(C.MAX_MESSAGE + 1)
      if len(raw) > C.MAX_MESSAGE or not raw.endswith(b"\n"):
        raise C.RoutingError("invalid_response")
      response = json.loads(raw)
      if response.get("id") != identity or response.get("protocol") != C.PROTOCOL:
        raise C.RoutingError("invalid_response")
      return response
  except TimeoutError:
    raise C.RoutingError("timeout") from None
  except (OSError, ValueError, TypeError, AttributeError):
    raise C.RoutingError("worker_failed") from None


def route(start: tuple[float, float, float | None], destination: dict, *, caller: str = "navigation", language: str = "en") -> dict:
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
  return result["route"]
