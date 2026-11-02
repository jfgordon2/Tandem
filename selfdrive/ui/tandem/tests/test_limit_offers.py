from types import SimpleNamespace

import pytest
from cereal import custom

from openpilot.common.constants import CV
from openpilot.selfdrive.ui.onroad.alert_renderer import Alert
from openpilot.selfdrive.ui.tandem.onroad import view as onroad
from openpilot.selfdrive.ui.tandem.forecast import Announcer
from openpilot.selfdrive.ui.tandem.onroad.limits import LimitFollower, LimitOfferState, OfferChime
from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, LimitWatch


@pytest.fixture
def limit_view(monkeypatch):
  plan = custom.StarPilotPlan.new_message(lateralCheck=True)
  sm = {"starpilotPlan": plan}
  state = SimpleNamespace(sm=SimpleNamespace(valid={"starpilotPlan": True}), is_metric=False, started=True,
                          engaged=True, always_on_lateral_active=False, starpilot_toggles={},
                          ui_params=SimpleNamespace(get_bool=lambda _: False))

  class Messages(dict):
    valid = state.sm.valid

  state.sm = Messages(sm)
  monkeypatch.setattr(onroad, "ui_state", state)
  now = [0.0]
  monkeypatch.setattr(onroad.time, "monotonic", lambda: now[0])
  view = onroad.EssentialsOnroadView.__new__(onroad.EssentialsOnroadView)
  view._closed = True  # state-only view: no camera or GPU resources to clean up
  view._limit_offer = LimitOfferState()
  view._follower = LimitFollower()
  view._offer_chime = OfferChime()
  view._limits = LimitWatch()
  view._chips = ChipStack()
  view._headroom_warning = False
  view._forecast, view._announcer = SimpleNamespace(tick=lambda: None, forecast=None), Announcer()
  view.chimes = []
  view._memory = SimpleNamespace(put_nonblocking=lambda key, value: view.chimes.append((key, value)))

  def update(current=55, pending=65, source="None"):
    plan.slcSpeedLimit = current * CV.MPH_TO_MS
    plan.unconfirmedSlcSpeedLimit = pending * CV.MPH_TO_MS
    plan.speedLimitChanged = pending > 0
    plan.slcSpeedLimitSource = source
    plan.slcPresentedSpeedLimitSource = "Map Data"
    return view._offer()

  return view, update, now, state


@pytest.mark.parametrize("fallback", ["None", "Previous Limit", ""])
def test_ignored_consecutive_limit_stays_hidden_across_expiry_and_source_gaps(limit_view, fallback):
  view, update, _, state = limit_view
  assert update().limit == pytest.approx(65)
  view._ignore_limit()
  assert update() is None
  assert update(pending=0, source=fallback) is None
  state.sm.valid["starpilotPlan"] = False
  assert update() is None
  state.sm.valid["starpilotPlan"] = True
  assert update(pending=65.001) is None


@pytest.mark.parametrize("current,pending,source", [(55, 70, "None"), (55, 60, "None"), (45, 0, "Map Data"), (55, 0, "Dashboard")])
def test_an_intervening_limit_up_or_down_allows_the_ignored_limit_again(limit_view, current, pending, source):
  view, update, _, _ = limit_view
  assert update() is not None
  view._ignore_limit()
  update(current=current, pending=pending, source=source)
  assert update().limit == pytest.approx(65)


def test_a_lower_limit_asks_to_slow_down(limit_view):
  _, update, _, _ = limit_view
  offer = update(current=65, pending=55)
  assert offer.limit == pytest.approx(55) and offer.lower
  assert not update(current=55, pending=65).lower


def test_each_new_card_chimes_once_with_the_pre_alert(limit_view):
  view, update, _, _ = limit_view
  for _ in range(3):
    view._chime_for(update())
  assert view.chimes == [("TestAlert", "preAlert")]
  view._ignore_limit()
  view._chime_for(update())
  view._chime_for(update(pending=70))
  assert view.chimes == [("TestAlert", "preAlert")] * 2


def test_unit_changes_do_not_clear_a_dismissal(limit_view):
  view, update, _, state = limit_view
  update()
  view._ignore_limit()
  state.is_metric = True
  assert update() is None
  assert update(pending=70).limit == pytest.approx(70 * CV.MPH_TO_KPH)


def test_replacement_limit_gets_a_fresh_confirmation_countdown(limit_view):
  _, update, now, _ = limit_view
  assert update().seconds_left == 30
  now[0] = 10
  assert update().seconds_left == 20
  assert update(pending=70).seconds_left == 30


def test_a_new_drive_clears_the_dismissal(limit_view, monkeypatch):
  view, update, _, _ = limit_view
  update()
  view._ignore_limit()
  monkeypatch.setattr(onroad.StarPilotOnroadView, "_offroad_transition", lambda self: None)
  view._offroad_transition()
  assert update().limit == pytest.approx(65)


@pytest.mark.parametrize("hidden_by", ["alert", "headroom", "hidden_hud", "offroad"])
def test_limit_changes_are_observed_while_the_card_is_hidden(limit_view, hidden_by):
  view, update, _, state = limit_view
  update()
  view._ignore_limit()
  plan = state.sm["starpilotPlan"]
  plan.speedLimitChanged = False
  plan.unconfirmedSlcSpeedLimit = 0
  plan.slcSpeedLimitSource = "Map Data"  # a live 55 after the dismissed 65
  alert = Alert(alert_type="takeOver/critical") if hidden_by == "alert" else None
  view.alert_renderer = SimpleNamespace(will_render=lambda: (alert, False))
  view._draw_hud_controls = hidden_by != "hidden_hud"
  view._headroom_warning = hidden_by == "headroom"
  state.started = hidden_by != "offroad"
  view._navigating = lambda: False
  view._render_layers()   # production draws these under the border, not after the inherited _render
  assert not view._layers_visible
  assert update().limit == pytest.approx(65)
