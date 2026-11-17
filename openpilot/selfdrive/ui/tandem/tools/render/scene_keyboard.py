from openpilot.starpilot.ui.raylib import rl
from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard


def main(frame, save, out, tap, gui_app):
  kb = EssentialsKeyboard(min_text_size=6, password_mode=True, show_password_toggle=True, action="Set up")
  kb.set_title("Choose a Galaxy password", "At least 6 characters. Galaxy asks for it when you sign in.")
  kb.set_text("tandem")
  kb._input_box._last_char_time = 0   # past the brief reveal of the last character
  rect = rl.Rectangle(0, 0, 2160, 1080)
  for _ in range(6):
    frame(lambda: kb.render(rect))
  save(f"{out}/keyboard.png")
  kb.set_text("tan")
  kb.handle_key_press("123")
  for _ in range(6):
    frame(lambda: kb.render(rect))
  save(f"{out}/keyboard_numbers.png")
