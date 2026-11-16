"""Display values and identities passed from StarPilot to the Essentials driving screen."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from openpilot.selfdrive.ui.tandem.i18n import N_, t_


class ChipTone(Enum):
  """The design treatment for a status chip."""

  INFO = "info"
  PAUSED = "paused"
  WAITING = "waiting"
  ALERT = "alert"


@dataclass(frozen=True)
class Chip:
  """One status from a qualified StarPilot input."""

  key: str
  label: str
  icon: str
  tone: ChipTone = ChipTone.INFO


@dataclass(frozen=True)
class LimitDecision:
  """The exact native speed-limit proposal rendered by a confirmation card."""

  session: str
  decision_id: int
  presentation_id: int
  candidate_mps: float


@dataclass(frozen=True)
class LimitOffer:
  """The display values and wire identity for one speed-limit proposal."""

  identity: LimitDecision
  limit: float
  target: float | None
  unit: str
  source: str
  seconds_left: float
  total: float
  vienna: bool = False


@dataclass(frozen=True)
class DrivingAlert:
  """StarPilot's selected alert with the approved presentation level."""

  level: str
  title: str
  detail: str = ""


@dataclass(frozen=True)
class BarState:
  """The bottom bar reads the set speed and independent native permissions."""

  engaged: bool = False
  adjust_speed: bool = False
  disengage: bool = False
  set_speed: float | None = None
  street: str = ""


@dataclass(frozen=True)
class DriveDisplay:
  """An immutable render sample for one onroad frame."""

  bar: BarState = BarState()
  speed: float | None = None
  unit: str = "mph"
  posted: str = ""
  vienna: bool = False
  left: bool = False
  right: bool = False
  monitor: float | None = None
  attention_warning: bool = False
  torque: float | None = None
  chips: tuple[Chip, ...] = ()
  alert: DrivingAlert | None = None
  offer: LimitOffer | None = None


class RamWatch:
  """Hold the upstream memory advisory until usage drops to 85 percent."""

  def __init__(self) -> None:
    self._percent = 0
    self._visible = False

  def update(self, raised: bool, percent: int | None) -> Chip | None:
    if percent is not None:
      self._percent = max(0, min(percent, 100))
    self._visible = raised or (self._visible and self._percent > 85)
    if not self._visible:
      return None
    label = t_("Low on RAM · {}% used", self._percent) if self._percent else N_("Low on RAM")
    return Chip("ram", label, "memory", ChipTone.ALERT)


def displayed_speed(value: float | None, factor: float) -> float | None:
  """Leave missing or nonfinite speed unavailable in the HUD."""
  return value * factor if value is not None and math.isfinite(value) and value >= 0 else None
