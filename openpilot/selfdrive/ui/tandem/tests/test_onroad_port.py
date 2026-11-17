"""The driving screen on StarPilot 7: release's layers, fed by StarPilot's alerts, permissions and decision identities."""
from __future__ import annotations

import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem import screens, tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts, layers, size as Z
from openpilot.selfdrive.ui.tandem.onroad.binding import driving_alert, lane_change, proposal
from openpilot.selfdrive.ui.tandem.onroad.layers import BarState, LimitOffer, OnroadBar
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay, border_color
from openpilot.selfdrive.ui.tandem.onroad.state import DriveDisplay, DrivingAlert, LimitDecision, Proposal, displayed_speed
from openpilot.selfdrive.ui.tandem.onroad.status import Chip, ChipStack, ChipTone, RamWatch, Snapshot
from openpilot.starpilot.ui.raylib import rl


def _bar(state: BarState) -> OnroadBar:
  return OnroadBar(lambda: state, Mock(), Mock(), Mock(), Mock())


def test_cruise_and_disengage_controls_follow_starpilots_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
  """MAX − / + work only where StarPilot 7 accepts them from the screen (not on the car's own cruise); the wheel only
  disengages, and only with its permission. The screen can't engage on StarPilot 7."""
  from openpilot.selfdrive.ui.tandem import draw
  from openpilot.selfdrive.ui.tandem.controls import Button
  for name in ("fill", "text"):   # no window in tests: lay the bar out without drawing it
    monkeypatch.setattr(draw, name, Mock(return_value=0))
  monkeypatch.setattr(Button, "render", Mock())
  for can_adjust in (True, False):
    bar = _bar(BarState(engaged=True, set_speed=63, can_adjust=can_adjust))
    assert bar._minus.enabled is can_adjust and bar._plus.enabled is can_adjust
  for engaged, can_disengage, enabled in ((True, True, True), (True, False, False), (False, True, False)):
    bar = _bar(BarState(engaged=engaged, set_speed=63, can_disengage=can_disengage))
    bar._render(rl.Rectangle(0, 0, 2160, 1080))
    assert bar._engage.enabled is enabled


def test_low_ram_holds_until_recovery_and_gives_way_first() -> None:
  ram = RamWatch()
  assert not ram.update(False, 90)
  assert ram.update(True, 91) and ram.update(False, 87)
  assert not ram.update(False, 85)
  stack = ChipStack()
  chips = stack.update(Snapshot(curve_control=True, events={"lowMemory"}, memory_percent=91), 0.0, False)
  low = next(chip for chip, _ in chips if chip.key == "low_memory")
  assert low.label == "Low on RAM · 91% used" and low.tone == ChipTone.ALERT
  assert [chip.key for chip, _ in sorted(chips, key=lambda c: c[0].key != "curve")][0] == "curve"


def test_a_new_decision_needs_a_new_card_and_answers_only_its_own() -> None:
  offer = LimitOffer(55, 58, "mph", "map", 18, 30)
  current = Proposal(LimitDecision("test", 1, 1, 24.5), offer)
  shown = [current]
  resolve = Mock()
  overlay = OnroadOverlay(lambda: DriveDisplay(proposal=shown[0]), Mock(), Mock(), Mock(), resolve)
  first = overlay._limit_card(current)
  assert first is not None
  assert overlay._limit_card(replace(current, offer=replace(offer, seconds_left=16))) is first
  newer = Proposal(replace(current.identity, presentation_id=2), offer)
  shown[0] = newer
  second = overlay._limit_card(newer)
  assert second is not None and second is not first and first not in overlay._children
  assert first._offer() is None              # the old card no longer shows the new decision's offer
  first._match._click_callback()
  resolve.assert_called_once_with(current.identity, True)
  assert overlay._limit_card(None) is None and second not in overlay._children


def test_critical_alert_preempts_every_driving_action(monkeypatch: pytest.MonkeyPatch) -> None:
  state = DriveDisplay(bar=BarState(engaged=True, set_speed=63), alert=DrivingAlert(alerts.CRITICAL, "Take control"))
  overlay = OnroadOverlay(lambda: state, Mock(), Mock(), Mock(), Mock())
  draw_alert, draw_speed, render_bar = Mock(), Mock(), Mock()
  monkeypatch.setattr(alerts, "draw_alert", draw_alert)
  monkeypatch.setattr(layers, "draw_speed", draw_speed)
  monkeypatch.setattr(overlay._bar, "render", render_bar)
  monkeypatch.setattr(overlay, "_limit_card", Mock())
  monkeypatch.setattr("openpilot.selfdrive.ui.tandem.draw.stroke", Mock())
  overlay._render(rl.Rectangle(0, 0, 2160, 1080))
  assert draw_alert.call_args.args[1:4] == (alerts.CRITICAL, "Take control", "")
  draw_speed.assert_not_called()
  render_bar.assert_not_called()
  overlay._limit_card.assert_called_once_with(None)


