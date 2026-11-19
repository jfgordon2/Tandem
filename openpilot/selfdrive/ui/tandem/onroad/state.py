"""One onroad frame as the view passes it to the overlay, and the StarPilot 7 identities its actions must carry.

The drawing state (BarState, ArcState, LimitOffer, chips) is release's, from layers.py and status.py; this adds what
StarPilot 7 needs on top: the exact speed-limit proposal a card answers, and StarPilot's selected alert as a level.
"""
from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING, Any
from dataclasses import dataclass, field

from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState, LimitOffer
from openpilot.selfdrive.ui.tandem.i18n import t_
from openpilot.selfdrive.ui.tandem.onroad.status import Chip

if TYPE_CHECKING:
  from openpilot.starpilot.ui.navigation_state import NavigationDisplay


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
  pedals: tuple[float, float] | None = None   # (brake, gas) tiles under the monitor tile (extras.Pedals), None when off
  border: tuple[Any, Any] = (None, None)      # each side's highlight color (extras.border_halves), None for none
  model: tuple[str, float] | None = None      # the model chip's state and opacity (extras.ModelChip), None when hidden
  turn: tuple[str, str, str, str] | None = None   # the next turn while guiding: (distance, instruction, maneuver, modifier)


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


def turn(navigation: NavigationDisplay | None, metric: bool) -> tuple[str, str, str, str] | None:
  """The turn card's distance, instruction, maneuver and direction from StarPilot's guidance, or None without a route.
  The distance is rounded as StarPilot's own card rounds it."""
  if navigation is None:
    return None
  from openpilot.starpilot.ui.navigation_state import distance_text
  if navigation.arrived:
    return "", navigation.text, "arrive", ""
  return distance_text(navigation.distance_m, metric), navigation.text, navigation.maneuver_type, navigation.modifier


def route_progress(navigation: NavigationDisplay | None, metric: bool, now: datetime.datetime) -> tuple[str, str]:
  """The bar's arrival time and what's left ("12 min · 8.4 mi") from StarPilot's guidance, or blanks without a route.

  Args:
    navigation: StarPilot's navigation display (OnroadState.navigation), guiding or arrived.
    metric: Kilometers instead of miles.
    now: The wall clock, for the arrival time.
  """
  if navigation is None:
    return "", ""
  seconds, meters = navigation.remaining_seconds, navigation.remaining_distance_m
  arrive = (now + datetime.timedelta(seconds=seconds)).strftime("%-I:%M %p")
  distance = t_("{} km", f"{meters / 1000:.1f}") if metric else t_("{} mi", f"{meters / 1609.344:.1f}")
  return arrive, t_("{} min · {}", max(1, round(seconds / 60)), distance)
