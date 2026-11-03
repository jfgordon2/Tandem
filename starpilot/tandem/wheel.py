"""Temporary wheel-button discovery for Tandem; upstream's public testing API stays unchanged."""
import os


def start_testing(memory, params=None):
  from openpilot.starpilot.system.wheel_controls.wheel_controlsd import TEST_ACTIVE_PARAM
  memory.put_bool(TEST_ACTIVE_PARAM, True)


def cancel_learning(memory, params):
  from openpilot.starpilot.system.wheel_controls import wheel_controlsd as wc
  memory.remove(wc.LEARN_SLOT_PARAM)
  if params.get_bool(wc.ENABLED_PARAM) and not wc.load_mappings(params) and not wc.selected_joystick_device(params):
    params.put_bool(wc.ENABLED_PARAM, False)


def testing_requested():
  if os.getenv("TANDEM_SETTINGS", "1") == "0":
    return False
  from openpilot.common.params import Params
  return Params(memory=True).get_bool("WheelControlTestActive")


def daemon_type(base):
  if os.getenv("TANDEM_SETTINGS", "1") == "0":
    return base

  class TandemWheelDaemon(base):
    def _testing_allowed(self) -> bool:
      return True

    def _handle_key(self, source, code):
      from openpilot.starpilot.system.wheel_controls.wheel_controlsd import LEARN_SLOT_PARAM
      self._update_testing()
      if self.learning_slot is not None and self.params_memory.get_int(LEARN_SLOT_PARAM) != self.learning_slot + 1:
        self.learning_slot = None
      super()._handle_key(source, code)

  return TandemWheelDaemon
