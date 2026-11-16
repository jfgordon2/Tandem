"""Bind the approved driving screen to StarPilot's camera, snapshots and action owners."""
from __future__ import annotations

import math
import time
from functools import cached_property
from typing import Any

from openpilot.cereal import messaging
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.onroad.alert_renderer import Alert as NativeAlert
from openpilot.selfdrive.ui.onroad.augmented_road_view import AugmentedRoadView
from openpilot.selfdrive.ui.tandem.onroad import alerts, size as Z
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay, road_rect
from openpilot.selfdrive.ui.tandem.onroad.state import BarState, Chip, DriveDisplay, DrivingAlert, LimitDecision, LimitOffer, RamWatch, displayed_speed
from openpilot.selfdrive.ui.tandem.onroad.streets import short_street
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.ui_state import device, ui_state
from openpilot.starpilot.controllers import cruise_action, mode_actions
from openpilot.starpilot.speed_limits.acceptance import CONFIRMATION_NS
from openpilot.starpilot.ui.onroad_state import AlertSize, OnroadAlert, OnroadState, SlcActionKind, SlcUiRequest, manual_slc_confirmation
from openpilot.starpilot.ui.presentation import Profile
from openpilot.starpilot.ui.raylib import rl
from openpilot.starpilot.ui.runtime_snapshot import RuntimeSnapshotAdapter, current_message, display_message
from openpilot.starpilot.ui.shell import ShellMode
from openpilot.starpilot.ui.slc_action_dispatch import SlcActionDispatcher
from openpilot.starpilot.ui.unified_speed_presentation import resolve_unified_speed
from openpilot.system.ui.lib.application import MousePos


LIMIT_SOURCES = {
  "map": N_("map"),
  "dashboard": N_("dashboard"),
  "vision": N_("camera"),
  "online": N_("online maps"),
}


def driving_alert(selected: OnroadAlert, fallback: NativeAlert | None) -> DrivingAlert | None:
  """Keep the native timeout and all critical alerts, even before the first coherent snapshot."""
  if fallback is not None and (fallback.status == 2 or selected.size == AlertSize.NONE):
    level = alerts.CRITICAL if fallback.status == 2 or fallback.size == 3 else alerts.WARNING if fallback.status == 1 else alerts.INFO
    return DrivingAlert(level, fallback.text1, fallback.text2)
  if selected.size == AlertSize.NONE:
    return None
  if selected.alert_type.split("/", 1)[0] == "reverseGear" and not selected.critical:
    return DrivingAlert(alerts.INFO, selected.text1, selected.text2)
  level = alerts.CRITICAL if selected.critical or selected.size == AlertSize.FULL else alerts.WARNING if selected.user_prompt else alerts.INFO
  return DrivingAlert(level, selected.text1, selected.text2)


def limit_offer(state: OnroadState, allowed: bool, now_ns: int) -> LimitOffer | None:
  """Use StarPilot's pending decision, adjusted speed and confirmation clock."""
  if not allowed or not manual_slc_confirmation(Profile.LARGE, state):
    return None
  obs = state.speed_limit
  if obs.session_id is None or obs.decision_id is None or obs.presentation_id is None or obs.pending_speed_limit_mps is None:
    return None
  elapsed = now_ns - obs.pending_since_ns
  if not 0 < obs.pending_since_ns <= now_ns or not 0 <= elapsed < CONFIRMATION_NS:
    return None
  factor = CV.MS_TO_KPH if state.metric else CV.MS_TO_MPH
  limit = obs.pending_speed_limit_mps * factor
  target = displayed_speed(obs.pending_adjusted_limit_mps, factor)
  source = LIMIT_SOURCES.get(obs.pending_source, N_("speed limit source"))
  decision = LimitDecision(obs.session_id, obs.decision_id, obs.presentation_id, obs.pending_speed_limit_mps)
  return LimitOffer(decision, limit, target, "km/h" if state.metric else "mph", source,
                    (CONFIRMATION_NS - elapsed) / 1e9, CONFIRMATION_NS / 1e9, state.appearance.use_vienna_sign)


