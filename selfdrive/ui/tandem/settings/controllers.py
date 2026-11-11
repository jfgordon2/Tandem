"""Opt into Tandem presentation without intercepting the shared GUI navigation stack."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.system.ui.widgets import DialogResult


def confirmed_controller(base: type[Any]) -> type[Any]:
  """StarPilot's settings controller, made to run an action Tandem's dialog already confirmed.

  run_confirmed(action, callback) answers that action's own confirmation with Confirm while callback runs, so StarPilot's
  dialog doesn't ask again.
  """
  class ConfirmedController(base):
    _confirmed_action: str | None = None

    def run_confirmed(self, action: str, callback: Callable[[], None]) -> None:
      previous = self._confirmed_action
      self._confirmed_action = action
      try:
        callback()
      finally:
        self._confirmed_action = previous

    def _request_confirmation(self, action: str, message: str, label: str, callback: Callable[[DialogResult], None]) -> None:
      if action == self._confirmed_action:
        callback(DialogResult.CONFIRM)
      else:
        super()._request_confirmation(action, message, label, callback)

  return ConfirmedController


def notice_controller(base: type[Any], notify: Callable[[str], None]) -> type[Any]:
  class NoticeController(base):
    def _show_notice(self, message: str) -> None:
      notify(message)

  return NoticeController
