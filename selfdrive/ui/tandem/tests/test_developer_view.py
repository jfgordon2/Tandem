from types import SimpleNamespace

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, i18n
from openpilot.selfdrive.ui.tandem.onroad import developer as D


def test_strip_keys_reads_known_metrics_in_order_and_caps_at_five():
  assert D.strip_keys(None) == list(D.STRIP_DEFAULT) and D.strip_keys("") == list(D.STRIP_DEFAULT)
  assert D.strip_keys("none") == []
  assert D.strip_keys(b"delay,steer,bogus,accel") == ["accel", "delay", "steer"]
  assert len(D.strip_keys(",".join(D.STRIP_METRICS))) == D.STRIP_MAX


class _Params:
  def __init__(self, values):
    self.values = values

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def get(self, key, return_default=False):
    return self.values.get(key)


def _ui(toggles):
  return SimpleNamespace(sm=SimpleNamespace(valid={}), is_metric=False, starpilot_toggles=toggles)


def test_rows_follow_starpilots_switches_and_the_strip_follows_the_pick():
  D.DEVELOPER_STRIP.set("steer,accel")
  data = D.read(_ui({"cpu_metrics": False, "numerical_temp": True, "gpu_metrics": False, "memory_metrics": True,
                     "show_fps": False, "adjacent_path_metrics": False, "speed_limit_sources": True}),
                _Params({D.STRIP_PARAM: "steer,accel"}))
  assert (data.show_cpu, data.show_temp, data.show_gpu, data.show_ram, data.show_fps) == (False, True, False, True, False)
  assert not data.show_lanes and data.show_source
  assert [label for label, _ in data.strip_values()] == ["accel", "steer"]
  # Before StarPilot's toggles arrive, the params decide
  D.DEVELOPER_STRIP.set(",".join(D.STRIP_DEFAULT))
  data = D.read(_ui({}), _Params({"ShowGPU": True}))
  assert data.show_gpu and not data.show_cpu and data.strip == D.STRIP_DEFAULT


def test_strip_follows_the_developer_view_switch_not_developer_ui_alone():
  params = _Params({"DeveloperUI": True, "DeveloperSidebar": True})
  assert D.developer_view_on(_ui({}), params)
  # Developer View off, Lead Insights on: Developer UI stays on, the strip goes
  assert not D.developer_view_on(_ui({"developer_ui": True, "developer_sidebar": False}), params)
  assert not D.developer_view_on(_ui({"developer_ui": False, "developer_sidebar": True}), params)
  assert D.developer_view_on(_ui({"developer_ui": True, "developer_sidebar": True}), _Params({}))


def test_strip_translates_labels_and_keeps_a_gap_before_values(monkeypatch):
  labels = []
  monkeypatch.setattr(draw, "fill", lambda *args: None)
  monkeypatch.setattr(draw, "text_width", lambda *args: 20)
  monkeypatch.setattr(draw, "fit", lambda value, *args: value)
  monkeypatch.setattr(draw, "text", lambda rect, value, *args: labels.append((rect, value)))
  for code, expected in (("es", ["acel.", "objetivo", "dirección"]), ("ar", ["تسارع", "مطلوب", "توجيه"])):
    monkeypatch.setattr(i18n, "_language", lambda c=code: c)
    labels.clear()
    D.draw_strip(rl.Rectangle(0, 0, 1200, D.strip_h()), D.DevData(strip=("accel", "want", "steer")))
    assert [value for _, value in labels[::2]] == expected
    for (label, _), (value, _) in zip(labels[::2], labels[1::2], strict=True):
      assert value.x > label.x + label.width


def test_long_translated_strip_labels_fit_without_shortening_the_numbers(monkeypatch):
  monkeypatch.setattr(D, "translate", lambda value: "long translated metric label" * 20)
  monkeypatch.setattr(draw, "fill", lambda *args: None)
  monkeypatch.setattr(draw, "text_width", lambda value, *args: len(value))
  monkeypatch.setattr(draw, "fit", lambda value, size, weight, width: value[:int(width)])
  drawn = []
  monkeypatch.setattr(draw, "text", lambda rect, value, *args: drawn.append((rect, value)))
  rect = rl.Rectangle(0, 0, 1200, D.strip_h())
  data = D.DevData()
  D.draw_strip(rect, data)
  cells = D.row(D.inset(rect, x=D.T.px(20)), [D.FILL] * len(data.strip), D.T.px(12))
  for (label, _), (value, text), cell, (_, expected) in zip(drawn[::2], drawn[1::2], cells, data.strip_values(), strict=True):
    assert label.x >= cell.x and value.x + value.width <= cell.x + cell.width
    assert text == expected
