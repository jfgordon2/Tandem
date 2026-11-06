"""Routing policy and paths outside upstream's compiled param registry."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

VERSION = "3.9.1"
PROTOCOL = 1
MAX_MESSAGE = 16 * 1024 * 1024
DEADLINE = 15.0
SCREENS = ("TANDEM_SETTINGS", "TANDEM_HOME", "TANDEM_ONROAD", "TANDEM_SIDEBAR")


class RoutingError(Exception):
  def __init__(self, code: str):
    self.code = code
    super().__init__(code)


def enabled() -> bool:
  if any(os.getenv(name, "1") == "0" for name in SCREENS) or os.getenv("TANDEM_ROUTING") == "0":
    return False
  if os.getenv("TANDEM_ROUTING") == "1":
    return True
  try:
    return not (preference_path().parent / ".tandem_routing_disabled_on").exists()
  except (OSError, ImportError):
    return False


def policy_path() -> Path:
  return preference_path().parent / ".tandem_routing_policy.json"


def policy() -> tuple[bool, str]:
  try:
    value = json.loads(policy_path().read_text())
    if type(value.get("offline_only")) is not bool or value.get("preferred") not in ("online", "offline"):
      raise ValueError("invalid routing policy")
    return value["offline_only"], value["preferred"]
  except FileNotFoundError:
    # Preserve an explicitly enabled earlier trial as strict offline mode.
    return preference(), "online"
  except (OSError, ValueError, TypeError, AttributeError, ImportError):
    # An unreadable/corrupt saved strict choice must not enable network routing.
    return True, "offline"


def set_policy(*, offline_only: bool | None = None, preferred: str | None = None) -> None:
  only, first = policy()
  atomic_json(policy_path(), {"offline_only": only if offline_only is None else bool(offline_only),
                             "preferred": preferred if preferred in ("online", "offline") else first})


def provider_order() -> tuple[str, ...]:
  only, first = policy()
  return ("offline",) if only else (first, "offline" if first == "online" else "online")


def preference_path() -> Path:
  # Match prefs.Flag's storage convention without importing the UI package initializer.
  if os.getenv("TANDEM_PREFS_DIR"):
    folder = Path(os.environ["TANDEM_PREFS_DIR"])
  else:
    from openpilot.common.params import Params
    folder = Path(Params().get_param_path()).parent
  return folder / ".tandem_offline_routing_on"


def preference() -> bool:
  try:
    return preference_path().is_file()
  except (OSError, ImportError):
    return False


def set_enabled(on: bool) -> None:
  # Maintainer rollback is deliberately separate from the driver's policy.
  require_parked()
  marker = preference_path().parent / ".tandem_routing_disabled_on"
  if on:
    marker.unlink(missing_ok=True)
  else:
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def root() -> Path:
  default = "/data/tandem/navigation" if Path("/TICI").exists() else str(Path(tempfile.gettempdir()) / f"tandem-routing-{os.getuid()}")
  return Path(os.getenv("TANDEM_ROUTING_DIR", default))


def socket_path() -> Path:
  from openpilot.starpilot.tandem.state import state_dir
  return state_dir() / "routing.sock"


def runtime_python() -> Path:
  return root() / "runtimes" / VERSION / "bin" / "python"


def runtime_ready() -> bool:
  try:
    return runtime_python().is_file() and json.loads((runtime_python().parent.parent / "receipt.json").read_text())["version"] == VERSION
  except (OSError, ValueError, KeyError, TypeError):
    return False


def require_parked() -> None:
  if not Path("/TICI").exists():
    return
  from openpilot.common.params import Params
  params = Params()
  if params.get_bool("IsOnroad") or params.get("NavDestination"):
    raise RoutingError("park_to_change")


def atomic_json(path: Path, value) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = None
  try:
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
      temporary = Path(stream.name)
      json.dump(value, stream, allow_nan=False)
      stream.flush()
      os.fsync(stream.fileno())
    temporary.replace(path)
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)


def should_run(_started=False, params=None, *_args) -> bool:
  if not enabled():
    return False
  from openpilot.starpilot.tandem.routing import demand
  if params is None:
    from openpilot.common.params import Params
    params = Params()
  return demand.needed(params) or demand.awake()
