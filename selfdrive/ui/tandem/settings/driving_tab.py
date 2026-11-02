"""The Driving tab: a hub of six tiles and the power-user switches."""
from __future__ import annotations

from collections.abc import Callable

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.chrome import HubTile
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, ToggleButton
from openpilot.selfdrive.ui.tandem.settings.bundles import BUNDLES, TUNER_MODE
from openpilot.selfdrive.ui.tandem.settings.alerts import Alerts, alerts_page, sound_player
from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner, tuner_page
from openpilot.selfdrive.ui.tandem.settings.maps import Maps, MapsPage, RegionsPage
from openpilot.selfdrive.ui.tandem.settings.model import CatalogPage, Models, model_page
from openpilot.selfdrive.ui.tandem.settings.vehicle import Vehicle, extras_page, vehicle_page
from openpilot.selfdrive.ui.tandem.settings.display import Display, driving_screen_panel, edit_startup_message, map_panel, theme_panel
from openpilot.selfdrive.ui.tandem.blocks import Columns
from openpilot.selfdrive.ui.tandem.settings.device import driver_monitoring_rows
from openpilot.selfdrive.ui.tandem.settings.pages import FillPage, HubPage, Section, SectionPage, Strip
from openpilot.selfdrive.ui.tandem.settings.speed_steering import (Assistance, Navigation, SpeedSteering, VehicleProfile, Weather,
                                                                   assistance_panel, driver_monitoring_panel, everyday_panel, navigation_panel,
                                                                   vehicle_profile_panel, weather_panel)


class Lazy:
  def __init__(self, make: Callable):
    self._make = make
    self._value = None

  def get(self):
    if self._value is None:
      self._value = self._make()
    return self._value


def chevron_glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.chevron(rect, color, size)


def driving_hub(window) -> Widget:
  """window provides store, live, push and pop."""
  store, live = window.store, window.live
  speed = SpeedSteering(store)
  profile = VehicleProfile(store)
  weather = Weather(store)
  navigation = Navigation(store)
  assistance = Assistance(store, live)
  screen = Display(store, window.boot_logos)
  alerts = Alerts(store, sound_player())
  # Model and car data come from StarPilot's own screens, built the first time they're needed.
  models = Lazy(lambda: Models(store, window.model_source()))
  vehicle = Lazy(lambda: Vehicle(store, window.car_catalog()))
  maps = Lazy(lambda: Maps(store, window.maps_source()))

  def open_maps() -> None:
    def open_regions() -> None:
      def download() -> None:
        maps.get().source.download()
        window.pop()
      window.push(RegionsPage(maps.get(), download))
    window.push(MapsPage(maps.get(), open_regions, window.device_data().storage, window))

  def open_destinations() -> None:
    """Where to? over the settings window; its Offline maps button closes it and opens ours."""
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.selfdrive.ui.tandem.destinations import destinations_screen
    gui_app.push_widget(destinations_screen(gui_app.pop_widget, lambda: (gui_app.pop_widget(), open_maps())))

  def open_mapbox_help() -> None:
    from openpilot.selfdrive.ui.tandem.mapbox_help import mapbox_key_sheet
    window.present(mapbox_key_sheet(window.dismiss))

  def tuner() -> bool:
    return TUNER_MODE.is_on(store)

  def set_bundle(bundle, on: bool) -> None:
    bundle.set(store, on)
    if bundle is TUNER_MODE and on:
      open_tuner()

  def opener(make: Callable[[], Widget]) -> Callable[[], None]:
    return lambda: window.push(make())

  def open_tuner() -> None:
    window.push(tuner_page(Tuner(store), window))

  def speed_steering() -> Widget:
    tuner_button = Button("Tuner Mode", open_tuner, ButtonStyle.SECONDARY, width=T.SIDEBAR_WIDTH, accessory=chevron_glyph)
    tuner_button.set_visible(tuner)
    return SectionPage("SPEED & STEERING", [
      Section("Everyday", lambda: everyday_panel(speed)),
      Section("Vehicle Profile", lambda: vehicle_profile_panel(profile), value=profile.summary),
      Section("Weather", lambda: weather_panel(weather), value=weather.summary),
      Section("Navigation", lambda: navigation_panel(navigation, open_destinations, open_maps, open_mapbox_help)),
    ], footer=[tuner_button])

  def assistance_page() -> Widget:
    """openpilot's core switches beside driver monitoring, gathered from Speed & Steering and This Device."""
    from openpilot.selfdrive.ui.tandem.settings.device_sections import confirm
    ask = lambda title, message, label, action, danger, icon: confirm(window, title, message, label, action, danger, icon)  # noqa: E731
    return FillPage(Columns([assistance_panel(assistance),
                             driver_monitoring_panel(assistance, driver_monitoring_rows(window.device(), ask))], [1.4, 1]))

  def display() -> Widget:
    return SectionPage("DISPLAY", [
      Section("Driving Screen", lambda: driving_screen_panel(screen, window)),
      Section("Theme & Startup", lambda: theme_panel(screen, lambda: edit_startup_message(screen), window)),
      Section("Map", lambda: map_panel(screen, open_maps)),
    ])

  def car() -> str:
    return store.get_str("CarModelName") or "Detected on the first drive"

  strip = Strip("POWER USER", "Extra detail and fine tuning, each behind one switch", [
    ToggleButton(b.name, lambda b=b: b.is_on(store), lambda on, b=b: set_bundle(b, on)) for b in BUNDLES])

  def open_search() -> None:
    from openpilot.selfdrive.ui.tandem.settings.search import SettingsSearch

    def pick(entry) -> None:
      window.dismiss()
      window.open_at(entry.tab, entry.page, entry.section)
    window.present(SettingsSearch(tuner, pick, window.dismiss))

  from openpilot.selfdrive.ui.tandem.settings.search import SearchButton
  hub = HubPage("Driving", "Good defaults are on. Change only what matters to you.", [
    HubTile("Speed & Steering", [speed.summary, speed.speed_limit_summary], opener(speed_steering), icon="wheel"),
    HubTile("Display", [screen.summary, screen.path_summary], opener(display), icon="display"),
    HubTile("Alerts", [alerts.summary, alerts.chimes_summary], opener(lambda: alerts_page(alerts, window)),
            icon="volume"),
    HubTile("Driving Model", [lambda: models.get().summary(), lambda: models.get().update_summary()],
            opener(lambda: model_page(models.get(), opener(lambda: CatalogPage(models.get(), window.device_data().storage)))), icon="model"),
    HubTile("Vehicle", [car, lambda: f"{profile.summary()} profile · {vehicle.get().buttons_summary()}"],
            opener(lambda: vehicle_page(vehicle.get(), window, opener(lambda: extras_page(window.car_extras(), window)))), icon="car"),
    HubTile("Assistance", [assistance.summary, assistance.monitoring_summary], opener(assistance_page), icon="shield"),
  ], rows=[3, 3], strip=strip, trailing=SearchButton(open_search))
  # Each page the hub opens, by name, for settings search to open a result's page.
  hub.pages = {"speed_steering": opener(speed_steering), "display": opener(display), "alerts": opener(lambda: alerts_page(alerts, window)),
               "model": opener(lambda: model_page(models.get(), opener(lambda: CatalogPage(models.get(), window.device_data().storage)))),
               "vehicle": opener(lambda: vehicle_page(vehicle.get(), window, opener(lambda: extras_page(window.car_extras(), window)))),
               "assistance": opener(assistance_page), "tuner": open_tuner}
  return hub
