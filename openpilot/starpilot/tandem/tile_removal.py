"""Cooperate with navtilesd to remove its downloaded navigation data."""
from __future__ import annotations

from collections.abc import Callable
import math
import os
from pathlib import Path
import secrets
import shutil
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from openpilot.starpilot.navigation.google_tiles import GoogleTiles
  from openpilot.starpilot.navigation.navtilesd import Environment, TileDaemon

REQUEST = ".tandem-clear-tiles.json"
REPLY = ".tandem-clear-tiles-result.json"
TIMEOUT = 25.0


def request_clear_tiles(root: Path, parked: Callable[[], bool]) -> bool:
  """Ask the writer to clear its own file stores and wait for its acknowledgement."""
  from openpilot.starpilot.navigation.offline_roads import read_json, write_json

  if not parked():
    return False
  token = secrets.token_hex(16)
  expires = time.monotonic() + TIMEOUT
  write_json(root / REQUEST, {"id": token, "expires": expires})
  try:
    while parked() and time.monotonic() < expires:
      result = read_json(root / REPLY, 1024)
      if isinstance(result, dict) and result.get("id") == token:
        return result.get("complete") is True
      time.sleep(.1)
  finally:
    pending = read_json(root / REQUEST, 1024)
    if isinstance(pending, dict) and pending.get("id") == token:
      (root / REQUEST).unlink(missing_ok=True)
  return False


def remove_owned_directory(path: Path) -> None:
  """Remove a managed directory without following a replacement or mount."""
  if not path.exists() and not path.is_symlink():
    return
  if path.is_symlink() or path.resolve() != path or not path.is_dir():
    raise OSError("Map folder is unavailable")
  device = path.parent.stat().st_dev
  if path.stat().st_dev != device:
    raise OSError("A map folder is in use")
  for folder, dirs, _ in os.walk(path):
    for name in dirs:
      child = Path(folder) / name
      if not child.is_symlink() and child.stat().st_dev != device:
        raise OSError("A map folder is in use")
  shutil.rmtree(path)


def consume_clear_tiles(daemon: TileDaemon, google: GoogleTiles, env: Environment, ui_params: Any,
                        routing: Callable[[], dict]) -> bool:
  """Run on the tile writer, between updates, with an offroad request from the map owner."""
  from openpilot.starpilot.navigation.offline_roads import KINDS, read_json, write_json

  path = daemon.state.root / REQUEST
  if not path.is_file():
    return False
  try:
    request = read_json(path, 1024)
    path.unlink(missing_ok=True)
  except OSError:
    return False
  if not isinstance(request, dict):
    return False
  token, expires = request.get("id"), request.get("expires")
  now = time.monotonic()
  if (type(token) is not str or len(token) != 32 or not isinstance(expires, (int, float))
      or not now < expires <= now + TIMEOUT):
    return False
  complete = False
  idle = not any(not progress.finished for progress in daemon.progress.values())
  try:
    allowed = (idle and not env.onroad and not env.route and not routing().get("destination")
               and not ui_params.get("NavDestination") and ui_params.get_bool("IsOffroad"))
    if allowed:
      with daemon.state._exclusive():
        for kind in KINDS:
          remove_owned_directory(daemon.store.root / kind)
        remove_owned_directory(google.store.root / "tiles")
        google.want.unlink(missing_ok=True)
      complete = True
  except (OSError, RuntimeError, ValueError):
    pass
  finally:
    daemon.last_trim = -math.inf
    daemon.sweep_needed = True
    daemon.saved_full_at = None
    daemon.last_status = -math.inf
  try:
    write_json(daemon.state.root / REPLY, {"id": token, "complete": complete})
  except OSError:
    pass
  return True
