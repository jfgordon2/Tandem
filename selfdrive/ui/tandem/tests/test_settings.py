from enum import IntEnum

from openpilot.system.ui.widgets import DialogResult, Widget
from openpilot.selfdrive.ui.tandem.settings import upstream
from openpilot.selfdrive.ui.tandem.settings.pages import Section, SectionPage
from openpilot.selfdrive.ui.tandem.settings.speed_steering import OFFSET_KEYS, SpeedSteering
from openpilot.selfdrive.ui.tandem.settings.live import FakeLive
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab

DEFAULTS = {"LongitudinalPersonality": 1, "ShowSpeedLimits": True, "SpeedLimitController": False, "Offset1": 5.0,
            "ConditionalExperimental": True, "CurveSpeedController": True, "MinimumLaneChangeSpeed": 20.0}


class FakeCache:
  def __init__(self, values=None):
    self.values = dict(DEFAULTS, **(values or {}))
    self.invalidations = 0

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def get_int(self, key, return_default=False):
    return int(self.values.get(key, 0))

  def get_float(self, key, return_default=False):
    return float(self.values.get(key, 0.0))

  def get(self, key, return_default=False):
    return self.values.get(key)

  def put_bool(self, key, value):
    self.values[key] = value

  put = put_int = put_float = put_bool

  def invalidate(self):
    self.invalidations += 1


def _model(values=None):
  cache = FakeCache(values)
  notified = []
  return SpeedSteering(SettingsStore(cache, lambda: notified.append(1))), cache, notified


class Page(Widget):
  def __init__(self, name, events, inner_depth=0):
    super().__init__()
    self.name = name
    self.events = events
    self.inner_depth = inner_depth

  def can_go_back(self):
    return self.inner_depth > 0

  def go_back(self):
    self.inner_depth -= 1

  def show_event(self):
    self.events.append(("show", self.name))

  def hide_event(self):
    self.events.append(("hide", self.name))

  def _render(self, rect):
    pass


def _window():
  events = []
  window = SettingsWindow(store=SettingsStore(FakeCache(), lambda: None), live=FakeLive())
  window._roots = [lambda n=n: Page(n, events) for n in ("driving", "device", "connections", "software")]
  closed = []
  window.set_callbacks(on_close=lambda: closed.append(1))
  return window, events, closed


# ── store and Speed & Steering ──

def test_store_writes_typed_values_then_notifies_once():
  cache = FakeCache()
  notified = []
  SettingsStore(cache, lambda: notified.append(1)).write({"A": True, "B": 2, "C": 1.5})
  assert (cache.values["A"], cache.values["B"], cache.values["C"]) == (True, 2, 1.5)
  assert type(cache.values["C"]) is float
  assert notified == [1] and cache.invalidations == 1


def test_driving_style_sets_gap_acceleration_and_braking_together():
  model, cache, notified = _model()
  assert model.style == 1
  model.set_style(2)
  assert (cache.values["LongitudinalPersonality"], cache.values["AccelerationProfile"], cache.values["DecelerationProfile"]) == (0, 2, 2)
  assert model.style == 2
  model.set_style(0)
  assert (cache.values["LongitudinalPersonality"], cache.values["AccelerationProfile"], cache.values["DecelerationProfile"]) == (2, 1, 1)
  assert model.style == 0 and len(notified) == 2


def test_speed_limits_off_show_match():
  model, cache, _ = _model()
  assert model.speed_limits == 1 and not model.matching
  model.set_speed_limits(2)
  assert cache.values["ShowSpeedLimits"] and cache.values["SpeedLimitController"] and cache.values["SetSpeedLimit"] and model.matching
  model.set_speed_limits(0)
  assert not cache.values["ShowSpeedLimits"] and not cache.values["SpeedLimitController"] and model.speed_limits == 0


def test_offset_applies_to_every_speed_range():
  model, cache, notified = _model()
  model.set_offset(7)
  assert [cache.values[k] for k in OFFSET_KEYS] == [7.0] * 7
  assert model.offset == 7 and len(notified) == 1


def test_tap_to_confirm_asks_only_for_higher_limits():
  model, cache, _ = _model()
  model.set_higher_limits(1)
  assert cache.values["SLCConfirmation"] and cache.values["SLCConfirmationHigher"] and not cache.values["SLCConfirmationLower"]
  model.set_higher_limits(0)
  assert not cache.values["SLCConfirmation"] and model.higher_limits == 0


def test_higher_and_lower_limits_ask_separately():
  model, cache, _ = _model()
  model.set_lower_limits(1)
  assert cache.values["SLCConfirmation"] and cache.values["SLCConfirmationLower"] and not cache.values["SLCConfirmationHigher"]
  assert (model.higher_limits, model.lower_limits) == (0, 1)
  model.set_higher_limits(1)
  assert (model.higher_limits, model.lower_limits) == (1, 1)
  model.set_lower_limits(0)
  assert cache.values["SLCConfirmation"] and (model.higher_limits, model.lower_limits) == (1, 0)
  model.set_higher_limits(0)
  assert not cache.values["SLCConfirmation"] and (model.higher_limits, model.lower_limits) == (0, 0)


def test_max_follows_limits_is_a_marker_file_not_a_param(tandem_prefs):
  """No new param key: the device's compiled registry wouldn't know it, and writing it would crash the UI."""
  model, cache, _ = _model()
  before = dict(cache.values)
  assert model.max_follows                                  # on by default, with no file
  model.set_max_follows(False)
  assert not model.max_follows and list(tandem_prefs.iterdir())
  model.set_max_follows(True)
  assert model.max_follows and not list(tandem_prefs.iterdir())
  assert cache.values == before                             # no param written


def test_grouped_switches_and_summaries():
  model, cache, _ = _model({"IsMetric": True})
  assert model.smart_slowdowns
  model.set_smart_slowdowns(False)
  assert not cache.values["ConditionalExperimental"] and not cache.values["CurveSpeedController"]
  model.set_lane_changes(1)
  assert model.summary() == "Standard · Auto lane change"
  assert model.unit == "km/h" and model.lane_change_speed == 20


# ── window navigation ──

def test_back_steps_out_of_inner_pages_then_pops_then_closes():
  window, _, closed = _window()
  window.push(Page("detail", [], inner_depth=1))
  assert window.can_go_back()
  window.back()
  assert window.depth == 2 and window.can_go_back()
  window.back()
  assert window.depth == 1 and not window.can_go_back() and not closed
  window.back()
  assert closed == [1]


def test_tabs_keep_their_own_stacks():
  window, _, _ = _window()
  window.push(Page("detail", []))
  window.select_tab(Tab.CONNECTIONS)
  assert window.depth == 1 and window.top.name == "connections"
  window.select_tab(Tab.DRIVING)
  assert window.depth == 2 and window.top.name == "detail"


def test_only_the_visible_page_gets_show_and_hide():
  window, events, _ = _window()
  window.show_event()
  window.push(Page("detail", events))
  window.select_tab(Tab.DEVICE)
  window.hide_event()
  assert events == [("show", "driving"), ("hide", "driving"), ("show", "detail"), ("hide", "detail"), ("show", "device"),
                    ("hide", "device")]


def test_opening_at_an_upstream_panel_starts_that_tab_from_its_first_page():
  PanelType = IntEnum("PanelType", "STARPILOT DEVICE NETWORK BLUETOOTH TOGGLES SOFTWARE DEVELOPER")
  window, _, _ = _window()
  window.push(Page("detail", []))
  window.set_current_panel(PanelType.SOFTWARE)
  assert window.tab == Tab.SOFTWARE
  window.set_current_panel(PanelType.TOGGLES)
  assert window.tab == Tab.DRIVING and window.depth == 1


def test_developer_opens_the_device_tab_on_its_developer_section():
  PanelType = IntEnum("PanelType", "DEVELOPER")
  window = SettingsWindow(store=SettingsStore(FakeCache(), lambda: None), live=FakeLive())
  events = []
  window._roots[Tab.DEVICE] = lambda: SectionPage("DEVICE", [Section(n, lambda n=n: Page(n, events)) for n in "abcde"] +
                                                  [Section("dev", lambda: Page("dev", events))])
  window.set_current_panel(PanelType.DEVELOPER)
  assert window.tab == Tab.DEVICE and window.top.current.name == "dev"


