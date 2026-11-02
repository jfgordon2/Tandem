"""When the menu times out while driving, what's open on top of settings closes with it."""
from types import SimpleNamespace

from openpilot.selfdrive.ui.tandem.menu_idle import close_overlays


def _app(*widgets):
  calls = []
  app = SimpleNamespace(_nav_stack=list(widgets), pop_widgets_to=lambda w, instant: calls.append((w, instant)))
  return app, calls


def test_overlays_close_with_the_menu_while_driving():
  main, keyboard = object(), object()
  app, calls = _app(main, keyboard)
  assert close_overlays(app, driving=True)
  assert calls == [(main, True)]                 # back to MainLayout, which goes to the driving view itself


def test_parked_or_nothing_on_top_leaves_the_stack_alone():
  main, keyboard = object(), object()
  app, calls = _app(main, keyboard)
  assert not close_overlays(app, driving=False)  # parked: a keyboard you're using stays
  app, calls = _app(main)
  assert not close_overlays(app, driving=True) and calls == []
