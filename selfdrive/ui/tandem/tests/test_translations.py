"""Tandem's translation catalog (i18n.py, tools/translations.py, translations/)."""
import importlib.util
import re
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


@pytest.mark.parametrize("code", ["ar", "de", "es", "fr", "ja", "ko", "pt-BR", "th", "tr", "uk", "zh-CHS", "zh-CHT"])
def test_completed_languages_translate_every_entry_and_plural_form(code):
  entries = i18n.parse_po((i18n.CATALOG_DIR / f"tandem_{code}.po").read_text(encoding="utf-8"))
  assert set(entries) == set(tool.strings())
  for k, value in entries.items():
    source = k.split(i18n.CONTEXT)[-1]
    for form in value if isinstance(value, list) else [value]:
      assert form.strip(), (code, k)
      assert i18n._holes_fit(source, form), (code, k, form)
      assert re.findall(r"</?[^>]+>", source) == re.findall(r"</?[^>]+>", form), (code, k)
      assert all(url.rstrip(".") in form for url in re.findall(r"https?://[\w./-]+", source)), (code, k)
      assert source.count("\n") == form.count("\n"), (code, k)


@pytest.mark.parametrize("code,driving,setup,direction,alerts,regions,minutes", [
  ("fr", "Conduite", "Configurer", "Changement de voie vers la gauche", ("alerte", "alertes"),
   ("région", "régions"), "il y a 2 minutes"),
  ("pt-BR", "Condução", "Configurar", "Mudando de faixa à esquerda", ("alerta", "alertas"),
   ("região", "regiões"), "há 2 minutos"),
])
def test_completed_languages_work_from_the_language_picker(monkeypatch, code, driving, setup, direction, alerts, regions, minutes):
  monkeypatch.setattr(i18n, "_language", lambda: f"main_{code}")
  assert i18n.translate("Driving") == driving
  assert i18n.translate(i18n.N_("Set up", context="action")) == setup
  assert i18n.t_("Changing lanes {}", "left") == direction
  for n in (0, 1, 2):
    index = 0 if n <= 1 else 1
    assert i18n.tn_("{} alert", "{} alerts", n) == f"{n} {alerts[index]}"
    assert i18n.translate(f"{n} region" + ("s" if n != 1 else "")) == f"{n} {regions[index]}"
  assert i18n.translate("2 minutes ago") == minutes


@pytest.mark.parametrize("code,curve,pressed,active,join", [
  ("de", "Kurventempo", "GEDRÜCKT", "aktiv · 62 km/h", ", dann "),
  ("es", "vel. curva", "PULSADO", "activo · 62 km/h", ", después "),
  ("ja", "カーブ速度", "押されました", "動作中 · 62 km/h", "、次に"),
])
def test_developer_labels_and_setup_join_follow_the_selected_language(monkeypatch, code, curve, pressed, active, join):
  monkeypatch.setattr(i18n, "_language", lambda: f"main_{code}")
  assert i18n.translate("curve spd") == curve
  assert i18n.translate("PRESSED") == pressed
  assert i18n.t_("active · {} {}", 62, "km/h") == active
  assert i18n.translate(", then ") == join
  for literal in ("{} m/s²", "St", "Hwy", "RGB", "IL, IN, IA, KS, MI, MN, MO, NE, ND, OH, SD, WI"):
    assert i18n.translate(literal) == literal


@pytest.mark.parametrize("code,driving,setup,direction,forecast,alerts,regions,minutes", [
  ("ko", "주행", "설정", "왼쪽 차로로 변경 중", "12분 후 비", "알림 {}개", "지역 {}개", "2분 전"),
  ("zh-CHS", "驾驶", "设置", "正在向左侧变道", "12分钟后雨", "{}条警报", "{}个地区", "2分钟前"),
  ("zh-CHT", "駕駛", "設定", "正在向左側變換車道", "12分鐘後雨", "{}則警報", "{}個地區", "2分鐘前"),
])
def test_cjk_languages_translate_values_and_counts(monkeypatch, code, driving, setup, direction, forecast, alerts, regions, minutes):
  monkeypatch.setattr(i18n, "_language", lambda: f"main_{code}")
  assert i18n.translate("Driving") == driving
  assert i18n.translate(i18n.N_("Set up", context="action")) == setup
  assert i18n.t_("Changing lanes {}", "left") == direction
  assert i18n.t_("{} in {} min", "Rain", 12) == forecast
  for n in (0, 1, 2, 21):
    assert i18n.tn_("{} alert", "{} alerts", n) == alerts.format(n)
    assert i18n.translate(f"{n} region" + ("s" if n != 1 else "")) == regions.format(n)
  assert i18n.translate("2 minutes ago") == minutes


@pytest.mark.parametrize("code,driving,setup,direction,forecast", [
  ("tr", "Sürüş", "Kur", "sol şeride geçiyor", "12 dk sonra Yağmur"),
  ("uk", "Водіння", "Налаштувати", "Зміна смуги: ліворуч", "Дощ через 12 хв"),
])
def test_turkish_and_ukrainian_follow_the_language_picker(monkeypatch, code, driving, setup, direction, forecast):
  monkeypatch.setattr(i18n, "_language", lambda: f"main_{code}")
  assert i18n.translate("Driving") == driving
  assert i18n.translate(i18n.N_("Set up", context="action")) == setup
  assert i18n.t_("Changing lanes {}", "left") == direction
  assert i18n.t_("{} in {} min", "Rain", 12) == forecast