def test_section_page_builds_sections_when_chosen_and_forwards_events():
  events, built = [], []

  def make(name):
    built.append(name)
    return Page(name, events, inner_depth=1)

  page = SectionPage("X", [Section("A", lambda: make("a")), Section("B", lambda: make("b"))])
  page.show_event()
  page.select(1)
  assert built == ["a", "b"]
  assert events == [("show", "a"), ("hide", "a"), ("show", "b")]
  assert page.can_go_back()
  page.go_back()
  assert not page.can_go_back()


# ── hosted StarPilot panels ──

class FakeStarPilot(Widget):
  CATEGORIES = [{"title": "Sounds", "panel": "SOUNDS"},
                {"title": "Controls", "children": [{"title": "Maps", "children": [{"title": "Map Data", "panel": "MAPS"}]}]}]

  def __init__(self):
    super().__init__()
    self._selected_leaf = None
    self._callback = None
    self.depth = 0

  def set_depth_callback(self, callback):
    self._callback = callback

  def _set_depth(self, depth):
    self.depth = depth
    self._callback(depth)

  def reset_to_root(self):
    self._selected_leaf = None
    self._set_depth(0)

  def _open_leaf(self, leaf):
    self._selected_leaf = leaf
    self._set_depth(1)

  def navigate_back(self):
    if self.depth == 1:
      self._selected_leaf = None
    self._set_depth(self.depth - 1)

  def _render(self, rect):
    pass


def test_find_leaf_searches_nested_folders():
  assert upstream.find_leaf(FakeStarPilot.CATEGORIES, "MAPS")["title"] == "Map Data"


def test_starpilot_page_opens_its_panel_and_pops_when_starpilot_leaves_it():
  layout = FakeStarPilot()
  exits = []
  page = upstream.StarPilotPage("MAPS", on_exit=lambda: exits.append(1), layout=lambda: layout)
  page.show_event()
  assert layout._selected_leaf["panel"] == "MAPS" and not exits
  layout._set_depth(2)
  assert page.can_go_back()
  page.go_back()
  assert not page.can_go_back()
  layout.navigate_back()      # StarPilot's own back button
  page._update_state()
  assert exits == [1]


def test_starpilot_section_reopens_instead_of_showing_the_starpilot_hub():
  layout = FakeStarPilot()
  page = upstream.StarPilotPage("SOUNDS", layout=lambda: layout)
  page.show_event()
  layout.navigate_back()
  page._update_state()
  assert layout._selected_leaf["panel"] == "SOUNDS" and layout.depth == 1


# ── This Device ──

class FakeDevice:
  def __init__(self, paired=False, offroad=True, calibration="Calibrated"):
    self.paired, self.offroad, self.cal = paired, offroad, calibration
    self.calls = []
    self.refreshes = 0

  def is_paired(self):
    return self.paired

  def is_offroad(self):
    return self.offroad

  def engaged(self):
    return False

  def calibration(self):
    return self.cal

  def remote_access_label(self):
    return "Set Up"

  def ids(self):
    return "abc123 · serial"

  def imei(self):
    return "351234567890123"

  def show_regulatory(self):
    return False

  def refresh(self):
    self.refreshes += 1

  def __getattr__(self, name):
    return lambda: self.calls.append(name)


def _rows(panel):
  return {row._title: row for row in panel.items if hasattr(row, "_title")}


def test_this_device_buttons_call_the_device_and_respect_offroad():
  from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel
  device = FakeDevice(offroad=False)
  panel = ThisDevicePanel(device)
  rows = _rows(panel)
  rows["Camera Calibration"]._control._click_callback()
  assert device.calls == ["recalibrate"]
  assert "Driver Camera" not in rows and "Driver Monitoring" not in rows   # moved to Driving › Assistance
  assert rows["Camera Calibration"]._control.enabled
  restart, power_off = panel._footer._buttons
  assert power_off.is_visible and not power_off.enabled   # shown greyed out while driving
  restart._click_callback()
  assert device.calls == ["recalibrate", "restart"]
  device.offroad = True
  assert power_off.enabled


def test_driver_monitoring_lives_under_assistance():
  from openpilot.selfdrive.ui.tandem.settings.device import driver_monitoring_rows
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Assistance, assistance_panel, driver_monitoring_panel
  store, cache = _store({"AlwaysOnDM": False, "DisengageOnAccelerator": True})
  device, asked = FakeDevice(offroad=False), []
  model = Assistance(store, FakeLive())
  rows = _rows(driver_monitoring_panel(model, driver_monitoring_rows(
    device, lambda title, message, label, action, danger, icon: asked.append((label, action)))))
  assert list(rows) == ["Always-On Driver Monitoring", "Driver Camera", "Driver Monitoring", "Sentry Mode", "Sensitivity"]
  assert "Always-On Driver Monitoring" not in _rows(assistance_panel(model))
  assert not rows["Driver Camera"]._control.enabled and not rows["Driver Monitoring"]._control.enabled   # the car must be off
  device.offroad = True
  rows["Driver Camera"]._control._click_callback()
  rows["Driver Monitoring"]._control._click_callback()
  assert device.calls == ["driver_camera"] and [label for label, _ in asked] == ["Reset"]   # the reset asks first
  asked[0][1]()
  assert device.calls[-1] == "reset_driver_monitoring"
  assert model.summary() == "Gas pedal disengages" and model.monitoring_summary() == "Driver monitoring while engaged"


def test_this_device_hides_pair_once_paired_and_refreshes_on_show():
  from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel
  device = FakeDevice()
  panel = ThisDevicePanel(device)
  phone = _rows(panel)["Phone App"]
  assert phone._control.is_visible
  device.paired = True
  assert not phone._control.is_visible
  panel.show_event()
  assert device.refreshes == 1
  assert not _rows(panel)["Regulatory"].is_visible


# ── Driving sections and bundles ──

def _store(values=None):
  cache = FakeCache(values)
  return SettingsStore(cache, lambda: None), cache


def test_smart_slowdowns_turns_on_its_triggers_and_off_conditional_chill():
  model, cache, _ = _model({"ConditionalChill": True, "CECurves": False})
  model.set_smart_slowdowns(True)
  assert cache.values["CECurves"] and cache.values["CEStopLights"] and not cache.values["ConditionalChill"]


def test_vehicle_profile_towing_keeps_a_trailer_weight():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import VehicleProfile
  store, cache = _store()
  profile = VehicleProfile(store)
  assert profile.summary() == "Car"
  profile.set_profile(3)
  assert cache.values["TruckTuning"] and cache.values["TrailerLoad"] == 5000 and profile.towing
  profile.set_trailer_load(2)
  assert cache.values["TrailerLoad"] == 8000 and profile.trailer_load == 2
  profile.set_profile(1)
  assert cache.values["EVTuning"] and not cache.values["TruckTuning"] and cache.values["TrailerLoad"] == 0
  assert profile.summary() == "EV"


def test_weather_auto_writes_preset_amounts():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Weather
  store, cache = _store()
  weather = Weather(store)
  assert weather.summary() == "Off"
  weather.set_mode(0)
  assert cache.values["WeatherPresets"] and cache.values["IncreaseFollowingSnow"] > cache.values["IncreaseFollowingRain"] > 0


def test_navigation_reads_home_and_work_from_favorites():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Navigation
  store, _ = _store({"FavoriteDestinations": [{"name": "12 Elm St", "is_home": True}, {"name": "Gym"}, {"name": "Cafe"}]})
  nav = Navigation(store)
  assert nav.home() == "12 Elm St" and nav.work() is None and nav.others() == 2


def test_safe_mode_drives_relaxed_and_locks_driving_style():
  from openpilot.selfdrive.ui.tandem.settings.live import FakeLive
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Assistance
  store, cache = _store({"ExperimentalMode": True})
  Assistance(store, FakeLive()).set_safe_mode(True)
  assert cache.values["SafeMode"] and not cache.values["ExperimentalMode"] and cache.values["LongitudinalPersonality"] == 2
  assert SpeedSteering(store).safe_mode


