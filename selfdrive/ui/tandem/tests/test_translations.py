"""Tandem's translation catalog (i18n.py, tools/translations.py, translations/)."""
import importlib.util
import sys
from pathlib import Path

import pytest

from openpilot.selfdrive.ui.tandem import i18n

TOOLS = Path(__file__).resolve().parents[1] / "tools"
_spec = importlib.util.spec_from_file_location("translations_tool", TOOLS / "translations.py")
tool = importlib.util.module_from_spec(_spec)
sys.modules["translations_tool"] = tool   # dataclasses look their module up
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
  bad = [(k, v) for k, v in entries.items() if isinstance(v, str) and v and "{}" in k and not i18n._holes_fit(k, v)]
  assert not bad
  forms = tool.PLURAL_FORMS.get(code, 2)
  assert all(len(v) == forms for v in entries.values() if isinstance(v, list))


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
  assert i18n.t_("Sets {} options", 12) == "Sets 12 options"
  monkeypatch.setattr(i18n, "_language", lambda: "main_es")
  assert i18n.t_("Sets {} options", 12) == "Ajusta 12 opciones"


def test_po_reader_round_trips_quotes_and_escapes(tmp_path):
  path = tmp_path / "tandem_xx.po"
  entries = {e.key: e for e in (tool.Entry('for "{}"'), tool.Entry("Line\\one"), tool.Entry("Set up", context="action"),
                                  tool.Entry("{} alert", plural="{} alerts"))}
  translated = {'for "{}"': 'para "{}"', "Line\\one": "L\\1", i18n.key("Set up", "action"): "Configurar",
                "{} alert": ["{} alerta", "{} alertas"]}
  tool.write(path, "es", entries, translated, {})
  assert i18n.parse_po(path.read_text(encoding="utf-8")) == translated


def test_the_strings_drivers_reported_missing_are_in_the_catalog():
  """Labels in .get() defaults, the keyboard's space bar, strftime names, captions and StarPilot's own text."""
  pot = i18n.parse_po((i18n.CATALOG_DIR / "tandem.pot").read_text(encoding="utf-8"))
  for msgid in ("Check now", "Working…", "space", "Backup {}", "REGIONS", "{} region selected", "U.S. Midwest Region (12 States)"):
    assert msgid in pot, msgid


def test_keys_icons_and_states_stay_out_of_the_catalog():
  pot = i18n.parse_po((i18n.CATALOG_DIR / "tandem.pot").read_text(encoding="utf-8"))
  for key in ("Total", "Free", "trash", "busy", "roundabout turn"):
    assert key not in pot, key


def test_a_name_with_its_value_keeps_the_value():
  c = i18n.Catalog({"Drives": "Fahrten", "Maps": "Karten"})
  assert c.translate("Drives 21.0 GB") == "Fahrten 21.0 GB"
  assert c.translate("Maps 4 GB") == "Karten 4 GB"
  assert c.translate("Unknown 3 GB") == "Unknown 3 GB"


def test_marking_helpers_in_english(monkeypatch):
  monkeypatch.setattr(i18n, "_language", lambda: "en")
  assert i18n.N_("Off") == "Off" and i18n.N_("Set up", context="action") == "Set up"
  assert i18n.t_("Sets {} options", 12) == "Sets 12 options"
  assert i18n.tn_("{} alert", "{} alerts", 1) == "1 alert" and i18n.tn_("{} alert", "{} alerts", 3) == "3 alerts"


def test_plurals_follow_each_language():
  es = i18n.Catalog({"{} alert": ["{} alerta", "{} alertas"]}, "es", {"{} alert": "{} alerts"})
  ja = i18n.Catalog({"{} alert": ["{}件"]}, "ja", {"{} alert": "{} alerts"})
  assert es.plural("{} alert", "{} alerts", 1, (1,)) == "1 alerta" and es.plural("{} alert", "{} alerts", 4, (4,)) == "4 alertas"
  assert ja.plural("{} alert", "{} alerts", 4, (4,)) == "4件"
  assert es.translate("2 alerts") == "2 alertas" and es.translate("1 alert") == "1 alerta"   # StarPilot's trn() text
  assert [i18n.plural_index("uk", n) for n in (1, 3, 5, 21)] == [0, 1, 2, 0]


def test_context_picks_its_own_translation():
  c = i18n.Catalog({i18n.key("Set up", "action"): "Einrichten", "Set up · protected": "Eingerichtet · geschützt"}, "de")
  assert c.translate(i18n.N_("Set up", context="action")) == "Einrichten"
  assert c.translate("Set up") == "Set up"   # without the context it's another entry (untranslated here)


def test_pseudo_language_brackets_every_marked_string(monkeypatch):
  monkeypatch.setenv("TANDEM_PSEUDO", "1")
  monkeypatch.setattr(i18n, "_loaded", {})
  assert i18n.translate("Driving Style").startswith("[Driving Style ") and i18n.translate("Driving Style").endswith("~]")
  assert i18n.t_("Sets {} options", 3).startswith("[Sets 3 options")
  assert i18n.translate("Main St") == "Main St"   # not marked: stays bare, so the check lists it


def test_the_extractor_reads_marks_and_their_context(tmp_path, monkeypatch):
  (tmp_path / "screen.py").write_text(
    'from x import N_, t_, tn_\nA = N_("One " +\n       "two")\nB = N_("Set up", context="action")\n' +
    'C = t_("Sets {} options", 3)\nD = tn_("{} alert", "{} alerts", 2)\nE = "not marked"\n')
  monkeypatch.setattr(tool, "files", lambda: [tmp_path / "screen.py"])
  monkeypatch.setattr(tool, "PACKAGE", tmp_path)
  monkeypatch.setattr(tool, "UPSTREAM", [])
  monkeypatch.setattr(tool, "UPSTREAM_ALERTS", "none.json")
  entries = tool.strings()
  assert set(entries) == {"One two", i18n.key("Set up", "action"), "Sets {} options", "{} alert"}
  assert entries["{} alert"].plural == "{} alerts"


def test_tandem_templates_dont_rewrite_other_text_as_it_is_drawn():
  """t_() fills Tandem's own templates; draw-time matching is only for the ones flagged "drawn" (StarPilot's, N_())."""
  es = i18n.load("es")
  alert = "openpilot won't automatically start until it connects to internet to check for updates."
  assert es.translate(alert) == alert                       # not "{} hasta las {}"
  assert es.translate("2 regions") == "2 regiones"           # StarPilot's trn() text still matches
  assert es.translate("Backup 2026-10-24 0910").startswith("Copia ")   # an N_() template


def test_the_home_screen_alert_sentences_are_in_the_catalog():
  """StarPilot's offroad alerts (alerts_offroad.json), with %1 as a hole matched when drawn."""
  es = i18n.load("es")
  assert es.translate("Taking camera snapshots. System won't start until finished.").startswith("Tomando capturas")
  assert es.translate("Chestnut USB link is slow. Check the USB cable. The current speed is 480 Mbps.").endswith("es 480 Mbps.")
