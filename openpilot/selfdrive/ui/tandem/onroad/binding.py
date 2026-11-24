"""The driving screen's choices from StarPilot 7's state, as plain functions: which alert shows, the new-limit card's
offer, the model's lane change, and the chips for stops, traffic, held steering and a new speed limit. view.py reads
StarPilot and calls these; they import nothing device-only, so they're tested off the device.
"""
from __future__ import annotations

from typing import Any

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.selfdrive.ui.tandem.onroad.layers import LimitOffer
from openpilot.selfdrive.ui.tandem.onroad.status import LimitWatch
from openpilot.selfdrive.ui.tandem.onroad.state import DrivingAlert, LimitDecision, Proposal, displayed_speed
from openpilot.starpilot.speed_limits.acceptance import CONFIRMATION_NS
from openpilot.starpilot.speed_limits.vision.stop_observation import STOP_MAX_AGE_NS

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
  if selected.alert_type.split("/", 1)[0] == "reverseGear" and not selected.critical:   # release's centered words
    return DrivingAlert(alerts.REVERSE, selected.text1, selected.text2)
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


def stop_sign_seen(observed_ns: int, now_ns: int, dashboard: bool) -> bool:
  """Whether a stop sign is in view: the car's dashboard shows one, or StarPilot's camera saw one within the time its own
  STOP sign stays on screen (stop_sign_widget.py).

  Args:
    observed_ns: When StarPilot's camera last confirmed a stop sign (OnroadState.stop_sign_observed_ns), or 0.
    now_ns: The snapshot's time, on the same monotonic clock.
    dashboard: The car's dashboard reports a stop sign (starpilotCarState.dashboardStopSign).
  """
  return dashboard or (observed_ns > 0 and 0 <= now_ns - observed_ns < STOP_MAX_AGE_NS)


def stop_chips(stopping: bool, sign: bool, reason: str | None, longitudinal: bool) -> tuple[bool, bool, bool]:
  """The stop and traffic chips, as StarPilot's own gauge reads its conditional mode.

  Args:
    stopping: Conditional mode accepted a stop and is controlling the speed (onroad_conditional.stop_active).
    sign: A stop sign is in view (stop_sign_seen).
    reason: Conditional mode's current reason (onroad_conditional.reason), e.g. "cem_lead".
    longitudinal: openpilot controls the speed.

  Returns:
    (stopping for a light or sign, ...for a stop sign, slowing for the car ahead).
  """
  return stopping, stopping and sign, bool(longitudinal and not stopping and reason == "cem_lead")


def steering_held(pause_allowed: bool, wants_steering: bool, lateral_active: bool, standstill: bool) -> bool:
  """Whether StarPilot's Pause steering below (or its signal-only form) is what holds steering off: its own rule
  (starpilot/lateral/pause.py) says pause, and steering really is off.

  Args:
    pause_allowed: StarPilot's LateralPause.allowed for the current car state.
    wants_steering: openpilot is engaged, or Always On Steering is latched.
    lateral_active: openpilot is steering now (carControl.latActive).
    standstill: The car is stopped.
  """
  return wants_steering and not pause_allowed and not lateral_active and not standstill


def matching_limit(watch: LimitWatch, obs: Any, speed_mps: float, longitudinal: bool, now: float) -> bool:
  """Whether the Matching limit chip shows: the limit StarPilot accepted changed and its speed limit control is holding
  the car under the set speed on the way to it (LimitWatch).

  Args:
    watch: This drive's LimitWatch, updated every frame so it sees each change.
    obs: StarPilot's speed limit observation (OnroadState.speed_limit).
    speed_mps: The car's speed.
    longitudinal: openpilot controls the speed.
    now: Monotonic seconds.
  """
  limit = obs.accepted_speed_limit_mps or 0.0
  target = obs.accepted_adjusted_limit_mps or obs.effective_cap_mps or limit
  pending = obs.pending_speed_limit_mps is not None or bool(obs.automatic_adoption_pending)
  return watch.update(limit, target, longitudinal and bool(obs.limiting_max_set), pending,
                      1.0 if obs.driver_override_active else 0.0, speed_mps, now)
