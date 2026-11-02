"""Power-user bundles: one switch each, and each switch writes a fixed set of params.

A bundle owns its keys while it is on. Turning it off writes the off values, which are the Essentials
defaults, not upstream's: upstream shows developer UI by default on this screen size.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_

Values = dict[str, bool | int | float]


@dataclass(frozen=True)
class Bundle:
  name: str
  description: str
  key: str                      # the param that says whether the bundle is on
  on: Values
  off: Values = field(default_factory=dict)

  def is_on(self, store: SettingsStore) -> bool:
    on = self.on[self.key]
    return store.get_bool(self.key) if isinstance(on, bool) else store.get_int(self.key) >= on

  def set(self, store: SettingsStore, on: bool) -> None:
    store.write(self.on if on else self.off)


def _switches(keys: list[str], on: bool) -> Values:
  return dict.fromkeys(keys, on)


# The master switches stay on, so the parts below them decide.
_DEVELOPER_GATES = {"DeveloperUI": True, "DeveloperMetrics": True, "DeveloperWidgets": True}
_DEVELOPER_KEYS = ["DeveloperSidebar", "FPSCounter", "ShowCPU", "ShowGPU", "NumericalTemp", "ShowMemoryUsage", "AdjacentPathMetrics",
                   "SpeedLimitSources"]
_LEAD_KEYS = ["LeadInfo", "RadarTracksUI", "ShowStoppingPoint", "ShowStoppingPointMetrics", "AdjacentPath", "PedalsOnUI"]

DEVELOPER_VIEW = Bundle(
  N_("Developer View"), N_("Sidebar with live metrics, CPU, GPU, memory and temperatures, and where speed limits come from"),
  "DeveloperSidebar", _DEVELOPER_GATES | _switches(_DEVELOPER_KEYS, True), _switches(_DEVELOPER_KEYS, False))

LEAD_INSIGHTS = Bundle(
  N_("Lead Insights"), N_("Distance and speed of the car ahead, radar tracks, stopping point, adjacent paths and pedals"),
  "LeadInfo", _DEVELOPER_GATES | _switches(_LEAD_KEYS, True), _switches(_LEAD_KEYS, False))

# Tuner Mode writes no driving values. It shows the fine-tuning screens, through StarPilot's own tuning level.
TUNER_MODE = Bundle(
  N_("Tuner Mode"), N_("Fine-tuning screens for gas, brake, steering and following"),
  "TuningLevel", {"TuningLevel": 3, "TuningLevelConfirmed": True}, {"TuningLevel": 0})

BUNDLES = [DEVELOPER_VIEW, LEAD_INSIGHTS, TUNER_MODE]
