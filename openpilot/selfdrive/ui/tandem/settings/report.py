"""The release Report a Problem form, with confirmed background delivery."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
import threading

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Columns, Field, Label, Stack, Surface
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.prefs import Text
from openpilot.selfdrive.ui.tandem.ram import RamLog, report_text
from openpilot.selfdrive.ui.tandem.rows import OptionList, Padded
from openpilot.selfdrive.ui.tandem.settings.pages import Rebuilding
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow
from openpilot.system.ui.widgets import Widget

DISCORD = Text("report_discord")
REPORT_CATEGORIES = [N_("Acceleration felt harsh or jerky"), N_("Braking was too sudden"), N_("It disengaged when I didn't expect it"),
                     N_("It felt slow to respond"), N_("An alert was unclear"), N_("My steering wheel buttons aren't working"), N_("Something else")]


class Report:
  """Hold the release form and publish success only after the sender confirms it."""

  def __init__(self, ram: RamLog, allowed: Callable[[], bool], send: Callable[[str, str, Callable[[], bool]], bool],
               edit: Callable[[str, str, Callable[[str], None]], None]) -> None:
    self._ram = ram
    self._allowed, self._send, self.edit = allowed, send, edit
    self.category = -1
    self.details = ""
    self.discord = DISCORD.get() or ""
    self.sent = False
    self._pending: Future[bool] | None = None

  @property
  def sending(self) -> bool:
    """Keep one outgoing report in flight."""
    return self._pending is not None

  def ready(self) -> bool:
    """Require a category and a local settings session before sending."""
    return 0 <= self.category < len(REPORT_CATEGORIES) and self._allowed() and not self.sent and not self.sending

  def send(self) -> None:
    """Collect the selected category, entered details and the recent low-memory summaries."""
    if not self.ready():
      return
    parts = [REPORT_CATEGORIES[self.category]]
    if self.details.strip():
      parts.append(self.details.strip()[:4096])
    if snapshots := self._ram.snapshots():
      parts.append(report_text(snapshots))
    issue = "\n".join(parts)
    discord = self.discord.strip()[:64]
    job: Future[bool] = Future()

    def transfer() -> None:
      """Keep delivery and settings persistence off the UI thread."""
      try:
        accepted = self._send(issue, discord, self._allowed)
        if accepted and discord:
          DISCORD.set(discord)
      except Exception:
        accepted = False
      job.set_result(accepted)

    threading.Thread(target=transfer, daemon=True, name="tandem-issue-report").start()
    self._pending = job

  def complete(self) -> bool | None:
    """Return an outcome once without blocking a frame."""
    if self._pending is None or not self._pending.done():
      return None
    self.sent = self._pending.result()
    self._pending = None
    return self.sent


def report_panel(report: Report) -> Widget:
  """Report a Problem's page: pick a category, add details, send."""
  def edit(title: str, get: Callable[[], str], set_: Callable[[str], None]) -> Callable[[], None]:
    """Bind a release form field to the supplied text editor."""
    def open_keyboard() -> None:
      """Open the text editor for the selected field."""
      if not report.sending:
        report.edit(title, get(), set_)
    return open_keyboard

  def pick(index: int) -> None:
    """Select the category for a new report."""
    if not report.sending:
      report.category = index
      report.sent = False

  send = Button(lambda: N_("Sent. Thank you!") if report.sent else N_("Send report"), report.send, ButtonStyle.PRIMARY, height=T.px(56),
                weight=T.FONT_EXTRABOLD)
  send.set_enabled(report.ready)
  happened = Stack([
    Padded(Label(N_("What happened?"), T.font_px(22)), x=T.px(10), y=T.px(4)),
    OptionList(REPORT_CATEGORIES, lambda: report.category, pick, row_height=T.px(52), outlined=True, font_size=T.font_px(15)),
  ], gap=T.px(4))
  details = Stack([
    Field(N_("Details (optional)"), lambda: report.details, N_("Where and when it happened"),
          edit(N_("Details"), lambda: report.details, lambda v: setattr(report, "details", v)), height=T.px(72)),
    Field(N_("Discord name (optional)"), lambda: report.discord, N_("So we can follow up"),
          edit(N_("Discord name"), lambda: report.discord, lambda v: setattr(report, "discord", v))),
    SPACER,
    send,
  ], gap=T.px(14))
  return Surface(Columns([Padded(happened, x=T.px(10), y=T.px(12)), Padded(details, x=T.px(18), y=T.px(16))], [1.25, 1], gap=0),
                 T.SURFACE_2, T.RADIUS_PANEL)


def report_section(report: Report, window: SettingsWindow) -> Widget:
  """Display a retryable error through the existing Settings notice."""
  def poll() -> None:
    """Consume network results on the UI thread."""
    if report.complete() is False:
      window.notice(N_("Report a Problem"), N_("The report could not be sent. Try again."))
  return Rebuilding(lambda: None, lambda: report_panel(report), tick=poll)
