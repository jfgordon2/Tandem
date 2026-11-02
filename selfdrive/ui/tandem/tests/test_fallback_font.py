"""The Noto fallback font (tools/fallback_font.py) and Arabic shaping (arabic.py)."""
import importlib.util
import re
from pathlib import Path

from openpilot.selfdrive.ui.tandem.arabic import join, shape

FONTS = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_spec = importlib.util.spec_from_file_location("fallback_font", Path(__file__).resolve().parents[1] / "tools" / "fallback_font.py")
fallback_font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fallback_font)


def atlas_chars() -> set[int]:
  return {int(m) for m in re.findall(r"^char id=(\d+)", (FONTS / "NotoSans-Fallback.fnt").read_text(encoding="utf-8"), re.M)}


def test_upstream_names_the_noto_fallback_and_it_is_committed():
  from openpilot.system.ui.lib.application import FontWeight
  assert FontWeight.UNIFONT == "NotoSans-Fallback.fnt"
  assert (FONTS / "NotoSans-Fallback.png").is_file() and (FONTS / "NotoSans-OFL.txt").is_file()


def test_the_atlas_has_every_character_the_translations_use():
  """Fails when a translation gains characters: rerun tools/fallback_font.py (subset, then build)."""
  chars, _ = fallback_font.charset()
  missing = sorted(chars - atlas_chars())
  assert not missing, "rebuild NotoSans-Fallback: " + " ".join(f"U+{c:04X}" for c in missing)


def test_the_atlas_has_every_arabic_form_shape_can_produce():
  forms = {c for c in range(0xFE70, 0xFEFD) if c not in (0xFE75,)}
  assert forms <= atlas_chars()


def test_arabic_and_cyrillic_use_the_fallback():
  from openpilot.system.ui.lib.multilang import UNIFONT_LANGUAGES
  assert {"ar", "uk", "th", "zh-CHT", "zh-CHS", "ko", "ja"} <= set(UNIFONT_LANGUAGES)


def test_letters_join_by_position():
  # beh, then the same letter at the start, middle and end of a word
  assert join("ب") == "ﺏ"
  assert join("ببب") == "ﺑﺒﺐ"
  assert join("اب") == "ﺍﺏ"      # alef doesn't join forward, so beh stands alone


def test_lam_alef_is_one_ligature():
  assert join("لا") == "ﻻ"
  assert join("سلام") == "ﺳﻼﻡ"   # salaam: lam-alef joined to the seen before it


def test_lines_read_right_to_left_with_numbers_and_latin_in_order():
  out = shape("تحديث 0.10.1 openpilot")
  assert out.startswith("openpilot 0.10.1 ")
  assert out.endswith(join("تحديث")[::-1])
  assert shape("(م)") == "(ﻡ)"            # brackets mirror inside a right-to-left run


def test_text_without_arabic_is_untouched():
  for text in ("Hello 123", "Українська", "日本語", ""):
    assert shape(text) == text
