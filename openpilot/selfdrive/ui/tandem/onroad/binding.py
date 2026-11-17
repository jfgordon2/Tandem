"""The driving screen's choices from StarPilot 7's state, as plain functions: which alert shows, the new-limit card's
offer, and the model's lane change. view.py reads StarPilot and calls these; they import nothing device-only, so they're
tested off the device.
"""
from __future__ import annotations

from typing import Any

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.selfdrive.ui.tandem.onroad.layers import LimitOffer
from openpilot.selfdrive.ui.tandem.onroad.state import DrivingAlert, LimitDecision, Proposal, displayed_speed
from openpilot.starpilot.speed_limits.acceptance import CONFIRMATION_NS

NONE, FULL = "none", "full"   # StarPilot 7's AlertSize values (a StrEnum)
STATUS_USER_PROMPT, STATUS_CRITICAL = 1, 2   # cereal's AlertStatus, on openpilot's native alert
SIZE_FULL = 3

LIMIT_SOURCES = {
  "map": N_("map"),
  "dashboard": N_("dashboard"),
  "vision": N_("camera"),
  "online": N_("online maps"),
}


def driving_alert(selected: Any, fallback: Any | None, help_steer: bool = False) -> DrivingAlert | None:
  """Keep the native timeout and all critical alerts, even before the first coherent snapshot.

  As on release, a noncritical alert the status chips already say (alerts.shown_as_chip) is left to its chip, and a
  steering-limit alert is left to Help steer while that shows.

  Args:
    selected: StarPilot's selected alert (OnroadAlert).
    fallback: openpilot's own alert renderer's alert, or None.
    help_steer: Help steer is showing.
  """
  if fallback is not None and (fallback.status == STATUS_CRITICAL or selected.size == NONE):
    level = (alerts.CRITICAL if fallback.status == STATUS_CRITICAL or fallback.size == SIZE_FULL else
             alerts.WARNING if fallback.status == STATUS_USER_PROMPT else alerts.INFO)
    return DrivingAlert(level, fallback.text1, fallback.text2)
  if selected.size == NONE:
    return None
  if not (selected.critical or selected.size == FULL):
    if alerts.shown_as_chip(selected.alert_type) or (help_steer and alerts.replaced_by_headroom(selected.alert_type)):
      return None
  if selected.alert_type.split("/", 1)[0] == "reverseGear" and not selected.critical:
    return DrivingAlert(alerts.INFO, selected.text1, selected.text2)
  level = alerts.CRITICAL if selected.critical or selected.size == FULL else alerts.WARNING if selected.user_prompt else alerts.INFO
  return DrivingAlert(level, selected.text1, selected.text2)


def proposal(obs: Any, metric: bool, vienna: bool, now_ns: int) -> Proposal | None:
  """Release's new-limit card for StarPilot's pending decision, with its adjusted speed and confirmation clock.

  Args:
    obs: StarPilot's speed limit observation (SpeedLimitObservation), already cleared for a manual confirmation.
    metric: Speeds in km/h.
    vienna: The round sign used outside the US.
    now_ns: The observation time, monotonic ns.
  """
  if obs.session_id is None or obs.decision_id is None or obs.presentation_id is None or obs.pending_speed_limit_mps is None:
    return None
  elapsed = now_ns - obs.pending_since_ns
  if not 0 < obs.pending_since_ns <= now_ns or not 0 <= elapsed < CONFIRMATION_NS:
    return None
  factor = CV.MS_TO_KPH if metric else CV.MS_TO_MPH
  limit = obs.pending_speed_limit_mps * factor
  target = displayed_speed(obs.pending_adjusted_limit_mps, factor)
  # Lower than the limit in use asks to slow down rather than speed up; with none in use it's a speed up.
  in_use = obs.accepted_adjusted_limit_mps or obs.accepted_speed_limit_mps
  pending = obs.pending_adjusted_limit_mps or obs.pending_speed_limit_mps
  source = LIMIT_SOURCES.get(obs.pending_source, N_("speed limit source"))
  decision = LimitDecision(obs.session_id, obs.decision_id, obs.presentation_id, obs.pending_speed_limit_mps)
  offer = LimitOffer(limit, limit if target is None else target, "km/h" if metric else "mph", source,
                     (CONFIRMATION_NS - elapsed) / 1e9, CONFIRMATION_NS / 1e9, vienna, lower=in_use is not None and pending < in_use)
  return Proposal(decision, offer)


def lane_change(meta: Any) -> tuple[str, str]:
  """The model's lane change as release's chips name it: (off/pre/starting/finishing, left/right/none)."""
  state = {1: "pre", 2: "starting", 3: "finishing"}.get(int(meta.laneChangeState.raw), "off")
  return state, {1: "left", 2: "right"}.get(int(meta.laneChangeDirection.raw), "none")