def test_bundles_switch_their_keys_together():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW, LEAD_INSIGHTS, TUNER_MODE
  store, cache = _store()
  assert not DEVELOPER_VIEW.is_on(store)
  DEVELOPER_VIEW.set(store, True)
  assert DEVELOPER_VIEW.is_on(store) and cache.values["ShowCPU"] and cache.values["DeveloperUI"]
  DEVELOPER_VIEW.set(store, False)
  assert not cache.values["ShowCPU"] and not cache.values["DeveloperSidebar"]
  LEAD_INSIGHTS.set(store, True)
  assert cache.values["LeadInfo"] and cache.values["RadarTracksUI"] and cache.values["DeveloperMetrics"]
  TUNER_MODE.set(store, True)
  assert TUNER_MODE.is_on(store) and cache.values["TuningLevel"] == 3
  TUNER_MODE.set(store, False)
  assert not TUNER_MODE.is_on(store)


def test_tuner_sections_hide_with_tuner_mode():
  events = []
  shown = {"tuner": True}
  page = SectionPage("X", [Section("A", lambda: Page("a", events)), Section("T", lambda: Page("t", events), visible=lambda: shown["tuner"])])
  page.select(1)
  shown["tuner"] = False
  page._update_state()
  assert page.selected == 0


# ── Display and Alerts ──

def test_path_style_presets_round_trip():
  from openpilot.selfdrive.ui.tandem.settings.display import Display
  store, cache = _store({"PathWidth": 6.1, "AccelerationPath": True})
  display = Display(store)
  assert display.path_style == 3
  for i in range(4):
    display.set_path_style(i)
    assert display.path_style == i
  display.set_path_style(1)
  assert cache.values["PathWidth"] == 3.0 and not cache.values["AccelerationPath"]


def test_turn_signal_whimsy_round_trip():
  from openpilot.selfdrive.ui.tandem.settings.display import SIGNAL_STYLES, Display
  from openpilot.selfdrive.ui.tandem.onroad.turn_signals import BUNDLED_SIGNAL_PATHS
  store, cache = _store({"SignalAnimation": "stock", "CustomThemes": False, "RandomThemes": True})
  display = Display(store)
  assert display.signal_style == 0 and display.signal_name() == "Standard"
  assert [name for name, _ in SIGNAL_STYLES] == ["Standard", "Jumping frog", "Pouncing cat", "Bouncing ball"]
  for i, (name, slug) in enumerate(SIGNAL_STYLES):
    assert slug == "stock" or BUNDLED_SIGNAL_PATHS[slug].is_dir()          # StarPilot ships every Whimsy animation
    display.set_signal_style(i)
    assert display.signal_style == i and display.signal_name() == name
  display.set_signal_style(1)   # as StarPilot's picker: themes on (it reads SignalAnimation only then), random themes off
  assert cache.values["SignalAnimation"] == "frog" and cache.values["CustomThemes"] and not cache.values["RandomThemes"]
  display.set_signal_style(0)
  assert cache.values["SignalAnimation"] == "stock"
  store, _ = _store({"SignalAnimation": "sequential", "CustomThemes": True})   # chosen in StarPilot's settings: not drawn here
  assert Display(store).signal_name() == "Standard"


def test_driving_style_banner_only_controls_the_profile_message():
  from openpilot.selfdrive.ui.tandem.settings.display import Display
  from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner
  store, cache = _store({"AdvancedCustomUI": True, "HideChangingLanesBanner": False, "HideTurningBanner": True,
                         "HideDistanceProfileBanner": True})
  display = Display(store)
  assert not display.driving_style_banner
  assert display.summary() == "Style banner hidden"
  display.set_driving_style_banner(True)
  assert display.driving_style_banner and not cache.values["HideDistanceProfileBanner"]
  assert display.summary() == "Style banner shown"
  display.set_driving_style_banner(False)
  assert not display.driving_style_banner and cache.values["HideDistanceProfileBanner"]
  assert not cache.values["HideChangingLanesBanner"] and cache.values["HideTurningBanner"]

  # Tuner resets must not invert this independent display preference.
  Tuner(store).reset_all()
  assert not display.driving_style_banner
  display.set_driving_style_banner(True)
  Tuner(store).reset_all()
  assert display.driving_style_banner


def test_driving_style_banner_respects_existing_visibility_settings():
  from openpilot.selfdrive.ui.tandem.settings.display import Display
  for advanced, hidden, shown in ((True, True, False), (True, False, True), (False, True, True), (False, False, True)):
    store, cache = _store({"AdvancedCustomUI": advanced, "HideDistanceProfileBanner": hidden})
    display = Display(store)
    assert display.driving_style_banner == shown
    display.set_driving_style_banner(False)
    assert not display.driving_style_banner and cache.values["AdvancedCustomUI"]


def test_volume_presets_and_custom_levels():
  from openpilot.selfdrive.ui.tandem.settings.alerts import AUTO, CUSTOM, GROUPS, Alerts
  store, cache = _store({k: AUTO for g in GROUPS for k in g.keys})
  alerts = Alerts(store)
  assert alerts.preset == 0 and alerts.level_label(GROUPS[0]) == "Auto"
  alerts.set_preset(2)
  assert cache.values["AlertVolumeControl"] and alerts.preset == 2 and alerts.level_label(GROUPS[2]) == "60%"   # driver attention at Normal
  alerts.set_level(GROUPS[0], 40)
  assert alerts.preset == CUSTOM and cache.values["EngageVolume"] == cache.values["DisengageVolume"] == 40


def test_safety_volumes_never_go_below_the_floor():
  from openpilot.selfdrive.ui.tandem.settings.alerts import GROUPS, SAFETY_FLOOR, Alerts
  store, cache = _store()
  alerts = Alerts(store)
  alerts.set_level(GROUPS[3], 5)
  assert cache.values["WarningImmediateVolume"] == SAFETY_FLOOR
  alerts.set_level(GROUPS[0], 5)
  assert cache.values["EngageVolume"] == 5


def test_custom_level_from_auto_starts_other_groups_at_normal():
  from openpilot.selfdrive.ui.tandem.settings.alerts import GROUPS, Alerts
  store, cache = _store({"AlertVolumeControl": False})
  Alerts(store).set_level(GROUPS[1], 50)
  assert cache.values["EngageVolume"] == GROUPS[0].levels[1] and cache.values["PromptVolume"] == 50


def test_window_overlay_blocks_page_and_back_dismisses_it():
  window, _, closed = _window()
  sheet = Page("sheet", [])
  window.present(sheet)
  assert window.overlay is sheet
  window.back()
  assert window.overlay is None and not closed


# ── Driving Model and Vehicle ──

def test_model_states_and_use_recommended():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeModels
  from openpilot.selfdrive.ui.tandem.settings.model import Models
  store, cache = _store({"AutomaticallyDownloadModels": True})
  source = FakeModels()
  models = Models(store, source)
  assert models.use_recommended and models.summary() == "Recommended"
  assert [models.status(m) for m in source.items] == ["active", "on_device", "download", "unavailable"]
  source.download("nlp")
  assert models.status(source.items[2]) == "downloading" and models.update_summary() == "Downloading"
  source.use("vtx")
  assert not models.use_recommended and models.summary() == "Vortex"
  models.set_use_recommended(True)
  assert source.current == "rdf43" and cache.values["AutomaticallyDownloadModels"]


def test_remove_unused_keeps_active_and_recommended():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeModels
  from openpilot.selfdrive.ui.tandem.settings.model import Models
  store, _ = _store()
  source = FakeModels()
  source.use("vtx")
  Models(store, source).remove_unused()
  assert [m.key for m in source.items if m.installed] == ["rdf43", "vtx"]
  source.use("rdf43")
  Models(store, source).remove_unused()
  assert [m.key for m in source.items if m.installed] == ["rdf43"]


def test_choosing_a_car_turns_off_detection():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeCars
  from openpilot.selfdrive.ui.tandem.settings.vehicle import CarPicker, Vehicle
  store, cache = _store({"CarMake": "Toyota", "CarModelName": "RAV4 2019-21"})
  vehicle = Vehicle(store, FakeCars())
  picker = CarPicker(vehicle)
  assert picker._make == 2 and picker._model == 0
  picker._pick_model(1)
  assert picker.save()
  assert cache.values["ForceFingerprint"] and cache.values["CarModel"] == "TOYOTA_RAV4H_TSS2" and vehicle.manual
  picker._pick_make(1)
  assert not picker.save()    # a make alone isn't a car
  vehicle.use_detection()
  assert not vehicle.manual


