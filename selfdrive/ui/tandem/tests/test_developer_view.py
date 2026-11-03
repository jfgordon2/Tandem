from types import SimpleNamespace

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