def test_help_steer_takes_the_bars_place_and_the_border(monkeypatch: pytest.MonkeyPatch) -> None:
  state = DriveDisplay(bar=BarState(engaged=True, set_speed=63), arc=layers.ArcState(0.9, 0.0, True, layers.AT_LIMIT), help_steer=True)
  overlay = OnroadOverlay(lambda: state, Mock(), Mock(), Mock(), Mock())
  help_render, bar_render = Mock(), Mock()
  for name in ("draw_speed", "draw_driver_monitor"):   # no window in tests
    monkeypatch.setattr(layers, name, Mock())
  monkeypatch.setattr("openpilot.selfdrive.ui.tandem.draw.stroke", Mock())
  monkeypatch.setattr(overlay._arc, "render", Mock())
  monkeypatch.setattr(overlay._help, "render", help_render)
  monkeypatch.setattr(overlay._bar, "render", bar_render)
  overlay._render(rl.Rectangle(0, 0, 2160, 1080))
  help_render.assert_called_once()
  bar_render.assert_not_called()
  assert border_color(state) == layers.LIMIT_BORDER_COLOR
  assert border_color(DriveDisplay(bar=BarState(engaged=True))) == T.SUCCESS


def test_recovery_switch_keeps_upstream_view(monkeypatch: pytest.MonkeyPatch) -> None:
  from openpilot.system.ui.widgets import Widget
  module = ModuleType("openpilot.selfdrive.ui.onroad.augmented_road_view")

  class StockView(Widget):
    """Stand-in for the device-only native camera view."""

    def _render(self, rect: rl.Rectangle) -> None:
      pass

  module.AugmentedRoadView = StockView  # type: ignore[attr-defined]
  monkeypatch.setitem(sys.modules, module.__name__, module)
  monkeypatch.setenv("TANDEM_ONROAD", "0")
  assert type(screens.onroad()) is StockView
  monkeypatch.setenv("TANDEM_ONROAD", "1")
  monkeypatch.setenv("STARPILOT_UI", "upstream")
  view = screens.onroad()
  assert type(view) is StockView
  # MainLayout reads requires_full_view from the view's class, so openpilot's view (or a test's Mock) is left alone.
  assert getattr(type(view), "requires_full_view", None) is None
  import ast
  from pathlib import Path
  source = ast.parse((Path(__file__).resolve().parents[1] / "onroad/view.py").read_text())   # device-only imports: read, don't import
  view_class = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "EssentialsOnroad")
  assert any(isinstance(n, ast.FunctionDef) and n.name == "requires_full_view" for n in view_class.body)


@pytest.mark.parametrize("speed", [None, float("nan"), float("inf"), -1])
def test_missing_speed_never_becomes_a_valid_value(speed: float | None) -> None:
  assert displayed_speed(speed, 2.24) is None


def test_the_bar_fits_beside_the_open_sidebar_at_both_text_sizes() -> None:
  rect = rl.Rectangle(0, 0, 2160 - T.px(288), 1080)
  bar = _bar(BarState(engaged=True, set_speed=63, street="County Road F31"))
  try:
    for larger in (False, True):
      Z.set_text(larger)
      r = bar.rects(rect)
      menu, speed, center, engage = r["menu"], r["speed"], r["center"], r["engage"]
      assert 0 <= menu.x and menu.x + menu.width < speed.x < center.x < engage.x
      assert center.width >= T.px(250) and engage.x + engage.width <= rect.width
      assert "where" not in r                    # no destinations on StarPilot 7 yet
  finally:
    Z.set_text(False)


def test_steering_stroke_renders_both_caps_facing_the_camera(monkeypatch: pytest.MonkeyPatch) -> None:
  """raylib 6 has no circle sectors: the round ends are fans that stay visible with backface culling."""
  fan = Mock()
  monkeypatch.setattr(rl, "draw_triangle_strip", Mock())
  monkeypatch.setattr(rl, "draw_triangle_fan", fan)
  layers.draw_stroke([rl.Vector2(20, 25), rl.Vector2(60, 25)], 10, rl.WHITE)
  assert fan.call_count == 2
  for call, tip_x in zip(fan.call_args_list, (15, 65), strict=True):
    points, count, _ = call.args
    center, start, next_point = points[:3]
    assert count == len(points)
    assert points[9].x == pytest.approx(tip_x)
    assert points[9].y == pytest.approx(center.y)
    assert (start.x - center.x) * (next_point.y - center.y) - (start.y - center.y) * (next_point.x - center.x) < 0