def test_wheel_button_actions():
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeCars
  from openpilot.selfdrive.ui.tandem.settings.vehicle import Vehicle
  store, cache = _store()
  vehicle = Vehicle(store, FakeCars())
  lkas = vehicle.catalog.buttons()[2]
  assert vehicle.action_name(lkas) == "Car default" and vehicle.buttons_summary() == "Car default buttons"
  vehicle.set_action(lkas, 9)
  assert cache.values["LKASButtonControl"] == 9 and vehicle.action_name(lkas) == "Always-on steering"
  assert vehicle.buttons_summary() == "Buttons customized"


# ── Tuner Mode ──

def test_tunable_default_override_and_reset_to_the_cars_value():
  from openpilot.selfdrive.ui.tandem.settings.tuner import DEFAULT, OVERRIDE, STEERING, Tuner
  store, cache = _store({"SteerFriction": 0.12, "SteerFrictionStock": 0.12})
  tuner = Tuner(store)
  friction = STEERING[1]
  assert tuner.status(friction) == DEFAULT
  before = tuner.changed(STEERING)
  tuner.set_value(friction, 0.2)
  assert tuner.status(friction) == OVERRIDE and cache.values["AdvancedLateralTune"] and tuner.changed(STEERING) == before + 1
  tuner.reset(friction)
  assert cache.values["SteerFriction"] == 0.12 and tuner.status(friction) == DEFAULT


def test_steering_delay_is_learned_until_overridden():
  from openpilot.selfdrive.ui.tandem.settings.tuner import LEARNED, OVERRIDE, STEERING, Tuner
  store, cache = _store({"UseAutoSteerDelay": True, "SteerDelay": 0.2, "SteerDelayStock": 0.2})
  tuner = Tuner(store)
  delay = STEERING[0]
  assert tuner.status(delay) == LEARNED
  tuner.set_value(delay, 0.3)
  assert not cache.values["UseAutoSteerDelay"] and tuner.status(delay) == OVERRIDE
  tuner.reset(delay)
  assert cache.values["UseAutoSteerDelay"] and tuner.status(delay) == LEARNED


def test_profiles_follow_driving_style_until_overridden():
  from openpilot.selfdrive.ui.tandem.settings.tuner import FROM_STYLE, OVERRIDE, Tuner
  store, cache = _store()
  SpeedSteering(store).set_style(2)
  tuner = Tuner(store)
  assert tuner.profile_status("AccelerationProfile") == FROM_STYLE
  before = tuner.gas_brake_changes()
  tuner.set_accel_profile(3)
  assert tuner.profile_status("AccelerationProfile") == OVERRIDE and tuner.gas_brake_changes() == before + 1


def test_steering_controller_choices():
  from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner
  store, cache = _store()
  tuner = Tuner(store)
  for i in range(4):
    tuner.set_controller(i)
    assert tuner.controller == i


def test_bundle_overrides_count_items_that_differ():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW
  from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner
  store, cache = _store()
  DEVELOPER_VIEW.set(store, True)
  tuner = Tuner(store)
  assert tuner.bundle_changes(DEVELOPER_VIEW) == 0
  tuner.set_switch("ShowGPU", False)
  assert tuner.item_differs(DEVELOPER_VIEW, "ShowGPU") and tuner.bundle_changes(DEVELOPER_VIEW) == 1


def test_reset_all_restores_defaults_and_bundle_values():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW
  from openpilot.selfdrive.ui.tandem.settings.tuner import GAPS, STEERING, Tuner
  store, cache = _store({"SteerKPStock": 1.1})
  DEVELOPER_VIEW.set(store, True)
  tuner = Tuner(store)
  tuner.set_value(STEERING[3], 2.0)
  tuner.set_gap("RelaxedFollow", 2.5)
  tuner.set_switch("ShowGPU", False)
  tuner.set_controller(0)                          # Auto: NNFF on
  tuner.reset_all()
  assert cache.values["SteerKP"] == 1.1 and cache.values["RelaxedFollow"] == GAPS[0][2] and cache.values["ShowGPU"]
  assert tuner.controller == 3 and not cache.values["NNFF"] and not cache.values["NNFFLite"]   # Torque; NNFF is opt-in


def test_reset_all_tuning_asks_first():
  from openpilot.system.ui.widgets import DialogResult
  from openpilot.selfdrive.ui.tandem.overlays import Dialog
  from openpilot.selfdrive.ui.tandem.settings.tuner import STEERING, Tuner, tuner_page

  class Window:
    overlay = None

    def present(self, overlay):
      self.overlay = overlay

    def dismiss(self):
      self.overlay = None

  store, cache = _store({"SteerKPStock": 1.1})
  tuner, window = Tuner(store), Window()
  tuner.set_value(STEERING[3], 2.0)
  reset = tuner_page(tuner, window)._sidebar._footer[0]
  assert reset._label == "Reset all tuning"
  reset._click_callback()
  assert isinstance(window.overlay, Dialog) and cache.values["SteerKP"] == 2.0   # nothing changes until confirmed
  window.overlay._finish(DialogResult.CANCEL)
  assert window.overlay is None and cache.values["SteerKP"] == 2.0
  reset._click_callback()
  window.overlay._finish(DialogResult.CONFIRM)
  assert cache.values["SteerKP"] == 1.1


# ── Device sections ──

def _general(values=None, engaged=False):
  from openpilot.selfdrive.ui.tandem.settings.device_sections import General
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeData
  store, cache = _store(values)
  return General(store, FakeData(), FakeLive(engaged=engaged)), cache


def test_general_brightness_uploads_and_language():
  general, cache = _general({"ScreenBrightness": 101})
  assert general.brightness == 1
  general.set_brightness(0)
  assert cache.values["ScreenBrightness"] == 40 and cache.values["ScreenBrightnessOnroad"] == 30 and general.brightness == 0
  general.set_uploads(1)
  assert not cache.values["NoUploads"] and cache.values["DisableOnroadUploads"] and general.uploads == 1
  general.set_uploads(0)
  assert cache.values["NoUploads"] and general.uploads == 0
  general.data.set_language("es")
  assert general.language_name() == "Español"


def test_recording_switches_wait_until_disengaged():
  general, _ = _general(engaged=True)
  assert general.recording_locked()
  general, cache = _general({"RecordFrontLock": True})
  assert general.recording_locked()
  general, _ = _general()
  assert not general.recording_locked()


def test_report_needs_a_category_and_includes_details():
  from openpilot.selfdrive.ui.tandem.settings.device_sections import REPORT_CATEGORIES, Report
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeData
  store, cache = _store()
  data = FakeData()
  report = Report(data, store)
  report.send()
  assert not data.reports
  report.category, report.details, report.discord = 1, "on the highway", "driver42"
  report.send()
  assert data.reports == [(f"{REPORT_CATEGORIES[1]}: on the highway", "driver42")] and cache.values["DiscordUsername"] == "driver42"


def test_backup_restore_asks_first():
  from openpilot.selfdrive.ui.tandem.settings.device_sections import confirm
  window, _, _ = _window()
  done = []
  confirm(window, "Restore?", "Replaces settings.", "Restore", lambda: done.append(1))
  window.overlay._on_result(DialogResult.CANCEL)
  assert not done and window.overlay is None
  confirm(window, "Restore?", "Replaces settings.", "Restore", lambda: done.append(1))
  window.overlay._on_result(DialogResult.CONFIRM)
  assert done == [1]


# ── Network, Bluetooth, Software ──

def _network(values=None):
  from openpilot.selfdrive.ui.tandem.settings.network_tab import Network
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWifi
  store, cache = _store(values)
  asked = []
  wifi = FakeWifi()
  net = Network(wifi, store, ask=lambda title, sub, current, done, *a, **k: asked.append((title, done)))
  return net, wifi, cache, asked


def test_wifi_connects_saved_open_and_secured_networks():
  net, wifi, _, asked = _network()
  home, cafe, neighbor = wifi.networks
  assert net.status("Home Wi-Fi") == "Connected" and net.status("Neighbor") == ""
  net.choose(cafe)
  assert wifi.calls[-1] == ("connect", "Coffee Shop", "", False)
  net.choose(neighbor)
  title, done = asked[-1]
  assert title == "Enter password"
  done("hunter2hunter2")
  assert wifi.calls[-1] == ("connect", "Neighbor", "hunter2hunter2", False)
  wifi.need_auth("Neighbor")
  assert asked[-1][0] == "Wrong password"


def test_save_data_marks_cellular_and_current_wifi_metered():
  net, wifi, cache, _ = _network({"GsmApn": "fast.apn"})
  net.set_save_data(True)
  assert cache.values["GsmMetered"] and ("gsm", False, "fast.apn", True) in wifi.calls and ("metered", 1) in wifi.calls


