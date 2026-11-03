"""Tandem observes the actual upstream speed-controller choice, including a selected next turn."""
import pytest

from openpilot.selfdrive.controls.tests import test_starpilot_vcruise as fixtures
from openpilot.starpilot.tandem.navigation import controller_type


@pytest.mark.parametrize("maneuver,modifier", [("turn", "left"), ("turn", "right"), ("turn", "sharpLeft"),
                                               ("turn", "sharpRight"), ("turn", "uturn"), ("roundabout", "right")])
@pytest.mark.parametrize("next_turn", [False, True])
def test_selected_maneuver_and_target_follow_upstream_and_clear_with_navigation(monkeypatch, maneuver, modifier, next_turn):
  monkeypatch.setenv("TANDEM_ONROAD", "1")
  original = fixtures.StarPilotVCruise
  monkeypatch.setattr(fixtures, "StarPilotVCruise", controller_type(original))
  nav = {"valid": True, "maneuverType": "continue", "maneuverModifier": "straight", "maneuverDistance": 5.0}
  prefix = "nextManeuver" if next_turn else "maneuver"
  nav.update({f"{prefix}Type": maneuver, f"{prefix}Modifier": modifier, f"{prefix}Distance": 30.0})
  planner, cruise = fixtures.make_vcruise(nav_state=nav)
  toggles = fixtures.make_toggles()
  toggles.nav_longitudinal_allowed = True
  messages = fixtures.make_sm(standstill=False)
  target = fixtures.update_vcruise(cruise, messages, toggles, now=0.0, v_ego=20.0)
  assert 0 < target == cruise.nav_turn_target < 20.0
  assert (cruise.nav_turn_maneuver, cruise.nav_turn_modifier) == (maneuver, modifier)
  # The original controller calculates exactly the same target.
  stock = original(planner)
  assert fixtures.update_vcruise(stock, messages, toggles, now=0.0, v_ego=20.0) == target
  planner.params_memory.values["NavInstructionState"] = {"valid": False}
  fixtures.update_vcruise(cruise, messages, toggles, now=0.1, v_ego=20.0)
  assert cruise.nav_turn_target == 0.0
  assert (cruise.nav_turn_maneuver, cruise.nav_turn_modifier) == ("", "")
