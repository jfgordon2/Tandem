from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem import fonts, tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.system.ui.lib import application as app


@pytest.mark.parametrize("lazy", [False, True])
def test_gui_loads_and_reuses_faces(monkeypatch: pytest.MonkeyPatch, lazy: bool) -> None:
  loaded = []
  default_fonts = []
  gui = app.GuiApplication()

  def load(path: str) -> SimpleNamespace:
    loaded.append(Path(path).name)
    return SimpleNamespace(texture=SimpleNamespace(id=len(loaded)))

  monkeypatch.setattr(app.rl, "load_font", load)
  monkeypatch.setattr(app.rl, "gen_texture_mipmaps", lambda _texture: None)
  monkeypatch.setattr(app.rl, "set_texture_filter", lambda *_args: None)
  monkeypatch.setattr(app.rl, "gui_set_font", default_fonts.append)
  monkeypatch.setattr(app, "gui_app", gui)
  monkeypatch.setattr(app.multilang, "requires_unifont", lambda: True)

  gui._load_fonts(lazy=lazy)
  assert loaded == ([app.FontWeight.NORMAL] if lazy else list(app.FontWeight))
  assert default_fonts == [gui.font()]

  fallback = app.font_fallback(gui.font())
  assert fallback is gui.font(app.FontWeight.UNIFONT)
  if lazy:
    assert loaded == [app.FontWeight.NORMAL, app.FontWeight.UNIFONT]

  brand = gui.font(app.FontWeight.BRAND)
  assert app.font_fallback(brand) is brand
  assert gui.font(app.FontWeight.BRAND) is brand
  assert loaded.count(app.FontWeight.BRAND) == 1


def test_lazy_fonts_respect_upstream_screen_switches(monkeypatch: pytest.MonkeyPatch) -> None:
  switches = ("TANDEM_HOME", "TANDEM_SETTINGS", "TANDEM_ONROAD", "TANDEM_SIDEBAR")
  for switch in switches:
    monkeypatch.setenv(switch, "1")
  assert fonts.lazy_upstream_fonts()
  for switch in switches:
    with monkeypatch.context() as env:
      env.setenv(switch, "0")
      assert not fonts.lazy_upstream_fonts()


@pytest.mark.parametrize("language", ["en", "ja"])
def test_alert_faces_are_ready_at_startup(monkeypatch: pytest.MonkeyPatch, language: str) -> None:
  loaded = []
  monkeypatch.setattr(alerts, "font", loaded.append)
  monkeypatch.setattr(alerts, "multilang", SimpleNamespace(language=language))
  alerts.prepare_fonts()
  assert loaded[:4] == [T.FONT, T.FONT_SEMIBOLD, T.FONT_BOLD, T.FONT_EXTRABOLD]
  assert loaded[4:] == ([] if language == "en" else [T.FONT_UNIFONT])
