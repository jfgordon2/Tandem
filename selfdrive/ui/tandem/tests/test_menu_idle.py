"""An untouched menu while driving goes back to the driving view after MENU_IDLE_S."""
from enum import IntEnum
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem import menu_idle as M


@pytest.fixture
def clock():
  t = [0.0]
  return t, M.MenuIdle(lambda: t[0])


def test_ten_untouched_seconds_while_driving_go_back(clock):
  t, idle = clock
  t[0] = 9.9
  assert not idle.update(driving=True, touched=False, away=True)
  t[0] = 10.0
  assert idle.update(driving=True, touched=False, away=True)
  t[0] = 15.0
  assert not idle.update(driving=True, touched=False, away=True)   # the timer starts over after going back


def test_a_touch_restarts_the_ten_seconds(clock):
  t, idle = clock
  t[0] = 8.0
  assert not idle.update(driving=True, touched=True, away=True)
  t[0] = 17.9
  assert not idle.update(driving=True, touched=False, away=True)
  t[0] = 18.0
  assert idle.update(driving=True, touched=False, away=True)


def test_parked_or_already_on_the_driving_view_never_counts(clock):
  t, idle = clock
  t[0] = 60.0
  assert not idle.update(driving=False, touched=False, away=True)  # parked: the menu stays
  t[0] = 65.0
  assert not idle.update(driving=True, touched=False, away=False)  # the bare driving view: nothing to close
  t[0] = 74.9
  assert not idle.update(driving=True, touched=False, away=True)   # counted from when the menu came up
  t[0] = 75.0
  assert idle.update(driving=True, touched=False, away=True)


def test_going_back_closes_overlays_the_sidebar_and_settings(monkeypatch):
  MainState = IntEnum("MainState", "HOME SETTINGS ONROAD")   # as layouts/main.py names them
  calls = []
  sidebar = SimpleNamespace(is_visible=True, set_visible=lambda on: calls.append(("sidebar", on)))
  main = SimpleNamespace(_sidebar=sidebar, _current_mode=MainState.SETTINGS, _set_mode_for_state=lambda: calls.append("mode"))
  keyboard = object()
  app = SimpleNamespace(_nav_stack=[main, keyboard], pop_widgets_to=lambda w, instant: calls.append(("pop", w is main, instant)))
  assert M._main_layout(app) is main and M._away(app, main)
  M._back_to_driving(app, main)
  assert calls == [("pop", True, True), ("sidebar", False), "mode"]

  bare = SimpleNamespace(_sidebar=SimpleNamespace(is_visible=False), _current_mode=MainState.ONROAD)
  assert not M._away(SimpleNamespace(_nav_stack=[bare]), bare)
  assert M._away(SimpleNamespace(_nav_stack=[bare, keyboard]), bare)
