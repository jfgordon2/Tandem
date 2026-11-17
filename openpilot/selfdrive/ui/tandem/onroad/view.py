"""Bind release's driving screen (layers.py, status.py, alerts.py) to StarPilot 7's camera, snapshots and action owners.

StarPilot still picks the alert, qualifies every action and decides each speed-limit proposal; this reads its state
into release's state objects (BarState, Snapshot for the chips, ArcState, LimitOffer) once a frame.
"""
from __future__ import annotations

import math
import time
from functools import cached_property
from typing import Any

from openpilot.cereal import messaging
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.onroad.augmented_road_view import AugmentedRoadView
from openpilot.selfdrive.ui.tandem.onroad import alerts, size as Z
from openpilot.selfdrive.ui.tandem.onroad.compass import DriveCompass
from openpilot.selfdrive.ui.tandem.onroad.limits import LimitFollower
from openpilot.selfdrive.ui.tandem.prefs import MAX_FOLLOWS_LIMIT
from openpilot.selfdrive.ui.tandem.onroad.binding import driving_alert, lane_change, proposal
from openpilot.selfdrive.ui.tandem.onroad.layers import AT_LIMIT, ArcState, BarState, Headroom
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay, road_rect
from openpilot.selfdrive.ui.tandem.onroad.state import DriveDisplay, DrivingAlert, LimitDecision, Proposal, displayed_speed
from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, RamWatch, Snapshot
from openpilot.selfdrive.ui.tandem.onroad.streets import short_street
from openpilot.selfdrive.ui.tandem.ram import RamLog, shared_log
from openpilot.selfdrive.ui.ui_state import device, ui_state
from openpilot.starpilot.controllers import cruise_action, mode_actions
from openpilot.starpilot.ui.onroad_state import AlertSize, ObservationKind, OnroadState, SlcActionKind, SlcUiRequest, manual_slc_confirmation
from openpilot.starpilot.ui.presentation import Profile
from openpilot.starpilot.ui.raylib import rl
from openpilot.starpilot.ui.runtime_snapshot import RuntimeSnapshotAdapter, current_message, display_message
from openpilot.starpilot.ui.shell import ShellMode
from openpilot.starpilot.ui.slc_action_dispatch import SlcActionDispatcher
from openpilot.starpilot.ui.unified_speed_presentation import resolve_unified_speed
from openpilot.system.ui.lib.application import MousePos


PREVIEW_SECONDS = 2.5   # how far ahead the arc's preview looks, as on release


def limit_offer(state: OnroadState, allowed: bool, now_ns: int) -> Proposal | None:
  """The new-limit card's proposal, when StarPilot asks the driver to confirm and the screen may answer."""
  if not allowed or not manual_slc_confirmation(Profile.LARGE, state):
    return None
  return proposal(state.speed_limit, state.metric, state.appearance.use_vienna_sign, now_ns)


