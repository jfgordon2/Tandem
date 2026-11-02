"""The Essentials onroad view: StarPilot's view with the Essentials layers on top.

It subclasses StarPilotOnroadView and overrides only the parts Essentials replaces:
- the torque bar becomes the headroom arc, above the bar;
- the road name moves into the bar;
- the paused and weather badges beside the driver monitor become a status chip, bottom left above the bar;
- the current speed, the speed limit sign and the turn card are drawn in the Essentials style, with StarPilot still
  deciding when each shows; the speed pill carries Essentials' turn signal in place of StarPilot's animations;
- the driving personality button, the experimental-mode wheel, the favorites menu, the side-camera bubble and the stopped
  timer are removed;
- the driver monitor icon moves top right, drawn as an Essentials tile from upstream's driver state;
- alerts are drawn in the mock's three levels (info pill, warning card, critical takeover), with upstream still choosing them.
Everything else, from the camera and path to alerts, is upstream's.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable
import time

import pyray as rl

from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.ui.onroad.alert_renderer import AlertRenderer
from openpilot.selfdrive.ui.onroad.augmented_road_view import CAMERA_VIEW_DRIVER
from openpilot.selfdrive.ui.lib.starpilot_visuals import get_border_roundness
from openpilot.selfdrive.ui.onroad.starpilot import starpilot_border, starpilot_onroad_view
from openpilot.selfdrive.ui.onroad.starpilot.compass import get_compass_text
from openpilot.selfdrive.ui.tandem.onroad.streets import short_street, short_streets_in
from openpilot.selfdrive.ui.onroad.starpilot.starpilot_onroad_view import StarPilotOnroadView
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import MousePos
from openpilot.selfdrive.ui.onroad.starpilot.navigation_card import NavigationCardRenderer
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts, extras
from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_H, DevData, developer_view_on, draw_lead_tag, draw_strip, lead_of, read
from openpilot.selfdrive.ui.tandem.onroad.layers import (AT_LIMIT, BAR_HEIGHT, BAR_MARGIN, LIMIT_BORDER_COLOR, LIMIT_LANE_COLOR, ArcState, BarState,
                                                         Headroom, HeadroomArc, HelpSteer, ARC, DEV_ARC, LimitCard, LimitOffer, OnroadBar, StatusChip,
                                                         dm_tile, draw_driver_monitor, draw_speed, draw_speed_limit,
                                                         draw_turn_card, sign_tile, TURN_BELOW_SIGN, TURN_CARD_TOP)
from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, LimitWatch, chips_for, snapshot
from openpilot.selfdrive.ui.tandem.onroad.limits import LimitFollower, LimitOfferState, OfferChime
from openpilot.selfdrive.ui.tandem.onroad.lead import GapTracker, detailed_tag_on, lead_anchor, read_lead_sample
from openpilot.selfdrive.ui.tandem.forecast import Announcer, heads_up, now_conditions, shared_service, wall_clock
from openpilot.selfdrive.ui.tandem.prefs import MAX_FOLLOWS_LIMIT, WEATHER_CHIME, WEATHER_HEADS_UP

CONFIRM_TIMEOUT = 30.0      # StarPilot rejects an unanswered higher limit after 30 s
PREVIEW_SECONDS = 2.5
V_CRUISE_UNSET = 255


class EssentialsTurnCard(NavigationCardRenderer):
  """StarPilot's turn card, keeping its route data, drawn as the mock's card top left, below the speed limit sign or
  the new-limit card when one is showing. Taps do nothing: End route is in the bar."""

  def __init__(self, top: Callable[[], float]):
    super().__init__()
    self._top = top
    self.box: rl.Rectangle | None = None   # where it was drawn this frame, if it was

  def _render(self, rect: rl.Rectangle) -> None:
    self.box = None
    if not self._valid:
      return
    text = short_streets_in(" ".join(t for t in (self._primary_text, self._secondary_text) if t))
    self.box = draw_turn_card(rect, self._distance, text, self._maneuver_type, self._modifier, self._top())


class EssentialsAlertRenderer(AlertRenderer):
  """StarPilot's alert renderer, keeping its choice of alert, timing and fades, drawn in the mock's three levels."""

  headroom_warning: Callable[[], bool] = staticmethod(lambda: False)   # the view's Help steer warning is up
  limit_card: Callable[[], bool] = staticmethod(lambda: False)         # the new-limit card is asking

  def get_alert(self, sm):
    previous = self._prev_alert
    alert = super().get_alert(sm)
    if alert is not None and (alerts.shown_as_chip(alert.alert_type)
                              or (alerts.replaced_by_headroom(alert.alert_type) and self.headroom_warning())
                              or ((alert.alert_type or "").split("/", 1)[0] == alerts.LIMIT_ALERT and self.limit_card())):
      self._prev_alert = previous   # not shown, so nothing to fade out either; the status chip says it
      return None
    return alert

  def level(self) -> str | None:
    alert, _ = self.will_render()
    return alerts.level(alert.size, alert.status, alert.alert_type) if alert is not None else None

  def _get_alert_rect(self, rect: rl.Rectangle, size: int) -> rl.Rectangle:
    alert = self._current_alert or self._prev_alert
    kind = alerts.level(alert.size, alert.status, alert.alert_type) if alert is not None else alerts.REVERSE
    if kind == alerts.REVERSE:
      return super()._get_alert_rect(rect, size)
    return alerts.box(rect, kind, alert.text1, alert.text2)

  def _draw_background(self, alert) -> None:
    kind = alerts.level(alert.size, alert.status, alert.alert_type)
    if kind == alerts.REVERSE:
      return super()._draw_background(alert)
    where = rl.Rectangle(self._rect.x, self._alert_y_filter.x, self._rect.width, self._rect.height)   # slides as upstream's does
    alerts.draw_alert(where, kind, alert.text1, alert.text2, self._alpha_filter.x)

  def _draw_text(self, alert) -> None:
    if alerts.level(alert.size, alert.status, alert.alert_type) == alerts.REVERSE:
      super()._draw_text(alert)   # drawn with the background above otherwise


class _NoFavorites:
  """Stands in for StarPilot's favorites menu (the lower-left gesture), which Essentials doesn't show."""

  def process_mouse_events(self, events, rect) -> bool:
    return False

  def blocks_pointer(self, mouse_pos) -> bool:
    return False

  def render(self, rect) -> None:
    pass

  def render_corner_hint(self, rect) -> None:
    pass

  def collapse(self) -> None:
    pass


class _NoStoppedTimer:
  """Stands in for StarPilot's stopped timer, which Essentials doesn't show: the speed always stays."""
  replaces_current_speed = False
  is_visible = False

  def render(self, rect=None) -> None:
    pass


class EssentialsOnroadView(StarPilotOnroadView):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    zones = self.layout_manager.zones
    # StarPilot widgets Essentials replaces: the personality button, its driver monitor and steering wheel icons, and the
    # Aether Gauge (Conditional Experimental's "STOPPED"/"SLOW"/curve/light indicator), which the status chip says instead.
    # The pedal icons and the model-source badge are drawn by us (onroad/extras.py) in the Essentials style.
    for zone, widget in (("bottom", self._personality_button_widget), ("bottom", self._driver_monitor_widget),
                         ("right", self._steering_wheel_widget), ("left", self._aethergauge_widget), ("right", self._pedals_widget),
                         ("right_center", self._model_source_widget)):
      if widget in zones[zone]:
        zones[zone].remove(widget)
      widget.set_visible(False)
    self._model_chip = extras.ModelChip(self._model_source_widget)
    self.model_renderer._draw_radar_marker_texture = extras.draw_radar_marker   # white dots ringed in black
    # StarPilot's curve glow keeps its timing and fade; Essentials draws it in our blue at every curve strength.
    starpilot_border._glow_color = lambda intensity: T.ACCENT
    starpilot_border._TRAINING = T.ACCENT

    self._memory = Params(memory=True)
    self._memory.put_nonblocking("SteeringHeadroomWarning", 0.0)
    self._chips = ChipStack()
    self._forecast = shared_service()   # the parked screen shows the same forecast
    self._announcer = Announcer()
    self._limits = LimitWatch()
    self._chip_list: list = []   # (chip, opacity), nearest the bar first
    self._headroom = Headroom()
    self._arc_state = ArcState()
    self._headroom_warning = False
    self._headroom_chimed = False
    self._limit_offer = LimitOfferState()
    self._follower = LimitFollower()
    self._offer_chime = OfferChime()
    self._bar = OnroadBar(self._bar_state, self._open_menu, self._step_speed, self._toggle_engaged, self._end_route)
    self._chip_view = StatusChip(lambda: self._chip_list)
    self._arc = HeadroomArc(lambda: self._arc_state, lambda: DEV_ARC if self._dev is not None else ARC,   # each mock's curve
                            lambda: self._headroom_warning)
    self._help = HelpSteer()
    self._limit = LimitCard(self._offer, self._match_limit, self._ignore_limit)   # in the sign's place, top left
    # StarPilot's HUD keeps deciding when the speed and turn card show; they're drawn in the Essentials style.
    self._turn_card = EssentialsTurnCard(self._turn_top)
    self._hud_renderer._navigation_card = self._turn_card
    self._hud_renderer._draw_current_speed = self._draw_current_speed
    self._hud_renderer.draw_gradients = False   # no dark fade from the top or bottom edge: our tiles carry their own fills
    self._favorite_radial_menu = _NoFavorites()
    self._pip_sidecam.set_visible(False)   # the side-camera bubble: a Galaxy developer feature, and it would cover the bar
    self._stopped_timer_widget = _NoStoppedTimer()
    self.alert_renderer = EssentialsAlertRenderer()
    self.alert_renderer.headroom_warning = lambda: self._headroom_warning   # hides steerSaturated while Help steer shows
    self.alert_renderer.limit_card = lambda: self._offer() is not None      # hides Speed limit changed while the card asks
    self._layers_visible = False
    self._dev: DevData | None = None            # Developer View's readout, while StarPilot's Developer UI is on
    self.model_renderer._draw_lead_metrics = self._lead_tag   # Lead Insights' text becomes the mock's tag
    # The primary lead uses the shared developer tag with an anchor and connector (design/gaptag.html).
    self.model_renderer._draw_lead_indicator = self._draw_leads
    self.model_renderer._draw_adjacent_leads = self._draw_adjacent_leads
    self._gap_tracker = GapTracker()
    self._gap_state = None
    self._braking_for_lead = False   # the Slowing for traffic chip's rule, so the bar turns amber with it
    self._nav_sm = None

  # Upstream pieces replaced here

  def _draw_current_speed(self, rect: rl.Rectangle) -> None:
    sm = ui_state.sm
    car = sm["carState"] if sm.valid.get("carState", False) and sm.recv_frame["carState"] >= ui_state.started_frame else None
    left, right = (bool(car.leftBlinker), bool(car.rightBlinker)) if car is not None else (False, False)
    draw_speed(rect, self._hud_renderer.speed, "km/h" if ui_state.is_metric else "mph", self._hud_renderer.speed_offset_y,
               left, right, time.monotonic())

  def _render_turn_signals(self) -> None:
    """Essentials' turn signal is in the speed pill. A Whimsy animation (Display › Turn Signal) also crosses the road above
    the bar, drawn by StarPilot's renderer with its frames, timing and blind spot frame; hidden while an alert shows."""
    if ui_state.starpilot_toggles.get("signal_icons", "stock") not in extras.WHIMSY_SIGNALS:
      self._turn_signals.close()
      return
    c = self._content_rect
    rl.begin_scissor_mode(int(c.x), int(c.y), int(c.width), int(c.height))
    try:
      self._turn_signals.render(c, ui_state, enabled=self.alert_renderer.will_render()[0] is None,
                                bottom_margin=BAR_HEIGHT + BAR_MARGIN + extras.SIGNAL_GAP)
    finally:
      rl.end_scissor_mode()

  def _render_speed_card(self):
    """The posted limit StarPilot's speed card would show, as the mock's sign; hidden while the new-limit card asks."""
    if self._full_alert_showing() or self.alert_renderer.level() == alerts.CRITICAL:
      self._unified_speed_widget.collapse_sources()
      return
    limit = self._posted_limit()
    if limit is not None:
      draw_speed_limit(sign_tile(self._content_rect), limit, ui_state.ui_params.get_bool("UseVienna"), self._sign_note())

  def _turn_top(self) -> float:
    """The turn card stays below whatever holds the top left corner: the new-limit card while it asks, else the sign."""
    if self._offer() is not None:
      box = self._limit.box(self._content_rect)
      return box.y + box.height - self._content_rect.y + T.px(12)
    return TURN_BELOW_SIGN if self._posted_limit() is not None else TURN_CARD_TOP

  def _posted_limit(self) -> str | None:
    """The limit for the sign, or None when it's hidden: no limit known, or the new-limit card is asking."""
    widget = self._unified_speed_widget
    widget._refresh_snapshot()   # cached per frame
    limit = widget._presentation.posted_speed_text
    return None if limit in ("", "–") or self._offer() is not None else limit

  def _render_driver_monitor(self) -> None:
    """Upstream's driver state (its fades already hide it for alerts, stale data and the hide toggle), as our tile."""
    dm = self.driver_state_renderer
    dm._update_state()
    attentive = dm._color_fade_filter.update(0.0 if dm._awareness_unfull else 1.0)
    if not (ui_state.started and self._draw_hud_controls) or self.alert_renderer.will_render()[0] is not None:
      return
    draw_driver_monitor(dm_tile(self._content_rect), dm._fade_filter.x, attentive, dm.is_active)

  def _sign_note(self) -> str:
    """Developer View's line under the sign: where the limit came from and the offset ("MAP · +3")."""
    if self._dev is None or not self._dev.show_source or not ui_state.sm.valid.get("starpilotPlan", False):
      return ""
    plan = ui_state.sm["starpilotPlan"]
    offset = round(plan.slcSpeedLimitOffset * (CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH))
    return f"{self._dev.limit_source.upper()} · {offset:+d}".replace("-", "−")

  def _lead_tag(self, adjacent, chevron, lead_data) -> None:
    """Lead Insights for the lead car: our tag above it. Adjacent cars keep only StarPilot's markers, as in the mock."""
    if adjacent:
      return
    car = ui_state.sm["carState"]
    lead = lead_of(lead_data, car.vEgo, bool(ui_state.is_metric))
    if lead is not None:
      draw_lead_tag(chevron[1][0], min(p[1] for p in chevron), lead)

  def _draw_leads(self, radar_state) -> None:
    """The primary lead's gap tag; secondary leads keep their faint ground bars and optional metrics."""
    mr = self.model_renderer
    leads = [radar_state.leadOne, radar_state.leadTwo]
    for i, lead in enumerate(mr._lead_vehicles):
      if i == 0:
        state, anchor = self._gap_state, lead_anchor(lead.chevron)
        if state is not None and anchor is not None:
          draw_lead_tag(anchor.x, anchor.y, state.lead, compact=not detailed_tag_on(ui_state, mr._params), value=state.label,
                        anchored=True, braking=self._braking_for_lead, opacity=state.opacity, progress=state.progress,
                        bounds=self._content_rect)
        continue
      rect = extras.lead_bar_rect(lead.chevron)
      if rect is None:
        continue
      extras.draw_lead_bar(rect, extras.LEAD_INK, extras.LEAD_FAINT, outline=False)
      if mr._lead_info_enabled and i < len(leads) and leads[i] and leads[i].status:
        mr._draw_lead_metrics(False, lead.chevron, leads[i])

  def _draw_adjacent_leads(self) -> None:
    """Cars in the next lanes (Lead Insights): faint bars without the outline, so the car you follow stays the obvious one."""
    sm, mr = ui_state.sm, self.model_renderer
    if not sm.valid.get("starpilotRadarState", False):
      return
    state = sm["starpilotRadarState"]
    for idx, lead_data in enumerate((state.leadLeft, state.leadRight)):
      if not (lead_data and lead_data.status):
        continue
      rect = extras.lead_bar_rect(mr._adjacent_lead_vehicles[idx].chevron)
      if rect is not None:
        extras.draw_lead_bar(rect, extras.LEAD_INK, extras.LEAD_FAINT, outline=False)
      if mr._lead_info_enabled:
        mr._draw_lead_metrics(True, mr._adjacent_lead_vehicles[idx].chevron, lead_data)

  def _render_developer_metrics(self):
    """Developer View's readout, gathered here; StarPilot's device line moves to our panel and the controls to our strip."""
    self._dev = read(ui_state) if developer_view_on(ui_state, self._params) else None   # drawn as our strip, see _render

  def _render_road_name(self):
    pass

  def _render_bottom_row_widgets(self):
    pass

  def _render_torque_bar(self) -> None:
    self._arc.render(self._content_rect)
    if self._headroom_warning:
      self._help.render(self._content_rect)

  def _update_state(self) -> None:
    super()._update_state()
    self._update_gap_tag()
    self._update_headroom()

  def _update_gap_tag(self) -> None:
    # Update even on frames when upstream has no marker to draw, so losing a lead resets acquisition and smoothing.
    params = self.model_renderer._params
    threshold = params.get_int("LeadDetectionProbability") or params.get_int("LeadDetectionThreshold") or 50
    sample = read_lead_sample(ui_state, threshold / 100.0 if threshold > 1.0 else threshold)
    self._gap_state = self._gap_tracker.update(sample, time.monotonic())

  def _update_headroom(self) -> None:
    # Compute before the model and border draw, so all warning layers share this frame's state.
    sm = ui_state.sm
    fresh = all(sm.valid.get(service, False) and sm.alive.get(service, False)
                and sm.recv_frame[service] >= ui_state.started_frame
                for service in ("carControl", "carOutput", "controlsState", "carState", "selfdriveState"))
    active = bool(ui_state.started and fresh and sm["carControl"].latActive and not sm["carState"].steeringPressed
                  and not self.is_in_reverse() and self._camera_view() != CAMERA_VIEW_DRIVER)
    if active:
      self._torque_bar._update_state()   # upstream's estimate, including angle-controlled cars
    usage = float(self._torque_bar._torque_filter.x) if active else 0.0
    now = time.monotonic()
    stage = self._headroom.stage(usage, now, active)
    self._arc_state = ArcState(usage, self._preview() if active else 0.0, active, stage)
    # Other alerts, including their exit animation, keep visual priority. A steering-limit alert doesn't: Help steer is
    # the one prompt for it, whether our estimate or openpilot's saturation check reaches the limit first.
    showing = (self.alert_renderer.get_alert(sm), self.alert_renderer.will_render()[0])
    clear = all(a is None or alerts.replaced_by_headroom(a.alert_type) for a in showing)
    warning = active and (stage == AT_LIMIT or alerts.steer_limit_alert(sm)) and clear
    self.model_renderer.lane_line_color_override = LIMIT_LANE_COLOR if warning else None
    if warning and not self._headroom_chimed:
      self._memory.put_nonblocking("SteeringHeadroomWarning", now)
      self._headroom_chimed = True
    elif self._headroom_warning and not warning:
      self._memory.put_nonblocking("SteeringHeadroomWarning", 0.0)
    if not warning:
      self._headroom_chimed = False   # one chime per warning
    self._headroom_warning = warning

  def _get_border_color(self):
    if self._headroom_warning:
      return LIMIT_BORDER_COLOR
    return alerts.border(self.alert_renderer.level()) or super()._get_border_color()

  def hide_event(self):
    self._gap_tracker.reset()
    self._gap_state = None
    self._headroom.stage(0.0, time.monotonic(), active=False)
    self._arc_state = ArcState()
    self._headroom_warning = self._headroom_chimed = False
    self.model_renderer.lane_line_color_override = None
    self._memory.put_nonblocking("SteeringHeadroomWarning", 0.0)
    super().hide_event()

  # Our layers

  def _render(self, rect: rl.Rectangle):
    self._layers_visible = False   # set again by _render_layers, from _draw_border, on frames that draw the view
    super()._render(rect)
    self._render_driver_monitor()

  def _draw_border(self, rect: rl.Rectangle):
    # Our layers go under the border, as the camera does, so its rounded inner corners stay round at the bottom too.
    rl.begin_scissor_mode(int(self._content_rect.x), int(self._content_rect.y), int(self._content_rect.width),
                          int(self._content_rect.height))
    self._render_layers()
    rl.end_scissor_mode()
    # StarPilot's border, its overlay effects, and our signal and blind-spot halves (its steering-torque fill is left out:
    # the steering arc says the same).
    border_width = self._get_border_width()
    rl.draw_rectangle_lines_ex(rect, border_width, rl.BLACK)
    border_rect = rl.Rectangle(rect.x + border_width, rect.y + border_width, rect.width - 2 * border_width, rect.height - 2 * border_width)
    roundness = get_border_roundness(border_rect, border_width)
    rl.draw_rectangle_rounded_lines_ex(border_rect, roundness, 10, border_width, self._get_border_color())
    halves = self._border_halves()
    if halves is not None:
      extras.draw_border_halves(rect, border_rect, roundness, border_width, halves)
    starpilot_onroad_view.render_overlay(border_rect, border_width)

  def _border_halves(self):
    """The signal and blind-spot halves, under StarPilot's SignalMetrics and BlindSpotMetrics. Alerts and Help steer keep the
    whole border."""
    params = getattr(ui_state, "ui_params", None)
    if params is None or self._headroom_warning or alerts.border(self.alert_renderer.level()) is not None:
      return None
    signal_on, blind_on = params.get_bool("SignalMetrics"), params.get_bool("BlindSpotMetrics")
    if not (signal_on or blind_on) or not ui_state.sm.valid.get("carState", False):
      return None
    car = ui_state.sm["carState"]
    left_blind, right_blind = bool(car.leftBlindspot), bool(car.rightBlindspot)
    if ui_state.starpilot_toggles.get("v_asm_enabled", False):
      from openpilot.starpilot.common.vision_bsm import get_fresh_vasm_state
      vasm_left, vasm_right = get_fresh_vasm_state(ui_state.params_memory)
      left_blind, right_blind = left_blind or vasm_left, right_blind or vasm_right
    return extras.border_halves(signal_on, blind_on, bool(car.leftBlinker), bool(car.rightBlinker), left_blind, right_blind, rl.get_time())

  def _render_extra_road_overlays(self, rect: rl.Rectangle) -> None:
    """StarPilot's path extras in our colors: path edges, adjacent lanes and blind spots, the stopping point, then the curve
    glow under the HUD."""
    mr = self.model_renderer
    if mr._path.projected_points.size:
      if mr._path_edge_width > 0.0 and mr._track_edge_vertices.size >= 4:
        extras.draw_path_edges(mr._rect, mr._track_edge_vertices, mr._path.projected_points)
      extras.draw_lanes(mr._rect, self._lane_sides())
      self._render_stopping_point()
    starpilot_onroad_view.render_behind(rect, self._get_border_width())

  def _lane_sides(self):
    """(polygon, kind) for each adjacent lane, under StarPilot's AdjacentPath and BlindSpotPath."""
    mr, params, sm = self.model_renderer, self.model_renderer._params, ui_state.sm
    adjacent, blind_spot = params.get_bool("AdjacentPath"), params.get_bool("BlindSpotPath")
    vertices = mr._adjacent_path_vertices
    if not (adjacent or blind_spot) or not vertices or len(vertices) < 2:
      return []
    blind = [False, False]
    if blind_spot and sm.recv_frame["carState"] >= ui_state.started_frame:
      blind = [bool(sm["carState"].leftBlindspot), bool(sm["carState"].rightBlindspot)]
      if ui_state.starpilot_toggles.get("v_asm_enabled", False):
        from openpilot.starpilot.common.vision_bsm import get_fresh_vasm_state
        blind = [a or b for a, b in zip(blind, get_fresh_vasm_state(ui_state.params_memory), strict=True)]
    widths = [0.0, 0.0]
    if adjacent and sm.recv_frame["starpilotPlan"] >= ui_state.started_frame:
      widths = [float(sm["starpilotPlan"].laneWidthLeft), float(sm["starpilotPlan"].laneWidthRight)]
    return [(vertices[i], "blind_spot" if blind[i] else ("lane" if adjacent and widths[i] > 0.0 else None)) for i in range(2)]

  def _render_stopping_point(self) -> None:
    params, sm = ui_state.ui_params, ui_state.sm
    if not params.get_bool("ShowStoppingPoint") or not sm.valid.get("starpilotPlan", False) or not sm["starpilotPlan"].redLight:
      return
    ends = extras.path_end(self.model_renderer._path.projected_points)
    if ends is None:
      return
    distance = 0.0 if sm.valid.get("carState", False) and sm["carState"].standstill else float(sm["starpilotPlan"].forcingStopLength)
    label = extras.stop_text(distance, bool(ui_state.is_metric)) if params.get_bool("ShowStoppingPointMetrics") else None
    extras.draw_stopping_point(ends, label)

  def _render_layers(self) -> None:
    offer = self._offer()   # observe limit changes even when an alert is covering the card
    self._chime_for(offer)
    self._follow_limit()
    alert, _ = self.alert_renderer.will_render()
    # Help steer is a Warning alert drawn by us: like StarPilot's alerts, it takes the bar's place at the bottom.
    self._layers_visible = bool(ui_state.started and self._draw_hud_controls and alert is None and not self._headroom_warning)
    now = time.monotonic()
    current = snapshot(ui_state, self._navigating(), self._limits, now)
    self._apply_forecast(current)
    self._braking_for_lead = any(chip.key == "traffic" for chip in chips_for(current))
    self._chip_list = self._chips.update(current, now, alert is not None or self._headroom_warning)
    if not self._layers_visible:
      return
    c = self._content_rect
    self._render_corner_extras(c)
    lift = 0.0
    if self._dev is not None and self._dev.strip:   # the picked metrics, just above the bar; the chip moves up over it
      lift = STRIP_H + T.px(6)
      draw_strip(rl.Rectangle(c.x, c.y + c.height - BAR_MARGIN - BAR_HEIGHT - lift, c.width, STRIP_H), self._dev)
    self._chip_view.render(rl.Rectangle(c.x, c.y, c.width, c.height - lift))
    self._limit.render(c)
    self._bar.render(c)

  def _render_corner_extras(self, c: rl.Rectangle) -> None:
    """Under the driver monitor tile: the pedal tiles (Lead Insights), then the external-GPU model chip."""
    tile = dm_tile(c)
    y = tile.y + tile.height + T.px(10)
    car = ui_state.sm["carState"] if ui_state.sm.valid.get("carState", False) else None
    sp_car = ui_state.sm["starpilotCarState"] if ui_state.sm.valid.get("starpilotCarState", False) else None
    levels = extras.pedal_levels(ui_state.ui_params, car, sp_car)
    if levels is not None:
      y = extras.draw_pedals(tile, levels)
    self._model_chip.render(tile.x + tile.width, y)

  def _handle_mouse_press(self, mouse_pos: MousePos):
    # Taps on our layers stay ours; anywhere else keeps upstream's behavior (toggling the sidebar).
    if self._layers_visible:
      hits = self._bar.hit_rects(self._content_rect)
      if self._offer() is not None:
        hits.append(self._limit.box(self._content_rect))
      if any(rl.check_collision_point_rec(mouse_pos, r) for r in hits):
        return
    super()._handle_mouse_press(mouse_pos)

  # State

  def _navigating(self) -> bool:
    return bool(self._params.get("NavDestination"))

  def _bar_state(self) -> BarState:
    metric = bool(ui_state.is_metric)
    conversion = 1.0 if metric else CV.KPH_TO_MPH
    set_speed = 0.0
    if ui_state.sm.valid.get("carState", False):
      v_cruise = float(ui_state.sm["carState"].vCruiseCluster)
      if 0 < v_cruise < V_CRUISE_UNSET:
        set_speed = v_cruise * conversion
    street = ""
    if ui_state.sm.valid.get("mapdOut", False):
      street = short_street(str(ui_state.sm["mapdOut"].roadName or ""))
    navigating = self._navigating()
    arrive, left = self._route_progress(metric) if navigating else ("", "")
    return BarState(engaged=bool(ui_state.engaged), can_engage=bool(ui_state.started), set_speed=set_speed,
                    unit="km/h" if metric else "mph", street=street, navigating=navigating, arrive=arrive, left=left,
                    heading=extras.heading(get_compass_text()), weather=None if navigating else self._weather_now(metric))

  def _weather_now(self, metric: bool) -> tuple[str, str] | None:
    """The forecast's current hour for the bar, without a route (Weather heads-up's forecast, General › Temperature)."""
    if not WEATHER_HEADS_UP.get():
      return None
    from openpilot.selfdrive.ui.tandem.prefs import celsius
    return now_conditions(self._forecast.forecast, wall_clock(), celsius(metric))

  def _route_progress(self, metric: bool) -> tuple[str, str]:
    """Arrival time and what's left, from navInstruction. ui_state doesn't subscribe to it, so this view does."""
    if self._nav_sm is None:
      import cereal.messaging as messaging
      self._nav_sm = messaging.SubMaster(["navInstruction"])
    self._nav_sm.update(0)
    if not self._nav_sm.valid.get("navInstruction", False):
      return "", ""
    nav = self._nav_sm["navInstruction"]
    seconds, meters = float(nav.timeRemaining), float(nav.distanceRemaining)
    arrive = (datetime.datetime.now() + datetime.timedelta(seconds=seconds)).strftime("%-I:%M %p")
    distance = f"{meters / 1000:.1f} km" if metric else f"{meters / 1609.344:.1f} mi"
    return arrive, f"{max(1, round(seconds / 60))} min · {distance}"

  def _preview(self) -> float:
    """Lateral acceleration the planned path needs PREVIEW_SECONDS ahead, as a share of the car's maximum."""
    if not ui_state.sm.valid.get("modelV2", False) or not ui_state.sm.valid.get("carState", False):
      return 0.0
    model = ui_state.sm["modelV2"]
    times, yaw_rates = list(model.orientationRate.t), list(model.orientationRate.z)
    if not times:
      return 0.0
    index = min(range(len(times)), key=lambda i: abs(times[i] - PREVIEW_SECONDS))
    max_lat = ui_state.CP.maxLateralAccel if ui_state.CP and ui_state.CP.maxLateralAccel else 3.0
    return float(yaw_rates[index]) * float(ui_state.sm["carState"].vEgo) / max_lat

  def _apply_forecast(self, current) -> None:
    """Weather heads-up (forecast.py): its chip from 15 minutes before rain, snow or storms until they end, and one soft
    chime (the pre-alert, as the new-limit card uses) when an event is first seen within the hour."""
    self._forecast.tick()
    if not WEATHER_HEADS_UP.get():
      return
    wall = wall_clock()
    hint = heads_up(self._forecast.forecast, wall)
    show, chime = self._announcer.update(hint, wall)
    if chime and ui_state.started and WEATHER_CHIME.get():   # Alerts › Chimes › Weather heads-up
      self._memory.put_nonblocking("TestAlert", "preAlert")
    if show and hint is not None:
      current.forecast, current.forecast_active = (hint.text, hint.icon), hint.active

  def _chime_for(self, offer: LimitOffer | None) -> None:
    """The pre-alert chime as a new-limit card appears, through soundd's TestAlert (as StarPilot's sound previews play
    onroad). Skipped when StarPilot's own Speed limit changed chime is on, which already sounds for the change."""
    identity = None if offer is None else (round(offer.limit), self._limit_offer.since)
    if self._offer_chime.update(identity) and not ui_state.ui_params.get_bool("SpeedLimitChangedAlert"):
      self._memory.put_nonblocking("TestAlert", "preAlert")

  def _follow_limit(self) -> None:
    """MAX follows each limit StarPilot adopts (limits.LimitFollower), through the same request the bar's − and + use."""
    sm = ui_state.sm
    if not (sm.valid.get("starpilotPlan", False) and sm.valid.get("carState", False)):
      return
    plan = sm["starpilotPlan"]
    v_cruise = float(sm["carState"].vCruiseCluster)
    set_speed = v_cruise * CV.KPH_TO_MS if 0 < v_cruise < V_CRUISE_UNSET else 0.0
    target = self._follower.update(float(plan.slcSpeedLimit), str(plan.slcSpeedLimitSource), float(plan.slcSpeedLimitOffset),
                                   set_speed, bool(ui_state.engaged))
    if target is not None and MAX_FOLLOWS_LIMIT.get():
      self._memory.put_float("SLCForceCruiseSpeed", target)

  def _offer(self) -> LimitOffer | None:
    if not ui_state.sm.valid.get("starpilotPlan", False):
      return None
    plan = ui_state.sm["starpilotPlan"]
    now = time.monotonic()
    pending_ms = float(plan.unconfirmedSlcSpeedLimit) if plan.speedLimitChanged else 0.0
    self._limit_offer.observe(pending_ms, float(plan.slcSpeedLimit), str(plan.slcSpeedLimitSource), now)
    conversion = CV.MS_TO_KPH if ui_state.is_metric else CV.MS_TO_MPH
    pending = pending_ms * conversion
    current = float(plan.slcSpeedLimit) * conversion
    since = self._limit_offer.since
    if since is None or not (plan.speedLimitChanged and abs(pending - current) > 0.5) or self._limit_offer.ignored:
      return None
    # Lower or higher than the limit in use: the last one StarPilot adopted, as it compares (its target can lag).
    adopted = self._follower.limit * conversion if self._follower.limit > 1 else current
    offset = float(plan.slcSpeedLimitOffset) * conversion
    return LimitOffer(pending, pending + offset, "km/h" if ui_state.is_metric else "mph",
                      str(plan.slcPresentedSpeedLimitSource or plan.slcSpeedLimitSource or "map"),
                      CONFIRM_TIMEOUT - (now - since), CONFIRM_TIMEOUT, ui_state.ui_params.get_bool("UseVienna"),
                      lower=pending < adopted)

  def _offroad_transition(self) -> None:
    super()._offroad_transition()
    self._limit_offer = LimitOfferState()
    self._limits = LimitWatch()
    self._follower = LimitFollower()
    self._offer_chime = OfferChime()

  # Actions

  def _open_menu(self) -> None:
    if self._click_callback is not None:
      self._click_callback()

  def _step_speed(self, direction: int) -> None:
    from openpilot.starpilot.system.wheel_controls.wheel_controlsd import set_controller_cruise_speed
    state = self._bar_state()
    step = max(1.0, self._params.get_float("CustomCruise") or 1.0)
    target = (round(state.set_speed / step) + direction) * step
    set_controller_cruise_speed(target, self._params, self._memory)

  def _toggle_engaged(self) -> None:
    from openpilot.starpilot.common.controller_actions import CONTROLLER_ACTION_DISENGAGE, CONTROLLER_ACTION_ENGAGE
    from openpilot.starpilot.system.wheel_controls.wheel_controlsd import trigger_controller_action
    trigger_controller_action(CONTROLLER_ACTION_DISENGAGE if ui_state.engaged else CONTROLLER_ACTION_ENGAGE, self._memory)

  def _end_route(self) -> None:
    self._params.remove("NavDestination")
    self._memory.remove("NavInstructionState")

  def _match_limit(self) -> None:
    self._memory.put_bool("SpeedLimitAccepted", True)

  def _ignore_limit(self) -> None:
    offer = self._offer()
    if offer is not None:
      self._limit_offer.ignore()
