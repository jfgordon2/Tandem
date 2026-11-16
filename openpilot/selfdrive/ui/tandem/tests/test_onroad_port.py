"""The new onroad layout keeps safety alerts and native decision identities."""
from __future__ import annotations

import sys
from dataclasses import replace
from types import ModuleType
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem import screens, tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts, hud, size as Z
from openpilot.selfdrive.ui.tandem.onroad.bar import OnroadBar
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay
from openpilot.selfdrive.ui.tandem.onroad.state import BarState, Chip, DriveDisplay, DrivingAlert, LimitDecision, LimitOffer, RamWatch, displayed_speed
from openpilot.starpilot.ui.raylib import rl


def test_read_only_cruise_displays_set_speed_without_touch_controls() -> None:
  with_controls = BarState(engaged=True, adjust_speed=True, disengage=True, set_speed=63)
  state = with_controls
  bar = OnroadBar(lambda: state, Mock(), Mock(), Mock())
  rect = rl.Rectangle(0, 0, 2160, 1080)
  adjustable = bar.rects(rect)
  assert bar._minus.is_visible and bar._plus.is_visible and bar._wheel.enabled
  state = replace(with_controls, adjust_speed=False)
  read_only = bar.rects(rect)
  assert read_only[1].width < adjustable[1].width
  assert not bar._minus.is_visible and not bar._plus.is_visible
  assert bar._wheel.enabled
  state = BarState()
  assert not bar._wheel.enabled


def test_low_ram_advisory_waits_for_recovery_and_has_low_priority() -> None:
  monitor = RamWatch()
  assert monitor.update(False, 90) is None
  assert monitor.update(True, 91).label == "Low on RAM · 91% used"
  assert monitor.update(False, 87) is not None
  assert monitor.update(False, None) is not None
  assert monitor.update(False, 85) is None
  curve = Chip("curve", "Slowing for curve", "curve")
  ram = monitor.update(True, 91)
  assert ram is not None
  overlay = OnroadOverlay(lambda: DriveDisplay(chips=(curve, ram)), Mock(), Mock(), Mock(), Mock())
  try:
    Z.set_text(False)
    assert [chip.key for chip, _ in overlay._visible_chips()] == ["curve"]
    Z.set_text(True)
    assert [chip.key for chip, _ in overlay._visible_chips()] == ["ram", "curve"]
  finally:
    Z.set_text(False)


def test_new_limit_decision_replaces_touch_targets() -> None:
  current = LimitOffer(LimitDecision("test", 1, 1, 24.5), 55, 58, "mph", "map", 18, 30)
  resolve = Mock()
  overlay = OnroadOverlay(lambda: DriveDisplay(offer=current), Mock(), Mock(), Mock(), resolve)
  first = overlay._limit_card(current)
  assert first is not None
  assert overlay._limit_card(replace(current, seconds_left=16)) is first
  # The new proposal needs a new press. An old widget also keeps the old wire identity.
  newer = replace(current, identity=replace(current.identity, presentation_id=2))
  second = overlay._limit_card(newer)
  assert second is not None and second is not first and first not in overlay._children
  first._match._click_callback()
  resolve.assert_called_once_with(current.identity, True)
  assert overlay._limit_card(None) is None and second not in overlay._children


def test_critical_alert_preempts_every_driving_action(monkeypatch: pytest.MonkeyPatch) -> None:
  state = DriveDisplay(bar=BarState(True, True, True, 63), alert=DrivingAlert(alerts.CRITICAL, "Take control"))
  overlay = OnroadOverlay(lambda: state, Mock(), Mock(), Mock(), Mock())
  draw_alert, draw_speed, render_bar = Mock(), Mock(), Mock()
  monkeypatch.setattr(alerts, "draw_alert", draw_alert)
  monkeypatch.setattr(hud, "draw_speed", draw_speed)
  monkeypatch.setattr(overlay._bar, "render", render_bar)
  monkeypatch.setattr(overlay, "_limit_card", Mock())
  monkeypatch.setattr("openpilot.selfdrive.ui.tandem.draw.stroke", Mock())
  overlay._render(rl.Rectangle(0, 0, 2160, 1080))
  assert draw_alert.call_args.args[1:4] == (alerts.CRITICAL, "Take control", "")
  draw_speed.assert_not_called()
  render_bar.assert_not_called()
  overlay._limit_card.assert_called_once_with(None)


