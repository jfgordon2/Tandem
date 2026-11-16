"""Tandem's hooks in upstream files: each defaults to upstream's behavior."""
from types import SimpleNamespace


def test_font_shaping_and_fallback_are_scoped_to_tandem(monkeypatch):
  from openpilot.selfdrive.ui.tandem import draw, fonts
  from openpilot.system.ui.lib import application
  before = application.TEXT_SHAPERS[:]
  with draw._own_font:
    assert application.KEEP_FONT and len(application.TEXT_SHAPERS) == len(before) + 2
  assert not application.KEEP_FONT and application.TEXT_SHAPERS == before
  monkeypatch.setattr(fonts.rl, "load_font", lambda path: SimpleNamespace(texture=SimpleNamespace(id=1), source=path, glyphCount=0, glyphs=[]))
  monkeypatch.setattr(fonts.rl, "gen_texture_mipmaps", lambda _: None)
  monkeypatch.setattr(fonts.rl, "set_texture_filter", lambda *args: None)
  monkeypatch.setattr(fonts, "_loaded", {})
  assert fonts.font(application.FontWeight.NORMAL).source.endswith("Figtree-Regular.fnt")
  assert application.FontWeight.NORMAL == "Inter-Regular.ttf" and application.TEXT_SHAPERS == before


def test_measuring_applies_the_same_shapers_as_drawing(monkeypatch):
  from openpilot.system.ui.lib import application, text_measure
  measured = []
  monkeypatch.setattr(text_measure.rl, "measure_text_ex", lambda font, text, size, spacing: measured.append(text) or text_measure.rl.Vector2(0, 0))
  monkeypatch.setattr(application, "TEXT_SHAPERS", [str.upper])
  monkeypatch.setattr(text_measure, "TEXT_SHAPERS", application.TEXT_SHAPERS)
  font = SimpleNamespace(texture=SimpleNamespace(id=-7))
  text_measure.measure_text_cached(font, "shaped", 20)
  assert measured == ["SHAPED"]
