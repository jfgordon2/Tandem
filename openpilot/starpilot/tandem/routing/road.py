"""Road data for the chosen states from StarPilot 7's own map owner (starpilot/maps/operation_owner.py).

Release drove StarPilot 6's road downloader; StarPilot 7 downloads road data one region at a time through its map
operation owner, while parked, and keeps every earlier region in each new generation. A map job asks it for each chosen
state it doesn't have yet, waits for it to finish, then installs the routing graphs. StarPilot's snapshot doesn't name
its regions, so map-road.json records which states Tandem got road data for; when StarPilot's maps are deleted (an empty
selected generation) the record no longer counts.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from openpilot.starpilot.tandem.routing import config as C

RECORD = "map-road.json"
POLL_S = 0.5
type Request = Callable[[dict], dict]
type Publish = Callable[..., None]


def _request(message: dict) -> dict:
  """One request to StarPilot's map owner: its result, or RoutingError with the reason it gives."""
  from openpilot.starpilot.maps.operation_owner import MapOperationUnavailable, request_operation
  try:
    reply = request_operation({"version": 1, **message})
  except MapOperationUnavailable:
    raise C.RoutingError("road_unavailable") from None
  if not reply["ok"]:
    code = reply["error"].get("code")
    raise C.RoutingError({"not_parked": "interrupted", "busy": "road_busy"}.get(code, "road_download_failed"))
  return dict(reply["result"])


def _read_record() -> dict:
  try:
    value = json.loads((C.root() / RECORD).read_text())
    return value if isinstance(value, dict) else {}
  except (OSError, ValueError):
    return {}


def present(request: Request = _request) -> set[str]:
  """The states Tandem has road data for in StarPilot's selected maps."""
  generation = request({"op": "status"}).get("selectedGeneration") or ""
  record = _read_record()
  if not generation or not isinstance(record.get("regions"), list):
    return set()
  return {str(r) for r in record["regions"]}


def _remember(regions: set[str]) -> None:
  C.atomic_json(C.root() / RECORD, {"regions": sorted(regions)})


def ensure(tokens: list[str], gate: Callable[[], None], publish: Publish, request: Request = _request,
           sleep: Callable[[float], Any] = time.sleep) -> None:
  """Downloads road data for each state in tokens that StarPilot doesn't have yet, one at a time.

  Args:
    tokens: The chosen states ("us_state.IA").
    gate: Between steps: raises RoutingError when the job is cancelled or must pause.
    publish: The job's progress (phase "road", current_regions, and done and total in StarPilot's map groups).
    request: StarPilot's map owner (a stand-in in tests).
    sleep: Waits between polls.

  Raises:
    RoutingError: road_download_failed, road_unavailable, road_busy or coverage_unavailable when StarPilot can't, or the
      gate's reason.
  """
  have = present(request)
  missing = [token for token in tokens if token not in have]
  if not missing:
    return
  regions = {row["token"]: row for row in request({"op": "catalog"}).get("regions", [])}
  setup = request({"op": "setup"})
  limits = (setup.get("maxTransferBytes"), setup.get("maxNewDiskBytes"))
  if any(type(limit) is not int or limit <= 0 for limit in limits):
    raise C.RoutingError("road_unavailable")
  for token in missing:
    row = regions.get(token)
    if row is None or not row.get("available"):
      raise C.RoutingError("coverage_unavailable")
    gate()
    expected = request({"op": "status"}).get("selectedGeneration") or ""
    started = request({"op": "start", "regionToken": token, "maxTransferBytes": limits[0], "maxNewDiskBytes": limits[1],
                       "expectedCurrentGeneration": expected})
    operation = started.get("operationId")
    publish(phase="road", current_regions=[token], done=0, total=int(row.get("groups") or 0))
    while True:
      try:
        gate()
      except C.RoutingError:
        request({"op": "cancel", "operationId": operation})   # StarPilot keeps its maps as they were
        raise
      status = request({"op": "status"})
      if status.get("operationId") != operation:
        raise C.RoutingError("road_download_failed")
      publish(done=int(status.get("completedGroups") or 0), total=int(status.get("totalGroups") or 0))
      state = status.get("state")
      if state == "completed":
        have.add(token)
        _remember(have)
        break
      if state in ("failed", "canceled", "interrupted", "unavailable"):
        raise C.RoutingError("interrupted" if status.get("errorCode") == "not_parked" else "road_download_failed")
      sleep(POLL_S)