def test_alert_or_change_in_permissions_discards_a_pressed_bar() -> None:
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


def _alert(alert_type: str, size: str = "small", critical: bool = False, user_prompt: bool = False) -> SimpleNamespace:
  return SimpleNamespace(size=size, text1="Title", text2="Detail", critical=critical, alert_type=alert_type, user_prompt=user_prompt)


def test_alerts_keep_starpilots_choice_in_the_mocks_levels() -> None:
  assert driving_alert(_alert("x"), None) == DrivingAlert(alerts.INFO, "Title", "Detail")
  assert driving_alert(_alert("x", size="none"), None) is None
  assert driving_alert(_alert("x", user_prompt=True), None).level == alerts.WARNING
  assert driving_alert(_alert("x", size="full"), None).level == alerts.CRITICAL
  assert driving_alert(_alert("x", critical=True), None).level == alerts.CRITICAL
  timeout = SimpleNamespace(status=2, size=3, text1="TAKE CONTROL IMMEDIATELY", text2="")
  assert driving_alert(_alert("", size="none"), timeout).level == alerts.CRITICAL   # before the first coherent snapshot


def test_chip_alerts_and_steering_limits_give_way_but_critical_ones_never_do() -> None:
  assert driving_alert(_alert("greenLight/warning"), None) is None                   # the chip says it
  assert driving_alert(_alert("lowMemory/permanent"), None) is None
  assert driving_alert(_alert("lowMemory/noEntry", user_prompt=True), None) is not None
  saturated = _alert("steerSaturated/warning", user_prompt=True)
  assert driving_alert(saturated, None, help_steer=False).level == alerts.WARNING
  assert driving_alert(saturated, None, help_steer=True) is None                   # Help steer says it
  assert driving_alert(_alert("greenLight/warning", critical=True), None).level == alerts.CRITICAL


def _observation(**changes: object) -> SimpleNamespace:
  now = 100_000_000_000
  base = {"session_id": "s", "decision_id": 4, "presentation_id": 2, "pending_speed_limit_mps": 55 / 2.236936,
              "pending_adjusted_limit_mps": 58 / 2.236936, "accepted_speed_limit_mps": 45 / 2.236936, "accepted_adjusted_limit_mps": 48 / 2.236936,
              "pending_source": "map", "pending_since_ns": now - 12_000_000_000}
  base.update(changes)
  return SimpleNamespace(**base)


def test_new_limit_offer_keeps_releases_wording_and_starpilots_identity() -> None:
  now = 100_000_000_000
  higher = proposal(_observation(), False, False, now)
  assert higher is not None and higher.identity == LimitDecision("s", 4, 2, 55 / 2.236936)
  assert round(higher.offer.limit) == 55 and round(higher.offer.target) == 58 and higher.offer.unit == "mph"
  assert not higher.offer.lower and higher.offer.source == "map" and 0 < higher.offer.seconds_left < higher.offer.total
  lower = proposal(_observation(pending_speed_limit_mps=35 / 2.236936, pending_adjusted_limit_mps=38 / 2.236936), False, False, now)
  assert lower is not None and lower.offer.lower                                    # "Slow down to 38 mph?"
  assert proposal(_observation(pending_adjusted_limit_mps=None), False, False, now).offer.target == pytest.approx(55, abs=0.01)
  assert proposal(_observation(decision_id=None), False, False, now) is None
  assert proposal(_observation(pending_since_ns=now - 60_000_000_000), False, False, now) is None   # expired


def test_lane_change_reads_the_models_meta() -> None:
  meta = SimpleNamespace(laneChangeState=SimpleNamespace(raw=2), laneChangeDirection=SimpleNamespace(raw=1))
  assert lane_change(meta) == ("starting", "left")
  idle = SimpleNamespace(laneChangeState=SimpleNamespace(raw=0), laneChangeDirection=SimpleNamespace(raw=0))
  assert lane_change(idle) == ("off", "none")


def test_chips_come_from_releases_rules() -> None:
  chips = ChipStack().update(Snapshot(engaged=True, standstill=True, waiting_for_resume=True), 0.0, False)
  assert [chip.key for chip, _ in chips] == ["ready"]
  assert Chip("x", "y", ChipTone.INFO, "z").tone == ChipTone.INFO
