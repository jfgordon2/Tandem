from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.selfdrive.ui.tandem import i18n

SMALL, MID, FULL = 1, 2, 3
NORMAL, PROMPT, CRITICAL, STARPILOT = 0, 1, 2, 3


def test_levels_follow_status_and_size():
  assert alerts.level(SMALL, STARPILOT, "greenLight/permanent") == alerts.INFO       # Light Turned Green
  assert alerts.level(MID, NORMAL, "buttonCancel/noEntry") == alerts.INFO            # openpilot Unavailable
  assert alerts.level(SMALL, NORMAL) == alerts.INFO                                  # Pay Attention, early
  assert alerts.level(MID, PROMPT, "promptDriverDistracted/permanent") == alerts.WARNING
  assert alerts.level(SMALL, PROMPT) == alerts.WARNING
  assert alerts.level(FULL, PROMPT, "steerTempUnavailable/softDisable") == alerts.CRITICAL
  assert alerts.level(FULL, CRITICAL, "fcw/permanent") == alerts.CRITICAL
  assert alerts.level(MID, CRITICAL) == alerts.CRITICAL                              # openpilot crashed


def test_reverse_gear_keeps_upstream_drawing():
  assert alerts.level(FULL, NORMAL, "reverseGear/permanent") == alerts.REVERSE


def test_border_only_for_warning_and_critical():
  assert alerts.border(alerts.INFO) is None
  assert alerts.border(None) is None
  assert alerts.border(alerts.WARNING) == alerts.WARNING_BORDER
  assert alerts.border(alerts.CRITICAL) == alerts.CRITICAL_BORDER


def test_routine_status_banners_go_to_chips():
  assert alerts.shown_as_chip("greenLight/permanent")
  assert alerts.shown_as_chip("leadDeparting/permanent")
  assert alerts.shown_as_chip("laneChange/warning")
  assert alerts.shown_as_chip("turningLeft/warning")
  assert alerts.shown_as_chip("turningRight/warning")
  assert alerts.shown_as_chip("laneChangeBlocked/warning")       # Lane change blocked; the chime still plays
  assert alerts.shown_as_chip("laneChangeBlockedLoud/warning")
  assert not alerts.shown_as_chip("preLaneChangeLeft/warning")
  assert not alerts.shown_as_chip("preLaneChangeRight/warning")
  assert not alerts.shown_as_chip("personalityChanged/warning")
  assert not alerts.shown_as_chip("speedLimitChanged/permanent")   # hidden only while the new-limit card asks (view.py)
  assert not alerts.shown_as_chip("promptDriverDistracted/permanent")
  assert not alerts.shown_as_chip("")


def test_alerts_translate_before_folding_upstream_line_breaks(monkeypatch):
  monkeypatch.setattr(i18n, "_language", lambda: "main_tr")
  assert alerts._clean("TAKE CONTROL IMMEDIATELY") == "HEMEN KONTROLÜ DEVRALIN"
  assert alerts._clean("Restart the car to retry,\nsmall model is still available") == \
    "Yeniden denemek için aracı yeniden çalıştırın, küçük model hâlâ kullanılabilir"


def test_reverse_gear_translation_only_changes_the_display_copy(monkeypatch):
  from dataclasses import dataclass
  from types import SimpleNamespace

  @dataclass
  class Alert:
    text1: str
    text2: str
    size: int = FULL
    status: int = NORMAL
    alert_type: str = "reverseGear/permanent"

  monkeypatch.setattr(i18n, "_language", lambda: "main_uk")
  source = Alert("Reverse\nGear", "")
  display = alerts.translated(source)
  assert display.text1 == "Задня\nпередача"
  assert source.text1 == "Reverse\nGear"
  assert (display.size, display.status, display.alert_type) == (source.size, source.status, source.alert_type)
  faces, drawn = [], []
  monkeypatch.setattr(alerts, "face_for", lambda text, face: faces.append(text) or alerts.T.FONT_UNIFONT)
  selected = []
  label = SimpleNamespace(set_font_weight=selected.append)
  alerts.draw_reverse(source, label, label, drawn.append)
  assert faces == ["Задняпередача", ""]
  assert selected == [alerts.T.FONT_UNIFONT, alerts.T.FONT_UNIFONT]
  assert drawn[0].text1 == display.text1
  assert source.text1 == "Reverse\nGear"
