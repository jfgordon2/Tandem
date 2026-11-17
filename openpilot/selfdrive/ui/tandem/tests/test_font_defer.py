"""The native font gate and lazy loader keep stock behavior and warm alert faces."""
from unittest.mock import Mock

import pytest

from openpilot.starpilot.tandem.font_loading import defer_inter
from openpilot.system.ui.lib import application as app


def test_font_gate_respects_native_and_recovery_layouts() -> None:
  """The small and recovery layouts retain all the native faces at startup."""
  assert defer_inter(True, {})
  assert not defer_inter(False, {})
  assert not defer_inter(True, {"STARPILOT_UI": "upstream"})
  assert not defer_inter(True, dict.fromkeys(("TANDEM_HOME", "TANDEM_SETTINGS", "TANDEM_ONROAD", "TANDEM_SIDEBAR"), "0"))


def test_medium_and_semibold_load_on_first_request(monkeypatch: pytest.MonkeyPatch) -> None:
  """Use the same native loader and keep the regular and bold alert faces warm."""
  monkeypatch.setattr(app, "BIG_UI", True)
  monkeypatch.setattr(app.multilang, "languages", {})
  monkeypatch.setattr(app.multilang, "requires_font_fallback", lambda: False)
  owner = object.__new__(type(app.gui_app))
  owner._fonts, owner._deferred_faces = {}, {}
  loaded = Mock(side_effect=lambda weight, _: owner._fonts.__setitem__(weight, weight))
  owner._load_face = loaded
  owner._load_fonts()
  assert set(owner._fonts) == {app.FontWeight.NORMAL, app.FontWeight.BOLD, app.FontWeight.UNIFONT}
  assert owner.font(app.FontWeight.MEDIUM) == app.FontWeight.MEDIUM
  assert owner.font(app.FontWeight.MEDIUM) == app.FontWeight.MEDIUM
  assert loaded.call_count == 4


@pytest.mark.parametrize(("screen", "weight", "releases"), [
  ("tandem", app.FontWeight.NORMAL, True),
  ("tandem", app.FontWeight.UNIFONT, False),
  ("upstream", app.FontWeight.NORMAL, False),
])
def test_glyph_images_released_only_for_tandem_inter(
  monkeypatch: pytest.MonkeyPatch, screen: str, weight: app.FontWeight, releases: bool,
) -> None:
  """Keep the atlas and only free Inter's CPU images in the Tandem UI."""
  monkeypatch.setenv("STARPILOT_UI", screen)
  monkeypatch.setenv("TANDEM_SETTINGS", "1")
  monkeypatch.setattr(app, "BIG_UI", True)
  font = Mock()
  release = Mock()
  monkeypatch.setattr(app.rl, "load_font_ex", lambda *_: font)
  monkeypatch.setattr(app.rl, "gen_texture_mipmaps", Mock())
  monkeypatch.setattr(app.rl, "set_texture_filter", Mock())
  monkeypatch.setattr(app.rl, "release_font_glyph_images", release, raising=False)
  owner = object.__new__(type(app.gui_app))
  owner._fonts = {}
  owner._load_face(weight, [65])
  assert owner._fonts[weight] is font
  if releases:
    release.assert_called_once_with(font)
  else:
    release.assert_not_called()
