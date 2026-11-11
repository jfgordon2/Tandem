"""Software: version and update status, automatic updates, release channel, Reset Settings, and Uninstall.

Checking, downloading and installing are upstream's SoftwareLayout actions, so they keep its signals to the updater.
Choosing a branch and uninstalling use our sheet and dialogs, then write what upstream's would. Reset Settings applies
the Essentials defaults.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TYPE_CHECKING

import pyray as rl

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import SPACER, Card, Columns, Label
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch, Tone, ValueButton
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text
from openpilot.selfdrive.ui.tandem.settings.bundles import TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.pages import FillPage
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

if TYPE_CHECKING:
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow


class UpdateActions(Protocol):
  """What the Software tab needs from StarPilot's updater: check, download, install, branches and release notes."""

  def tick(self) -> None: ...
  def check_or_download(self) -> None: ...
  def install(self) -> None: ...
  def branches(self) -> list[str]: ...          # upstream's order: the current branch and the common ones first
  def target_branch(self) -> str: ...
  def set_branch(self, branch: str) -> None: ...
  def uninstall(self, erase: bool) -> None: ...  # erase: a factory reset too
  def release_notes(self) -> str: ...           # plain text


UPDATER_STATES = {"checking": N_("Checking for an update"), "downloading": N_("Downloading the update"), "finalizing": N_("Getting the update ready")}


class Software:
  """The Software tab: the version, update state and action, automatic updates and branch."""

  def __init__(self, store: SettingsStore, actions: UpdateActions, reset: Callable[[], None]):
    self._store = store
    self.actions = actions
    self._reset = reset

  def version(self) -> str:
    return self._store.get_str("UpdaterCurrentDescription") or N_("Unknown version")

  def version_parts(self) -> tuple[str, str]:
    """"0.10.1 / release / Oct 28" as ("0.10.1", "release · Oct 28")."""
    number, *rest = [p.strip() for p in self.version().split(" / ")]
    return number, " · ".join(rest)

  def state(self) -> str:
    """One of: busy, failed, available (to download), ready (to install), current."""
    if (self._store.get_str("UpdaterState") or "idle") != "idle":
      return "busy"
    if self._store.get_bool("UpdateAvailable"):
      return "ready"
    if self._store.get_int("UpdateFailedCount") > 0:
      return "failed"
    return "available" if self._store.get_bool("UpdaterFetchAvailable") else "current"

  def status_badge(self) -> tuple[str, Tone]:
    return {"busy": (N_("Updating"), Tone.ACCENT), "ready": (N_("Ready to install"), Tone.SUCCESS), "failed": (N_("Check failed"), Tone.WARNING),
            "available": (N_("Update available"), Tone.ACCENT), "current": (N_("Up to date"), Tone.SUCCESS)}[self.state()]

  def status_line(self) -> str:
    """The update state in a line, under the version."""
    state = self.state()
    if state == "busy":
      return UPDATER_STATES.get(self._store.get_str("UpdaterState"), N_("Updating"))
    if state == "ready":
      return t_("{} installs when you turn off the car or restart", self._store.get_str('UpdaterNewDescription') or 'A new version')
    if state == "failed":
      return N_("Couldn't check for updates. Check the connection and try again.")
    if state == "available":
      return N_("A new version is available to download")
    return N_("You have the latest version")

  def action_label(self) -> str:
    labels = {"busy": N_("Working…"), "ready": N_("Restart to install"), "failed": N_("Try again"), "available": N_("Download")}
    return labels.get(self.state(), N_("Check now"))

  def act(self) -> None:
    if self.state() == "ready":
      self.actions.install()
    elif self.state() != "busy":
      self.actions.check_or_download()

  @property
  def automatic(self) -> bool:
    return self._store.get_bool("AutomaticUpdates")

  def set_automatic(self, on: bool) -> None:
    self._store.write({"AutomaticUpdates": on})

  def channel(self) -> str:
    branch = self._store.get_str("UpdaterTargetBranch") or self._store.get_str("GitBranch")
    return {"release": N_("Stable"), "release3": N_("Stable"), "master": N_("Stable"), "staging": N_("Beta")}.get(branch, branch or N_("Stable"))

  def tuner(self) -> bool:
    return TUNER_MODE.is_on(self._store)

  def reset_settings(self) -> None:
    self._reset()


STATUS_INK = {Tone.SUCCESS: T.SUCCESS_TEXT, Tone.ACCENT: T.ACCENT_TEXT, Tone.WARNING: T.WARNING}


def notes_text(html: str) -> str:
  """Release notes arrive as the updater's HTML; our sheet shows plain paragraphs and bullets."""
  import html as html_lib
  import re
  text = re.sub(r"<\s*li[^>]*>", "• ", html, flags=re.I)
  text = re.sub(r"<\s*(br|/p|/li|/h[1-6]|/ul|/ol)[^>]*>", "\n", text, flags=re.I)
  text = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
  lines = [line.strip() for line in text.splitlines()]
  return "\n".join(line for line in lines if line) or N_("No release notes for this version.")


def show_notes(model: Software, window: SettingsWindow) -> None:
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  paragraphs = [Text(p, T.font_px(17), T.TEXT_SECONDARY) for p in model.actions.release_notes().split("\n") if p.strip()]
  window.present(Sheet(t_("What's new in {}", model.version_parts()[0]), ListPanel(paragraphs, dividers=False, header_divider=False),
                       on_dismiss=window.dismiss))


