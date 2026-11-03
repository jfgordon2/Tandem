import os
"""StarPilot's own AlertRenderer, fed fixed alerts, over the Essentials onroad layers as the view shows them during an alert."""
import sys
import types
import pyray as rl


def _stub_cereal():
  class E:  # enum stand-ins with the values the renderer compares
    pass
  size = type("AlertSize", (), dict(none=0, small=1, mid=2, full=3))
  status = type("AlertStatus", (), dict(normal=0, userPrompt=1, critical=2))
  sp_status = type("AlertStatus", (), dict(starpilot=3))
  log = types.SimpleNamespace(SelfdriveState=types.SimpleNamespace(AlertSize=size, AlertStatus=status))
  custom = types.SimpleNamespace(StarPilotSelfdriveState=types.SimpleNamespace(AlertStatus=sp_status, AlertSize=size))
  cereal = types.ModuleType("cereal")
  cereal.log = log
  cereal.custom = custom
  cereal.messaging = types.SimpleNamespace(SubMaster=object)
  sys.modules.setdefault("cereal", cereal)
  if "openpilot.selfdrive.ui.ui_state" not in sys.modules:
    m = types.ModuleType("openpilot.selfdrive.ui.ui_state")
    m.ui_state = types.SimpleNamespace(sm=None, starpilot_toggles={}, started_time=0, started_frame=0)
    sys.modules["openpilot.selfdrive.ui.ui_state"] = m
  return size, status, sp_status


SIZE, STATUS, SP = _stub_cereal()
from openpilot.selfdrive.ui.onroad import alert_renderer as ar
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.onroad.layers import draw_speed, draw_speed_limit, sign_tile
import scene_onroad
import ast
from openpilot.selfdrive.ui.tandem.onroad import alerts

# The view's EssentialsAlertRenderer, taken from its source so the harness draws exactly what the view does
# (importing view.py would pull in StarPilot's whole onroad stack).
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "onroad", "view.py")).read()
_node = next(n for n in ast.parse(_src).body if isinstance(n, ast.ClassDef) and n.name == "EssentialsAlertRenderer")
_ns = {"AlertRenderer": ar.AlertRenderer, "alerts": alerts, "rl": rl, "Callable": __import__("collections.abc").abc.Callable}
exec(compile(ast.Module([_node], []), "view.py", "exec"), _ns)
EssentialsAlertRenderer = _ns["EssentialsAlertRenderer"]

W, H = 2160, 1080
ENGAGED, DISENGAGED = rl.Color(0x16, 0x7F, 0x40, 255), rl.Color(0x12, 0x28, 0x39, 255)

ALERTS = {
  "alert_green_light": (ar.Alert("Light Turned Green", "", SIZE.small, SP.starpilot), DISENGAGED),
  "alert_lead_departed": (ar.Alert("Lead Departed", "", SIZE.small, SP.starpilot), DISENGAGED),
  "alert_pay_attention": (ar.Alert("Pay Attention", "Driver Distracted", SIZE.mid, STATUS.userPrompt), ENGAGED),
  "alert_take_control": (ar.Alert("Take Control", "Turn Exceeds Steering Limit", SIZE.mid, STATUS.userPrompt), ENGAGED),
  "alert_unavailable": (ar.Alert("openpilot Unavailable", "Cancel Pressed", SIZE.mid, STATUS.normal), DISENGAGED),
  "alert_soft_disable": (ar.Alert("TAKE CONTROL IMMEDIATELY", "Steering Assist Temporarily Unavailable", SIZE.full, STATUS.userPrompt), ENGAGED),
  "alert_fcw": (ar.Alert("BRAKE!", "Risk of Collision", SIZE.full, STATUS.critical), ENGAGED),
  "alert_driver_distracted": (ar.Alert("DISENGAGE IMMEDIATELY", "Driver Distracted", SIZE.full, STATUS.critical), ENGAGED),
  "alert_driver_unresponsive": (ar.Alert("DISENGAGE IMMEDIATELY", "Driver Unresponsive", SIZE.full, STATUS.critical), ENGAGED),
  "alert_system_unresponsive": (ar.Alert("TAKE CONTROL IMMEDIATELY", "System Unresponsive", SIZE.full, STATUS.critical), ENGAGED),
  "alert_calibration": (ar.Alert("Calibrating: 42%", "Drive Above 25 km/h", SIZE.mid, STATUS.normal), DISENGAGED),
  "alert_sensor_fault": (ar.Alert("TAKE CONTROL IMMEDIATELY", "Sensor Data Invalid", SIZE.full, STATUS.critical), ENGAGED),
  "alert_model_restart": (ar.Alert("Big Model Failed", "Restart the car to retry,\nsmall model is still available", SIZE.mid,
                                  STATUS.normal), DISENGAGED),
  "alert_reverse": (ar.Alert("Reverse\nGear", "", SIZE.full, STATUS.normal, "reverseGear/permanent"), DISENGAGED),
}


def scene(alert, border):
  outer = rl.Rectangle(0, 0, W, H)
  rect = rl.Rectangle(30, 30, W - 60, H - 60)
  renderer = EssentialsAlertRenderer()
  renderer.get_alert = lambda sm: alert
  renderer._alpha_filter.x = 1.0
  def render():
    scene_onroad.road(rect)
    draw.stroke(rl.Rectangle(rect.x - 6, rect.y - 6, rect.width + 12, rect.height + 12), rl.Color(0, 0, 0, 255), T.px(18), 16)
    renderer._current_alert = alert
    kind = renderer.level()
    draw.stroke(outer, alerts.border(kind) or border, T.px(18), 36)
    draw_speed(rect, 44, "mph")
    if alert.size != SIZE.full and kind != alerts.CRITICAL:   # the view hides the sign under a takeover
      draw_speed_limit(sign_tile(rect), "45", False)
    # the bar, chip, new-limit card and driver monitor tile all hide while an alert shows
    renderer._current_alert = alert
    renderer._alert_y_filter.x = renderer._get_alert_rect(rect, alert.size).y
    renderer._alert_y_filter.initialized = True
    renderer.render(rect)
  return render


def main(frame, save, out, tap, gui_app):
  for name, (alert, border) in ALERTS.items():
    render = scene(alert, border)
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
