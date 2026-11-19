"""The Driving tab: release's hub and pages, on StarPilot 7's settings owners (settings/starpilot7.py)."""
from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, TYPE_CHECKING

from openpilot.starpilot.ui.raylib import rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.blocks import Columns
from openpilot.selfdrive.ui.tandem.chrome import HubTile
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ToggleButton
from openpilot.selfdrive.ui.tandem.places import StarPilotPlaces
from openpilot.selfdrive.ui.tandem.prefs import TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts, alerts_page
from openpilot.selfdrive.ui.tandem.settings.bundles import BUNDLES, Bundle
from openpilot.selfdrive.ui.tandem.settings.device import driver_monitoring_rows
from openpilot.selfdrive.ui.tandem.settings.display import Display, driving_screen_panel, path_panel
from openpilot.selfdrive.ui.tandem.settings.maps import Maps, MapsPage, MapsSource, RegionsPage
from openpilot.selfdrive.ui.tandem.settings.model import CatalogPage, Models, ModelSource, model_page
from openpilot.selfdrive.ui.tandem.settings.navigation import NavigationSettings, navigation_panel
from openpilot.selfdrive.ui.tandem.settings.pages import FillPage, HubPage, Section, SectionPage, Strip
from openpilot.selfdrive.ui.tandem.settings.speed_steering import (Assistance, Rows, SpeedSteering, Weather, assistance_panel,
                                                                   driver_monitoring_panel, everyday_panel, weather_panel)
from openpilot.selfdrive.ui.tandem.settings.starpilot7 import RoadStyle
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.settings.live import Live
from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner, tuner_page
from openpilot.selfdrive.ui.tandem.settings.vehicle import Vehicle, extras_page, vehicle_page
from openpilot.selfdrive.ui.tandem.i18n import N_

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.search import Entry
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow


class Lazy[V]:
  """A model made on first use, so opening Driving doesn't build every page's state."""

  def __init__(self, make: Callable[[], V]):
    self._make = make
    self._value: V | None = None

  def get(self) -> V:
    if self._value is None:
      self._value = self._make()
    return self._value


def chevron_glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.chevron(rect, color, size)


class DrivingServices:
  """What the Driving tab needs from StarPilot and the device, made by essentials.py on the device and by fakes in tests.

  Args:
    store: Plain openpilot settings.
    live: The car's live state.
    rows: StarPilot's settings pages.
    road: The path's look in StarPilot's onroad layout.
    models: StarPilot's driving models, made on first use.
    vehicle: The car picker, door locks and wheel buttons, made on first use.
    device: DeviceOwner, for the driver camera preview and the driver monitoring reset.
    owns_set: Whether StarPilot sets MAX on this car (not the car's own cruise).
    play: Plays an alert sample.
    storage: Storage & Data's sizes, for the model catalog.
    recount: Has Storage & Data measure again.
    ram: Whether Device › RAM is showing (a drive has run low), so search finds it.
    navigation: StarPilot's navigation (places.py), made on first use; the real one by default.
    maps: Offline Maps' source (settings/map_source.py), made on first use; None without offline routing.
  """

  def __init__(self, store: SettingsStore, live: Live, rows: Rows, road: RoadStyle, models: Callable[[], ModelSource],
               vehicle: Callable[[], Vehicle], device: Any, owns_set: Callable[[], bool], play: Callable[[str], None] | None = None,
               storage: Callable[[], dict[str, float]] = dict, recount: Callable[[], None] = lambda: None,
               ram: Callable[[], bool] = lambda: False, navigation: Callable[[], StarPilotPlaces] | None = None,
               maps: Callable[[], MapsSource] | None = None):
    self.store, self.live, self.rows, self.road = store, live, rows, road
    self.models, self.vehicle, self.device, self.owns_set = models, vehicle, device, owns_set
    self.play, self.storage, self.recount, self.ram = play, storage, recount, ram
    self.navigation = navigation or _device_navigation
    self.maps = maps


def _device_navigation() -> StarPilotPlaces:
  """StarPilot's navigation on the device: changes while not replaying or projecting, as Where to? makes them."""
  from openpilot.selfdrive.ui.ui_state import ui_state
  return StarPilotPlaces(allowed=lambda: ui_state.replay_clock is None and not ui_state.projection_read_only,
                         metric=lambda: bool(ui_state.is_metric))