def test_wheel_buttons_highlight_and_assign():
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import AssignSheet, WheelButtons
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWheel
  source = FakeWheel()
  wheel = WheelButtons(source)
  first = wheel.buttons()[0]
  assert wheel.action_name(first) == "Engage" and not wheel.is_pressed(first)
  source.state["last_tested"] = {"mapped": True, "slot": 3}
  assert wheel.is_pressed(first)
  source.state["last_tested"] = {"mapped": False}
  assert wheel.unassigned_pressed()

  sheet = AssignSheet(wheel)
  sheet.show_event()
  assert source.learning == 5 and not sheet.ready
  source.maps.append({"id": "c", "device_name": "Wheel Remote", "event_name": "BTN_C", "slot": 5})
  source.state["last_learned"] = source.maps[-1]
  sheet._update_state()
  sheet._pick(2)
  assert sheet.ready and sheet.save()
  assert wheel.action_name(source.maps[-1]) == "Change driving style"


def test_cancelling_assignment_removes_a_learned_button():
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import AssignSheet, WheelButtons
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWheel
  source = FakeWheel()
  sheet = AssignSheet(WheelButtons(source))
  sheet.show_event()
  source.maps.append({"id": "c", "device_name": "Wheel Remote", "event_name": "BTN_C", "slot": 5})
  source.state["last_learned"] = source.maps[-1]
  sheet._update_state()
  sheet.cancel()
  assert [m["id"] for m in source.maps] == ["a", "b"] and source.learning is None


def _connections(window, wheel, bt, section):
  from openpilot.selfdrive.ui.tandem.settings import connections
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import WheelButtons
  from openpilot.selfdrive.ui.tandem.settings.network_tab import Network
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWifi
  page = connections.connections_page(Network(FakeWifi(), window.store), lambda: None, WheelButtons(wheel), bt, window)
  page.select(section)
  return page


def test_connections_sections_keep_radios_busy_only_while_shown():
  from openpilot.selfdrive.ui.tandem.settings import connections
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth, FakeWheel
  source, bt = FakeWheel(), FakeBluetooth()
  source.state["testing"] = False
  window, _, _ = _window()
  page = _connections(window, source, bt, connections.WIFI)
  window._roots[Tab.CONNECTIONS] = lambda: page
  window.show_event()
  window.select_tab(Tab.CONNECTIONS)
  assert [s.label for s in page._sections] == ["Wi-Fi", "Cellular", "Bluetooth Remote", "Car Audio & Devices"]
  assert not source.state["testing"] and ("active", True) not in bt.calls     # Wi-Fi open: Bluetooth idle
  page.select(connections.AUDIO)
  assert bt.calls[-1] == ("active", True)
  page.select(connections.CELLULAR)
  assert bt.calls[-1] == ("active", False)


def test_opening_upstream_network_and_bluetooth_lands_in_their_connections_sections():
  from openpilot.selfdrive.ui.tandem.settings import connections
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth, FakeWheel
  PanelType = IntEnum("PanelType", "STARPILOT DEVICE NETWORK BLUETOOTH TOGGLES SOFTWARE DEVELOPER")
  window, _, _ = _window()
  page = _connections(window, FakeWheel(), FakeBluetooth(), connections.CELLULAR)
  window._roots[Tab.CONNECTIONS] = lambda: page
  window.set_current_panel(PanelType.BLUETOOTH)
  assert window.tab == Tab.CONNECTIONS and page.selected == connections.REMOTE
  window.set_current_panel(PanelType.NETWORK)
  assert page.selected == connections.WIFI


def test_bluetooth_page_tests_unmapped_buttons_and_cancels_learning_when_hidden():
  from openpilot.selfdrive.ui.tandem.settings import connections
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth, FakeWheel
  source = FakeWheel()
  source.maps.clear()
  source.state["testing"] = False
  bt = FakeBluetooth()
  window, _, _ = _window()
  window._roots[Tab.CONNECTIONS] = lambda: _connections(window, source, bt, connections.REMOTE)
  window.show_event()
  window.select_tab(Tab.CONNECTIONS)
  assert source.state["testing"] and bt.calls[-1] == ("active", True)

  source.start_learning(3)
  window.hide_event()
  assert source.learning is None and not source.state["testing"]
  assert bt.calls[-1] == ("active", False)


def test_bluetooth_test_mode_suppresses_real_actions_only_while_the_page_is_shown():
  from openpilot.selfdrive.ui.tandem.settings import connections
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import UpstreamWheel
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth
  from openpilot.starpilot.common import controller_actions
  from openpilot.starpilot.system.wheel_controls import wheel_controlsd
  from openpilot.starpilot.system.wheel_controls.tests.test_wheel_controlsd import FakeParams, source

  params = FakeParams({"IsOffroad": False, "IsOnroad": True})
  memory = FakeParams()
  wheel_controlsd.set_controller_action_slot(0, controller_actions.CONTROLLER_ACTION_BOOKMARK, "Save a clip", params)
  wheel_controlsd.upsert_mapping(source(), 164, wheel_controlsd.FAVORITE_SLOT_COUNT, params)
  from openpilot.starpilot.tandem.wheel import daemon_type
  daemon = daemon_type(wheel_controlsd.WheelControlsDaemon)(params, memory)
  wheel = UpstreamWheel.__new__(UpstreamWheel)
  wheel._params, wheel._memory = params, memory
  wheel._wc, wheel._ca = wheel_controlsd, controller_actions
  wheel.favorite_slots = wheel_controlsd.FAVORITE_SLOT_COUNT
  window, _, _ = _window()
  window._roots[Tab.CONNECTIONS] = lambda: _connections(window, wheel, FakeBluetooth(), connections.REMOTE)
  window.show_event()

  def press(expected_clips):
    daemon._handle_key(source(), 164)
    assert memory.get_int("WheelButtonBookmarkCounter") == expected_clips

  try:
    press(1)
    window.select_tab(Tab.CONNECTIONS)
    press(1)
    assert daemon.testing and daemon.last_tested["mapped"]

    window.select_tab(Tab.DEVICE)
    press(2)
    assert not daemon.testing

    window.select_tab(Tab.CONNECTIONS)
    press(2)
    window.push(Page("another page", []))
    press(3)
    window.pop()
    press(3)

    window.hide_event()
    press(4)
    window.show_event()
    press(4)
    window.hide_event()
    press(5)
    assert not memory.get_bool(wheel_controlsd.TEST_ACTIVE_PARAM)
  finally:
    window.hide_event()
    daemon.close()


def test_software_states_and_actions():
  from openpilot.selfdrive.ui.tandem.settings.software_tab import Software
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeUpdates
  store, cache = _store({"UpdaterState": "idle", "UpdaterCurrentDescription": "0.10.1 / release"})
  updates = FakeUpdates()
  software = Software(store, updates, lambda: None)
  assert software.state() == "current" and software.action_label() == "Check now"
  assert software.version_parts() == ("0.10.1", "release")
  software.act()
  cache.values["UpdaterFetchAvailable"] = True
  assert software.action_label() == "Download"
  cache.values["UpdateAvailable"] = True
  software.act()
  assert updates.calls == ["check_or_download", "install"]
  cache.values["UpdaterState"] = "downloading"
  assert software.state() == "busy" and software.status_line() == "Downloading the update"


def test_reset_settings_applies_essentials_with_one_signal():
  from openpilot.selfdrive.ui.tandem.settings.bundles import DEVELOPER_VIEW
  from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
  cache = FakeCache({"LongitudinalPersonality": 0, "SpeedLimitController": False})
  notified = []
  store = SettingsStore(cache, lambda: notified.append(1))
  DEVELOPER_VIEW.set(store, True)
  notified.clear()
  apply_essentials(store)
  assert notified == [1]
  speed = SpeedSteering(store)
  assert speed.style == 1 and speed.matching and speed.offset == 3 and speed.higher_limits == 1 and speed.lane_changes == 0
  assert not DEVELOPER_VIEW.is_on(store) and cache.values["GreenLightAlert"] and not cache.values["HolidayThemes"]
  assert cache.values["Compass"]   # the heading beside the street name in the bar
  assert speed.max_follows and speed.lower_limits == 0


