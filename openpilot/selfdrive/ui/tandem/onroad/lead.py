"""The lead car's tag (design/gaptag.html): the gap, or distance, gap and relative speed in the power-user views.

On StarPilot 7 the tag takes the place of the text StarPilot's model renderer draws above its lead marker (its Lead Info);
the marker is StarPilot's own. The tracker keeps the reading calm and restarts a short entrance for a new lead or a cut-in.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from openpilot.starpilot.ui.raylib import rl

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.onroad.developer import Lead
from openpilot.selfdrive.ui.tandem.i18n import t_

LEAD_UNSURE = 0.45          # opacity when the model isn't sure the car ahead is there
LEAD_SETTLE = 0.25          # s for a new car's tag to come in
LEAD_JUMP = 8.0             # m: a lead this much nearer than the last one is a new car (a cut-in)


class LeadSettle:
  """How far a lead's tag has come in (0 to 1): a car that appears, or one much nearer than the last (a cut-in), starts
  again and comes in over LEAD_SETTLE."""

  def __init__(self) -> None:
    self._since: float | None = None
    self._distance: float | None = None

  def update(self, present: bool, distance: float, now: float) -> float:
    """The settle-in, 0 to 1 with an ease-out: it restarts when a lead first appears or jumps much closer.

    Args:
      present: There's a lead to draw.
      distance: Its distance in meters.
      now: The time in seconds.
    """
    if not present:
      self._since = self._distance = None
      return 0.0
    if self._since is None or (self._distance is not None and self._distance - distance > LEAD_JUMP):
      self._since = now
    self._distance = distance
    t = min(1.0, (now - self._since) / LEAD_SETTLE)
    return 1.0 - (1.0 - t) ** 3   # ease out


DISTANCE_SPEED = 1.0       # m/s: enter distance mode near a stop
GAP_SPEED = 1.5            # m/s: return to seconds above this, avoiding flicker
VALUE_TAU = 0.3           # seconds: smooth the displayed value, never the driving data


@dataclass(frozen=True)
class LeadSample:
  """One frame's lead car, as the gap tag reads it: distance and speeds in m/s, and whether the model is confident."""
  distance: float
  speed: float
  relative_speed: float = 0.0
  metric: bool = False
  confident: bool = True
  radar: bool = False


@dataclass(frozen=True)
class GapTagState:
  """What the gap tag draws this frame: its label, the lead's values, its opacity and how far it has settled in."""
  label: str
  lead: Lead
  opacity: float
  progress: float


def read_lead_sample(state: Any, threshold: float) -> LeadSample | None:
  """Use only live, valid messages from this drive, including the model that places the marker."""
  sm = state.sm
  if not state.started or not all(sm.valid.get(name, False) and sm.alive.get(name, False)
                                  and sm.recv_frame.get(name, -1) >= state.started_frame
                                  for name in ("radarState", "carState", "modelV2")):
    return None
  lead, car = sm["radarState"].leadOne, sm["carState"]
  if not lead.status:
    return None
  distance, speed, relative = float(lead.dRel), float(car.vEgo), float(lead.vRel)
  if not all(math.isfinite(value) for value in (distance, speed, relative)) or not 0 < distance <= 1000 or speed < 0:
    return None
  probability = float(lead.modelProb)
  return LeadSample(distance, speed, relative, bool(state.is_metric), math.isfinite(probability) and probability >= threshold,
                    bool(getattr(lead, "radar", False)))


def detailed_tag_on(appearance: Any) -> bool:
  """Distance, gap and relative speed in either power-user view: Developer View, or StarPilot's Lead Info."""
  return bool(appearance.show_developer_sidebar or int(appearance.lead_info_mode) != 0)


def lead_anchor(chevron: list[tuple[float, float]]) -> rl.Vector2 | None:
  """Estimate the roof from StarPilot's projected ground point and marker size, without a new object detector."""
  if not chevron or len(chevron) != 3:
    return None
  x, ground = chevron[1]
  size = chevron[0][1] - ground
  if not all(math.isfinite(value) for value in (x, ground, size)) or size <= 0:
    return None
  return rl.Vector2(x, ground - size * 2.5 * 0.55 - T.px(2))


class GapTracker:
  """Keep the display calm, restarting its 250 ms entrance for a new lead or the existing cut-in rule."""

  def __init__(self) -> None:
    self.reset()

  def reset(self) -> None:
    self._settle = LeadSettle()
    self._distance_mode: bool | None = None
    self._value: float | None = None
    self._last_time: float | None = None

  def update(self, sample: LeadSample | None, now: float) -> GapTagState | None:
    """Follows the lead car from frame to frame and returns what its tag shows.

    Below DISTANCE_SPEED the tag shows the distance, above GAP_SPEED the time gap, keeping its mode in between; the value
    eases toward each new reading.

    Args:
      sample: This frame's lead, or None when there isn't one (the tracker resets).
      now: The time in seconds.

    Returns:
      The tag's state, or None without a lead.
    """
    if sample is None:
      self.reset()
      return None
    progress = self._settle.update(True, sample.distance, now)
    previous_mode = self._distance_mode
    if progress == 0.0 or previous_mode is None:
      self._distance_mode = sample.speed < GAP_SPEED
    elif sample.speed < DISTANCE_SPEED:
      self._distance_mode = True
    elif sample.speed > GAP_SPEED:
      self._distance_mode = False

    distance = t_("{} m", round(sample.distance)) if sample.metric else t_("{} ft", round(sample.distance * CV.METER_TO_FOOT))
    relative = sample.relative_speed * (CV.MS_TO_KPH if sample.metric else CV.MS_TO_MPH)
    relative_text = f"{round(relative):+d} {'km/h' if sample.metric else 'mph'}".replace("-", "−")
    if sample.confident:
      target = sample.distance if self._distance_mode else sample.distance / sample.speed
      if progress == 0.0 or previous_mode != self._distance_mode or self._value is None or self._last_time is None:
        self._value = target
      else:
        dt = max(0.0, now - self._last_time)
        self._value += (target - self._value) * (1.0 - math.exp(-dt / VALUE_TAU))
      label = (t_("{} m", round(self._value)) if sample.metric else t_("{} ft", round(self._value * CV.METER_TO_FOOT))) \
              if self._distance_mode else t_("{} s", f"{self._value:.1f}")
      gap = "--" if self._distance_mode else label
    else:
      self._value = None      # returning confidence starts with the current value, never an old one
      label = distance = gap = relative_text = "--"
    self._last_time = now
    lead = Lead(distance, gap, relative_text, sample.confident and relative < -0.5, "radar" if sample.radar else "vision")
    return GapTagState(label, lead, 1.0 if sample.confident else LEAD_UNSURE, progress)
