from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.tandem.settings import software_tab as S
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeUpdates


class Window:
  def __init__(self):
    self.shown = []

  def present(self, overlay):
    self.shown.append(overlay)

  def dismiss(self):
    pass

  @property
  def top(self):
    return self.shown[-1]


class Model:
  def __init__(self):
    self.actions = FakeUpdates()

  def version_parts(self):
    return "0.10.1", "release"


def test_uninstall_asks_three_times_like_upstream():
  for answers, expected in [((DialogResult.CANCEL,), []),
                            ((DialogResult.CONFIRM, DialogResult.CANCEL), [("uninstall", False)]),          # Skip keeps data
                            ((DialogResult.CONFIRM, DialogResult.CONFIRM, DialogResult.CONFIRM), [("uninstall", True)]),
                            ((DialogResult.CONFIRM, DialogResult.CONFIRM, DialogResult.CANCEL), [("uninstall", False)])]:
    model, window = Model(), Window()
    S.uninstall(model, window)
    for answer in answers:
      window.top._finish(answer)
    assert model.actions.calls == expected, answers


def test_branch_sheet_sets_the_target():
  model, window = Model(), Window()
  S.choose_branch(model, window)
  window.top._body._on_change(1)
  assert model.actions.calls == [("branch", "staging")]


def test_release_notes_become_plain_text():
  html = "<h1>Version 0.10.1</h1><ul><li>Smoother &amp; calmer</li><li>Fixes</li></ul><p>Thanks!</p>"
  assert S.notes_text(html) == "Version 0.10.1\n• Smoother & calmer\n• Fixes\nThanks!"
  assert S.notes_text("") == "No release notes for this version."


def test_sound_test_counts_down_in_our_dialog():
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import sound_test
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth
  bt, window = FakeBluetooth(), Window()
  sound_test(bt, "AA", window)
  assert bt.calls == [("test", "AA")]
  assert not window.top._cancel.is_visible           # a notice with one button
  from openpilot.selfdrive.ui.tandem.base import resolve
  assert resolve(window.top._message) == "A sound plays in 3…"


def test_face_box_follows_upstreams_mapping():
  import pyray as rl
  from openpilot.selfdrive.ui.tandem.drivercamera import face_box
  box = face_box(0.0, 0.109, rl.Rectangle(0, 0, 2160, 1080))
  assert (round(box.x), round(box.y), box.width) == (970, 390, 220)   # centered at upstream's (1080, 500)
  half = face_box(0.0, 0.109, rl.Rectangle(0, 0, 1080, 540))
  assert half.width == 110                                              # scales with the view


def _bt_window():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth
  return FakeBluetooth(), Window()


def test_connected_device_opens_our_sheet_and_forget_asks_first():
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.overlays import Dialog, Sheet
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import device_sheet
  bt, window = _bt_window()
  car = bt.status().devices[0]
  assert bt.select(car.address)                          # connected: its actions, not upstream's option list
  sheet = device_sheet(bt, car, window)
  window.present(sheet)
  assert isinstance(window.top, Sheet)
  rows = {r._title: r for r in sheet._body._items if hasattr(r, "_title")}
  rows["Alerts and Chimes"]._control._on_change(False)
  assert ("audio", "") in bt.calls
  rows["Forget"]._control._click_callback()
  assert isinstance(window.top, Dialog) and ("forget", "AA") not in bt.calls   # asks first
  window.top._finish(DialogResult.CONFIRM)
  assert ("forget", "AA") in bt.calls


def test_pairing_prompts_use_our_dialog_and_answer_the_device():
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import pairing_prompt
  bt, window = _bt_window()
  pairing_prompt(bt, {"id": "p1", "name": "Pixel 9", "kind": "confirm", "value": "123456"}, window)
  assert isinstance(window.top, Dialog) and window.top._title == "Pair with Pixel 9?"
  window.top._finish(DialogResult.CONFIRM)
  assert bt.calls[-1] == ("respond", "p1", True, "")
  pairing_prompt(bt, {"id": "p2", "name": "Pixel 9", "display_only": True, "value": "Enter 0000 on the device"}, window)
  assert not window.top._cancel.is_visible                # a notice; nothing to answer


def test_model_notices_come_back_as_messages_not_upstream_boxes(monkeypatch):
  from openpilot.system.ui.lib.application import gui_app
  from openpilot.selfdrive.ui.tandem.settings.controllers import notice_controller
  pushed, messages = [], []
  monkeypatch.setattr(gui_app, "push_widget", pushed.append)

  class Controller:
    def _show_notice(self, message):
      gui_app.push_widget(message)

    def download(self):
      self._show_notice("Cannot download models while driving.")

  notice_controller(Controller, messages.append)().download()
  assert messages == ["Cannot download models while driving."] and not pushed
  Controller().download()
  assert pushed == ["Cannot download models while driving."]