class EssentialsOnroad(AugmentedRoadView):
  """Use the existing camera and model layer. StarPilot still owns action admission."""

  def __init__(self) -> None:
    super().__init__(stock_hud=False)
    self._snapshot: RuntimeSnapshotAdapter | None = None
    self._display = DriveDisplay()
    self._compass = DriveCompass()
    self._follower = LimitFollower()
    self._native: OnroadState | None = None
    self._road_sm: messaging.SubMaster | None = None
    self._ram = RamWatch()
    self._chip_stack = ChipStack()
    self._headroom = Headroom()
    self._safe = True
    self._safe_at = -1_000_000_000
    self._prepared = False
    self._overlay = self._child(OnroadOverlay(lambda: self._display, self._menu, self._step, self._disengage, self._resolve))

  @cached_property
  def _ram_log(self) -> RamLog:
    return shared_log()

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

  def _chips_from(self, now_ns: int, state: OnroadState) -> Snapshot:
    """Release's chip inputs from StarPilot 7. Planner reasons StarPilot 7 doesn't publish the same way yet (stop lights and
    signs, slowing for traffic, steering held, turns, matching a new limit, weather) stay off until their sources are mapped
    (PORTING.md)."""
    sm, after = ui_state.sm, ui_state.started_frame
    snap = Snapshot(engaged=state.engaged, metric=state.metric, speed=state.speed_mps or 0.0,
                    curve_control=bool(state.curve is not None and state.curve.controlling))
    snap.always_on_lateral = bool(state.aol_latched and state.lateral_active)
    car = display_message(sm, "carState", now_ns, after_frame=after)
    if car is not None and car.canValid and not car.canTimeout:
      snap.standstill, snap.accel, snap.waiting_for_resume = bool(car.standstill), float(car.aEgo), bool(car.cruiseState.standstill)
      snap.signal_on = bool(car.leftBlinker or car.rightBlinker)
      snap.signal_direction = "both" if car.leftBlinker and car.rightBlinker else "left" if car.leftBlinker else "right" if car.rightBlinker else "none"
      snap.blindspot = bool(car.leftBlindspot if car.leftBlinker else car.rightBlindspot)
    model = display_message(sm, "modelV2", now_ns, after_frame=after)
    if model is not None:
      snap.lane_change, snap.lane_change_direction = lane_change(model.meta)
    sp_car = display_message(sm, "starpilotCarState", now_ns, after_frame=after)
    if sp_car is not None:
      snap.lateral_paused, snap.speed_paused = bool(sp_car.pauseLateral), bool(sp_car.pauseLongitudinal)
      snap.coasting, snap.pulse_glide = bool(sp_car.forceCoast), bool(sp_car.pulseAndGlide)
    events = current_message(sm, "onroadEvents", now_ns, after_frame=after)
    snap.events = {str(event.name) for event in events} if events is not None else set()
    if state.alert.size != AlertSize.NONE and state.alert.alert_type:   # held alerts outlast their one-frame events
      snap.events.add(state.alert.alert_type.split("/", 1)[0])
    memory = current_message(sm, "deviceState", now_ns)
    if memory is not None:
      snap.memory_percent = int(memory.memoryUsagePercent)
    snap.low_ram = self._ram.update("lowMemory" in snap.events, snap.memory_percent)
    return snap

  def _arc(self, state: OnroadState, now_ns: int) -> ArcState:
    """Release's steering arc from StarPilot 7's torque use, with the planned path's need PREVIEW_SECONDS ahead."""
    active = bool(state.lateral_active and state.torque_source_available and not state.reversing)
    usage = max(-1.0, min(1.0, state.torque_utilization)) if active else 0.0
    preview = 0.0
    model = display_message(ui_state.sm, "modelV2", now_ns, after_frame=ui_state.started_frame) if active else None
    if model is not None and state.speed_mps is not None:
      times, rates = list(model.orientationRate.t), list(model.orientationRate.z)
      if times and len(times) == len(rates):
        index = min(range(len(times)), key=lambda i: abs(times[i] - PREVIEW_SECONDS))
        cp = ui_state.CP
        max_lat = float(cp.maxLateralAccel) if cp is not None and cp.maxLateralAccel else 3.0
        preview = float(rates[index]) * state.speed_mps / max_lat
    return ArcState(usage, preview, active, self._headroom.stage(usage, now_ns / 1e9, active))

  def prepare_frame(self) -> bool:
    """Capture this frame before MainLayout decides whether the sidebar can show."""
    self._prepared = True
    if not ui_state.started and ui_state.replay_clock is None:
      if self._native is not None:
        self._compass.offroad(time.monotonic())   # the drive ended: keep its last heading
      self._display, self._native = DriveDisplay(), None
      return False
    Z.refresh()
    if self._snapshot is None:
      self._snapshot = RuntimeSnapshotAdapter(ui_state)
    state = self._snapshot.build(ShellMode.ONROAD, onroad_view_only=True, stopped_timer_profile="large").onroad
    self._native = state
    now_ns = state.observed_ns
    fallback = self.alert_renderer.get_alert(ui_state.sm) if ui_state.replay_clock is None else None
    arc = self._arc(state, now_ns)
    steer_limit = alerts.replaced_by_headroom(state.alert.alert_type) and not state.alert.critical
    help_steer = arc.active and (arc.stage == AT_LIMIT or steer_limit)
    visible_alert = driving_alert(state.alert, fallback, help_steer)
    help_steer = help_steer and visible_alert is None   # other alerts keep priority, as on release
    if now_ns - self._safe_at >= 1_000_000_000:
      self._safe_at = now_ns
      self._safe = bool(ui_state.params.get_bool("SafeMode"))
    allowed = self._writable(state, visible_alert)
    sm, cp, after = ui_state.sm, ui_state.CP, ui_state.started_frame
    car = display_message(sm, "carState", now_ns, after_frame=after)
    dm = display_message(sm, "driverMonitoringState", now_ns, after_frame=after)
    if ui_state.replay_clock is None:
      self._compass.update(ui_state, time.monotonic(), bool(state.reversing))
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
    snapshot = self._chips_from(now_ns, state)
    if ui_state.started and not ui_state.projection_read_only and ui_state.replay_clock is None:
      self._ram_log.drive(after, time.monotonic())
      if snapshot.low_ram and snapshot.memory_percent > self._ram.CLEAR:
        self._ram_log.note(after, snapshot.memory_percent)
    chips = self._chip_stack.update(snapshot, now_ns / 1e9, visible_alert is not None or help_steer)
    unit = "km/h" if state.metric else "mph"
    self._display = DriveDisplay(
      bar=BarState(engaged=state.engaged, set_speed=cruise or 0.0, unit=unit, street=self._street(time.monotonic_ns()), heading=self._compass.heading(),
                   can_adjust=bool(can_adjust), can_disengage=bool(can_disengage)),
      speed=displayed_speed(state.speed_mps, factor), unit=unit, posted=posted,
      vienna=state.appearance.use_vienna_sign,
      left=bool(car is not None and car.canValid and not car.canTimeout and car.leftBlinker),
      right=bool(car is not None and car.canValid and not car.canTimeout and car.rightBlinker),
      monitor=monitoring, attention_warning=bool(visible_alert is not None and visible_alert.level == alerts.WARNING
                                                and "distract" in state.alert.alert_type.lower()),
      arc=arc, help_steer=help_steer, chips=tuple(chips), alert=visible_alert,
      proposal=limit_offer(state, allowed and not self._safe, now_ns),
    )
    self._follow_limit(state, allowed and not self._safe)
    return visible_alert is not None and visible_alert.level == alerts.CRITICAL

  def _follow_limit(self, state: OnroadState, allowed: bool) -> None:
    """MAX follows limits: adopt each new posted limit once through StarPilot's ADOPT, where StarPilot sets MAX."""
    obs, cp = state.speed_limit, ui_state.CP
    pending = obs.pending_speed_limit_mps is not None or obs.automatic_adoption_pending
    valid = obs.kind == ObservationKind.VALID and obs.source != "none"
    if not self._follower.update(obs.speed_limit_mps, valid, pending, bool(state.engaged)):
      return
    if (allowed and MAX_FOLLOWS_LIMIT.get() and cp is not None and not cp.pcmCruise and ui_state.replay_clock is None and
        obs.session_id and obs.decision_id is not None and obs.presentation_id and obs.speed_limit_mps):
      self._limit_actions.dispatch(SlcUiRequest(SlcActionKind.ADOPT, obs.session_id, obs.decision_id, obs.presentation_id,
                                                obs.speed_limit_mps))

  def requires_full_view(self) -> bool:
    """MainLayout asks before drawing: a critical alert takes the whole screen, so the sidebar closes."""
    return self.prepare_frame()

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
    if self._can_act() and self._display.bar.can_adjust and not ui_state.params.get_bool("SafeMode"):
      self._cruise_actions.dispatch(direction > 0, ui_state.sm, ui_state.CP, self._publisher, now_ns=time.monotonic_ns())

  def _disengage(self) -> None:
    if self._can_act() and self._display.bar.engaged and self._display.bar.can_disengage:
      self._mode_actions.dispatch("disengage", ui_state.sm, ui_state.CP, self._publisher, now_ns=time.monotonic_ns())

  def _resolve(self, identity: LimitDecision, match: bool) -> None:
    proposal = self._display.proposal
    if not self._can_act() or proposal is None or proposal.identity != identity or ui_state.params.get_bool("SafeMode"):
      return
    kind = SlcActionKind.ACCEPT if match else SlcActionKind.REJECT
    self._limit_actions.dispatch(SlcUiRequest(kind, identity.session, identity.decision_id, identity.presentation_id, identity.candidate_mps))

  def _handle_mouse_press(self, mouse_pos: MousePos, /) -> None:
    """Only the menu tile opens the sidebar in the Essentials view."""

  def hide_event(self) -> None:
    super().hide_event()
    self._display, self._native = DriveDisplay(), None
    self._prepared = False
    self._headroom.stage(0.0, 0.0, active=False)
    self._chip_stack = ChipStack()
    self._overlay.reset_controls()
