"""Software: version and update status, Automatic Updates, release channel, Reset Settings, and Uninstall
(release's settings/software_tab.py and design/softwaretab.html).

StarPilot 7's software owner does the work, through the watch Home shares (tandem/software.py): checking, downloading
and installing, each with the revision the driver saw. Automatic Updates turns StarPilot's automatic downloads and
automatic installation on or off together. Uninstall asks once and sets DoUninstall, as StarPilot 7's own panel does.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Label
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch, Tone, ValueButton
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.pages import FillPage
from openpilot.selfdrive.ui.tandem.software import SoftwareWatch, Stage
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.widgets import Widget

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

BUSY = (Stage.READING, Stage.CHECKING, Stage.DOWNLOADING, Stage.PREPARING, Stage.RESTARTING)
WAITING = {Stage.UNAVAILABLE: N_("Updater unavailable"), Stage.PARK: N_("Park to update"), Stage.DISABLED: N_("Updates are disabled")}
UPDATER_STATES = {Stage.READING: N_("Reading software status"), Stage.CHECKING: N_("Checking for an update"),
                  Stage.DOWNLOADING: N_("Downloading the update"), Stage.PREPARING: N_("Getting the update ready"),
                  Stage.RESTARTING: N_("Restart pending")}


class Software:
  """The Software tab: the version, update state and action, Automatic Updates and branch, read from the shared watch."""

  def __init__(self, watch: SoftwareWatch, read: Callable[[str], object], uninstall: Callable[[], None]):
    """Makes the tab's model.

    Args:
      watch: StarPilot's software state and actions (tandem/software.py's shared_software).
      read: Reads a param, for the installed version's description.
      uninstall: Uninstalls openpilot, after the driver confirms.
    """
    self.watch = watch
    self._read = read
    self._uninstall = uninstall

  def tick(self) -> None:
    self.watch.poll()

  def version_parts(self) -> tuple[str, str]:
    """"7.0.0 / development / 1abbbc6 / Nov 16" as ("7.0.0", "development · Nov 16"): the commit stays out of sight."""
    description = self._read("UpdaterCurrentDescription")
    parts = [p.strip() for p in description.split(" / ")] if isinstance(description, str) and description else []
    number = parts[0] if parts else self.watch.state.home.installed or N_("Unknown version")
    rest = [p for p in parts[1:] if not (len(p) == 7 and all(c in "0123456789abcdef" for c in p))]
    return number, " · ".join(rest)

  def state(self) -> str:
    """One of release's states: busy, failed, available (to download), ready (to install), current; or waiting, while
    StarPilot can't update now (driving, updates turned off, or no updater)."""
    stage = self.watch.state.stage
    if stage in BUSY:
      return "busy"
    if stage == Stage.READY:
      return "ready"
    if stage in (Stage.CHECK_FAILED, Stage.DOWNLOAD_FAILED):
      return "failed"
    if stage == Stage.AVAILABLE:
      return "available"
    return "waiting" if stage in WAITING else "current"

  def status_badge(self) -> tuple[str, Tone]:
    if self.state() == "waiting":
      return WAITING[self.watch.state.stage], Tone.WARNING
    return {"busy": (N_("Updating"), Tone.ACCENT), "ready": (N_("Ready to install"), Tone.SUCCESS), "failed": (N_("Check failed"), Tone.WARNING),
            "available": (N_("Update available"), Tone.ACCENT), "current": (N_("Up to date"), Tone.SUCCESS)}[self.state()]

  def status_line(self) -> str:
    """The update state in a line, under the version."""
    state, software = self.state(), self.watch.state
    if self.watch.failed:
      return N_("Software change could not be saved")
    if state == "busy":
      if software.stage == Stage.DOWNLOADING and software.percent is not None:
        return t_("{}% downloaded", software.percent)
      return UPDATER_STATES.get(software.stage, N_("Updating"))
    if state == "ready":
      return t_("{} is ready to install", software.home.version or N_("A new version"))   # StarPilot 7 installs on a restart
    if state == "failed":
      return N_("Couldn't check for updates. Check the connection and try again.")
    if state == "available":
      return N_("A new version is available to download")
    if state == "waiting":
      return N_("Software actions are available while parked")
    return N_("You have the latest version")

  def action_label(self) -> str:
    labels = {"busy": N_("Working…"), "ready": N_("Restart to install"), "failed": N_("Try again"), "available": N_("Download")}
    return labels.get(self.state(), N_("Check now"))

  def can_act(self) -> bool:
    software = self.watch.state
    if not self.watch.writable:
      return False
    return {"ready": self.watch.can_install(software.home.target), "available": software.can_download,
            "failed": software.can_check or software.can_download, "current": software.can_check}.get(self.state(), False)

  def act(self) -> None:
    software, state = self.watch.state, self.state()
    if state == "ready" and software.home.target is not None:
      self.watch.install(software.home.target)
    elif state == "available" or state == "failed" and software.can_download:
      self.watch.download()
    elif state in ("current", "failed"):
      self.watch.check()

  @property
  def automatic(self) -> bool:
    return bool(self.watch.automatic)

  def can_set_automatic(self) -> bool:
    return self.watch.automatic is not None and self.watch.state.can_configure and self.watch.writable

  def set_automatic(self, on: bool) -> None:
    self.watch.set_automatic(on)

  def channel(self) -> str:
    branch = self.watch.state.branch or str(self._read("GitBranch") or "")
    return {"release": N_("Stable"), "release3": N_("Stable"), "master": N_("Stable"), "staging": N_("Beta")}.get(branch, branch or N_("Stable"))

  def tuner(self) -> bool:
    """Share the release Tuner Mode preference with the Device rail."""
    from openpilot.selfdrive.ui.tandem.prefs import TUNER_MODE
    return TUNER_MODE.get()

  def release_notes(self) -> str:
    return self.watch.state.installed_notes

  def uninstall(self) -> None:
    self._uninstall()


