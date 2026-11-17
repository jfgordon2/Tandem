"""The release Device › Backups panel and confirmations."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
import threading

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.layout import row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.backup_owner import Backup, BackupStore
from openpilot.selfdrive.ui.tandem.settings.pages import Rebuilding
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, confirm
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.widgets import Widget


class ButtonPair(Component):
  """Two buttons side by side, sharing the width."""

  grow_touch_target = False

  def __init__(self, first: Button, second: Button) -> None:
    super().__init__()
    self._buttons = [self._child(first), self._child(second)]

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    """Fit both buttons and the release gap."""
    widths = [button.preferred_size(max_width)[0] for button in self._buttons]
    return sum(widths) + T.px(10), T.BUTTON_HEIGHT

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    """Keep the shared clipping rectangle when the panel scrolls."""
    super().set_parent_rect(parent_rect)
    for button in self._buttons:
      button.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle) -> None:
    """Draw the two release actions with their natural widths."""
    widths = [button.preferred_size(rect.width)[0] for button in self._buttons]
    for button, bounds in zip(self._buttons, row(rect, widths, T.px(10)), strict=True):
      button.render(bounds)


def backups_panel(store: BackupStore, window: SettingsWindow) -> Component:
  """Reuse release's panel and confirm dialogs with one off-thread operation at a time."""
  backups: tuple[Backup, ...] = ()
  pending: Future[tuple[tuple[Backup, ...], str]] | None = None

  def available() -> bool:
    """A local user can start an action when the previous one has finished."""
    return pending is None and store.allowed()

  def submit(action: Callable[[], str | None] | None = None) -> None:
    """Read or update the list without doing storage or native owner work in render."""
    nonlocal pending
    if pending is not None or (action is not None and not store.allowed()):
      return
    result: Future[tuple[tuple[Backup, ...], str]] = Future()
    current = backups

    def work() -> None:
      """Return the operation outcome and latest completed backup list."""
      error = ""
      try:
        if action is not None:
          error = action() or ""
      except Exception as failure:
        error = str(failure) or type(failure).__name__
      try:
        latest = store.backups()
      except (OSError, ValueError, OverflowError) as failure:
        latest = current
        error = error or str(failure) or type(failure).__name__
      result.set_result((latest, error))

    threading.Thread(target=work, daemon=True, name="tandem-backup").start()
    pending = result

  def poll() -> None:
    """Publish the new list and present failures on the UI thread while the panel is shown."""
    nonlocal backups, pending
    if pending is not None and pending.done():
      backups, error = pending.result()
      pending = None
      if error:
        window.notice(N_("Backups"), t_("Backup operation could not finish. {}", error))

  def row_for(backup: Backup) -> SettingRow:
    """Draw each saved backup with the original delete and restore confirmations."""
    name = t_("Backup {}", backup.name.removeprefix("Backup ")) if backup.name.startswith("Backup ") else backup.name
    restore = Button(N_("Restore"), lambda: confirm(window, N_("Restore this backup?"), t_("Your current settings are replaced with {}.", name),
                                                     N_("Restore"), lambda: submit(lambda: store.restore(backup)), danger=False, icon="restart"))
    delete = Button(N_("Delete"), lambda: confirm(window, N_("Delete this backup?"), t_("{} can't be recovered.", name), N_("Delete"),
                                                   lambda: submit(lambda: store.delete(backup))), ButtonStyle.DANGER_SOFT)
    restore.set_enabled(available)
    delete.set_enabled(available)
    return SettingRow(name, backup.when, ButtonPair(delete, restore))

  def build() -> ListPanel:
    """Build the release layout from the current backup rows."""
    rows: list[Widget] = [row_for(backup) for backup in backups] or [Text(N_("No backups yet."))]
    create = Button(N_("Back up now"), lambda: submit(store.create), ButtonStyle.PRIMARY)
    create.set_enabled(available)
    return ListPanel([SectionHeader(N_("SAVED")), *rows], title=N_("Backups"), subtitle=N_("Snapshots of your settings. Drives aren't included."),
                     header_control=create)

  return Rebuilding(lambda: backups, build, tick=poll, on_show=submit)