def driving_hub(window: SettingsWindow, services: DrivingServices) -> HubPage:
  """The Driving tab's hub: its tiles, and the pages each opens."""
  from openpilot.selfdrive.ui.tandem.settings.window import Tab, confirm
  store, rows = services.store, services.rows

  def ask(title: str, message: str, label: str, action: Callable[[], None]) -> None:
    confirm(window, title, message, label, action, danger=False, icon="warning")

  speed = SpeedSteering(store, rows, ask, services.owns_set)
  weather = Weather()
  assistance = Assistance(store, services.live, rows)
  screen = Display(rows, services.road)
  alerts = Alerts(rows, services.play)
  models = Lazy(lambda: Models(services.models(), services.recount))
  places = Lazy(services.navigation)
  navigation = Lazy(lambda: NavigationSettings(places.get()))
  make_maps = services.maps
  maps = Lazy(lambda: Maps(make_maps())) if make_maps is not None else None

  def open_maps() -> None:
    """Offline Maps, and from it the region picker; a download goes back to the maps page, which shows its progress."""
    if maps is None:
      return
    def open_regions() -> None:
      def download() -> None:
        maps.get().source.download()
        window.back()
      window.push(RegionsPage(maps.get(), download))
    window.push(MapsPage(maps.get(), open_regions, services.storage, window))
  vehicle = Lazy(services.vehicle)

  def set_bundle(bundle: Bundle, on: bool) -> None:
    bundle.set(rows, on)

  def set_tuner(on: bool) -> None:
    TUNER_MODE.set(on)
    if on:
      open_tuner()

  def opener(make: Callable[[], Widget]) -> Callable[[], None]:
    return lambda: window.push(make())

  def open_tuner() -> None:
    window.push(tuner_page(Tuner(rows), window))

  def open_destinations() -> None:
    """Where to? over the settings window, on the same navigation as this page."""
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.selfdrive.ui.tandem.destinations import destinations_screen
    def maps_instead() -> None:
      gui_app.pop_widget()
      open_maps()
    gui_app.push_widget(destinations_screen(gui_app.pop_widget, maps_instead if maps is not None else None, places=places.get()))

  def open_key_help() -> None:
    from openpilot.selfdrive.ui.tandem.map_keys import map_key_sheet
    window.present(map_key_sheet(window.dismiss))

  def speed_steering() -> Widget:
    tuner_button = Button(N_("Tuner Mode"), open_tuner, ButtonStyle.SECONDARY, width=T.SIDEBAR_WIDTH, accessory=chevron_glyph)
    tuner_button.set_visible(TUNER_MODE.get)
    return SectionPage(N_("SPEED & STEERING"), [
      Section(N_("Everyday"), lambda: everyday_panel(speed)),
      Section(N_("Weather"), lambda: weather_panel(weather), value=weather.summary),
      Section(N_("Navigation"), lambda: navigation_panel(navigation.get(), open_destinations, open_key_help,
                                                         (lambda: maps.get()) if maps is not None else None, open_maps),
              value=lambda: navigation.get().summary()),
    ], footer=[tuner_button])

  def assistance_page() -> Widget:
    """openpilot's core switches beside driver monitoring, gathered from Speed & Steering and This Device."""
    def confirm_reset(title: str, message: str, label: str, action: Callable[[], None], danger: bool, icon: str) -> None:
      confirm(window, title, message, label, action, danger, icon)
    return FillPage(Columns([assistance_panel(assistance),
                             driver_monitoring_panel(assistance, driver_monitoring_rows(services.device, confirm_reset))], [1.4, 1]))

  def display() -> Widget:
    return SectionPage(N_("DISPLAY"), [
      Section(N_("Driving Screen"), lambda: driving_screen_panel(screen, window)),
      Section(N_("Path"), lambda: path_panel(screen, window)),
    ])

  def model() -> Widget:
    return model_page(models.get(), opener(lambda: CatalogPage(models.get(), services.storage)))

  def car() -> Widget:
    return vehicle_page(vehicle.get(), window, opener(lambda: extras_page(vehicle.get(), window)))

  bundle_buttons = []
  for bundle in BUNDLES:
    button = ToggleButton(bundle.name, partial(bundle.is_on, rows), partial(set_bundle, bundle))
    button.set_enabled(partial(bundle.editable, rows))   # StarPilot changes these only while parked
    bundle_buttons.append(button)
  strip = Strip(N_("POWER USER"), N_("Extra detail and fine tuning, each behind one switch"),
                [*bundle_buttons, ToggleButton(N_("Tuner Mode"), TUNER_MODE.get, set_tuner)])

  def open_search() -> None:
    from openpilot.selfdrive.ui.tandem.settings.search import SettingsSearch

    def pick(entry: Entry) -> None:
      window.dismiss()
      window.open_at(Tab(entry.tab), entry.section, entry.page)
    window.present(SettingsSearch(TUNER_MODE.get, pick, window.dismiss, ram=services.ram))

  from openpilot.selfdrive.ui.tandem.settings.search import SearchButton
  hub = HubPage(N_("Driving"), N_("Good defaults are on. Change only what matters to you."), [
    HubTile(N_("Speed & Steering"), [speed.summary, speed.speed_limit_summary], opener(speed_steering), icon="wheel"),
    HubTile(N_("Display"), [screen.summary, screen.path_summary], opener(display), icon="display"),
    HubTile(N_("Alerts"), [alerts.summary, alerts.chimes_summary], opener(lambda: alerts_page(alerts, window)), icon="volume"),
    HubTile(N_("Driving Model"), [lambda: models.get().summary(), lambda: models.get().update_summary()], opener(model), icon="model"),
    HubTile(N_("Vehicle"), [lambda: vehicle.get().car(), lambda: vehicle.get().buttons_summary()], opener(car), icon="car"),
    HubTile(N_("Assistance"), [assistance.summary, assistance.monitoring_summary], opener(assistance_page), icon="shield"),
  ], rows=[3, 3], strip=strip, trailing=SearchButton(open_search))
  # Each page the hub opens, by name, for settings search to open a result's page.
  hub.pages = {"speed_steering": opener(speed_steering), "display": opener(display), "alerts": opener(lambda: alerts_page(alerts, window)),
               "model": opener(model), "vehicle": opener(car), "assistance": opener(assistance_page), "tuner": open_tuner,
               "maps": open_maps}
  return hub
