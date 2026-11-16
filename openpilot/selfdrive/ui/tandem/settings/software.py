"""The approved Essentials panel inside StarPilot's Settings window."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum, auto
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Label
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ProgressBar, Switch
from openpilot.selfdrive.ui.tandem.home_software import InstallTarget
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, row
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.software_state import SoftwareState, SoftwareWatch, Stage
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.widgets import Widget


class Page(Enum):
  """Software panel, read-only notes, staged notes, or native options."""

  MAIN = auto()
  INSTALLED_NOTES = auto()
  UPDATE_NOTES = auto()
  OPTIONS = auto()


HEADERS = {Page.MAIN: N_("Software"), Page.INSTALLED_NOTES: N_("What's new"), Page.UPDATE_NOTES: N_("Update notes"),
           Page.OPTIONS: N_("Software options")}
STATUS = {
  Stage.READING: N_("Reading software status"),
  Stage.UNAVAILABLE: N_("Updater unavailable"),
  Stage.PARK: N_("Park to update"),
  Stage.DISABLED: N_("Updates are disabled"),
  Stage.CHECKING: N_("Checking for updates"),
  Stage.DOWNLOADING: N_("Downloading update"),
  Stage.PREPARING: N_("Preparing update"),
  Stage.RESTARTING: N_("Restart pending"),
  Stage.DOWNLOAD_FAILED: N_("Could not download the update"),
  Stage.CHECK_FAILED: N_("Couldn't check for updates"),
  Stage.AVAILABLE: N_("Update available"),
  Stage.READY: N_("Update ready"),
  Stage.CURRENT: N_("Up to date"),
  Stage.IDLE: N_("Installed software"),
}


def checked_at(stamp: str, now: datetime) -> str:
  """Format a qualified check timestamp as a relative time or local date."""
  try:
    checked = datetime.fromisoformat(stamp)
  except ValueError:
    return ""
  if checked.tzinfo is None:
    return ""
  minutes = int((now - checked).total_seconds() // 60)
  if minutes < 0:
    return ""
  if minutes == 0:
    return N_("Checked just now")
  if minutes < 60:
    return tn_("Checked {} minute ago", "Checked {} minutes ago", minutes)
  return t_("Checked {}", checked.astimezone().strftime("%x"))


def schedule_label(state: SoftwareState) -> str:
  """Show the scheduler's next actual restart in its configured timezone."""
  if not state.next_restart or state.installs is None:
    return ""
  try:
    restart = datetime.fromisoformat(state.next_restart).astimezone(ZoneInfo(state.installs.zone))
  except (ValueError, ZoneInfoNotFoundError):
    return ""
  return t_("Next scheduled restart · {}", restart.strftime("%I:%M %p %Z").lstrip("0"))


def detail(state: SoftwareState) -> str:
  """Describe the owner's current operation."""
  if state.stage == Stage.CHECKING:
    return N_("Looking for a newer version")
  if state.stage == Stage.AVAILABLE and state.branch:
    return t_("An update is available on {}", state.branch)
  if state.stage == Stage.DOWNLOADING and state.percent is not None:
    return t_("{}% downloaded", state.percent)
  if state.stage == Stage.READY:
    return t_("{} is ready to install", state.home.version)
  if state.stage in (Stage.DOWNLOAD_FAILED, Stage.CHECK_FAILED):
    return N_("Check your connection and try again")
  if state.stage == Stage.PARK:
    return N_("Software actions are available while parked")
  return checked_at(state.last_checked, datetime.now(UTC))


