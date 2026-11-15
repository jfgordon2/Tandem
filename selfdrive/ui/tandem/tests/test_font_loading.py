import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem import fonts, tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.system.ui.lib import application as app

TOOLS = Path(__file__).resolve().parents[1] / "tools"


@pytest.mark.parametrize("lazy", [False, True])
def test_gui_loads_and_reuses_faces(monkeypatch: pytest.MonkeyPatch, lazy: bool) -> None:
  loaded = []
  default_fonts = []
  gui = app.GuiApplication()

  def load(path: str) -> SimpleNamespace:
    loaded.append(Path(path).name)
    return SimpleNamespace(texture=SimpleNamespace(id=len(loaded)), glyphCount=0, glyphs=[])

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


def test_glyph_images_are_released_once(monkeypatch: pytest.MonkeyPatch) -> None:
  """Text draws from the atlas texture, so raylib's CPU copy of each glyph is freed; metrics stay."""
  freed = []
  null = app.rl.ffi.NULL
  data = [app.rl.ffi.new("char[]", 4) for _ in range(2)]
  glyphs = [SimpleNamespace(value=65 + i, advanceX=10, image=SimpleNamespace(data=data[i])) for i in range(2)]
  font = SimpleNamespace(glyphCount=2, glyphs=glyphs)
  monkeypatch.setattr(app.rl, "unload_image", freed.append)
  app.release_glyph_images(font)
  app.release_glyph_images(font)   # already released: nothing more to free
  assert len(freed) == 2
  assert all(g.image.data == null for g in glyphs)
  assert [(g.value, g.advanceX) for g in glyphs] == [(65, 10), (66, 10)]


def test_upstream_font_keeps_glyph_images_without_tandem(monkeypatch: pytest.MonkeyPatch) -> None:
  """With an Essentials screen off (lazy fonts off), upstream's loader behaves as upstream's."""
  released = []
  gui = app.GuiApplication()
  monkeypatch.setattr(app.rl, "load_font", lambda path: SimpleNamespace(texture=SimpleNamespace(id=1), glyphCount=0, glyphs=[]))
  monkeypatch.setattr(app.rl, "gen_texture_mipmaps", lambda _texture: None)
  monkeypatch.setattr(app.rl, "set_texture_filter", lambda *_args: None)
  monkeypatch.setattr(app.rl, "gui_set_font", lambda _font: None)
  monkeypatch.setattr(app, "release_glyph_images", released.append)
  gui._load_fonts(lazy=False)
  assert released == []
  gui._load_fonts(lazy=True)
  assert len(released) == 1


def _atlas_rows(face: str) -> tuple[int, int, int]:
  from PIL import Image
  folder = Path(app.FONT_DIR)
  fnt = (folder / f"{face}.fnt").read_text()
  bottom = max(int(y) + int(h) for y, h in re.findall(r"^char id=\d+\s+x=\d+\s+y=(\d+)\s+width=\d+\s+height=(\d+)", fnt, re.M))
  scale_h = int(re.search(r"^common .*\bscaleH=(\d+)", fnt, re.M)[1])
  return bottom, scale_h, Image.open(folder / f"{face}.png").height


@pytest.mark.parametrize("face", ["Figtree-Regular", "Figtree-Medium", "Figtree-SemiBold", "Figtree-Bold", "Figtree-ExtraBold",
                                  "JetBrainsMono-Medium", "JetBrainsMono-Bold", "NotoSans-Fallback"])
def test_tandem_atlases_are_cropped_to_their_glyphs(face: str) -> None:
  """Each atlas ends just below its lowest glyph (tools/crop_font_atlases.py), and its .fnt says so."""
  from PIL import Image
  bottom, scale_h, height = _atlas_rows(face)
  assert scale_h == height
  assert bottom < height <= bottom + 3 + 1 + 64
  image = Image.open(Path(app.FONT_DIR) / f"{face}.png")
  assert image.crop((image.width - 3, height - 3, image.width, height)).getchannel("A").getextrema() == (255, 255)   # raylib's white patch


def test_crop_keeps_glyphs_and_moves_the_white_patch(tmp_path: Path) -> None:
  import importlib.util
  from PIL import Image
  spec = importlib.util.spec_from_file_location("crop_font_atlases", TOOLS / "crop_font_atlases.py")
  crop = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(crop)
  image = Image.new("LA", (64, 256), (255, 0))
  image.paste((255, 200), (2, 2, 20, 70))         # a glyph down to row 70
  image.paste((255, 255), (61, 253, 64, 256))     # the white patch, bottom right
  image.save(tmp_path / "Face.png")
  fnt = "common lineHeight=200 base=200 scaleW=64 scaleH=256 pages=1\nchar id=65   x=2     y=2     width=18    height=68\n"
  (tmp_path / "Face.fnt").write_text(fnt)
  assert crop.crop("Face", tmp_path) == (256, 128)
  out = Image.open(tmp_path / "Face.png")
  assert out.size == (64, 128)
  assert list(out.crop((0, 0, 64, 70)).getdata()) == list(image.crop((0, 0, 64, 70)).getdata())
  assert out.crop((61, 125, 64, 128)).getchannel("A").getextrema() == (255, 255)
  assert "scaleH=128" in (tmp_path / "Face.fnt").read_text()
  assert crop.crop("Face", tmp_path) == (128, 128)   # cropping again changes nothing
