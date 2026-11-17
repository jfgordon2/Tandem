"""Defer native settings faces while keeping the driving and alert faces ready."""
from collections.abc import Mapping
import os


def defer_inter(big_ui: bool, environment: Mapping[str, str] = os.environ) -> bool:
  """Use on-demand Inter weights only for the Tandem big layout."""
  switches = ("TANDEM_HOME", "TANDEM_SETTINGS", "TANDEM_ONROAD", "TANDEM_SIDEBAR")
  return big_ui and environment.get("STARPILOT_UI") != "upstream" and any(environment.get(name, "1") != "0" for name in switches)
