"""Opt into Tandem presentation without intercepting the shared GUI navigation stack."""
from __future__ import annotations

from collections.abc import Callable

from openpilot.system.ui.widgets import DialogResult


def confirmed_controller(base):
  class ConfirmedController(base):
    _confirmed_action: str | None = None

    def run_confirmed(self, action: str, callback: Callable[[], None]) -> None:
      previous = self._confirmed_action
      self._confirmed_action = action
      try:
        callback()
      finally:
        self._confirmed_action = previous

    def _request_confirmation(self, action, message, label, callback):
      if action == self._confirmed_action:
        callback(DialogResult.CONFIRM)
      else:
        super()._request_confirmation(action, message, label, callback)

  return ConfirmedController


def notice_controller(base, notify: Callable[[str], None]):
  class NoticeController(base):
    def _show_notice(self, message: str):
      notify(message)

  return NoticeController
