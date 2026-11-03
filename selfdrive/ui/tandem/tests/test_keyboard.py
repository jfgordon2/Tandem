import pytest

from openpilot.selfdrive.ui.tandem import keyboard as K


@pytest.fixture(autouse=True)
def no_window(monkeypatch):
  """Upstream's constructor makes labels, buttons and textures that need a window; our keyboard replaces them all."""
  monkeypatch.setattr(K.upstream, "Label", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream, "Button", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream.gui_app, "texture", lambda *a, **k: None)


def _press(kb, key):
  kb._all_keys[key]._click_callback()


def test_typing_shift_and_layers_use_upstream_behavior():
  kb = K.EssentialsKeyboard(min_text_size=6, action="Set up")
  for key in "tan":
    _press(kb, key)
  _press(kb, K.SHIFT_OFF)
  _press(kb, "D")                       # shift is on for one letter, as upstream's
  assert kb.text == "tanD" and kb._layout_name == "lowercase"
  _press(kb, K.NUMBERS)
  _press(kb, "4")
  _press(kb, K.BACKSPACE)
  _press(kb, "2")
  assert kb.text == "tanD2" and kb._layout_name == "numbers"
  _press(kb, K.LETTERS)
  assert kb._layout_name == "lowercase"


def test_every_key_in_every_layer_has_a_widget():
  kb = K.EssentialsKeyboard()
  for rows in K.LAYOUTS.values():
    assert len(rows) == 4
    for keys in rows:
      for key in keys:
        assert key in kb._all_keys
  assert K.CAPS in kb._all_keys


def test_title_and_action_are_ours():
  kb = K.EssentialsKeyboard(action="Save")
  kb.set_title("Discord username", "Optional")
  kb.set_action("Next")
  assert (kb._title_text, kb._subtitle_text, kb.action) == ("Discord username", "Optional", "Next")


def test_field_uses_its_own_face_for_the_text_and_cursor(monkeypatch):
  from openpilot.system.ui.widgets.inputbox import InputBox

  own_font, upstream_font = object(), object()
  monkeypatch.setattr(K.draw, "_face", lambda text, face: own_font)
  monkeypatch.setattr(K.upstream.gui_app, "font", lambda *args: upstream_font)
  assert K._Field()._get_font() is own_font
  assert InputBox()._get_font() is upstream_font
