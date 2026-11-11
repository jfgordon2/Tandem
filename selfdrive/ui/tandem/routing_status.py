"""Driver wording for local routing status; backend error codes never become raw UI text."""
import math

from openpilot.selfdrive.ui.tandem.i18n import N_

MESSAGES = {
  "idle": N_("Finding a route…"),
  "routing": N_("Finding a route…"),
  "done": N_("Done"),
  "installation_failed": N_("Installation failed. Check the connection and package."),
  "disabled": N_("Online routing is selected"),
  "ready": N_("Offline routing data ready"),
  "runtime_missing": N_("Download maps for this region"),
  "data_missing": N_("Download maps for this region"),
  "data_incompatible": N_("Routing data needs to be installed again"),
  "outside_coverage": N_("This trip needs more routing data"),
  "no_route": N_("No offline route found for this trip"),
  "busy": N_("Routing is busy. Trying again…"),
  "timeout": N_("The route took too long. Trying again…"),
  "worker_failed": N_("Routing is unavailable. Trying again…"),
  "invalid_response": N_("Routing returned an unusable route"),
  "invalid_request": N_("This place has no usable coordinates"),
  "gps_waiting": N_("Waiting for a fresh GPS fix"),
  "rerouting": N_("Finding another offline route…"),
  "park_to_change": N_("Park and end the route to change routing data"),
  "no_space": N_("There is not enough storage for this package"),
  "bundle_exists": N_("This package is already installed with different data"),
  "cancelled": N_("Installation cancelled"),
  "superseded": N_("Finding the updated route…"),
  "catalog_unavailable": N_("Map downloads are unavailable. Try again when connected."),
  "download_failed": N_("Map download failed. Existing maps are kept."),
  "road_download_failed": N_("Road data download did not finish. Try again when connected."),
  "coverage_unavailable": N_("Offline routes are not available for every selected region."),
  "route_unavailable": N_("Route unavailable"),
  "online_unavailable": N_("Online routing is unavailable"),
}


def status_text(code: str) -> str:
  return MESSAGES.get(code, N_("Routing is unavailable"))


def display_estimate(state: dict, now: float) -> tuple[float, float] | None:
  """Validated display-only estimate, with a finite twenty-second grace."""
  try:
    value = state["estimate"]
    at, seconds, meters = (float(value[k]) for k in ("at", "seconds", "meters"))
    if not all(math.isfinite(n) for n in (at, seconds, meters)) or not 0 <= now - at <= 20 or min(seconds, meters) < 0:
      return None
    return max(0, seconds - (now - at)), meters
  except (KeyError, TypeError, ValueError, OverflowError):
    return None
