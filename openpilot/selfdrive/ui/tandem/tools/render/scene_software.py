"""Render the installed Software panel in the native Settings frame."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.controls import Button, Switch
from openpilot.selfdrive.ui.tandem.home_software import HomeSoftware, InstallTarget
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow
from openpilot.selfdrive.ui.tandem.settings.software import Page, SoftwarePanel
from openpilot.selfdrive.ui.tandem.settings.software_state import InstallPreference, SoftwareState, SoftwareWatch, Stage
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.lib.application import FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget


NAV = (("Device", 0), ("Network", 1), ("Toggles", 2), ("Software", 3), ("Firehose", 4), ("Developer", 5))


def settings_frame(gui_app: Any) -> None:
  """Draw the native Settings rail around the tested Software widget."""
  background = rl.Color(41, 41, 41, 255)
  draw.fill(rl.Rectangle(510, 10, 1640, 1060), background, 23)
  close = rl.Rectangle(150, 60, 200, 200)
  draw.fill(close, background, 100)
  draw.icon(close, "close", rl.WHITE, 70)
  font = gui_app.font(FontWeight.MEDIUM)
  for title, index in NAV:
    y = 300 + 110 * index
    measure = measure_text_cached(font, title, 65)
    color = rl.WHITE if title == "Software" else rl.Color(128, 128, 128, 255)
    rl.draw_text_ex(font, title, rl.Vector2(400 - measure.x, y + (110 - measure.y) / 2), 65, 0, color)


def options_fixture() -> Widget:
  """Use sample native rows in host renders. Production opens the original widget."""
  entries = [SettingRow("Current Version", "7.0.0", height=T.px(69)),
             SettingRow("Automatically Download Updates", control=Switch(True), height=T.px(69))]
  for label, action in (("Download", "CHECK"), ("Fast Update", "UPDATE"), ("Previous Version", "RESTORE"),
                        ("Target Branch", "SELECT"), ("Uninstall", "UNINSTALL"), ("Error Log", "VIEW")):
    entries.append(SettingRow(label, control=Button(action), height=T.px(69)))
  return ListPanel(entries, background=rl.Color(41, 41, 41, 255), header_divider=False)


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Render the ten approved states with the same data as the mocks."""
  last_checked = (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
  notes = "Improved display stability when entering or leaving a drive.\nUpdated speed-limit status on the driving screen."
  base = SoftwareState(stage=Stage.CURRENT, home=HomeSoftware(installed="7.0.0", current=True), branch="development",
                       installed_notes=notes, last_checked=last_checked, downloads=True, can_check=True, can_configure=True,
                       installs=InstallPreference(False, "0 0 * * *", "America/Chicago", "a" * 32))
  target = InstallTarget("development", "a" * 40, "b" * 40)
  assert base.installs is not None
  ready = replace(base, stage=Stage.READY, home=HomeSoftware("7.0.0", False, "7.0.1", notes, True, target),
                  next_restart="2026-11-17T00:00:00-06:00", installs=replace(base.installs, enabled=True))
  samples = (
    ("current", base, Page.MAIN), ("checking", replace(base, stage=Stage.CHECKING, can_check=False), Page.MAIN),
    ("available", replace(base, stage=Stage.AVAILABLE, can_download=True), Page.MAIN),
    ("downloading", replace(base, stage=Stage.DOWNLOADING, percent=42, can_check=False), Page.MAIN),
    ("ready", ready, Page.MAIN),
    ("park", replace(base, stage=Stage.PARK, can_check=False, can_configure=False), Page.MAIN),
    ("error", replace(base, stage=Stage.CHECK_FAILED), Page.MAIN),
    ("notes", ready, Page.UPDATE_NOTES), ("installed-notes", base, Page.INSTALLED_NOTES),
    ("options", base, Page.OPTIONS),
  )
  for name, state, page in samples:
    watch = SoftwareWatch(lambda: None, lambda _key: None, lambda state=state: state.stage != Stage.PARK, lambda _error: None)
    watch.state = state
    widget = SoftwarePanel(lambda _authorized, watch=watch: watch, options_fixture, lambda: True)
    widget.show_event()
    watch._next = float("inf")
    if page == Page.OPTIONS:
      widget._open_options()
    elif page == Page.UPDATE_NOTES:
      widget._open_update_notes(target)
    elif page != Page.MAIN:
      widget._set_page(page)

    def render(panel: SoftwarePanel = widget) -> None:
      settings_frame(gui_app)
      panel.render(rl.Rectangle(550, 25, 1560, 1030))

    for _ in range(12):
      frame(render)
    save(f"{out}/stage4-software-{name}.png")
    widget.hide_event()
    watch.close()