@pytest.mark.parametrize("n,alert,region,minute", [
  (0, "попереджень", "регіонів", "хвилин"),
  (1, "попередження", "регіон", "хвилину"),
  (2, "попередження", "регіони", "хвилини"),
  (5, "попереджень", "регіонів", "хвилин"),
  (11, "попереджень", "регіонів", "хвилин"),
  (12, "попереджень", "регіонів", "хвилин"),
  (14, "попереджень", "регіонів", "хвилин"),
  (21, "попередження", "регіон", "хвилину"),
  (22, "попередження", "регіони", "хвилини"),
  (25, "попереджень", "регіонів", "хвилин"),
  (101, "попередження", "регіон", "хвилину"),
])
def test_ukrainian_counts_keep_all_three_forms(monkeypatch, n, alert, region, minute):
  monkeypatch.setattr(i18n, "_language", lambda: "main_uk")
  assert i18n.tn_("{} alert", "{} alerts", n) == f"{n} {alert}"
  assert i18n.translate(f"{n} region" + ("s" if n != 1 else "")) == f"{n} {region}"
  assert i18n.translate(f"{n} minute" + ("s" if n != 1 else "") + " ago") == f"{n} {minute} тому"


def test_turkish_nouns_after_numbers_keep_the_same_form(monkeypatch):
  monkeypatch.setattr(i18n, "_language", lambda: "main_tr")
  for n in (0, 1, 2, 21):
    assert i18n.tn_("{} alert", "{} alerts", n) == f"{n} uyarı"
    assert i18n.translate(f"{n} regions") == f"{n} bölge"


@pytest.mark.parametrize("code,label,caption", [
  ("en", "Device", "DEVICE"),
  ("tr", "Device", "CİHAZ"),
  ("main_tr", "Driving Model", "SÜRÜŞ MODELİ"),
  ("tr", "ışık", "IŞIK"),
  ("uk", "Device", "ПРИСТРІЙ"),
])
def test_captions_use_the_selected_languages_uppercase(monkeypatch, code, label, caption):
  from openpilot.selfdrive.ui.tandem import draw
  monkeypatch.setattr(i18n, "_language", lambda: code)
  drawn = []
  monkeypatch.setattr(draw, "text", lambda rect, value, *args, **kwargs: drawn.append(value))
  draw.caption(None, label)
  assert drawn == [caption]


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
  monkeypatch.setattr(tool, "ONROAD_ALERTS", "none.py")
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


def test_the_extractor_follows_onroad_text_without_importing_the_driving_stack(tmp_path, monkeypatch):
  (tmp_path / "events.py").write_text('''
raise RuntimeError("must not import the events module")
class SoftDisableAlert(Alert):
  def __init__(self, alert_text_2):
    super().__init__("TAKE CONTROL IMMEDIATELY", alert_text_2, Status.critical)
def alert_callback(speed, n, CP):
  title = "Drive safely" if CP.ready else "Wait to engage"
  detail = f"Drive above {speed:.1f} km/h"
  Alert(title, detail, Status.normal)
  NoEntryAlert(f"{n} minute{'s' if n != 1 else ''} Left", alert_text_1="Too Distracted")
  Alert(CP.custom_title, CP.custom_detail, Status.normal)
  return soft_disable_alert("Steering Temporarily Unavailable")
''')
  monkeypatch.setattr(tool, "files", list)
  monkeypatch.setattr(tool, "UPSTREAM", [])
  monkeypatch.setattr(tool, "UPSTREAM_ALERTS", "none.json")
  monkeypatch.setattr(tool, "ROOT", tmp_path)
  monkeypatch.setattr(tool, "ONROAD_ALERTS", "events.py")
  entries = tool.strings()
  assert set(entries) == {"TAKE CONTROL IMMEDIATELY", "Drive safely", "Wait to engage", "Drive above {} km/h",
                          "{} minute Left", "Too Distracted", "Steering Temporarily Unavailable"}
  assert entries["{} minute Left"].plural == "{} minutes Left"
  assert all(e.drawn for e in entries.values())


@pytest.mark.parametrize("code", LANGUAGES)
def test_operational_alerts_translate_in_every_completed_language(monkeypatch, code):
  monkeypatch.setattr(i18n, "_language", lambda: f"main_{code}")
  for text in ("TAKE CONTROL IMMEDIATELY", "System Unresponsive", "BRAKE!", "Risk of Collision", "DISENGAGE IMMEDIATELY",
               "Driver Distracted", "Driver Unresponsive", "Steering Assist Temporarily Unavailable", "Take Control",
               "Turn Exceeds Steering Limit", "Cancel Pressed", "Reverse\nGear"):
    assert i18n.translate(text) != text, (code, text)
  for text in ("Drive above 30 km/h to engage", "Steer Unavailable Under 20 mph", "Calibrating: 42%",
               "Speed Error: -3.5 m/s", "Detected Lane Width Is Only 2.1 Meters"):
    translated = i18n.translate(text)
    assert translated != text, (code, text)
    assert re.findall(r"-?\d+(?:\.\d+)?", translated) == re.findall(r"-?\d+(?:\.\d+)?", text)