def test_maps_download_waits_for_parked_online_and_a_selection():
  from openpilot.selfdrive.ui.tandem.settings.maps import Maps
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeMaps
  store, cache = _store({"PreferredSchedule": 2})
  source = FakeMaps()
  maps = Maps(store, source)
  assert maps.ready() and maps.schedule == 2
  source.online = False
  assert not maps.ready() and maps.blocked_reason() == "Waiting: online"
  source.online = True
  source.set_selected("pkg:west", False)
  assert maps.blocked_reason() == "Choose at least one region"
  source.set_selected("s:CA", True)
  source.download()
  assert not maps.ready() and maps.status() == "Downloading California · 42%"
  maps.set_schedule(0)
  assert cache.values["PreferredSchedule"] == 0


def test_download_fraction_reads_the_percent():
  from openpilot.selfdrive.ui.tandem.settings.model import download_fraction
  assert download_fraction("45% · about 3 min left") == 0.45
  assert download_fraction("starting") == 0.0 and download_fraction("") == 0.0


def test_boot_logo_picker_lists_built_ins_then_downloads():
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  from openpilot.selfdrive.ui.tandem.settings.display import Display, boot_logo_sheet
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBootLogos

  class Window:
    overlay = None

    def present(self, overlay):
      self.overlay = overlay

    def dismiss(self):
      self.overlay = None

  store, cache = _store()
  logos = FakeBootLogos()
  display, window = Display(store, lambda: logos), Window()
  assert display.boot_logo_name() == "StarPilot"   # StarPilot's own default until Essentials is applied
  assert display.boot_logo_options() == [("tandem", "Tandem"), ("starpilot", "StarPilot"), ("stock", "comma"), ("aurora_logo", "Aurora Logo"),
                                         ("pixel_logo", "Pixel Logo")]   # a downloaded "stock" doesn't repeat comma's
  boot_logo_sheet(display, window)
  cards = lambda: window.overlay._body.items[0]._items  # noqa: E731
  cards()[0]._click_callback()
  assert cache.values["BootLogo"] == "tandem" and logos.installs == 1 and display.boot_logo_name() == "Default"
  boot_logo_sheet(display, window)
  assert isinstance(window.overlay, Sheet) and len(cards()) == 5
  cards()[3]._click_callback()
  assert cache.values["BootLogo"] == "aurora_logo" and display.boot_logo_name() == "Aurora Logo" and window.overlay is None
  boot_logo_sheet(display, window)
  assert [a._label for a in window.overlay._actions] == ["Done"]   # nothing to download


def test_essentials_choose_and_install_the_tandem_boot_logo():
  from openpilot.selfdrive.ui.tandem.settings.defaults import apply_essentials
  from openpilot.selfdrive.ui.tandem.settings.display import TANDEM_LOGO_FILE
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBootLogos
  store, cache = _store({"BootLogo": "starpilot"})
  logos = FakeBootLogos()
  apply_essentials(store, lambda: logos)
  assert cache.values["BootLogo"] == "tandem" and logos.installs == 1
  from PIL import Image
  with Image.open(TANDEM_LOGO_FILE) as image:
    assert image.size == (2160, 1080)   # StarPilot's boot logo size
    # Check decoded pixels: a near-black background still lights the OLED during boot.
    image = image.convert("RGB")
    for margin in ((0, 0, 2160, 200), (0, 880, 2160, 1080), (0, 0, 200, 1080), (1960, 0, 2160, 1080)):
      assert image.crop(margin).getextrema() == ((0, 0), (0, 0), (0, 0))


def test_upstream_boot_logos_install_tandem_once(tmp_path):
  from openpilot.selfdrive.ui.tandem.settings.display import TANDEM_LOGO_FILE, UpstreamBootLogos
  logos = UpstreamBootLogos.__new__(UpstreamBootLogos)   # skip the StarPilot import; point it at a temp folder
  logos._folder = tmp_path / "bootlogos"
  logos.install_tandem()
  installed = logos._folder / "tandem.jpg"
  assert installed.read_bytes() == TANDEM_LOGO_FILE.read_bytes()
  mtime = installed.stat().st_mtime_ns
  logos.install_tandem()
  assert installed.stat().st_mtime_ns == mtime   # already there: not copied again


def test_built_in_boot_logos_have_previews():
  from openpilot.selfdrive.ui.tandem.settings.display import BUILT_IN_IMAGES, BUILT_IN_LOGOS, Display
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBootLogos
  store, _ = _store()
  display = Display(store, FakeBootLogos)
  assert all(display.boot_logo_image(slug).is_file() for slug, _ in BUILT_IN_LOGOS)
  assert set(BUILT_IN_IMAGES) == {slug for slug, _ in BUILT_IN_LOGOS} and display.boot_logo_image("aurora_logo") is None



def test_pair_opens_the_pairing_page_when_given():
  from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel, pairing_page
  device = FakeDevice()
  opened = []
  panel = ThisDevicePanel(device, lambda: opened.append(pairing_page(device)))
  _rows(panel)["Phone App"]._control._click_callback()
  assert len(opened) == 1 and "pair" not in device.calls
  _rows(ThisDevicePanel(device))["Phone App"]._control._click_callback()
  assert device.calls == ["pair"]   # without a page, upstream's dialog


def test_remote_access_page_sets_up_and_unpairs():
  from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel, remote_access_page

  class Window:
    def __init__(self):
      self.presented = None

    def present(self, dialog):
      self.presented = dialog

    def dismiss(self):
      pass

  device, window, pages = FakeDevice(), Window(), []
  panel = ThisDevicePanel(device, None, lambda: pages.append(remote_access_page(device, window)))
  _rows(panel)["Remote Access"]._control._click_callback()
  page = pages[0]
  steps = page._body._items[0]
  set_up, unpair = steps._items[3], steps._items[4]
  assert set_up.is_visible and not unpair.is_visible
  set_up._click_callback()
  assert device.calls[-1] == "set_up_remote_access"
  device.remote_access_link = lambda: "https://galaxy.firestar.link/abc"
  assert unpair.is_visible and not set_up.is_visible
  unpair._click_callback()
  assert "unpair_remote_access" not in device.calls   # it asks first
  from openpilot.system.ui.widgets import DialogResult
  window.presented._on_result(DialogResult.CONFIRM)
  assert device.calls[-1] == "unpair_remote_access"


def test_device_actions_ask_first_with_our_dialog():
  from openpilot.selfdrive.ui.tandem.settings.device import ThisDevicePanel
  device, asked = FakeDevice(), []
  panel = ThisDevicePanel(device, ask=lambda title, message, label, action, danger, icon: asked.append((label, action, danger)))
  restart, power_off = panel._footer._buttons
  restart._click_callback()
  power_off._click_callback()
  _rows(panel)["Camera Calibration"]._control._click_callback()
  assert [(label, danger) for label, _, danger in asked] == [("Restart", False), ("Power Off", True), ("Recalibrate", False)]
  assert device.calls == []                       # nothing runs until the dialog says yes
  for _, action, _ in asked:
    action()
  assert device.calls == ["restart", "power_off", "recalibrate"]


def test_bar_metrics_pick_up_to_five_in_catalog_order_and_reset_to_the_mock():
  from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_DEFAULT
  from openpilot.selfdrive.ui.tandem.prefs import DEVELOPER_STRIP
  from openpilot.selfdrive.ui.tandem.settings.tuner import Tuner
  store, cache = _store()
  tuner = Tuner(store)
  assert tuner.strip() == list(STRIP_DEFAULT)            # unset: the mock's five
  tuner.toggle_strip("steer")                            # already five: nothing changes
  assert tuner.strip() == list(STRIP_DEFAULT)
  tuner.toggle_strip("jerk")
  tuner.toggle_strip("steer")
  assert tuner.strip() == ["accel", "want", "lat", "delay", "steer"]
  for key in list(tuner.strip()):
    tuner.toggle_strip(key)
  assert tuner.strip() == [] and DEVELOPER_STRIP.get() == "none" and "DeveloperStripMetrics" not in cache.values
  tuner.reset_all()
  assert tuner.strip() == list(STRIP_DEFAULT)


def test_bar_metrics_sheet_opens_from_developer_view_overrides():
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  from openpilot.selfdrive.ui.tandem.settings.tuner import BundleOverrides, StripPicker, Tuner

  class Window:
    overlay = None

    def present(self, overlay):
      self.overlay = overlay

    def dismiss(self):
      self.overlay = None

  store, _ = _store()
  tuner, window = Tuner(store), Window()
  BundleOverrides(tuner, window)._choose._click_callback()
  assert isinstance(window.overlay, Sheet) and isinstance(window.overlay._body, StripPicker)


