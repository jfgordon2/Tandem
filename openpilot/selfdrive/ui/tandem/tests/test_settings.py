"""Settings search (settings/search.py): its index matches the screens, and a result opens where its setting lives.

Driving and Connections are built over the test stand-ins and walked for their rows. Device and Software rows are checked
against the strings their screens are written with, as those screens need the device's owners to build.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from openpilot.selfdrive.ui.tandem import prefs
from openpilot.selfdrive.ui.tandem.base import resolve
from openpilot.selfdrive.ui.tandem.places import StarPilotPlaces
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeNavigationOwner
from openpilot.selfdrive.ui.tandem.rows import SettingRow
from openpilot.selfdrive.ui.tandem.settings import connections, search
from openpilot.selfdrive.ui.tandem.settings.pages import Rebuilding, SectionPage
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.system.ui.widgets import Widget

SETTINGS = Path(__file__).resolve().parents[1] / "settings"


def titles(widget: Any) -> set[str]:
  """Every SettingRow title in a widget tree."""
  found: set[str] = set()
  seen: set[int] = set()

  def walk(node: Any) -> None:
    if node is None or id(node) in seen:
      return
    seen.add(id(node))
    if isinstance(node, Rebuilding):
      node._update_state()   # builds its content, as the first frame would
    if isinstance(node, SettingRow):
      found.add(str(resolve(node._title)))
    for value in vars(node).values():   # children, item lists, built content and bottom rows alike
      for child in value if isinstance(value, (list, tuple)) else [value]:
        if isinstance(child, Widget):
          walk(child)
  walk(widget)
  return found


def section_titles(page: SectionPage) -> list[set[str]]:
  """Each section's rows, opening every section in turn."""
  out = []
  for index in range(len(page._sections)):
    page.select(index)
    out.append(titles(page.current))
  return out


@pytest.fixture
def driving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[SettingsWindow, Any]:
  from openpilot.selfdrive.ui.tandem.settings.driving_tab import DrivingServices, driving_hub
  from openpilot.selfdrive.ui.tandem.settings.model import StarPilotModels
  from openpilot.selfdrive.ui.tandem.settings.vehicle import Vehicle
  from openpilot.selfdrive.ui.tandem.tests.test_display_alerts_port import FakeRoad
  from openpilot.selfdrive.ui.tandem.tests.test_driving_port import FakeDoors, FakeManager, FakeSelection
  from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Store
  from openpilot.selfdrive.ui.tandem.tools.render.scene_driving import ExampleDevice, ExampleLive, example_owner
  monkeypatch.setattr(prefs, "prefs_dir", lambda: tmp_path)
  owner = example_owner()
  vehicle = Vehicle(FakeSelection(), owner.rows, FakeDoors(), lambda: "TOYOTA_RAV4H")
  services = DrivingServices(Store(LongitudinalPersonality=1), ExampleLive(), owner.rows, FakeRoad(),  # type: ignore[arg-type]
                             lambda: StarPilotModels(FakeManager(), clock=lambda: 0.0), lambda: vehicle, ExampleDevice(), lambda: True,
                             navigation=lambda: StarPilotPlaces(FakeNavigationOwner))
  window = SettingsWindow({Tab.DRIVING: lambda: hub}, initial=Tab.DRIVING)
  hub = driving_hub(window, services)
  window.show_event()
  return window, hub


def indexed(tab: int, page: str | None = None, section: int | None = None) -> set[str]:
  return {e.name for e in search.ENTRIES if e.row and e.tab == tab and e.page == page and (section is None or e.section == section)}


@pytest.mark.parametrize("page", ["speed_steering", "display"])
def test_driving_section_pages_match_the_index(driving: tuple[SettingsWindow, Any], page: str) -> None:
  window, hub = driving
  hub.pages[page]()
  for index, rows in enumerate(section_titles(window.top)):
    assert rows == indexed(0, page, index), (page, index)


@pytest.mark.parametrize("page", ["alerts", "vehicle", "assistance"])
def test_driving_pages_match_the_index(driving: tuple[SettingsWindow, Any], page: str) -> None:
  window, hub = driving
  hub.pages[page]()
  shown = titles(window.top)
  if page == "vehicle":
    shown -= {"Distance short press", "Distance long press", "LKAS press"}   # StarPilot's own names for this car's buttons
  assert shown == indexed(0, page)


def test_connections_match_the_index() -> None:
  from openpilot.selfdrive.ui.tandem.tests.fakes import connections_window
  window: Any = connections_window()
  window.show_event()
  networks = {"Home Wi-Fi", "Coffee Shop", "Neighbor"}   # the stand-in's nearby networks, each a row
  networks |= {"Download", "Upload", "Ping"}               # the network test's results: measurements, not settings
  networks |= {"Car Audio", "Pixel 9", "Wheel Remote"}     # the stand-in's Bluetooth devices
  for index, rows in enumerate(section_titles(window.top)):
    assert rows - networks == indexed(2, section=index), index


@pytest.mark.parametrize("tab,files", [(1, ["device.py", "general.py", "storage.py", "developer.py"]), (3, ["software.py"])])
def test_device_and_software_rows_are_on_their_screens(tab: int, files: list[str]) -> None:
  source = "".join((SETTINGS / name).read_text() for name in files)
  missing = [e.name for e in search.ENTRIES if e.tab == tab and e.row and f'N_("{e.name}")' not in source]
  assert not missing


def test_search_finds_settings_by_name_and_by_what_people_call_them() -> None:
  assert search.search("compass", tuner=False)[0].name == "Compass"
  assert search.search("speed test", tuner=False)[0].name == "Network Test"
  assert search.search("network test", tuner=False)[0].where == "Connections"
  assert "Network Test" in [e.name for e in search.search("latency", tuner=False)]
  assert not search.search("following gaps", tuner=False) and search.search("following gaps", tuner=True)
  assert not search.search("x", tuner=True)


def test_a_result_opens_its_page_and_section(driving: tuple[SettingsWindow, Any]) -> None:
  window, _ = driving
  entry = search.search("weather heads-up", tuner=False)[0]
  window.open_at(Tab(entry.tab), entry.section, entry.page)
  assert isinstance(window.top, SectionPage) and window.top.selected == entry.section == search.SECTIONS["speed_steering"].index("Weather")
  path = search.search("path style", tuner=False)[0]
  window.open_at(Tab(path.tab), path.section, path.page)
  assert window.top.selected == 1 and "Path Style" in titles(window.top.current)


def test_network_test_is_found_at_its_section() -> None:
  entry = search.search("speed test", tuner=False)[0]
  assert entry.section == connections.TEST
