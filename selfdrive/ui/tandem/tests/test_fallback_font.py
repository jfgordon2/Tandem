"""The Noto fallback font (tools/fallback_font.py) and Arabic shaping (arabic.py)."""
import importlib.util
import re
from pathlib import Path

from openpilot.selfdrive.ui.tandem.arabic import join, shape
from openpilot.selfdrive.ui.tandem import i18n, thai

FONTS = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_spec = importlib.util.spec_from_file_location("fallback_font", Path(__file__).resolve().parents[1] / "tools" / "fallback_font.py")
fallback_font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fallback_font)


def atlas_chars() -> set[int]:
  return {int(m) for m in re.findall(r"^char id=(\d+)", (FONTS / "NotoSans-Fallback.fnt").read_text(encoding="utf-8"), re.M)}


def test_tandem_owns_noto_and_upstream_keeps_its_fonts():
  from openpilot.system.ui.lib.application import FontWeight
  from openpilot.selfdrive.ui.tandem.fonts import font_file
  assert FontWeight.UNIFONT == "unifont.fnt"
  assert FontWeight.ROMAN == "Inter-Regular.fnt"
  assert font_file(FontWeight.UNIFONT) == "NotoSans-Fallback.fnt"
  assert font_file(FontWeight.ROMAN) == "Figtree-Regular.fnt"
  assert (FONTS / "NotoSans-Fallback.png").is_file() and (FONTS / "NotoSans-OFL.txt").is_file()


def test_the_atlas_has_every_character_the_translations_use():
  """Fails when a translation gains characters: rerun tools/fallback_font.py (subset, then build)."""
  chars, _ = fallback_font.charset()
  missing = sorted(chars - atlas_chars())
  assert not missing, "rebuild NotoSans-Fallback: " + " ".join(f"U+{c:04X}" for c in missing)


def test_the_atlas_has_every_arabic_form_shape_can_produce():
  forms = {c for c in range(0xFE70, 0xFEFD) if c not in (0xFE75,)}
  assert forms <= atlas_chars()


def test_arabic_and_cyrillic_use_the_owned_fallback(monkeypatch):
  from openpilot.selfdrive.ui.tandem import fonts, tokens as T
  latin = {int(cp) for cp in re.findall(r"^char id=(\d+)", (FONTS / "Figtree-Regular.fnt").read_text(), re.M)}
  monkeypatch.setattr(fonts, "covers", lambda face, text: all(ord(c) in latin for c in text))
  assert fonts.face_for("العربية", T.FONT) == T.FONT_UNIFONT
  assert fonts.face_for("Українська", T.FONT) == T.FONT_UNIFONT
  assert fonts.face_for("English", T.FONT) == T.FONT
  assert {ord(c) for c in "العربيةУкраїнська"} <= atlas_chars()


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


def test_arabic_measurements_keep_their_sign_number_and_unit_together():
  assert shape("أقل من 20 mph").startswith("20 mph ")
  assert shape("خطأ السرعة: -3.5 m/s").startswith("-3.5 m/s ")
  assert shape("الحرارة 42 °C").startswith("42 °C ")
  assert shape("تحقق من 12V").startswith("12V ")
  assert shape("الشبكة WiFi-123").startswith("WiFi-123 ")
  assert shape("افتح https://192.168.43.1").startswith("https://192.168.43.1 ")
  assert shape("أعلى من 31 mph (50 km/h)").startswith("31 mph (50 km/h) ")
  assert shape("الزاوية -2.4°").startswith("-2.4° ")
  assert shape("التقدم 42%").startswith("42% ")
  angles = shape("الجهاز (الميل: -2.4°، الانحراف: 1.2°)")
  assert angles.startswith("(1.2°") and angles.endswith(") " + join("الجهاز")[::-1]), angles
  assert "-2.4°" in angles
  assert '"sk."' in shape('ابدأ بـ "sk."')


def test_thai_vowels_and_tones_are_one_rendered_glyph():
  assert thai.clusters("ขี่เกียร์น้ำ") == ["ขี่", "เกี", "ย", "ร์", "น้ำ"]
  for text in ("ขี่", "ที่", "น้ำ", "เกี"):
    rendered = thai.shape(text)
    assert len(rendered) == 1
    assert thai.PUA_START <= ord(rendered) <= thai.PUA_END
    assert thai.logical(rendered) == text
    assert thai.trim_last("abc" + text) == "abc"
  assert thai.shape("openpilot 0.10.1") == "openpilot 0.10.1"


def test_thai_catalog_clusters_are_composed_in_the_committed_atlas():
  entries = i18n.load("th")
  values = list(entries.marked.values()) + [f for forms in entries.plurals.values() for f in forms]
  used = {c for text in values for c in thai.clusters(text) if len(c) > 1 and any(thai.is_thai(ch) for ch in c)}
  assert not used - thai.mapping().keys(), "rerun fallback_font.py subset and build"
  assert set(thai.mapping().values()) <= atlas_chars()
  metrics = {int(cp): int(advance) for cp, advance in re.findall(r"^char id=(\d+).*xadvance=(-?\d+)",
                                                               (FONTS / "NotoSans-Fallback.fnt").read_text(), re.M)}
  assert all(metrics[cp] > 0 for cp in thai.mapping().values())
