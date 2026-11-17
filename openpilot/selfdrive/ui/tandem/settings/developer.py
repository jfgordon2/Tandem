"""Release's Developer rows, driven by StarPilot's native toggle and SSH owners."""
from __future__ import annotations

from collections.abc import Callable
import time
from typing import TYPE_CHECKING, Any

from openpilot.selfdrive.ui.tandem.controls import Button, Switch
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow


if TYPE_CHECKING:
  from openpilot.selfdrive.ui.widgets.ssh_key import SshKeyFetcher


class DeveloperPanel(ListPanel):
  """Keep the release controls and use the existing owner for effects and admission."""

  def __init__(self, native: Any, params: Any, fetcher: SshKeyFetcher, local: Callable[[], bool], parked: Callable[[], bool],
               edit: Callable[[str, str, Callable[[str], None]], None]) -> None:
    self._native = native
    self._next = 0.0
    self._fetcher = fetcher
    self._fetching = False
    self._error = ""

    def user() -> str:
      """Read the account for the currently installed key set."""
      return str(params.get("GithubUsername") or "") if params.get("GithubSshKeys") else ""

    def fetched(error: str | None) -> None:
      """Publish the result on the UI thread."""
      self._fetching = False
      self._error = error or ""

    def add(username: str) -> None:
      """Fetch through the native SSH key owner."""
      if username and local() and not self._fetching:
        self._fetching, self._error = True, ""
        self._fetcher.fetch(username, fetched)

    def keys_action() -> None:
      """Remove existing keys or open the username editor."""
      if not local() or self._fetching:
        return
      if user():
        self._fetcher.clear()
      else:
        edit(N_("GitHub username"), "", add)

    def keys_line() -> str:
      """Show the current key owner or the release prompt."""
      if self._fetching:
        return N_("Getting keys from GitHub…")
      if self._error:
        return self._error
      return t_("Keys from GitHub user {}", user()) if user() else N_("Adds every public key in a GitHub account. Never use someone else's.")

    def toggle(key: str, title: str, subtitle: str, action: Callable[[bool], None],
               allowed: Callable[[], bool] = local) -> SettingRow:
      """Draw an Essentials switch around a native action with a fresh guard."""
      switch = Switch(lambda: params.get_bool(key), lambda value: action(value) if allowed() else None)
      switch.set_enabled(allowed)
      return SettingRow(title, subtitle, switch)

    alpha = toggle("AlphaLongitudinalEnabled", N_("openpilot Longitudinal (Alpha)"),
                   N_("Turns off the car's emergency braking. Off while engaged."), native._on_alpha_long_enabled,
                   lambda: parked() and native._alpha_long_toggle.action_item.enabled)
    alpha.set_visible(lambda: native._alpha_long_toggle.is_visible)
    keys = Button(lambda: N_("Remove") if user() else (N_("Adding…") if self._fetching else N_("Add")), keys_action)
    keys.set_enabled(lambda: local() and not self._fetching)
    joystick = toggle("JoystickDebugMode", N_("Joystick Debug Mode"),
                      N_("Drive openpilot's controls from a joystick. Change it with the car off."), native._on_joystick_debug_mode, parked)
    joystick.set_visible(lambda: native._joystick_toggle.is_visible)
    super().__init__([
      toggle("AdbEnabled", N_("ADB"), N_("Connect over USB or the network (docs.comma.ai). Change it with the car off."),
             native._on_enable_adb, parked),
      toggle("SshEnabled", N_("SSH"), N_("Remote shell access with the keys below"), native._on_enable_ssh),
      SettingRow(N_("SSH Keys"), keys_line, keys),
      joystick,
      alpha,
      toggle("ShowDebugInfo", N_("UI Debug Mode"), N_("Shows touches and the frame rate"), native._on_enable_ui_debug),
    ], title=N_("Developer"), footnote=N_("openpilot's developer options. They're only here with Tuner Mode on."))

  def show_event(self) -> None:
    """Refresh the native availability when opening the panel."""
    super().show_event()
    self._next = 0.0

  def _update_state(self) -> None:
    """Poll native gate changes and deliver asynchronous key-fetch results."""
    self._fetcher.update()
    now = time.monotonic()
    if now >= self._next:
      self._native._update_toggles()
      self._next = now + 1.0
    super()._update_state()