STATUS_INK = {Tone.SUCCESS: T.SUCCESS_TEXT, Tone.ACCENT: T.ACCENT_TEXT, Tone.WARNING: T.WARNING}


def show_notes(model: Software, window: SettingsWindow) -> None:
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  paragraphs = [Text(p, T.font_px(17), T.TEXT_SECONDARY) for p in model.release_notes().split("\n") if p.strip()]
  window.present(Sheet(t_("What's new in {}", model.version_parts()[0]), ListPanel(paragraphs, dividers=False, header_divider=False),
                       on_dismiss=window.dismiss))


def uninstall(model: Software, window: SettingsWindow) -> None:
  """Release's first Uninstall dialog. StarPilot 7 has no factory-reset step, and keeps settings that clearing params
  wouldn't erase, so release's two erase steps aren't offered."""
  from openpilot.selfdrive.ui.tandem import draw
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  from openpilot.system.ui.widgets import DialogResult

  def done(result: DialogResult) -> None:
    window.dismiss()
    if result == DialogResult.CONFIRM:
      model.uninstall()

  window.present(Dialog(N_("Uninstall openpilot?"), N_("The device removes openpilot and starts its setup again."), N_("Uninstall"), done,
                        tone=Tone.DANGER, glyph=lambda r, c, s: draw.icon(r, "trash", c, s)))


def software_page(model: Software, window: SettingsWindow) -> Widget:
  """The version and its actions on the left; update settings on the right."""
  action = Button(model.action_label, model.act, ButtonStyle.SECONDARY, height=T.px(56), font_size=T.font_px(17), weight=T.FONT_BOLD)
  action.set_enabled(model.can_act)
  version = Card([
    Label(lambda: model.status_badge()[0].upper(), T.font_px(15), lambda: STATUS_INK[model.status_badge()[1]],
          icon=lambda: "check" if model.state() in ("current", "ready") else None),
    Label(lambda: t_("Version {}", model.version_parts()[0]), T.font_px(30), weight=T.FONT_EXTRABOLD),
    Text(lambda: " · ".join(p for p in (model.version_parts()[1], model.status_line()) if p), T.font_px(16), T.TEXT_TERTIARY,
         padding=(0, 0)),
    SPACER,
    Columns([action, Button(N_("What's new"), lambda: show_notes(model, window), ButtonStyle.SECONDARY, height=T.px(56), font_size=T.font_px(17),
                            weight=T.FONT_BOLD)],
            gap=T.px(10)),
  ], gap=T.px(10), padding=(T.px(24), T.px(24)))
  channel = SettingRow(N_("Release Channel"), lambda: N_("Choose another branch") if model.tuner() else N_("Other branches are in Tuner Mode"),
                       ValueButton(model.channel))
  channel.set_enabled(model.tuner)
  automatic = SettingRow(N_("Automatic Updates"), N_("Download and install while parked"), Switch(lambda: model.automatic, model.set_automatic))
  automatic.set_enabled(model.can_set_automatic)
  # Reset Settings returns once the Essentials defaults are ported (PORTING.md); until then it shows, as release's, but can't run.
  reset = SettingRow(N_("Reset Settings"), N_("Back to the Essentials defaults. Backups are kept."), Button(N_("Reset")))
  reset.set_enabled(False)
  settings = ListPanel([automatic, channel, reset],
                       footer=Button(N_("Uninstall"), lambda: uninstall(model, window), ButtonStyle.DANGER_SOFT, height=T.px(52)))
  return FillPage(Columns([version, settings], [1, 1.15]))


class SoftwarePage(Component):
  """The Software tab's page; it keeps StarPilot's software state current while shown."""
  grow_touch_target = False

  def __init__(self, model: Software, window: SettingsWindow) -> None:
    super().__init__()
    self._model = model
    self._page = self._child(software_page(model, window))

  def show_event(self) -> None:
    super().show_event()
    self._model.watch.refresh()

  def _update_state(self) -> None:
    self._model.tick()

  def _render(self, rect: rl.Rectangle) -> None:
    self._page.render(rect)