def test_profiles_show_from_style_and_override_resets_to_the_style():
  from openpilot.selfdrive.ui.tandem.settings.tuner import FROM_STYLE, OVERRIDE, Tuner
  store, cache = _store({"LongitudinalPersonality": 1, "AccelerationProfile": 0, "DecelerationProfile": 1})
  tuner = Tuner(store)
  assert tuner.profile_status("AccelerationProfile") == FROM_STYLE
  tuner.set_accel_profile(2)                                    # Sport
  assert tuner.profile_status("AccelerationProfile") == OVERRIDE
  tuner.reset_profile("AccelerationProfile")
  assert tuner.profile_status("AccelerationProfile") == FROM_STYLE


def test_map_download_steps_regions_and_time_left():
  from openpilot.selfdrive.ui.tandem.settings.maps import Progress, RegionProgress, minutes_left
  regions = (RegionProgress("US_AK", 4, 4), RegionProgress("US_ID", 3, 5), RegionProgress("Germany", 0, 9))
  p = Progress(True, 7, 18, "US_ID", regions)
  assert p.step == 1 and p.current.code == "ID" and regions[2].code == "Germany"
  assert Progress(True, 0, 0, "").step == 0 and Progress(True, 18, 18, "").step == 2 and Progress(False, 18, 18, "").step == 3
  assert minutes_left((0.0, 0), 60.0, 6, 18) == 2          # 6 files a minute, 12 to go
  assert minutes_left((0.0, 0), 3.0, 1, 18) is None         # too early to tell


def test_region_tiles_keep_the_current_one_in_view_when_they_overflow():
  from openpilot.selfdrive.ui.tandem.settings.maps import tile_window
  assert tile_window(13, 5, 14) == (0, 13, 0)                 # all fit
  start, end, more = tile_window(56, 40, 21)
  assert start <= 40 < end and end - start == 20 and more == 36
  assert tile_window(56, None, 21) == (0, 20, 36)


# ── Settings search ──

def _rows_on(widget, seen=None) -> list[str]:
  """Every SettingRow title on a page, building panels that build on first draw."""
  from openpilot.selfdrive.ui.tandem.base import resolve
  from openpilot.selfdrive.ui.tandem.rows import SettingRow
  from openpilot.selfdrive.ui.tandem.settings.model import Rebuilding
  seen = seen if seen is not None else set()
  if id(widget) in seen:
    return []
  seen.add(id(widget))
  if isinstance(widget, Rebuilding) and widget._content is None:
    widget._update_state()
  titles = [resolve(widget._title)] if isinstance(widget, SettingRow) else []
  for child in list(getattr(widget, "_children", [])) + list(getattr(widget, "items", None) or []):
    titles += _rows_on(child, seen)
  for name in ("_content", "_panel", "current"):
    child = getattr(widget, name, None)
    if child is not None and hasattr(child, "render"):
      titles += _rows_on(child, seen)
  return titles


def _search_window():
  from openpilot.selfdrive.ui.tandem.settings import window as W
  from openpilot.selfdrive.ui.tandem.settings.bundles import TUNER_MODE
  from openpilot.selfdrive.ui.tandem.tests.fakes import (FakeBluetooth, FakeBootLogos, FakeCarExtras, FakeCars, FakeData,
                                                         FakeDeveloperSource, FakeMaps, FakeModels, FakeUpdates, FakeWheel, FakeWifi)
  models, wheel, maps = FakeModels(), FakeWheel(), FakeMaps()
  window = W.SettingsWindow(store=SettingsStore(FakeCache(), lambda: None), live=FakeLive(), model_source=lambda: models,
                            car_catalog=FakeCars, device_data=FakeData, device=FakeDevice, wifi=FakeWifi, wheel=lambda: wheel,
                            bluetooth=FakeBluetooth, updates=FakeUpdates, maps_source=lambda: maps, boot_logos=FakeBootLogos,
                            developer_source=FakeDeveloperSource, car_extras=FakeCarExtras)
  TUNER_MODE.set(window.store, True)
  return window


# Rows named after data (networks, backups, devices, the car's own buttons), not settings
DATA_ROWS = {"Home Wi-Fi", "Coffee Shop", "Neighbor", "Car Audio", "Pixel 9", "Home", "Work", "Distance", "LKAS", "Cruise main"}


def test_search_index_matches_every_settings_screen():
  from openpilot.selfdrive.ui.tandem.settings.search import ENTRIES, SECTIONS
  window = _search_window()
  places = sorted({(e.tab, e.page, e.section) for e in ENTRIES}, key=str)
  for tab, page, section in places:
    window.open_at(tab, page, section)
    shown = set(_rows_on(window.top))
    indexed = {e.name for e in ENTRIES if (e.tab, e.page, e.section) == (tab, page, section) and e.row}
    assert indexed <= shown, f"{(tab, page, section)}: indexed but not there: {indexed - shown}"
    if section is None and (page if page is not None else tab) in SECTIONS:
      continue   # a page with sections opens its first one, whose rows are indexed there
    unindexed = {t for t in shown - indexed if t not in DATA_ROWS and not t.startswith("Backup") and t != "Before update"}
    assert not unindexed, f"{(tab, page, section)}: rows missing from the search index: {unindexed}"


def test_search_finds_by_name_meaning_and_place_best_first():
  from openpilot.selfdrive.ui.tandem.settings.search import search
  names = [e.name for e in search("gas", tuner=True)]
  assert names[:2] == ["Gas & Brake", "Disengage on Gas Pedal"] and "Actuator Delay" in names
  assert "Gas & Brake" not in [e.name for e in search("gas", tuner=False)]          # Tuner Mode screens only while it's on
  assert [e.name for e in search("imperial", tuner=False)] == ["Units"]
  assert search("hotspot pass", tuner=False)[0].name == "Hotspot Password"
  assert search("g", tuner=True) == []                                                # two letters at least
  assert search("bluetooth remote", tuner=False)[0].where == "Connections"     # a section shows the place it sits in


def test_picking_a_result_opens_its_page_and_section():
  from openpilot.selfdrive.ui.tandem.settings.search import ResultCard, search
  window = _search_window()
  window.show_event()
  window.select_tab(Tab.SOFTWARE)
  results = search("trailer", tuner=True)
  assert [e.name for e in results] == ["Trailer Load", "Vehicle Profile"]
  card = ResultCard(0, lambda: results, lambda e: window.open_at(e.tab, e.page, e.section))
  card._click_callback()
  assert window.tab == Tab.DRIVING and window.depth == 2
  assert window.top.selected == 1                                                     # Speed & Steering › Vehicle Profile
  window.open_at(Tab.CONNECTIONS, None, 1)
  assert window.tab == Tab.CONNECTIONS and window.top.selected == 1


def test_language_shows_its_name_after_a_restart():
  from openpilot.selfdrive.ui.tandem.settings.device_sections import General, same_language
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeData
  data = FakeData()
  data.languages = lambda: [("English", "main_en"), ("Deutsch", "main_de")]
  general = General(SettingsStore(FakeCache(), lambda: None), data, FakeLive())
  for code in ("en", "main_en"):            # loaded at startup, and just chosen
    data.language = lambda code=code: code
    assert general.language_name() == "English"
  data.language = lambda: "de"
  assert general.language_name() == "Deutsch"
  assert same_language("main_de", "de") and not same_language("main_de", "main_en")



def test_compass_switch_writes_starpilots_compass():
  from openpilot.selfdrive.ui.tandem.settings.display import Display, driving_screen_panel
  store, cache = _store({"Compass": False})
  display = Display(store)
  row = _rows(driving_screen_panel(display, None))["Compass"]
  assert not row._control.value
  display.set_compass(True)
  assert cache.values["Compass"] and display.compass


def test_lead_car_tag_is_a_marker_file_on_by_default(tandem_prefs):
  from openpilot.selfdrive.ui.tandem.settings.display import Display, driving_screen_panel
  store, cache = _store({})
  display = Display(store)
  row = _rows(driving_screen_panel(display, None))["Lead Car Tag"]
  assert row._control.value and display.lead_tag and not list(tandem_prefs.iterdir())
  params = dict(cache.values)
  display.set_lead_tag(False)
  assert not display.lead_tag and not row._control.value and list(tandem_prefs.iterdir())
  assert cache.values == params   # no param: unknown keys crash the prebuilt params on the device