class EssentialsOnroad(AugmentedRoadView):
  """Use the existing camera and model layer. StarPilot still owns action admission."""

  def __init__(self) -> None:
    super().__init__()
    self._snapshot: RuntimeSnapshotAdapter | None = None
    self._display = DriveDisplay()
    self._native: OnroadState | None = None
    self._road_sm: messaging.SubMaster | None = None
    self._ram = RamWatch()
    self._safe = True
    self._safe_at = -1_000_000_000
    self._prepared = False
    self._overlay = self._child(OnroadOverlay(lambda: self._display, self._menu, self._step, self._disengage, self._resolve))

  @cached_property
  def _publisher(self) -> messaging.PubMaster:
    return messaging.PubMaster(["slcAction"])

  @cached_property
  def _cruise_actions(self) -> cruise_action.CruiseActionPublisher:
    return cruise_action.CruiseActionPublisher()

  @cached_property
  def _mode_actions(self) -> mode_actions.ModeActionPublisher:
    return mode_actions.ModeActionPublisher()

  @cached_property
  def _limit_actions(self) -> SlcActionDispatcher:
    return SlcActionDispatcher(self._publisher, self._current_slc)

  def _current_slc(self, now_ns: int) -> Any | None:
    return current_message(ui_state.sm, "slcState", now_ns, after_frame=ui_state.started_frame)

  def _writable(self, state: OnroadState, alert: DrivingAlert | None) -> bool:
    return bool(ui_state.started and device.awake and state.camera_available and not state.reversing and alert is None
                and not ui_state.projection_read_only and ui_state.replay_clock is None)

  def _street(self, now_ns: int) -> str:
    if ui_state.replay_clock is not None:
      return ""
    if self._road_sm is None:
      self._road_sm = messaging.SubMaster(["mapdOut"])
    self._road_sm.update(0)
    road = current_message(self._road_sm, "mapdOut", now_ns)
    return short_street(str(road.roadName or road.wayName)) if road is not None else ""

  def _situation(self, now_ns: int, state: OnroadState, selected: DrivingAlert | None) -> tuple[tuple[Chip, ...], DrivingAlert | None]:
    sm, after = ui_state.sm, ui_state.started_frame
    events = current_message(sm, "onroadEvents", now_ns, after_frame=after)
    active_ram = events is not None and any(str(event.name) == "lowMemory" for event in events)
    memory = current_message(sm, "deviceState", now_ns)
    percent = int(memory.memoryUsagePercent) if memory is not None else None
    # Keep only the explicitly noncritical permanent memory advisory in the chip.
    native_advisory = (state.alert.alert_type == "lowMemory/permanent" and selected is not None
                       and selected.level == alerts.INFO and percent is not None)
    ram = self._ram.update(active_ram or native_advisory, percent)
    chips = []
    if state.curve is not None and state.curve.controlling:
      chips.append(Chip("curve", N_("Slowing for curve"), "curve"))
    if ram is not None:
      chips.append(ram)
    return tuple(chips), None if native_advisory and ram is not None else selected

  def prepare_frame(self) -> bool:
    """Capture this frame before MainLayout decides whether the sidebar can show."""
    self._prepared = True
    if not ui_state.started and ui_state.replay_clock is None:
      self._display, self._native = DriveDisplay(), None
      return False
    Z.refresh()
    if self._snapshot is None:
      self._snapshot = RuntimeSnapshotAdapter(ui_state)
    state = self._snapshot.build(ShellMode.ONROAD, onroad_view_only=True, stopped_timer_profile="large").onroad
    self._native = state
    now_ns = state.observed_ns
    fallback = self.alert_renderer.get_alert(ui_state.sm) if ui_state.replay_clock is None else None
    selected = driving_alert(state.alert, fallback)
    chips, visible_alert = self._situation(now_ns, state, selected)
    if now_ns - self._safe_at >= 1_000_000_000:
      self._safe_at = now_ns
      self._safe = bool(ui_state.params.get_bool("SafeMode"))
    allowed = self._writable(state, visible_alert)
    sm, cp, after = ui_state.sm, ui_state.CP, ui_state.started_frame
    car = display_message(sm, "carState", now_ns, after_frame=after)
    dm = display_message(sm, "driverMonitoringState", now_ns, after_frame=after)
    factor = CV.MS_TO_KPH if state.metric else CV.MS_TO_MPH
    cruise = displayed_speed(state.cruise_kph, 1.0 if state.metric else CV.KPH_TO_MPH)
    can_adjust = cruise is not None and allowed and not self._safe and cruise_action.ui_authority(sm, cp, now_ns)
    can_disengage = state.engaged and allowed and mode_actions.authority(sm, cp, now_ns, "disengage")
    posted = resolve_unified_speed(state).posted_text if state.appearance.show_speed_limit_sign else ""
    monitoring = None
    if dm is not None and str(dm.activePolicy) == "vision":
      awareness = float(dm.awarenessStatus)
      if math.isfinite(awareness):
        monitoring = max(0.0, min(awareness, 1.0))
    self._display = DriveDisplay(
      bar=BarState(state.engaged, can_adjust, can_disengage, cruise, self._street(time.monotonic_ns())),
      speed=displayed_speed(state.speed_mps, factor), unit="km/h" if state.metric else "mph", posted=posted,
      vienna=state.appearance.use_vienna_sign,
      left=bool(car is not None and car.canValid and not car.canTimeout and car.leftBlinker),
      right=bool(car is not None and car.canValid and not car.canTimeout and car.rightBlinker),
      monitor=monitoring, attention_warning=bool(visible_alert is not None and visible_alert.level == alerts.WARNING
                                                and "distract" in state.alert.alert_type.lower()),
      torque=state.torque_utilization if state.lateral_active and state.torque_source_available else None,
      chips=chips, alert=visible_alert, offer=limit_offer(state, allowed and not self._safe, now_ns),
    )
    return visible_alert is not None and visible_alert.level == alerts.CRITICAL

  def _render(self, rect: rl.Rectangle, *, poll_camera: bool = True) -> None:
    if not self._prepared:
      self.prepare_frame()
    self._prepared = False
    state = self._native
    if state is None:
      return
    critical = self._display.alert is not None and self._display.alert.level == alerts.CRITICAL
    if not critical:
      inner = road_rect(rect)
      rl.begin_scissor_mode(int(inner.x), int(inner.y), int(inner.width), int(inner.height))
      try:
        self.render_camera_model_layer(inner, camera_view=int(state.appearance.camera_view),
                                       reverse_driver=state.reverse_driver_camera, poll_camera=poll_camera)
      finally:
        rl.end_scissor_mode()
    self._overlay.render(rect)

  def _can_act(self) -> bool:
    state = self._native
    return state is not None and self._writable(state, self._display.alert)

  def _menu(self) -> None:
    if self._display.alert is None and self._click_callback is not None:
      self._click_callback()

  def _step(self, direction: int) -> None:
    if self._can_act() and self._display.bar.adjust_speed and not ui_state.params.get_bool("SafeMode"):
      self._cruise_actions.dispatch(direction > 0, ui_state.sm, ui_state.CP, self._publisher, now_ns=time.monotonic_ns())

  def _disengage(self) -> None:
    if self._can_act() and self._display.bar.disengage:
      self._mode_actions.dispatch("disengage", ui_state.sm, ui_state.CP, self._publisher, now_ns=time.monotonic_ns())

  def _resolve(self, identity: LimitDecision, match: bool) -> None:
    offer = self._display.offer
    if not self._can_act() or offer is None or offer.identity != identity or ui_state.params.get_bool("SafeMode"):
      return
    kind = SlcActionKind.ACCEPT if match else SlcActionKind.REJECT
    self._limit_actions.dispatch(SlcUiRequest(kind, identity.session, identity.decision_id, identity.presentation_id, identity.candidate_mps))

  def _handle_mouse_press(self, mouse_pos: MousePos, /) -> None:
    """Only the menu tile opens the sidebar in the Essentials view."""

  def hide_event(self) -> None:
    super().hide_event()
    self._display, self._native = DriveDisplay(), None
    self._prepared = False
    self._overlay.reset_controls()