def test_recovery_switch_keeps_upstream_view(monkeypatch: pytest.MonkeyPatch) -> None:
  from openpilot.system.ui.widgets import Widget
  module = ModuleType("openpilot.selfdrive.ui.onroad.augmented_road_view")

  class StockView(Widget):
    """Stand-in for the device-only native camera view."""

    def _render(self, rect: rl.Rectangle) -> None:
      pass

  module.AugmentedRoadView = StockView
  monkeypatch.setitem(sys.modules, module.__name__, module)
  monkeypatch.setenv("TANDEM_ONROAD", "0")
  assert type(screens.onroad()) is StockView
  monkeypatch.setenv("TANDEM_ONROAD", "1")
  monkeypatch.setenv("STARPILOT_UI", "upstream")
  view = screens.onroad()
  assert type(view) is StockView
  assert not screens.onroad_requires_full_view(view)
  view.prepare_frame = Mock(return_value=True)
  assert screens.onroad_requires_full_view(view)


@pytest.mark.parametrize("speed", [None, float("nan"), float("inf"), -1])
def test_missing_speed_never_becomes_a_valid_value(speed: float | None) -> None:
  assert displayed_speed(speed, 2.24) is None


def test_mock_stage_dims_can_fit_standard_and_larger_max() -> None:
  rect = rl.Rectangle(0, 0, 2160 - T.px(288), 1080)
  bar = OnroadBar(lambda: BarState(True, True, True, 63, "County Road F31"), Mock(), Mock(), Mock())
  try:
    for larger in (False, True):
      Z.set_text(larger)
      menu, cruise, street, wheel = bar.rects(rect)
      assert 0 <= menu.x and menu.x + menu.width < cruise.x < street.x < wheel.x
      assert street.width >= T.px(250) and wheel.x + wheel.width <= rect.width
  finally:
    Z.set_text(False)


def test_steering_stroke_renders_both_caps_facing_the_camera(monkeypatch: pytest.MonkeyPatch) -> None:
  """The round ends stay visible with backface culling and extend outside the strip."""
  fan = Mock()
  monkeypatch.setattr(rl, "draw_triangle_strip", Mock())
  monkeypatch.setattr(rl, "draw_triangle_fan", fan)
  hud.draw_stroke([rl.Vector2(20, 25), rl.Vector2(60, 25)], 10, rl.WHITE)
  assert fan.call_count == 2
  for call, tip_x in zip(fan.call_args_list, (15, 65), strict=True):
    points, count, _ = call.args
    center, start, next_point = points[:3]
    assert count == len(points)
    assert points[9].x == pytest.approx(tip_x)
    assert points[9].y == pytest.approx(center.y)
    assert (start.x - center.x) * (next_point.y - center.y) - (start.y - center.y) * (next_point.x - center.x) < 0


def test_alert_or_change_in_authority_discards_a_pressed_bar() -> None:
  overlay = OnroadOverlay(lambda: DriveDisplay(), Mock(), Mock(), Mock(), Mock())
  overlay._sync_bar((True, True, True))
  first = overlay._bar
  overlay._sync_bar((True, True, True))
  assert overlay._bar is first
  overlay._sync_bar((True, False, True))
  assert overlay._bar is not first and first not in overlay._children
  active = overlay._bar
  overlay._sync_bar((False, False, False))
  assert overlay._bar is not active and active not in overlay._children