def test_quiet_is_25_percent_for_every_alert_sound():
  from openpilot.selfdrive.ui.tandem.settings.alerts import GROUPS, SAFETY_FLOOR, Alerts
  store, cache = _store({"AlertVolumeControl": False})
  alerts = Alerts(store)
  alerts.set_preset(1)
  keys = [k for g in GROUPS for k in g.keys]
  assert all(cache.values[k] == 25 == SAFETY_FLOOR for k in keys) and cache.values["AlertVolumeControl"]
  assert alerts.preset == 1


def test_boot_logo_previews_decode_jpegs_without_raylib():
  """The device's raylib can't open JPEGs; every built-in logo is one, so previews decode them as PNG first."""
  import io
  from PIL import Image
  from openpilot.selfdrive.ui.tandem.settings.display import BUILT_IN_IMAGES, _logo_png
  for slug, path in BUILT_IN_IMAGES.items():
    assert path.suffix == ".jpg"
    png = _logo_png(path, 400)
    assert png is not None and png[:8] == b"\x89PNG\r\n\x1a\n", slug
    with Image.open(io.BytesIO(png)) as image:
      assert image.size == (400, 200), slug                      # comma's portrait logo turned landscape too
  assert _logo_png(BUILT_IN_IMAGES["tandem"].with_suffix(".missing"), 400) is None


def test_connected_network_shows_the_local_ip_address():
  from openpilot.selfdrive.ui.tandem.settings.network_tab import Network
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWifi
  wifi = FakeWifi()
  network = Network(wifi, SettingsStore(FakeCache(), lambda: None))
  assert network.status_line(wifi.connected_ssid) == f"Connected · {wifi.ipv4_address}"
  other = next(n.ssid for n in wifi.networks if n.ssid != wifi.connected_ssid)
  assert wifi.ipv4_address not in network.status_line(other)
  wifi.ipv4_address = ""
  assert network.status_line(wifi.connected_ssid) == "Connected"


def test_download_tiles_show_codes_in_a_steady_order():
  from openpilot.selfdrive.ui.tandem.settings.maps import RegionProgress, region_tiles
  assert RegionProgress("us_state.IA", 0, 1).code == "IA" and RegionProgress("nation.DE", 0, 1).code == "DE"
  first = region_tiles([("us_state.IL", 1, 9), ("us_state.IA", 9, 9)])
  again = region_tiles([("us_state.IA", 9, 9), ("us_state.IL", 2, 9)])   # mapd's next update, in another order
  assert [r.code for r in first] == [r.code for r in again] == ["IA", "IL"]



def test_imei_is_read_once_from_the_modem_in_the_background(monkeypatch):
  import time
  from openpilot.system import hardware
  from openpilot.selfdrive.ui.tandem.settings.device import UpstreamDevice
  calls = []
  monkeypatch.setattr(hardware.HARDWARE, "get_imei", lambda slot: calls.append(slot) or "351234567890123", raising=False)
  device = UpstreamDevice.__new__(UpstreamDevice)
  device._tici, device._imei, device._imei_reading = True, "", False
  assert device.imei() == "Not available"
  device._read_imei()
  end = time.monotonic() + 5
  while device._imei_reading and time.monotonic() < end:
    time.sleep(0.01)
  device._read_imei()                                # already known: the modem isn't asked again
  assert device.imei() == "351234567890123" and calls == [0]

  # The first calls miss openpilot's 0.1 s modem timeout; it keeps trying on its own.
  monkeypatch.setattr(UpstreamDevice, "IMEI_WAIT_S", 0.01)
  tries = []

  def slow_modem(slot):
    tries.append(slot)
    if len(tries) < 3:
      raise RuntimeError("modem busy")
    return "351234567890124"
  monkeypatch.setattr(hardware.HARDWARE, "get_imei", slow_modem, raising=False)
  retrying = UpstreamDevice.__new__(UpstreamDevice)
  retrying._tici, retrying._imei, retrying._imei_reading = True, "", False
  retrying._read_imei()
  while retrying._imei_reading and time.monotonic() < end:
    time.sleep(0.01)
  assert retrying.imei() == "351234567890124" and len(tries) == 3

  monkeypatch.setattr(hardware.HARDWARE, "get_imei", lambda slot: (_ for _ in ()).throw(RuntimeError("no modem")), raising=False)
  failing = UpstreamDevice.__new__(UpstreamDevice)
  failing._tici, failing._imei, failing._imei_reading = True, "", False
  failing._read_imei()
  while failing._imei_reading and time.monotonic() < end:
    time.sleep(0.01)
  assert failing.imei() == "Not available" and not failing._imei_reading   # gives up, and can try again next time


def test_language_names_use_figtree_unless_it_lacks_a_letter(monkeypatch):
  from types import SimpleNamespace
  from openpilot.selfdrive.ui.tandem import fonts, tokens as T
  latin = [ord(c) for c in "?EnglishFraçaisTürkçeEspañol"]
  atlas = SimpleNamespace(glyphs=[SimpleNamespace(value=cp) for cp in latin])
  monkeypatch.setattr(fonts, "font", lambda face: atlas)
  monkeypatch.setattr(fonts.rl, "get_glyph_index", lambda f, cp: latin.index(cp) if cp in latin else 0)
  monkeypatch.setattr(fonts, "_covered", {})
  assert fonts.face_for("Français", T.FONT_SEMIBOLD) == T.FONT_SEMIBOLD
  assert fonts.face_for("Español", T.FONT_SEMIBOLD) == T.FONT_SEMIBOLD
  assert fonts.face_for("Українська", T.FONT_SEMIBOLD) == T.FONT_UNIFONT
  assert fonts.face_for("日本語", T.FONT_SEMIBOLD) == T.FONT_UNIFONT


def test_tandem_text_keeps_figtree_when_the_language_needs_unifont(monkeypatch):
  from types import SimpleNamespace
  from openpilot.selfdrive.ui.tandem import draw
  from openpilot.system.ui.lib import application
  monkeypatch.setattr(application.multilang, "requires_unifont", lambda: True)
  unifont, figtree = SimpleNamespace(texture=SimpleNamespace(id=1)), SimpleNamespace(texture=SimpleNamespace(id=2))
  monkeypatch.setattr(application.gui_app, "font", lambda weight=None: unifont)
  assert not application.KEEP_FONT and application.font_fallback(figtree) is unifont   # upstream's text still falls back
  with draw._own_font:
    with draw._own_font:                                     # nesting keeps it on until the outermost use ends
      pass
    assert application.font_fallback(figtree) is figtree
  assert not application.KEEP_FONT and application.font_fallback(figtree) is unifont


def test_the_language_list_leaves_out_the_novelty_styles():
  from openpilot.selfdrive.ui.tandem.settings.device_sections import picker_languages
  languages = [("English", "main_en"), ("Caveman", "main_caveman"), ("Deutsch", "main_de"), ("Pirate", "main_pirate"),
               ("Shakespearean", "main_shakespearean"), ("日本語", "main_ja")]
  assert [n for n, _ in picker_languages(languages, "en")] == ["English", "Deutsch", "日本語"]
  assert [n for n, _ in picker_languages(languages, "pirate")] == ["English", "Deutsch", "Pirate", "日本語"]   # in use: kept



def test_sentry_mode_writes_starpilots_params_and_sensitivity_presets():
  from openpilot.selfdrive.ui.tandem.settings.device import driver_monitoring_rows
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import Assistance, driver_monitoring_panel
  store, cache = _store({"SentryModeEnabled": False, "SentryModeSensitivity": 0.04})
  model = Assistance(store, FakeLive())
  rows = _rows(driver_monitoring_panel(model, driver_monitoring_rows(FakeDevice(), None)))
  assert not rows["Sentry Mode"]._control.value and model.sentry_sensitivity == 1   # off by default, Standard
  model.set_sentry(True)
  model.set_sentry_sensitivity(2)
  assert cache.values["SentryModeEnabled"] and cache.values["SentryModeSensitivity"] == 0.02 and model.sentry_sensitivity == 2
  cache.values["SentryModeSensitivity"] = 0.013   # set with Galaxy's slider: none of the three
  assert model.sentry_sensitivity == -1
