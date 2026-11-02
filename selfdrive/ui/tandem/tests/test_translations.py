"""Tandem's translation catalog (i18n.py, tools/translations.py, translations/)."""
import importlib.util
from pathlib import Path

import pytest

from openpilot.selfdrive.ui.tandem import i18n

TOOLS = Path(__file__).resolve().parents[1] / "tools"
_spec = importlib.util.spec_from_file_location("translations_tool", TOOLS / "translations.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)
LANGUAGES = sorted(p.stem.removeprefix("tandem_") for p in i18n.CATALOG_DIR.glob("tandem_*.po"))


def test_the_template_lists_every_string_tandem_draws():
  """Fails after Tandem's wording changes: run tools/translations.py update."""
  pot = i18n.parse_po((i18n.CATALOG_DIR / "tandem.pot").read_text(encoding="utf-8"))
  code = tool.strings()
  assert sorted(set(code) - set(pot))[:20] == [], "new strings: run tools/translations.py update"
  assert sorted(set(pot) - set(code))[:20] == [], "removed strings: run tools/translations.py update"


@pytest.mark.parametrize("code", LANGUAGES)
def test_each_language_covers_the_template_and_keeps_its_values(code):
  entries = i18n.parse_po((i18n.CATALOG_DIR / f"tandem_{code}.po").read_text(encoding="utf-8"))
  assert set(entries) == set(tool.strings())
  bad = [(k, v) for k, v in entries.items() if v and "{}" in k and not i18n._holes_fit(k, v)]
  assert not bad


def test_pilot_languages_are_mostly_translated():
  for code in ("de", "es", "ja"):
    entries = i18n.parse_po((i18n.CATALOG_DIR / f"tandem_{code}.po").read_text(encoding="utf-8"))
    assert sum(bool(v) for v in entries.values()) / len(entries) > 0.9


def catalog():
  return i18n.Catalog({"Sets {} options": "Ajusta {} opciones", "{} of {} files": "{1} 件中 {0} 件", "{} alert{}": "{0}件",
                       "Standard": "Estándar", "Auto lane change": "Cambio automático", "Green Light": "Semáforo en verde",
                       "Lead Departure": "Salida", "{} path": "Trayectoria {}", "Untranslated": ""})


def test_templates_fill_numbered_and_dropped_holes():
  c = catalog()
  assert c.translate("Sets 12 options") == "Ajusta 12 opciones"
  assert c.translate("3 of 12 files") == "12 件中 3 件"
  assert c.translate("2 alerts") == "2件"
  assert c.translate("Standard path") == "Trayectoria Estándar"   # the value is translated too


def test_built_text_is_translated_piece_by_piece():
  c = catalog()
  assert c.translate("Standard · Auto lane change") == "Estándar · Cambio automático"
  assert c.translate("Green light, lead departure") == "Semáforo en verde, Salida"
  assert c.translate("STANDARD") == "Estándar"


def test_unknown_and_untranslated_text_comes_back_unchanged():
  c = catalog()
  for text in ("Main St", "Untranslated", "62", "Home WiFi · 5 GHz"):
    assert c.translate(text) == text


def test_english_skips_the_catalog(monkeypatch):
  monkeypatch.setattr(i18n, "_language", lambda: "en")
  assert i18n.translate("Sets 12 options") == "Sets 12 options"
  monkeypatch.setattr(i18n, "_language", lambda: "main_es")
  assert i18n.translate("Sets 12 options") == "Ajusta 12 opciones"


def test_po_reader_round_trips_quotes_and_escapes(tmp_path):
  path = tmp_path / "tandem_xx.po"
  tool.write(path, "xx", {'for "{}"': ["a.py:1"], "Line\\one": ["a.py:2"]}, {'for "{}"': 'para "{}"', "Line\\one": "L\\1"}, {})
  assert i18n.parse_po(path.read_text(encoding="utf-8")) == {'for "{}"': 'para "{}"', "Line\\one": "L\\1"}