def choose_branch(model: Software, window: SettingsWindow) -> None:
  """Release Channel's picker, offered in Tuner Mode."""
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  from openpilot.selfdrive.ui.tandem.rows import OptionList
  branches = model.actions.branches()
  if not branches:
    return

  def pick(index: int) -> None:
    model.actions.set_branch(branches[index])
    window.dismiss()
  current = lambda: branches.index(model.actions.target_branch()) if model.actions.target_branch() in branches else 0  # noqa: E731
  window.present(Sheet(N_("Release Channel"), OptionList(branches, current, pick), subtitle=N_("The branch to download updates from"),
                       on_dismiss=window.dismiss))


def uninstall(model: Software, window: SettingsWindow) -> None:
  """Upstream's three steps in our dialogs: uninstall, then whether to erase everything too, then a last check."""
  from openpilot.selfdrive.ui.tandem import draw
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  from openpilot.system.ui.widgets import DialogResult
  trash = lambda r, c, s: draw.icon(r, "trash", c, s)  # noqa: E731

  def last(result: DialogResult) -> None:
    window.dismiss()
    model.actions.uninstall(erase=result == DialogResult.CONFIRM)   # as upstream: cancelling here still uninstalls

  def erase(result: DialogResult) -> None:
    window.dismiss()
    if result == DialogResult.CONFIRM:
      window.present(Dialog(N_("Erase everything?"), N_("Every setting, drive and download is deleted. This can't be undone."), N_("Erase"),
                            last, tone=Tone.DANGER, glyph=trash))
    else:
      model.actions.uninstall(erase=False)

  def first(result: DialogResult) -> None:
    window.dismiss()
    if result == DialogResult.CONFIRM:
      window.present(Dialog(N_("Factory reset too?"), N_("A factory reset also deletes every setting, drive and download. Skip keeps them."),
                            N_("Factory Reset"), erase, cancel_label=N_("Skip"), tone=Tone.DANGER, glyph=trash))

  window.present(Dialog(N_("Uninstall openpilot?"), N_("The device removes openpilot and starts its setup again."), N_("Uninstall"), first,
                        tone=Tone.DANGER, glyph=trash))


def software_page(model: Software, confirm: Callable[[str, str, str, Callable[[], None]], None], window: SettingsWindow) -> Widget:
  """The version and its actions on the left; update settings on the right."""
  action = Button(model.action_label, model.act, ButtonStyle.SECONDARY, height=T.px(56), font_size=T.font_px(17), weight=T.FONT_BOLD)
  action.set_enabled(lambda: model.state() != "busy")
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
                       ValueButton(model.channel, lambda: choose_branch(model, window)))
  channel.set_enabled(model.tuner)
  settings = ListPanel([
    SettingRow(N_("Automatic Updates"), N_("Download while parked, install when you turn off the car"),
               Switch(lambda: model.automatic, model.set_automatic)),
    channel,
    SettingRow(N_("Reset Settings"), N_("Back to the Essentials defaults. Backups are kept."),
               Button(N_("Reset"), lambda: confirm(N_("Reset settings?"), N_("Every setting goes back to the Essentials default. Your backups are kept."),
                                               N_("Reset"), model.reset_settings))),
  ], footer=Button(N_("Uninstall"), lambda: uninstall(model, window), ButtonStyle.DANGER_SOFT, height=T.px(52)))
  return FillPage(Columns([version, settings], [1, 1.15]))


class SoftwarePage(Component):
  """The Software tab's page; it keeps the updater's state current while shown."""
  grow_touch_target = False

  def __init__(self, model: Software, confirm: Callable[[str, str, str, Callable[[], None]], None], window: SettingsWindow) -> None:
    super().__init__()
    self._model = model
    self._page = self._child(software_page(model, confirm, window))

  def _update_state(self) -> None:
    self._model.actions.tick()

  def _render(self, rect: rl.Rectangle) -> None:
    self._page.render(rect)


class UpstreamUpdates:
  """UpdateActions backed by upstream's SoftwareLayout, whose state machine tracks the updater."""

  def __init__(self) -> None:
    from openpilot.selfdrive.ui.layouts.settings.software import SoftwareLayout
    self._layout = SoftwareLayout()

  def tick(self) -> None:
    self._layout._update_state()

  def check_or_download(self) -> None:
    self._layout._on_download_update()

  def install(self) -> None:
    self._layout._on_install_update()

  def branches(self) -> list[str]:
    """As upstream's branch picker lists them."""
    from openpilot.selfdrive.ui.ui_state import ui_state
    current = ui_state.ui_params.get("GitBranch") or ""
    branches = [b for b in (ui_state.ui_params.get("UpdaterAvailableBranches") or "").split(",") if b]
    for b in [current, "devel-staging", "devel", "nightly", "nightly-dev", "master"]:
      if b in branches:
        branches.remove(b)
        branches.insert(0, b)
    return branches

  def target_branch(self) -> str:
    from openpilot.selfdrive.ui.ui_state import ui_state
    return ui_state.ui_params.get("UpdaterTargetBranch") or ""

  def set_branch(self, branch: str) -> None:
    """What upstream's picker does on a choice: the target branch, then a nudge to the updater to check."""
    import os
    from openpilot.selfdrive.ui.ui_state import ui_state
    ui_state.ui_params.put("UpdaterTargetBranch", branch)
    os.system("pkill -SIGUSR1 -f system.updated.updated")

  def uninstall(self, erase: bool) -> None:
    """What upstream's last uninstall step does: a factory reset clears every param first."""
    from openpilot.selfdrive.ui.ui_state import ui_state
    if erase:
      ui_state.ui_params.clear_all()
    ui_state.ui_params.put_bool("DoUninstall", True)

  def release_notes(self) -> str:
    from openpilot.selfdrive.ui.ui_state import ui_state
    return notes_text((ui_state.ui_params.get("UpdaterCurrentReleaseNotes") or b"").decode("utf-8", "replace"))
