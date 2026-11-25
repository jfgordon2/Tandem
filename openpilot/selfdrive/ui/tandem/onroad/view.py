"""Bind release's driving screen (layers.py, status.py, alerts.py) to StarPilot 7's camera, snapshots and action owners.

StarPilot still picks the alert, qualifies every action and decides each speed-limit proposal; this reads its state
into release's state objects (BarState, Snapshot for the chips, ArcState, LimitOffer) once a frame.
"""
from __future__ import annotations

import datetime
import time
from dataclasses import replace
from collections.abc import Callable
from functools import cached_property
from typing import Any

from openpilot.cereal import messaging
from openpilot.common.constants import CV
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.onroad.augmented_road_view import AugmentedRoadView
from openpilot.selfdrive.ui.tandem.onroad import alerts, size as Z
from openpilot.selfdrive.ui.tandem.onroad.compass import DriveCompass
from openpilot.selfdrive.ui.tandem.onroad import developer, extras
from openpilot.selfdrive.ui.tandem.onroad.lead import (LEAD_BRAKING_INK, LEAD_FAINT, LEAD_INK, GapTagState, GapTracker, adjacent_chevron,
                                                       detailed_tag_on, draw_lead_bar, lead_anchor, lead_bar_rect, read_lead_sample)
from openpilot.selfdrive.ui.tandem.onroad.layers import bar_height, bar_margin
from openpilot.selfdrive.ui.tandem.onroad.limits import LimitFollower
from openpilot.selfdrive.ui.tandem.forecast import Announcer, ForecastService, heads_up, now_conditions, shared_service, wall_clock
from openpilot.selfdrive.ui.tandem.prefs import LEAD_TAG, MAX_FOLLOWS_LIMIT, TURN_SIGNAL, WEATHER_CHIME, WEATHER_HEADS_UP
from openpilot.selfdrive.ui.tandem.onroad.binding import (driving_alert, lane_change, matching_limit, proposal, steering_held,
                                                          stop_chips, stop_sign_seen)