class SoftwarePanel(Component):
  """Presentation with a lazy native options page and a revision-bound install action."""

  grow_touch_target = False

  def __init__(self, make_watch: Callable[[Callable[[], bool]], SoftwareWatch], make_options: Callable[[], Widget],
               local: Callable[[], bool]):
    super().__init__()
    self._local = local
    self._page = Page.MAIN
    self._active = False
    self._watch = make_watch(lambda: self._active and self._page != Page.OPTIONS and self._local())
    self._make_options = make_options
    self._options: Widget | None = None
    self._shown_target: InstallTarget | None = None
    self._notes: ListPanel | None = None
    self._notes_contents: str | None = None
    self._primary: Button | None = None
    self._primary_context: tuple[str, str, InstallTarget | None] | None = None
    self._more = self._child(Button(N_("More software options"), self._open_options, height=T.px(46)))
    self._more.set_enabled(self._local)
    self._back = self._child(Button(N_("Back"), self._back_to_main, height=T.px(46)))
    self._installed = self._child(Button(N_("What's new"), lambda: self._set_page(Page.INSTALLED_NOTES), height=T.px(46)))
    self._installed.set_enabled(lambda: bool(self._watch.state.installed_notes))
    self._restart = self._child(Button(N_("Restart and update"), self._restart_shown, ButtonStyle.PRIMARY, height=T.px(46)))
    self._restart.set_enabled(self._can_restart)
    self._progress = self._child(ProgressBar(lambda: (self._watch.state.percent or 0) / 100, height=T.px(6)))
    downloads = Switch(lambda: self._watch.state.downloads is True, self._change_downloads)
    downloads.set_enabled(lambda: self._can_configure() and self._watch.state.downloads is not None)
    installs = Switch(lambda: self._watch.state.installs is not None and self._watch.state.installs.enabled,
                      self._change_installs)
    installs.set_enabled(lambda: self._can_configure() and self._watch.state.installs is not None)
    target = Label(lambda: self._watch.state.branch, T.SIZE_SUBTITLE, T.TEXT_SECONDARY, T.FONT_BOLD, fit=True)
    settings = [
      SettingRow(N_("Automatic downloads"), N_("Download updates while parked"), downloads, height=T.px(75)),
      SettingRow(N_("Automatic installation"), N_("Restart at the scheduled time while parked"), installs, height=T.px(75)),
      SettingRow(N_("Target branch"), N_("Change in More software options"), target, height=T.px(75)),
      Text(lambda: schedule_label(self._watch.state), padding=(T.px(17), T.px(14))),
    ]
    settings[-1].set_visible(lambda: bool(schedule_label(self._watch.state)))
    self._settings = self._child(ListPanel(settings, header_divider=False))

  def show_event(self) -> None:
    """Start refreshing when StarPilot selects the Software panel."""
    self._active = True
    self._watch.refresh()
    super().show_event()

  def hide_event(self) -> None:
    """Revoke actions and forget any staged notes when leaving Software."""
    self._active = False
    self._back_to_main()
    super().hide_event()

  def _set_page(self, page: Page) -> None:
    if self._page == Page.OPTIONS and self._options is not None:
      self._options.hide_event()
    self._page = page
    if page == Page.OPTIONS and self._options is not None:
      self._options.show_event()

  def _back_to_main(self) -> None:
    self._shown_target = None
    self._watch.refresh()
    self._set_page(Page.MAIN)

  def _open_options(self) -> None:
    if self._local():
      if self._options is None:
        self._options = self._make_options()
      self._set_page(Page.OPTIONS)

  def _open_update_notes(self, shown: InstallTarget | None) -> None:
    if shown is not None and shown == self._watch.state.home.target:
      self._shown_target = shown
      self._set_page(Page.UPDATE_NOTES)

  def _change_downloads(self, enabled: bool) -> None:
    self._watch.automatic_downloads(enabled)

  def _change_installs(self, enabled: bool) -> None:
    self._watch.automatic_installs(enabled)

  def _can_configure(self) -> bool:
    return self._watch.writable and self._watch.state.can_configure

  def _can_restart(self) -> bool:
    return self._watch.writable and self._shown_target is not None and self._shown_target == self._watch.state.home.target

  def _restart_shown(self) -> None:
    if self._shown_target is not None:
      self._watch.install(self._shown_target)

  def _primary_button(self, state: SoftwareState) -> Button:
    download = state.stage in (Stage.AVAILABLE, Stage.DOWNLOAD_FAILED)
    target = state.home.target if state.stage == Stage.READY else None
    label = N_("Notes") if target is not None else N_("Download") if download else N_("Check now")
    context = label, state.branch, target
    if self._primary is None or self._primary_context != context:
      if self._primary is not None:
        self._children.remove(self._primary)
      def action() -> None:
        if target is not None:
          self._open_update_notes(target)
        elif download:
          self._watch.download()
        else:
          self._watch.check()

      self._primary = self._child(Button(label, action, ButtonStyle.PRIMARY, height=T.px(46)))
      self._primary.set_enabled(lambda: target is not None or (self._watch.writable and (
        self._watch.state.can_download if download else self._watch.state.can_check)))
      self._primary_context = context
    return self._primary

  def _version(self, rect: rl.Rectangle, state: SoftwareState) -> None:
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    percent_h = T.px(6) if state.percent is not None else 0
    status, installed, explanation, progress, _, actions = column(
      inset(rect, x=T.px(18), y=T.px(18)), [T.px(23), T.px(34), T.px(41), percent_h, FILL, T.px(46)], T.px(4))
    ink = (T.SUCCESS_TEXT if state.stage in (Stage.CURRENT, Stage.READY) else
           T.WARNING_TITLE if state.stage in (Stage.CHECK_FAILED, Stage.DOWNLOAD_FAILED) or self._watch.failed else T.ACCENT_TEXT)
    message = N_("Software change could not be saved") if self._watch.failed else STATUS[state.stage]
    draw.text(status, message, T.font_px(15), ink, T.FONT_BOLD)
    if state.home.installed:
      draw.text(installed, t_("Version {}", state.home.installed), T.font_px(29), T.TEXT, T.FONT_EXTRABOLD)
    draw.paragraph(explanation, detail(state), T.font_px(16), T.TEXT_TERTIARY)
    if percent_h:
      self._progress.render(progress)
    main, installed_action = row(actions, [FILL, FILL], T.px(8))
    self._primary_button(state).render(main)
    self._installed.render(installed_action)

  def _notes_panel(self, text: str) -> ListPanel:
    if self._notes is None or text != self._notes_contents:
      if self._notes is not None:
        self._children.remove(self._notes)
      lines = [Text(line, T.font_px(18), T.TEXT, padding=(0, T.px(3))) for line in text.splitlines() if line.strip()]
      self._notes = self._child(ListPanel(lines, background=T.SURFACE_2, dividers=False, header_divider=False))
      self._notes_contents = text
    return self._notes

  def _render_notes(self, rect: rl.Rectangle, state: SoftwareState) -> None:
    update = self._page == Page.UPDATE_NOTES
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    label, heading, notes, schedule, actions = column(
      inset(rect, T.px(20)), [T.px(19) if update else 0, T.px(37), FILL, T.px(25) if update else 0, T.px(46) if update else 0])
    if update:
      draw.text(label, N_("Update ready"), T.font_px(15), T.SUCCESS_TEXT, T.FONT_BOLD)
    version = state.home.version if update else state.home.installed
    if version:
      draw.text(heading, t_("Version {}", version), T.font_px(25), T.TEXT, T.FONT_EXTRABOLD)
    self._notes_panel(state.home.notes if update else state.installed_notes).render(notes)
    if update:
      if state.home.scheduled:
        draw.text(schedule, N_("Automatic installation is scheduled while parked."), T.font_px(15), T.TEXT_TERTIARY)
      width, _ = self._restart.preferred_size(actions.width)
      _, restart = row(actions, [FILL, width], T.px(10))
      self._restart.render(restart)

  def _render(self, rect: rl.Rectangle) -> None:
    if self._page == Page.OPTIONS and not self._local():
      self._back_to_main()
    state = self._watch.state if self._page == Page.OPTIONS else self._watch.poll()
    if self._page == Page.UPDATE_NOTES and self._shown_target != state.home.target:
      self._back_to_main()
    shell = inset(rect, y=T.px(8))
    if self._page != Page.OPTIONS:
      draw.fill(shell, T.BG, T.px(18))
    header, body = column(inset(shell, x=T.px(15), y=T.px(16)), [T.px(46), FILL], T.px(14))
    control = self._more if self._page == Page.MAIN else self._back
    width, _ = control.preferred_size(header.width)
    heading, button = row(header, [FILL, width], T.px(12))
    draw.text(heading, HEADERS[self._page], T.font_px(30), T.TEXT, T.FONT_EXTRABOLD, Align.START)
    control.render(button)
    if self._page == Page.MAIN:
      gap = T.px(14)
      current, choices = row(body, [(body.width - gap) / 2.13, FILL], gap)
      self._version(current, state)
      self._settings.render(choices)
    elif self._page == Page.OPTIONS and self._options is not None:
      self._options.render(body)
    else:
      self._render_notes(body, state)
