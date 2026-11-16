import re
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem import fonts, tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.system.ui.lib import application as app

TOOLS = Path(__file__).resolve().parents[1] / "tools"


LAZY_FACES = [app.FontWeight.MEDIUM, app.FontWeight.BOLD, app.FontWeight.SEMI_BOLD]


@pytest.fixture
def loader(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
  """A GuiApplication over a recorded raylib. Fonts are real structs, as the loader fills one in place."""
  rec = SimpleNamespace(gui=app.GuiApplication(), loaded=[], textures=0, unloaded=[], mipmapped=[], freed=[], released=[], default=[],
                        drawn=[], unifont=False)

  def texture(size: int) -> app.rl.Texture:
    made = app.rl.ffi.new("Texture *")[0]
    rec.textures += 1
    made.id, made.width, made.height = rec.textures, size, size
    return made

  def load(path: str) -> app.rl.Font:
    rec.loaded.append(Path(path).name)
    font = app.rl.ffi.new("Font *")[0]
    font.texture = texture(2048)
    font.baseSize = len(rec.loaded)   # each load brings its own face's metrics
    return font

  monkeypatch.setattr(app.rl, "load_font", load)
  monkeypatch.setattr(app.rl, "gen_image_color", lambda *_args: "pixel")
  monkeypatch.setattr(app.rl, "load_texture_from_image", lambda _image: texture(1))
  monkeypatch.setattr(app.rl, "unload_image", lambda _image: None)
  monkeypatch.setattr(app.rl, "unload_texture", lambda unloaded: rec.unloaded.append(unloaded.id))
  monkeypatch.setattr(app.rl, "gen_texture_mipmaps", lambda mipmapped: rec.mipmapped.append(mipmapped.id))
  monkeypatch.setattr(app.rl, "set_texture_filter", lambda *_args: None)
  monkeypatch.setattr(app.rl, "unload_font_data", lambda glyphs, count: rec.freed.append("glyphs"))
  monkeypatch.setattr(app.rl, "mem_free", lambda recs: rec.freed.append("recs"))
  monkeypatch.setattr(app.rl, "gui_set_font", rec.default.append)
  monkeypatch.setattr(app, "release_glyph_images", rec.released.append)
  monkeypatch.setattr(app, "gui_app", rec.gui)
  monkeypatch.setattr(app.multilang, "requires_unifont", lambda: rec.unifont)
  return rec


@pytest.fixture
def text_functions(loader: SimpleNamespace) -> Iterator[None]:
  """raylib's text functions as they are before a window patches them, put back afterwards; draws are recorded."""
  names = ("draw_text_ex", "gui_set_font", "_orig_draw_text_ex", "_orig_gui_set_font")
  saved = {name: getattr(app.rl, name) for name in names if hasattr(app.rl, name)}
  if "_orig_gui_set_font" in saved:
    del app.rl._orig_gui_set_font
  app.rl._orig_draw_text_ex = lambda font, *_args: loader.drawn.append(font)
  yield
  for name in names:
    if name in saved:
      setattr(app.rl, name, saved[name])
    elif hasattr(app.rl, name):
      delattr(app.rl, name)


def _draw(font: app.rl.Font) -> None:
  app.rl.draw_text_ex(font, "Speed", app.rl.Vector2(0, 0), 40, 0, app.rl.WHITE)


def _atlas(font: app.rl.Font) -> int:
  return font.texture.width


def test_without_lazy_fonts_the_loader_is_upstreams(loader: SimpleNamespace) -> None:
  """With an Essentials screen off (lazy fonts off), every face keeps its atlas and its glyph images."""
  gui = loader.gui
  gui._load_fonts()
  assert loader.loaded == list(app.FontWeight)
  assert (loader.unloaded, loader.released, gui._lazy_atlases) == ([], [], {})
  assert all(_atlas(gui.font(weight)) == 2048 for weight in app.FontWeight)
  assert loader.default == [gui.font()]


@pytest.mark.usefixtures("text_functions")
def test_text_functions_are_upstreams_without_lazy_fonts(loader: SimpleNamespace) -> None:
  gui, set_font = loader.gui, app.rl.gui_set_font
  gui._load_fonts()
  gui._patch_text_functions()
  assert app.rl.gui_set_font is set_font and not hasattr(app.rl, "_orig_gui_set_font")
  for weight in app.FontWeight:
    _draw(gui.font(weight))
    assert loader.drawn[-1] is gui.font(weight)
  assert loader.loaded == list(app.FontWeight)


def test_lazy_fonts_keep_metrics_and_drop_the_big_atlases(loader: SimpleNamespace) -> None:
  gui = loader.gui
  gui._load_fonts(lazy=True)
  faces = list(app.FontWeight)
  assert loader.loaded == faces   # every face is read once, so each font has its own metrics from the start
  assert [gui.font(weight).baseSize for weight in faces] == [1, 2, 3, 4, 5, 6]
  assert [weight for weight in faces if _atlas(gui.font(weight)) == 1] == LAZY_FACES
  assert loader.unloaded == [2, 4, 6]   # the atlases Medium, Bold and SemiBold were read with
  assert gui._lazy_atlases == {gui.font(weight).texture.id: weight for weight in LAZY_FACES}
  assert len({gui.font(weight).texture.id for weight in faces}) == 6   # text caches tell the faces apart by texture
  assert len(loader.released) == len(faces)
  assert loader.default == [gui.font()]


def test_measuring_a_lazy_face_leaves_its_atlas_unloaded(loader: SimpleNamespace) -> None:
  """Upstream's labels wrap their text when they're made; that alone doesn't bring the atlas in."""
  gui = loader.gui
  gui._load_fonts(lazy=True)
  for weight in app.FontWeight:
    assert app.font_fallback(gui.font(weight)) is gui.font(weight)
  assert len(loader.loaded) == 6
  assert [weight for weight in app.FontWeight if _atlas(gui.font(weight)) == 1] == LAZY_FACES


@pytest.mark.usefixtures("text_functions")
def test_a_lazy_face_gets_its_atlas_when_first_drawn(loader: SimpleNamespace) -> None:
  gui = loader.gui
  gui._load_fonts(lazy=True)
  gui._patch_text_functions()
  bold, medium = gui.font(app.FontWeight.BOLD), gui.font(app.FontWeight.MEDIUM)
  stand_in = bold.texture.id
  held = app.rl.ffi.new("Font *")
  held[0] = bold   # a copy of the font as it was before its atlas loaded
  mipmapped = len(loader.mipmapped)

  _draw(gui.font())
  assert len(loader.loaded) == 6

  _draw(bold)
  assert loader.drawn[-1] is bold   # the font widgets already hold is the one filled in
  assert loader.loaded[6:] == [app.FontWeight.BOLD]
  assert (_atlas(bold), bold.baseSize) == (2048, 7)
  assert loader.mipmapped[mipmapped:] == [bold.texture.id]
  assert loader.freed == ["glyphs", "recs"]   # the metrics it held are freed for the reloaded face's
  assert loader.released[-1] is bold
  assert stand_in not in loader.unloaded   # the stand-in stays, so no other texture takes its id
  assert _atlas(medium) == 1   # the other faces stay as they were

  _draw(bold)
  _draw(held[0])
  assert loader.drawn[-1] is bold   # a copy made earlier still draws with the atlas
  assert len(loader.loaded) == 7   # once loaded, a face isn't loaded again


@pytest.mark.usefixtures("text_functions")
def test_a_lazy_face_stays_unloaded_where_unifont_replaces_it(loader: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
  gui = loader.gui
  gui._load_fonts(lazy=True)
  gui._patch_text_functions()
  loader.unifont = True
  medium, brand = gui.font(app.FontWeight.MEDIUM), gui.font(app.FontWeight.BRAND)
  _draw(medium)
  assert loader.drawn[-1] is gui.font(app.FontWeight.UNIFONT)
  _draw(brand)
  assert loader.drawn[-1] is brand
  assert len(loader.loaded) == 6

  monkeypatch.setattr(app, "KEEP_FONT", True)   # Essentials drawing its own text keeps the face it asked for
  _draw(medium)
  assert loader.drawn[-1] is medium and _atlas(medium) == 2048


@pytest.mark.usefixtures("text_functions")
def test_raygui_is_given_a_lazy_face_with_its_atlas(loader: SimpleNamespace) -> None:
  """raygui draws with the font it's given (upstream's gui_label sets the bold face), so it's loaded before it's set."""
  gui = loader.gui
  gui._load_fonts(lazy=True)
  gui._patch_text_functions()
  bold = gui.font(app.FontWeight.BOLD)
  app.rl.gui_set_font(bold)
  assert loader.loaded[6:] == [app.FontWeight.BOLD] and _atlas(bold) == 2048
  assert loader.default[-1] is bold
  app.rl.gui_set_font(gui.font())
  assert len(loader.loaded) == 7 and loader.default[-1] is gui.font()


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