from openpilot.selfdrive.ui.tandem.onroad.layers import AT_LIMIT, ArcState, BarState, Headroom
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay, road_rect
from openpilot.selfdrive.ui.tandem.onroad.state import awareness, route_progress, turn, DriveDisplay, DrivingAlert, LimitDecision, Proposal, displayed_speed
from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, LimitWatch, RamWatch, Snapshot, chips_for, routing_chip, routing_state
from openpilot.selfdrive.ui.tandem.onroad.streets import short_street
from openpilot.selfdrive.ui.tandem.onroad.turn_signals import GAP as SIGNAL_GAP, STANDARD, TurnSignalRenderer
from openpilot.selfdrive.ui.tandem.places import StarPilotPlaces
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
# StarPilot's navigation statuses with a destination: the bar shows the route (End route, ARRIVE and LEFT) even before
# there's a route, as in design/valhalla2-chip-first-route.html.
ROUTE_ACTIVE = frozenset({"routing", "waitingForLocation", "routeUnavailable", "guiding", "arrived"})


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
    self._failed: set[str] = set()   # extras that failed once (_safely)
    self._pedals = extras.Pedals()
    self._help_steer = False         # the Help steer warning was up last frame (its chime, starpilot/tandem/headroom.py)
    self._gap_tracker = GapTracker()
    self._gap_state: GapTagState | None = None
    self._lead_tag_on, self._lead_tag_read = True, -1.0   # prefs.LEAD_TAG, read once a second
    self._lead_display: tuple[bool, int, bool | None] | None = None   # what the lead marker and its text show (_update_lead)
    self._dev: developer.DevData | None = None            # Developer View's values while StarPilot's sidebar setting is on
    self._road = rl.Rectangle(0, 0, 0, 0)                  # the road view's inner rect, for the lead tag's bounds
    # The lead tag takes the place of the text StarPilot's renderer draws above its lead marker (its Lead Info).
    self._stock_lead_info = self.model_renderer._draw_lead_info
    self.model_renderer._draw_lead_info = self._draw_lead_info  # type: ignore[method-assign]
    # And Tandem draws in place of its red lead marker (design/gaptag.html, leadmarker.html), as release did.
    self.model_renderer._draw_lead_indicator = self._draw_leads  # type: ignore[method-assign]
    self._braking_for_lead = False   # the Slowing for traffic chip's rule, so the tag or bar turns amber with it
    self._radar_sm: messaging.SubMaster | None = None   # the cars in the next lanes, while Lead Insights is on
    self._native: OnroadState | None = None
    self._road_sm: messaging.SubMaster | None = None
    self._ram = RamWatch()
    self._limits = LimitWatch()
    self._chip_stack = ChipStack()
    self._headroom = Headroom()
    self._safe = True
    self._safe_at = -1_000_000_000
    self._prepared = False
    self._routing_key: tuple[int, str] | None = None
    self._guided = False   # this drive had a route to this destination: a new request is a recalculation
    self._nav_status = ""   # StarPilot's published navigation status
    self._jetlink: Any = None   # StarPilot's Jetlink status feed, made when its widget is first placed
    self._model_chip = extras.ModelChip()
    self._announcer = Announcer()
    self._turn_signals = TurnSignalRenderer()
    self._signal_pack, self._signal_read_at = STANDARD, -1e9
    self._overlay = self._child(OnroadOverlay(lambda: self._display, self._menu, self._step, self._disengage, self._resolve,
                                              end_route=self._end_route, where_to=self._where_to))

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
    """Release's chip inputs from StarPilot 7. Stops and slowing for traffic come from StarPilot's conditional mode as
    its own gauge reads it, held steering from its Pause steering rule, and Matching limit from the limit it accepted.
    Slowing for a route turn asks StarPilot's own rule (navigation/intent.py) with the set speed."""
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
      self._safely("steering held chip", lambda: self._steering_held(snap, state, car, after, now_ns))
    model = display_message(sm, "modelV2", now_ns, after_frame=after)
    if model is not None:
      snap.lane_change, snap.lane_change_direction = lane_change(model.meta)
    sp_car = display_message(sm, "starpilotCarState", now_ns, after_frame=after)
    if sp_car is not None:
      snap.lateral_paused, snap.speed_paused = bool(sp_car.pauseLateral), bool(sp_car.pauseLongitudinal)
      snap.coasting, snap.pulse_glide = bool(sp_car.forceCoast), bool(sp_car.pulseAndGlide)
    self._safely("planner chips", lambda: self._planner_chips(snap, state, sp_car, now_ns))
    events = current_message(sm, "onroadEvents", now_ns, after_frame=after)
    snap.events = {str(event.name) for event in events} if events is not None else set()
    if state.alert.size != AlertSize.NONE and state.alert.alert_type:   # held alerts outlast their one-frame events
      snap.events.add(state.alert.alert_type.split("/", 1)[0])
    cruise_kph = state.cruise_kph
    if ui_state.CP is not None and cruise_kph and ui_state.replay_clock is None:
      self._safely("turn chip", lambda: self._turn_chip(snap, now_ns, float(cruise_kph) * CV.KPH_TO_MS))
    self._safely("weather heads-up", lambda: self._apply_forecast(snap))
    self._safely("navigation status", lambda: self._read_navigation(now_ns))
    self._safely("routing chip", lambda: self._routing_chip(snap, now_ns))
    memory = current_message(sm, "deviceState", now_ns)
    if memory is not None:
      snap.memory_percent = int(memory.memoryUsagePercent)
    snap.low_ram = self._ram.update("lowMemory" in snap.events, snap.memory_percent)
    self._braking_for_lead = any(chip.key == "traffic" for chip in chips_for(snap))
    return snap

  @cached_property
  def _lateral_pause(self) -> Any:
    from openpilot.starpilot.lateral.pause import LateralPause, read_settings
    return LateralPause(read_settings(ui_state.params), ui_state.params)

  def _steering_held(self, snap: Snapshot, state: OnroadState, car: Any, drive: int, now_ns: int) -> None:
    """Steering paused, under a speed or for a signal: StarPilot's own Pause steering rule (starpilot/lateral/pause.py)
    run on the same car state controlsd uses, shown only while steering is really off."""
    if drive <= 0:
      return
    pause = self._lateral_pause
    allowed = pause.allowed(car, now_ns=now_ns, source_ns=int(ui_state.sm.logMonoTime["carState"]), drive_id=drive)
    settings = pause.settings
    snap.pause_lateral_ms, snap.pause_on_signal = float(settings.speed_mps), bool(settings.signal_only)
    snap.pause_lateral_speed = settings.speed_mps * (CV.MS_TO_KPH if state.metric else CV.MS_TO_MPH)
    snap.steering_held = steering_held(allowed, bool(state.engaged or state.aol_latched), bool(state.lateral_active),
                                       snap.standstill)

  def _planner_chips(self, snap: Snapshot, state: OnroadState, sp_car: Any, now_ns: int) -> None:
    """Stopping (and for a stop sign), slowing for traffic, and Matching limit, from StarPilot's own readings."""
    from openpilot.starpilot.ui.onroad_conditional import reason, stop_active
    dashboard = bool(sp_car is not None and sp_car.dashboardStopSign > 0)
    sign = stop_sign_seen(state.stop_sign_observed_ns, now_ns, dashboard)
    snap.red_light, snap.stop_sign, snap.slowing_for_lead = stop_chips(stop_active(state), sign, reason(state),
                                                                       bool(state.longitudinal_active))
    obs = state.speed_limit
    snap.limit_changed = matching_limit(self._limits, obs, snap.speed, bool(state.longitudinal_active), time.monotonic())
    limit = obs.accepted_speed_limit_mps
    snap.speed_limit = limit * (CV.MS_TO_KPH if state.metric else CV.MS_TO_MPH) if limit else 0.0

  def _read_navigation(self, now_ns: int) -> None:
    """StarPilot's published navigation status, and whether this drive already had a route to its destination."""
    from openpilot.starpilot.navigation.wire import navigation_state
    sm, after = ui_state.sm, ui_state.started_frame
    message = display_message(sm, "starpilotNavigation", now_ns, after_frame=after)
    state = navigation_state(message) if message is not None else None
    self._nav_status = str(state.status) if state is not None else ""
    key = (after, str(state.destinationName) if state is not None else "")
    if key != self._routing_key:   # a new drive or destination starts with no route yet
      self._routing_key, self._guided = key, False
    self._guided |= self._nav_status == "guiding"

  def _model(self, state: OnroadState) -> tuple[str, float] | None:
    """The model chip from Jetlink's state, while StarPilot's onroad layout places its Jetlink widget (as StarPilot's own
    screen shows it). StarPilot's feed polls Jetlink off the drawing thread, only while it's wanted."""
    try:
      from openpilot.starpilot.ui.onroad_customization import JETLINK_WIDGET
      placed = state.customization["layouts"]["large"].get(JETLINK_WIDGET)
      wanted = bool(placed and placed["enabled"] and ui_state.started and ui_state.replay_clock is None)
      if self._jetlink is None and wanted:
        from openpilot.starpilot.models.jetlink_status import JetlinkStatusFeed
        self._jetlink = JetlinkStatusFeed()
      if self._jetlink is not None:
        self._jetlink.set_enabled(wanted)
      jetlink = self._jetlink.snapshot().state if self._jetlink is not None and wanted else "off"
    except Exception:
      cloudlog.exception("Tandem: model chip")
      jetlink = "off"
    return self._model_chip.update(jetlink, time.monotonic())

  @cached_property
  def _forecast(self) -> ForecastService:
    return shared_service()   # Home shows the same forecast

  def _apply_forecast(self, snap: Snapshot) -> None:
    """Weather heads-up (forecast.py): its chip from 15 minutes before rain, snow or storms until they end, and one soft
    chime (Tandem's WEATHER chime, through StarPilot's sound daemon) when an event is first seen within the hour."""
    if not WEATHER_HEADS_UP.get() or ui_state.replay_clock is not None or ui_state.projection_read_only:
      return
    self._forecast.tick()
    wall = wall_clock()
    hint = heads_up(self._forecast.forecast, wall)
    show, chime = self._announcer.update(hint, wall)
    if chime and ui_state.started and WEATHER_CHIME.get():   # Alerts › Chimes › Weather heads-up
      from openpilot.starpilot.tandem.state import WEATHER
      WEATHER.write(time.monotonic())
    if show and hint is not None:
      snap.forecast, snap.forecast_active = (hint.text, hint.icon), hint.active

  def _weather_now(self, metric: bool) -> tuple[str, str] | None:
    """The forecast's current hour for the bar, without a route (Weather heads-up's forecast, General › Temperature)."""
    if not WEATHER_HEADS_UP.get() or ui_state.replay_clock is not None:
      return None
    from openpilot.selfdrive.ui.tandem.prefs import celsius
    return now_conditions(self._forecast.forecast, wall_clock(), celsius(metric))

  def _routing_chip(self, snap: Snapshot, now_ns: int) -> None:
    """Tandem's routing chip (design/valhalla2-chip-*.html) from StarPilot's navigation status, with offline routing on:
    finding or recalculating a route, waiting for GPS, which maps a fallback switched to, or why there's no route."""
    from openpilot.starpilot.tandem.routing import config as C
    from openpilot.starpilot.tandem.routing.navigation import STATUS
    if not C.enabled():
      return
    status = self._nav_status
    now = time.monotonic()
    routing = routing_state(status, STATUS.read(max_age=60), STATUS.read(max_age=3), self._guided, now)
    snap.routing = routing_chip(routing, now, C.policy()[0])

  @staticmethod
  def _turn_chip(snap: Snapshot, now_ns: int, cruise_mps: float) -> None:
    """Slowing for turn while StarPilot's planner caps the set speed for the route's next turn, and the car is above it."""
    from openpilot.starpilot.navigation.intent import cruise_ceiling, current_instruction
    target = cruise_ceiling(ui_state.sm, ui_state.CP, now_ns, cruise_mps)
    nav = current_instruction(ui_state.sm, now_ns) if target is not None else None
    if target is not None and nav is not None and snap.speed > target + 0.5:
      snap.nav_turn = True
      snap.nav_turn_maneuver, snap.nav_turn_modifier = str(nav.instruction.maneuverType), str(nav.instruction.maneuverModifier)

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
    self._safely("help steer chime", lambda: self._signal_help_steer(help_steer))
    if now_ns - self._safe_at >= 1_000_000_000:
      self._safe_at = now_ns
      self._safe = bool(ui_state.params.get_bool("SafeMode"))
    allowed = self._writable(state, visible_alert)
    sm, cp, after = ui_state.sm, ui_state.CP, ui_state.started_frame
    car = display_message(sm, "carState", now_ns, after_frame=after)
    dm = display_message(sm, "driverMonitoringState", now_ns, after_frame=after)
    if ui_state.replay_clock is None:
      self._safely("compass", lambda: self._compass.update(ui_state, time.monotonic(), bool(state.reversing)))
    factor = CV.MS_TO_KPH if state.metric else CV.MS_TO_MPH
    cruise = displayed_speed(state.cruise_kph, 1.0 if state.metric else CV.KPH_TO_MPH)
    can_adjust = cruise is not None and allowed and not self._safe and cruise_action.ui_authority(sm, cp, now_ns)
    can_disengage = state.engaged and allowed and mode_actions.authority(sm, cp, now_ns, "disengage")
    posted = resolve_unified_speed(state).posted_text if state.appearance.show_speed_limit_sign else ""
    monitoring = None
    if dm is not None and str(dm.activePolicy) == "vision":
      monitoring = awareness(dm)
    snapshot = self._chips_from(now_ns, state)
    if ui_state.started and not ui_state.projection_read_only and ui_state.replay_clock is None:
      self._ram_log.drive(after, time.monotonic())
      if snapshot.low_ram and snapshot.memory_percent > self._ram.CLEAR:
        self._ram_log.note(after, snapshot.memory_percent)
    chips = self._chip_stack.update(snapshot, now_ns / 1e9, visible_alert is not None or help_steer)
    unit = "km/h" if state.metric else "mph"
    arrive, left = route_progress(state.navigation, bool(state.metric), datetime.datetime.now())
    navigating = state.navigation is not None or self._nav_status in ROUTE_ACTIVE
    self._display = DriveDisplay(
      bar=BarState(engaged=state.engaged, set_speed=cruise or 0.0, unit=unit, street=self._street(time.monotonic_ns()), heading=self._compass.heading(),
                   navigating=navigating, arrive=arrive, left=left, weather=None if navigating else self._weather_now(bool(state.metric)),
                   can_adjust=bool(can_adjust), can_disengage=bool(can_disengage)),
      speed=displayed_speed(state.speed_mps, factor), unit=unit, posted=posted,
      vienna=state.appearance.use_vienna_sign,
      left=bool(car is not None and car.canValid and not car.canTimeout and car.leftBlinker),
      right=bool(car is not None and car.canValid and not car.canTimeout and car.rightBlinker),
      monitor=monitoring, attention_warning=bool(visible_alert is not None and visible_alert.level == alerts.WARNING
                                                and "distract" in state.alert.alert_type.lower()),
      arc=arc, help_steer=help_steer, chips=tuple(chips), alert=visible_alert,
      proposal=limit_offer(state, allowed and not self._safe, now_ns),
      turn=turn(state.navigation, bool(state.metric)),
      model=self._model(state),
    )
    self._safely("pedals and border", lambda: self._extras(state, car, now_ns))
    self._safely("max follows limits", lambda: self._follow_limit(state, allowed and not self._safe))
    self._safely("lead tag", lambda: self._update_lead(state))
    self._dev = None
    if state.appearance.show_developer_sidebar:
      self._safely("developer view", lambda: setattr(self, "_dev", developer.read(sm, state, bool(state.metric))))
    return visible_alert is not None and visible_alert.level == alerts.CRITICAL

  LEAD_THRESHOLD = 0.35   # the model's confidence for a sure lead (release's Lead Detection Sensitivity default)

  def _update_lead(self, state: OnroadState) -> None:
    """The lead tag's state, and what StarPilot's renderer draws above its lead marker: our tag when it's on, otherwise
    StarPilot's Lead Info. The marker shows as on StarPilot's own screen."""
    now = time.monotonic()
    if now - self._lead_tag_read >= 1.0:   # Display › Driving Screen › Lead Car Tag
      self._lead_tag_on, self._lead_tag_read = LEAD_TAG.get(), now
    appearance = state.appearance
    mode = 1 if self._lead_tag_on else int(appearance.lead_info_mode)   # any mode but Off asks the renderer for the text
    self._lead_display = (True, mode, appearance.lead_info_metric)
    self._gap_state = self._gap_tracker.update(read_lead_sample(ui_state, self.LEAD_THRESHOLD), now)   # the tag, or the bar with it off

  def _extras(self, state: OnroadState, car: Any, now_ns: int) -> None:
    """StarPilot's pedal and border highlights, with its settings deciding when they show (onroad/extras.py)."""
    appearance = state.appearance
    pedals = self._pedals.update(state.wheel_acceleration, bool(appearance.wheel_pedal_feedback), now_ns, ui_state.started_frame)
    fresh = car is not None and car.canValid and not car.canTimeout
    border = extras.border_halves(bool(appearance.show_signal_border), bool(appearance.show_blindspot_border),
                                  bool(fresh and car.leftBlinker), bool(fresh and car.rightBlinker),
                                  bool(fresh and car.leftBlindspot), bool(fresh and car.rightBlindspot), now_ns / 1e9)
    self._display = replace(self._display, pedals=pedals, border=border)

  def _signal_help_steer(self, warning: bool) -> None:
    """Tell the sound daemon when Help steer appears (it chimes once) and when it goes away."""
    if warning == self._help_steer or ui_state.replay_clock is not None:
      return
    from openpilot.starpilot.tandem.state import HEADROOM
    HEADROOM.write(time.monotonic() if warning else 0.0)
    self._help_steer = warning

  def _safely(self, name: str, step: Callable[[], object]) -> None:
    """Run one of Tandem's driving-screen extras; a failure is logged once and skipped, never stopping the frame."""
    try:
      step()
    except Exception:
      if name not in self._failed:
        self._failed.add(name)
        cloudlog.exception(f"Tandem onroad: {name} failed")

  def _draw_lead_info(self, lead: Any, text: str) -> None:
    self._safely("lead tag", lambda: self._draw_lead_tag(lead, text))

  def _draw_lead_tag(self, lead: Any, text: str) -> None:
    """Above the lead marker: Tandem's tag, or StarPilot's own text when the tag is off."""
    if not self._lead_tag_on:
      self._stock_lead_info(lead, text)
      return
    state, anchor = self._gap_state, lead_anchor(lead.chevron)
    native = self._native
    if state is None or anchor is None or native is None:
      return
    developer.draw_lead_tag(anchor.x, anchor.y, state.lead, compact=not detailed_tag_on(native.appearance), value=state.label,
                            anchored=True, braking=self._braking_for_lead, opacity=state.opacity, progress=state.progress,
                            bounds=self._road, floor=self._tag_floor())

  def _draw_leads(self) -> None:
    self._safely("lead bars", self._draw_lead_bars)

  def _draw_lead_bars(self) -> None:
    """In place of StarPilot's red marker: the car you follow stays unobstructed under its tag, or gets the ground bar with
    the tag off (amber with Slowing for traffic, faded and settling in as the tag does). A second car ahead, and cars in
    the next lanes with Lead Insights or Developer View, keep faint bars without the outline."""
    renderer, native = self.model_renderer, self._native
    for i, lead in enumerate(renderer._lead_vehicles):
      rect = lead_bar_rect(lead.chevron)
      if rect is None:
        continue
      if i > 0:
        draw_lead_bar(rect, LEAD_INK, LEAD_FAINT, outline=False)
      elif not self._lead_tag_on:
        gap = self._gap_state
        draw_lead_bar(rect, LEAD_BRAKING_INK if self._braking_for_lead else LEAD_INK,
                      gap.opacity if gap is not None else 1.0, gap.progress if gap is not None else 1.0)
    if native is None or not detailed_tag_on(native.appearance) or ui_state.replay_clock is not None:
      return
    if self._radar_sm is None:
      self._radar_sm = messaging.SubMaster(["starpilotRadarState"])
    self._radar_sm.update(0)
    adjacent = current_message(self._radar_sm, "starpilotRadarState", native.observed_ns)
    for side in (adjacent.leadLeft, adjacent.leadRight) if adjacent is not None else ():
      rect = lead_bar_rect(adjacent_chevron(renderer, side) or [])
      if rect is not None:
        draw_lead_bar(rect, LEAD_INK, LEAD_FAINT, outline=False)

  def _strip_rect(self, inner: rl.Rectangle) -> rl.Rectangle | None:
    """Developer View's strip, just above the bar, when it has metrics to show."""
    if self._dev is None or not self._dev.strip:
      return None
    bottom = inner.y + inner.height - bar_margin() - bar_height() - developer.strip_gap()
    return rl.Rectangle(inner.x, bottom - developer.strip_h(), inner.width, developer.strip_h())

  def _tag_floor(self) -> float:
    """The lowest a lead tag may sit: above the metrics strip when it's shown, otherwise above the bar."""
    inner = self._road
    strip = self._strip_rect(inner)
    return (strip.y if strip is not None else inner.y + inner.height - bar_margin() - bar_height()) - developer.strip_gap()

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
    if self._dev is not None and not critical:   # Developer View's panel takes the right of the screen
      developer.draw_panel(rl.Rectangle(rect.x + rect.width - developer.WIDTH, rect.y, developer.WIDTH, rect.height), self._dev)
      rect = rl.Rectangle(rect.x, rect.y, rect.width - developer.WIDTH, rect.height)
    self._road = road_rect(rect)
    if not critical:
      inner = road_rect(rect)
      rl.begin_scissor_mode(int(inner.x), int(inner.y), int(inner.width), int(inner.height))
      try:
        # Display › Path Style is saved in StarPilot's large layout, which its own screen passes here too (runtime_app.py)
        self.render_camera_model_layer(inner, camera_view=int(state.appearance.camera_view),
                                       reverse_driver=state.reverse_driver_camera, poll_camera=poll_camera,
                                       road_style=state.customization["roadColors"]["large"],
                                       # it sets the renderer's lead display each frame: without it the tag is never asked for
                                       lead_display=self._lead_display)
        self._safely("turn signal", lambda: self._render_turn_signal(inner, state))
      finally:
        rl.end_scissor_mode()
    self._overlay.render(rect)
    strip = self._strip_rect(self._road)
    if strip is not None and self._dev is not None and self._display.alert is None and not self._display.help_steer:
      developer.draw_strip(strip, self._dev)

  def _render_turn_signal(self, inner: rl.Rectangle, state: OnroadState) -> None:
    """A Whimsy Turn Signal (Display › Theme) crosses the road above the bar while a blinker is on, hidden under an
    alert as on release; Standard is the chevrons in the speed pill alone."""
    now = time.monotonic()
    if now - self._signal_read_at >= 1.0:   # the choice changes only in settings
      self._signal_pack, self._signal_read_at = TURN_SIGNAL.get() or STANDARD, now
    shown = self._display.alert is None and not self._display.help_steer and not state.reversing
    car = display_message(ui_state.sm, "carState", state.observed_ns, after_frame=ui_state.started_frame) if shown else None
    self._turn_signals.render(inner, self._signal_pack, car, ui_state.started_frame,
                              bottom_margin=bar_height() + bar_margin() + SIGNAL_GAP)

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

  @cached_property
  def _places(self) -> StarPilotPlaces:
    return StarPilotPlaces(allowed=lambda: ui_state.replay_clock is None and not ui_state.projection_read_only,
                           metric=lambda: bool(ui_state.is_metric))

  def _where_to(self) -> None:
    """The bar's Where to? (without a route): the same screen as the parked card, over the driving view."""
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.selfdrive.ui.tandem.destinations import destinations_screen
    if self._can_act():
      gui_app.push_widget(destinations_screen(gui_app.pop_widget, places=self._places))

  def _end_route(self) -> None:
    """End route clears StarPilot's destination; its navigation process stops guiding."""
    if self._can_act() and self._display.bar.navigating:
      self._safely("end route", self._places.end_route)

  def _resolve(self, identity: LimitDecision, match: bool) -> None:
    proposal = self._display.proposal
    if not self._can_act() or proposal is None or proposal.identity != identity or ui_state.params.get_bool("SafeMode"):
      return
    kind = SlcActionKind.ACCEPT if match else SlcActionKind.REJECT
    self._limit_actions.dispatch(SlcUiRequest(kind, identity.session, identity.decision_id, identity.presentation_id, identity.candidate_mps))

  def _handle_mouse_press(self, mouse_pos: MousePos, /) -> None:
    """Only the menu tile opens the sidebar in the Essentials view."""

  def _handle_mouse_release(self, mouse_pos: MousePos, /) -> None:
    """A tap on the road closes the open sidebar, as the menu tile does; taps on the bar and cards stay theirs.

    The sidebar is open when MainLayout has moved this view right of it (its rect no longer starts at the screen's edge).
    """
    if self._rect.x > 0 and not self._overlay.on_control(mouse_pos.x, mouse_pos.y):
      self._menu()

  def hide_event(self) -> None:
    super().hide_event()
    self._turn_signals.close()
    self._gap_tracker.reset()
    self._gap_state = None
    self._display, self._native = DriveDisplay(), None
    self._prepared = False
    self._headroom.stage(0.0, 0.0, active=False)
    self._chip_stack = ChipStack()
    self._overlay.reset_controls()
