"""openpilot's Developer panel (Settings › Device › Developer, with Tuner Mode on), in our rows.

The same params and side effects as upstream's DeveloperLayout: ADB and SSH, GitHub SSH keys (upstream's SshKeyFetcher),
joystick debug, alpha longitudinal (only where the car offers it, with its warning), and UI debug (touches and FPS).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch, Tone
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

ALPHA_WARNING = N_("openpilot longitudinal control is in alpha for this car and turns off Automatic Emergency Braking (AEB). " +
                   "The car's own cruise control is the default. Experimental mode is recommended with it. " +
                   "openpilot restarts if the car is on.")


class DeveloperSource(Protocol):
  def offroad(self) -> bool: ...
  def engaged(self) -> bool: ...
  def alpha_available(self) -> bool: ...       # the car offers openpilot longitudinal in alpha
  def set_ui_debug(self, on: bool) -> None: ...
  def fetch_keys(self, username: str, done: Callable[[str | None], None]) -> None: ...   # done(error or None)
  def clear_keys(self) -> None: ...
  def tick(self) -> None: ...


class Developer:
  def __init__(self, store: SettingsStore, source: DeveloperSource):
    self.store = store
    self.source = source
    self.fetching = False
    self.error = ""

  def flag(self, key: str) -> bool:
    return self.store.get_bool(key)

  def set_flag(self, key: str, on: bool) -> None:
    self.store.write({key: on})

  def set_joystick(self, on: bool) -> None:
    self.store.write({"JoystickDebugMode": on, "LongitudinalManeuverMode": False})

  def set_alpha(self, on: bool) -> None:
    self.store.write({"AlphaLongitudinalEnabled": on, "OnroadCycleRequested": True})

  def set_ui_debug(self, on: bool) -> None:
    self.store.write({"ShowDebugInfo": on})
    self.source.set_ui_debug(on)

  def github_user(self) -> str:
    return self.store.get_str("GithubUsername") if self.store.get_str("GithubSshKeys") else ""

  def add_keys(self, username: str) -> None:
    if not username:
      return
    self.fetching, self.error = True, ""

    def done(error: str | None) -> None:
      self.fetching = False
      self.error = error or ""
    self.source.fetch_keys(username, done)

  def remove_keys(self) -> None:
    self.source.clear_keys()
    self.store.write({})          # refresh the cached values


class DeveloperPage(Component):
  """The panel, ticking the source so a finished key fetch lands on the UI thread."""
  grow_touch_target = False

  def __init__(self, dev: Developer, window):
    super().__init__()
    self._dev = dev
    self._panel = self._child(developer_panel(dev, window))

  def _update_state(self):
    self._dev.source.tick()

  def _render(self, rect):
    self._panel.render(rect)


def developer_panel(dev: Developer, window) -> ListPanel:
  def ask_username() -> None:
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets import DialogResult
    from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard
    keyboard = EssentialsKeyboard(max_text_size=39, min_text_size=1, action=N_("Add"))
    keyboard.set_title(N_("GitHub username"), N_("Your own account only: every public key in it gets SSH access"))
    keyboard.set_callback(lambda result: dev.add_keys(keyboard.text.strip()) if result == DialogResult.CONFIRM else None)
    gui_app.push_widget(keyboard)

  def keys_action() -> None:
    if dev.github_user():
      dev.remove_keys()
    elif not dev.fetching:
      ask_username()

  def keys_line() -> str:
    if dev.fetching:
      return N_("Getting keys from GitHub…")
    if dev.error:
      return dev.error
    user = dev.github_user()
    return t_("Keys from GitHub user {}", user) if user else N_("Adds every public key in a GitHub account. Never use someone else's.")

  def set_alpha(on: bool) -> None:
    if not on:
      dev.set_alpha(False)
      return
    from openpilot.selfdrive.ui.tandem.overlays import Dialog
    from openpilot.system.ui.widgets import DialogResult

    def done(result) -> None:
      window.dismiss()
      if result == DialogResult.CONFIRM:
        dev.set_alpha(True)
    window.present(Dialog(N_("Turn on alpha longitudinal?"), ALPHA_WARNING, N_("Turn On"), done, tone=Tone.DANGER,
                          glyph=lambda r, c, s: draw.icon(r, "warning", c, s)))

  adb = Switch(lambda: dev.flag("AdbEnabled"), lambda on: dev.set_flag("AdbEnabled", on))
  adb.set_enabled(dev.source.offroad)
  joystick = Switch(lambda: dev.flag("JoystickDebugMode"), dev.set_joystick)
  joystick.set_enabled(dev.source.offroad)
  alpha = Switch(lambda: dev.flag("AlphaLongitudinalEnabled"), set_alpha)
  alpha.set_enabled(lambda: not dev.source.engaged())
  keys = Button(lambda: N_("Remove") if dev.github_user() else (N_("Adding…") if dev.fetching else N_("Add")), keys_action, ButtonStyle.SECONDARY)
  alpha_row = SettingRow(N_("openpilot Longitudinal (Alpha)"), N_("Turns off the car's emergency braking. Off while engaged."), alpha)
  alpha_row.set_visible(dev.source.alpha_available)
  return ListPanel([
    SettingRow(N_("ADB"), N_("Connect over USB or the network (docs.comma.ai). Change it with the car off."), adb),
    SettingRow(N_("SSH"), N_("Remote shell access with the keys below"), Switch(lambda: dev.flag("SshEnabled"), lambda on: dev.set_flag("SshEnabled", on))),
    SettingRow(N_("SSH Keys"), keys_line, keys, subtitle_color=lambda: T.DANGER_TEXT if dev.error else T.TEXT_TERTIARY),
    SettingRow(N_("Joystick Debug Mode"), N_("Drive openpilot's controls from a joystick. Change it with the car off."), joystick),
    alpha_row,
    SettingRow(N_("UI Debug Mode"), N_("Shows touches and the frame rate"), Switch(lambda: dev.flag("ShowDebugInfo"), dev.set_ui_debug)),
  ], title=N_("Developer"), footnote=N_("openpilot's developer options. They're only here with Tuner Mode on."))


class UpstreamDeveloper:
  """DeveloperSource the way upstream's DeveloperLayout does it."""

  def __init__(self):
    from openpilot.common.params import Params
    from openpilot.selfdrive.ui.widgets.ssh_key import SshKeyFetcher
    self._params = Params()
    self._params.put_bool("LongitudinalManeuverMode", False)   # as upstream does when its panel opens
    self._fetcher = SshKeyFetcher(self._params)

  def offroad(self) -> bool:
    from openpilot.selfdrive.ui.ui_state import ui_state
    return ui_state.is_offroad()

  def engaged(self) -> bool:
    from openpilot.selfdrive.ui.ui_state import ui_state
    return bool(ui_state.engaged)

  def alpha_available(self) -> bool:
    from openpilot.selfdrive.ui.ui_state import ui_state
    available = ui_state.CP is not None and ui_state.CP.alphaLongitudinalAvailable
    if not available and self._params.get_bool("AlphaLongitudinalEnabled"):
      self._params.remove("AlphaLongitudinalEnabled")   # upstream clears it where the car doesn't offer it
    return bool(available)

  def set_ui_debug(self, on: bool) -> None:
    from openpilot.system.ui.lib.application import gui_app
    gui_app.set_show_touches(on)
    gui_app.set_show_fps(on)

  def fetch_keys(self, username: str, done: Callable[[str | None], None]) -> None:
    self._fetcher.fetch(username, done)

  def clear_keys(self) -> None:
    self._fetcher.clear()

  def tick(self) -> None:
    self._fetcher.update()   # delivers a finished fetch on the UI thread
