"""Release Device navigation, state, and report delivery on StarPilot 7."""
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem.settings.report import DISCORD, REPORT_CATEGORIES, Report
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.rows import Text


def test_firehose_opens_as_a_native_setup_page_outside_the_device_rail() -> None:
  """Native onboarding still reaches Firehose without adding a Device section."""
  page = Text("Device")
  setup = Text("Firehose")
  window = SettingsWindow({Tab.DEVICE: lambda: page}, initial=Tab.DEVICE, auxiliary={"FIREHOSE": lambda: setup})
  window.set_current_panel("FIREHOSE")
  assert window.top is setup
  window.back()
  assert window.top is page
  # Reentering setup always presents one auxiliary page.
  window.set_current_panel("FIREHOSE")
  window.set_current_panel("FIREHOSE")
  window.back()
  assert window.top is page


def test_report_waits_for_confirmation_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
  """An unsuccessful send keeps the release form and does not claim delivery."""
  jobs: list[Callable[[], None]] = []

  def thread(*, target: Callable[[], None], **_: object) -> SimpleNamespace:
    """Allow tests to deliver report results deterministically."""
    return SimpleNamespace(start=lambda: jobs.append(target))

  monkeypatch.setattr("openpilot.selfdrive.ui.tandem.settings.report.threading.Thread", thread)
  ram = Mock()
  ram.snapshots.return_value = []
  send = Mock(side_effect=[False, True])
  report = Report(ram, lambda: True, send, Mock())
  assert not report.ready()
  report.category, report.details, report.discord = 1, "At the intersection", "test.driver"
  report.send()
  report.send()
  assert len(jobs) == 1 and report.sending and not report.sent
  jobs.pop()()
  assert report.complete() is False and report.ready()
  assert DISCORD.get() is None
  report.send()
  jobs.pop()()
  assert report.complete() is True and report.sent and not report.ready()
  assert DISCORD.get() == "test.driver"
  assert send.call_args.args[:2] == (f"{REPORT_CATEGORIES[1]}\nAt the intersection", "test.driver")
