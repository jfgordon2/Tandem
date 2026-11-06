"""Chip inputs must describe live events or actual displayed alerts, not an empty alert's old name."""
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, snapshot


class Messages(dict):
  @property
  def valid(self):
    return dict.fromkeys(self, True)


def state(**messages):
  return SimpleNamespace(sm=Messages(messages), engaged=False, is_metric=False,
                         always_on_lateral_active=False, starpilot_toggles={})


def plan(direction=None):
  return SimpleNamespace(lateralCheck=True, cscControllingSpeed=False, redLight=False, forcingStop=False,
                         stopSignConfirmed=False, slcSpeedLimit=0, experimentalMode=False, trackingLead=False,
                         starpilotEvents=[SimpleNamespace(name=f"turning{direction}")] if direction else [],
                         pulseGlideCoasting=False)


@pytest.mark.parametrize("service", ["selfdriveState", "starpilotSelfdriveState"])
@pytest.mark.parametrize("direction", ["Left", "Right"])
def test_empty_turn_alert_cannot_renew_a_finished_turn_or_override_the_next_turn(service, direction, monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path))
  alert = SimpleNamespace(alertType=f"turning{direction}/warning", alertSize="none")
  current = state(starpilotPlan=plan(direction), **{service: alert})
  stack = ChipStack()
  assert stack.update(snapshot(current), 0, False)[0][0].label == f"Turning {direction.lower()}"
  current.sm["starpilotPlan"] = plan()
  assert stack.update(snapshot(current), 1, False)[0][0].key == "turning"  # normal two-second hold
  assert stack.update(snapshot(current), 2.31, False) == []
  assert stack.update(snapshot(current), 300, False) == []

  opposite = "Right" if direction == "Left" else "Left"
  current.sm["starpilotPlan"] = plan(opposite)
  assert stack.update(snapshot(current), 301, False)[0][0].label == f"Turning {opposite.lower()}"
  current.sm["starpilotPlan"] = plan()
  assert stack.update(snapshot(current), 304, False) == []


@pytest.mark.parametrize("service", ["selfdriveState", "starpilotSelfdriveState"])
@pytest.mark.parametrize("name", ["turningLeft", "turningRight", "greenLight", "leadDeparting", "lowMemory", "laneChangeBlockedLoud"])
def test_empty_alerts_do_not_supply_chip_reasons(service, name):
  current = state(**{service: SimpleNamespace(alertType=f"{name}/warning", alertSize="none")})
  assert snapshot(current).events == set()


@pytest.mark.parametrize("service", ["selfdriveState", "starpilotSelfdriveState"])
@pytest.mark.parametrize("name", ["turningLeft", "turningRight", "greenLight", "leadDeparting", "lowMemory", "laneChangeBlockedLoud"])
def test_active_alerts_still_supply_their_chip_reasons(service, name):
  current = state(**{service: SimpleNamespace(alertType=f"{name}/warning", alertSize="small")})
  assert snapshot(current).events == {name}