def test_onroad_alert_plurals_follow_the_selected_language(monkeypatch):
  monkeypatch.setattr(i18n, "_language", lambda: "main_uk")
  for n, minute, second in ((1, "хвилина", "секунда"), (2, "хвилини", "секунди"), (5, "хвилин", "секунд"),
                             (21, "хвилина", "секунда")):
    left = "Залишилася" if n in (1, 21) else "Залишилося"
    assert i18n.translate(f"{n} minute" + ("s" if n != 1 else "") + " Left") == f"{left} {n} {minute}"
    assert i18n.translate(f"{n} second" + ("s" if n != 1 else "") + " remaining. Press again to save early.") == \
      f"{left} {n} {second}. Натисніть ще раз, щоб зберегти раніше."


def test_every_picker_language_has_a_complete_catalog():
  import json
  from openpilot.selfdrive.ui.tandem.settings.device_sections import picker_languages
  path = tool.ROOT / "selfdrive/ui/translations/languages.json"
  languages = list(json.loads(path.read_text(encoding="utf-8")).items())
  codes = {code.removeprefix("main_") for _, code in picker_languages(languages, "en")} - {"en"}
  assert codes == set(LANGUAGES)
  for code in codes:
    assert all(tool.done(v) for v in tool.read(i18n.CATALOG_DIR / f"tandem_{code}.po")[0].values()), code


@pytest.mark.parametrize("code,driving,takeover,direction", [
  ("ar", "القيادة", "تول القيادة فورا", "تغيير المسار يسارا"),
  ("th", "การขับขี่", "เข้าควบคุมรถทันที", "กำลังเปลี่ยนเลนไปทางซ้าย"),
])
def test_arabic_and_thai_follow_the_picker(monkeypatch, code, driving, takeover, direction):
  monkeypatch.setattr(i18n, "_language", lambda: f"main_{code}")
  assert i18n.translate("Driving") == driving
  assert i18n.translate("TAKE CONTROL IMMEDIATELY") == takeover
  assert i18n.t_("Changing lanes {}", "left") == direction


@pytest.mark.parametrize("n,expected", [
  (0, "لا تنبيهات (0)"), (1, "تنبيه واحد (1)"), (2, "تنبيهان (2)"),
  (3, "3 تنبيهات"), (11, "11 تنبيها"), (100, "100 تنبيه"),
])
def test_arabic_uses_all_six_count_forms(monkeypatch, n, expected):
  monkeypatch.setattr(i18n, "_language", lambda: "main_ar")
  assert i18n.tn_("{} alert", "{} alerts", n) == expected


def test_thai_counts_do_not_add_an_english_plural(monkeypatch):
  monkeypatch.setattr(i18n, "_language", lambda: "main_th")
  for n in (0, 1, 2, 21):
    assert i18n.tn_("{} alert", "{} alerts", n) == f"การแจ้งเตือน {n} รายการ"


@pytest.mark.parametrize("code", ["ar", "th"])
def test_joined_scripts_do_not_get_caption_letter_spacing(monkeypatch, code):
  from openpilot.selfdrive.ui.tandem import draw
  monkeypatch.setattr(i18n, "_language", lambda: code)
  called = []
  monkeypatch.setattr(draw, "text", lambda *args, **kwargs: called.append(kwargs))
  draw.caption(None, "Device")
  assert called[0]["tracking"] == 0


@pytest.mark.parametrize("code,auto,pair,lead,coast", [
  ("ar", "تلقائي", "إقران", "المركبة الأمامية", "سير حر"),
  ("th", "อัตโนมัติ", "จับคู่", "รถคันหน้า", "ไหลตามแรงเฉื่อย"),
])
def test_arabic_and_thai_labels_use_the_automotive_meaning(monkeypatch, code, auto, pair, lead, coast):
  monkeypatch.setattr(i18n, "_language", lambda: code)
  assert [i18n.translate(s) for s in ("Auto", "Pair", "Lead", "Coast")] == [auto, pair, lead, coast]


@pytest.mark.parametrize("code", ["ar", "th"])
def test_arabic_and_thai_keep_service_names_domains_and_scopes(code):
  catalog = i18n.load(code)
  for source, tokens in (
    ("Chestnut not found", ("Chestnut",)),
    ("Open connect.comma.ai", ("connect.comma.ai",)),
    ("Please post the 'Error Log' in the StarPilot Discord!", ("StarPilot", "Discord")),
    ("Your default public token (pk.) is there already. Create a token, keep its public scopes, "
     + "and also check DOWNLOADS:READ so it starts with sk.", ("pk.", "sk.", "DOWNLOADS:READ")),
  ):
    translated = catalog.translate(source)
    assert translated != source
    assert all(token in translated for token in tokens), (source, translated)
