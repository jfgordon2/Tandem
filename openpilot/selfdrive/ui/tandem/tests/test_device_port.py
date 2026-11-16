"""Release-style Settings and Device actions on the StarPilot 7 widget contracts."""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem.settings.device import Calibration, device_page
from openpilot.selfdrive.ui.tandem.settings.device_owner import DeviceOwner
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab, confirm
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.widgets import DialogResult, Widget


class Page(Widget):
  """Record visit lifecycle without native services."""

  def __init__(self) -> None:
    super().__init__()
    self.shown = 0
    self.hidden = 0

  def show_event(self) -> None:
    self.shown += 1

  def hide_event(self) -> None:
    self.hidden += 1

  def _render(self, rect: rl.Rectangle) -> None:
    pass


def test_tabs_keep_independent_stack_and_close_from_root() -> None:
  close = Mock()
  driving, device, pairing = Page(), Page(), Page()
  window = SettingsWindow({Tab.DRIVING: lambda: driving, Tab.DEVICE: lambda: device}, close)
  window.show_event()
  window.select_tab(Tab.DEVICE)
  window.push(pairing)
  window.select_tab(Tab.DRIVING)
  assert window.top is driving and not window.can_go_back()
  window.select_tab(Tab.DEVICE)
  assert window.top is pairing and window.can_go_back()
  window.back()
  assert window.top is device and not window.can_go_back()
  window.back()
  assert (driving.shown, driving.hidden, device.shown, device.hidden, pairing.shown, pairing.hidden) == (2, 2, 2, 1, 2, 2)
  close.assert_called_once_with()


def test_release_modal_cancel_and_confirm() -> None:
  root = Page()
  window = SettingsWindow({Tab.DEVICE: lambda: root}, Mock(), initial=Tab.DEVICE)
  action = Mock()
  confirm(window, "Restart?", "Restart message", "Restart", action)
  window._overlay._finish(DialogResult.CANCEL)
  assert window._overlay is None
  action.assert_not_called()
  confirm(window, "Restart?", "Restart message", "Restart", action)
  window._overlay._finish(DialogResult.CONFIRM)
  assert window._overlay is None
  action.assert_called_once_with()


def test_device_keeps_release_rows_and_conditional_sections() -> None:
  device = Mock()
  device.calibration.return_value = Calibration.CALIBRATED
  device.is_paired.return_value = False
  device.pairing_supported.return_value = True
  device.is_offroad.return_value = False
  device.can_recalibrate.return_value = False
  device.provider_name.return_value = "comma connect"
  device.provider_web.return_value = "https://connect.comma.ai"
  sections = [Section("General", Page), Section("Backups", Page), Section("Storage & Data", Page),
              Section("RAM", Page, visible=False), Section("Report a Problem", Page), Section("Developer", Page, visible=False)]
  window = SettingsWindow({Tab.DEVICE: lambda: device_page(window, device, sections)}, Mock(), initial=Tab.DEVICE)
  window.show_event()
  root = window.top
  assert [s.label for s in root._sections] == [
    "This Device", "General", "Backups", "Storage & Data", "RAM", "Report a Problem", "Developer",
  ]
  panel = root.current
  rows = {item._title: item for item in panel.items if hasattr(item, "_title")}
  assert list(rows) == ["Phone App", "Remote Access", "Camera Calibration", "How It Works", "Regulatory", "Device ID and Serial", "IMEI"]
  assert rows["Phone App"]._control.is_visible
  assert not rows["Camera Calibration"]._control.enabled and not panel._footer._buttons[1].enabled
  root.select(4)
  assert root.selected == 0
  rows["Phone App"]._control._click_callback()
  assert window.can_go_back()
  window.back()
  device.is_paired.return_value = True
  assert not rows["Phone App"]._control.is_visible


def test_device_rechecks_authority_for_calibration_and_power(monkeypatch: pytest.MonkeyPatch) -> None:
  reset = SimpleNamespace(pending=False, request=Mock(return_value=True))
  module = ModuleType("openpilot.starpilot.ui.calibration_reset")
  module.calibration_reset = reset
  monkeypatch.setitem(sys.modules, module.__name__, module)
  ui = SimpleNamespace(engaged=False, is_offroad=Mock(return_value=True), projection_read_only=False, replay_clock=None, params=Mock())
  ui.params.get_bool.return_value = False
  device = DeviceOwner(ui, Mock(), Mock())

  ui.engaged = True
  device.recalibrate()
  device.restart()
  device.power_off()
  reset.request.assert_not_called()
  ui.params.put_bool.assert_not_called()

  ui.engaged = False
  ui.is_offroad.return_value = False
  device.power_off()
  ui.params.put_bool.assert_not_called()

  ui.is_offroad.return_value = True
  reset.pending = True
  device.recalibrate()
  reset.request.assert_not_called()
  reset.pending = False
  ui.params.get_bool.return_value = True
  device.recalibrate()
  reset.request.assert_not_called()
  assert device.calibration() == Calibration.UNKNOWN
  ui.params.get_bool.return_value = False
  device.recalibrate()
  reset.request.assert_called_once_with(ui.params)
  assert device.calibration() == Calibration.CALIBRATING

  device.restart()
  device.power_off()
  assert [call.args for call in ui.params.put_bool.call_args_list] == [("DoReboot", True), ("DoShutdown", True)]
  ui.projection_read_only = True
  device.restart()
  device.power_off()
  assert ui.params.put_bool.call_count == 2
