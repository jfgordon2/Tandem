"""Tandem's own font atlases (tools/crop_font_atlases.py)."""
import re
from pathlib import Path

import pytest

from openpilot.system.ui.lib import application as app

TOOLS = Path(__file__).resolve().parents[1] / "tools"


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
