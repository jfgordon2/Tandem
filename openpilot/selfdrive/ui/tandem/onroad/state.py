"""One onroad frame as the view passes it to the overlay, and the StarPilot 7 identities its actions must carry.

The drawing state (BarState, ArcState, LimitOffer, chips) is release's, from layers.py and status.py; this adds what
StarPilot 7 needs on top: the exact speed-limit proposal a card answers, and StarPilot's selected alert as a level.
"""
from __future__ import annotations

import math
from typing import Any
from dataclasses import dataclass, field

from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState, LimitOffer
from openpilot.selfdrive.ui.tandem.onroad.status import Chip


@dataclass(frozen=True)
class LimitDecision:
  """The exact native speed-limit proposal rendered by a confirmation card."""

  session: str
  decision_id: int
  presentation_id: int
  candidate_mps: float


@dataclass(frozen=True)
class Proposal:
  """A new-limit card's offer (release's LimitOffer) with the StarPilot 7 decision it answers."""

  identity: LimitDecision
  offer: LimitOffer


@dataclass(frozen=True)
class DrivingAlert:
  """StarPilot's selected alert in the mock's levels (alerts.INFO, WARNING or CRITICAL)."""

  level: str
  title: str
  detail: str = ""


@dataclass(frozen=True)
class DriveDisplay:
  """An immutable render sample for one onroad frame."""

  bar: BarState = field(default_factory=BarState)
  speed: float | None = None
  unit: str = "mph"
  posted: str = ""
  vienna: bool = False
  left: bool = False
  right: bool = False
  monitor: float | None = None          # driver awareness 0..1 while driver monitoring watches, else None
  attention_warning: bool = False
  arc: ArcState = field(default_factory=ArcState)
  help_steer: bool = False              # steering at its limit: the Help steer card takes the bar's place
  chips: tuple[tuple[Chip, float], ...] = ()   # (chip, opacity) nearest the bar first, from status.ChipStack
  alert: DrivingAlert | None = None
  proposal: Proposal | None = None


def awareness(dm: Any) -> float | None:
  """The driver's attention, 0 to 1, from StarPilot 7's driverMonitoringState: the active policy's awarenessPercent (the
  camera's, or the wheel-touch fallback's). None when it can't be read."""
  try:
    vision = str(dm.activePolicy) == "vision"
    policy = getattr(dm, "visionPolicyState" if vision else "wheeltouchPolicyState")
    value = float(policy.awarenessPercent) / 100.0
  except (AttributeError, TypeError, ValueError):
    return None
  return max(0.0, min(value, 1.0)) if math.isfinite(value) else None


def displayed_speed(value: float | None, factor: float) -> float | None:
  """Leave missing or nonfinite speed unavailable in the HUD."""
  return value * factor if value is not None and math.isfinite(value) and value >= 0 else None
