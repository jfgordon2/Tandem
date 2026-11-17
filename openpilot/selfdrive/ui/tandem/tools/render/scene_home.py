"""Capture the approved parked Home screens at 2160×1080."""
from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem.forecast import HourTile, Outlook
from openpilot.selfdrive.ui.tandem.home import HomeContent, HomeState, home_content_rect
from openpilot.selfdrive.ui.tandem.home_alerts import AlertsView, HomeAlert, UpdateView
from openpilot.selfdrive.ui.tandem.software import HomeSoftware, InstallTarget
from openpilot.selfdrive.ui.tandem.sidebar import WIDTH, Health, SidebarState, SidebarView, Status, connect_status, network_status
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.widgets import Widget


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  sidebar = SidebarView(lambda: SidebarState([
    network_status("Wi-Fi", 4), connect_status(Health.GOOD), Status("Temperature", "Good", Health.GOOD),
    Status("Vehicle", "Connected", Health.GOOD), Status("Maps", "Ready", Health.GOOD),
  ]), lambda: None, lambda: None, lambda: None)
  setup = "Standard style · Matching speed limits · Nudge to change lanes"
  installed = HomeSoftware(installed="7.0.0", current=True)
  update = HomeSoftware(installed="7.0.0", version="7.0.1", target=InstallTarget("development", "0" * 40, "1" * 40))
  notes = "Version 7.0.1\n• Smoother lane changes on curvy roads\n• Speed limits from offline maps in more states\n• Fixes for Toyota and Hyundai"
  forecast = Outlook("Light snow from 5:45 to 8:30 PM", "snow", True, "2:10 PM", [
    HourTile(f"{hour} {'PM' if index < 9 else 'AM'}", icon, temp, index in (3, 4, 5))
    for index, (hour, icon, temp) in enumerate(zip(
      (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2),
      ("cloud", "cloud", "cloud", "snow", "snow", "snow", "cloud", "cloud", "moon", "moon", "moon", "moon"),
      (34, 33, 32, 31, 30, 29, 28, 27, 26, 26, 25, 25), strict=True))
  ])
  alerts = [
    HomeAlert("Offroad_ConnectivityNeeded",
              "Connect to the internet to check for updates. openpilot won't start until it can check.", True),
    HomeAlert("Offroad_Recalibration",
              "openpilot detected a change in the device's mounting position. Make sure it's fully seated and the mount is secure.", False),
  ]
  noop = lambda: None  # noqa: E731
  samples: tuple[tuple[str, Widget], ...] = (
    ("stage4-home", HomeContent(lambda: HomeState(setup=setup, software=installed), noop, noop, noop)),
    ("stage4-home-update-ready", HomeContent(lambda: HomeState(setup=setup, software=update), noop, noop, noop)),
    ("stage4-home-update-notes", UpdateView(lambda: "7.0.1", lambda: notes, noop, noop, lambda: False, lambda: True)),
    ("stage4-home-update-scheduled", UpdateView(lambda: "7.0.1", lambda: notes, noop, noop, lambda: True, lambda: True)),
    ("stage4-home-alerts", AlertsView(lambda: alerts, noop, lambda: ("Snooze update", noop))),
    ("stage4-home-weather", HomeContent(lambda: HomeState(ignition=True, setup=setup, software=update), noop, noop, noop,
                                        lambda: forecast)),
  )
  for name, widget in samples:
    def render(view: Widget = widget) -> None:
      sidebar.render(rl.Rectangle(0, 0, WIDTH, 1080))
      view.render(home_content_rect(rl.Rectangle(WIDTH, 0, 2160 - WIDTH, 1080)))

    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
