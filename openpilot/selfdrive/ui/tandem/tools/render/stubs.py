"""Stand-ins for openpilot modules whose dependencies (zmq, cereal, ...) aren't installed here."""
import sys
import types


def _mod(name, **attrs):
  m = types.ModuleType(name)
  m.__dict__.update(attrs)
  sys.modules[name] = m
  return m


class _Log:
  def __getattr__(self, _):
    return lambda *a, **k: None


class _Hardware:
  def get_device_type(self):
    return "pc"

  def __getattr__(self, _):
    return lambda *a, **k: None


class _Ratekeeper:
  def __init__(self, *a, **k):
    pass

  def keep_time(self):
    return False

  def monitor_time(self):
    return False


def install():
  _mod("openpilot.common.swaglog", cloudlog=_Log())
  _mod("openpilot.system.hardware", HARDWARE=_Hardware(), PC=True, TICI=False)
  _mod("openpilot.common.realtime", Ratekeeper=_Ratekeeper, config_realtime_process=lambda *a, **k: None, DT_MDL=0.05, DT_CTRL=0.01)
