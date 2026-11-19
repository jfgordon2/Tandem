"""Stand-ins for the network, cellular, radio and Bluetooth services, for tests and headless renders."""
from dataclasses import replace

from openpilot.selfdrive.ui.tandem.settings.network_test import Connection, Via
from openpilot.starpilot.tandem.network_test import Phase, Result


class FakeNet:
  def __init__(self, ssid, strength, security_type=2, is_tethering=False):
    self.ssid, self.strength, self.security_type, self.is_tethering = ssid, strength, security_type, is_tethering


class FakeCellular:
  """Deterministic observations for settings tests and renders, with no D-Bus worker."""

  def __init__(self):
    from openpilot.starpilot.tandem.cellular import Monitor, Observation
    self.model = Monitor(reader_factory=None, clock=lambda: 0.0)
    self.value = Observation(sim=True, modem=11, registration=1, technology="LTE", quality=60, connected=True,
                             address="10.64.12.8", bearer_apn="carrier.apn", auto_config=True, identity=("modem", "bearer", "active"))
    self.active = False
    self.calls = []

  def set_active(self, active, apn=None):
    self.active = active
    self.calls.append(active)
    if apn is not None:
      self.model._target = apn

  def apn_saved(self, apn, previous):
    from dataclasses import replace
    self.model.apn_saved(apn, previous)
    if self.value is not None:
      self.value = replace(self.value, connected=False, connecting=True)

  def status(self):
    self.model._observation, self.model._updated = self.value, 0.0 if self.value is not None else None
    return self.model.status()


class FakeRadios:
  def __init__(self):
    from openpilot.starpilot.tandem.radios import Radio, RadioState
    self.states = {radio: RadioState(True, True, True) for radio in Radio}
    self.writing = self.read_failed = False
    self.failed = None

  def refresh(self):
    pass

  def state(self, radio):
    return self.states.get(radio)

  def set_enabled(self, radio, enabled):
    from dataclasses import replace
    self.states[radio] = replace(self.states[radio], enabled=enabled)


class FakeWifi:
  def __init__(self):
    self.radios = FakeRadios()
    self.cellular_status = FakeCellular()
    self.networks = [FakeNet("Home Wi-Fi", 90), FakeNet("Coffee Shop", 60, 0), FakeNet("Neighbor", 30)]
    self.saved = {"Home Wi-Fi"}
    self.connected_ssid = "Home Wi-Fi"
    self.connecting_to_ssid = None
    self.ipv4_address = "192.168.1.42"
    self.tethering_password = "swordfish1"
    self.tethering_ssid = "weedle-c488"
    self.tethering_name_ready = True
    self.tethering_name_busy = False
    self.tethering_name_failed = False
    self.tethering = False
    self.calls = []
    self.need_auth = None

  def add_callbacks(self, need_auth=None, **_):
    self.need_auth = need_auth

  def process_callbacks(self):
    pass

  def set_active(self, active):
    self.calls.append(("active", active))

  def is_connection_saved(self, ssid):
    return ssid in self.saved

  def activate_connection(self, ssid):
    self.calls.append(("activate", ssid))

  def connect_to_network(self, ssid, password, hidden=False):
    self.calls.append(("connect", ssid, password, hidden))

  def forget_connection(self, ssid):
    self.saved.discard(ssid)

  def is_tethering_active(self):
    return self.tethering

  def set_tethering_active(self, on):
    self.tethering = on

  def set_tethering_password(self, password):
    self.tethering_password = password

  def set_tethering_ssid(self, name):
    self.tethering_ssid = name

  def set_current_network_metered(self, metered):
    self.calls.append(("metered", metered))


class FakeWheel:
  favorite_slots = 3

  def __init__(self):
    self.maps = [{"id": "a", "device_name": "Wheel Remote", "event_name": "BTN_A", "slot": 3},
                 {"id": "b", "device_name": "Wheel Remote", "event_name": "BTN_B", "slot": 4}]
    self.keys = {3: "a:engage_openpilot", 4: "a:disengage_openpilot"}
    self.state = {"testing": True, "last_tested": None, "devices": [{"name": "Wheel Remote"}]}
    self.learning = None

  def mappings(self):
    return self.maps

  def action(self, slot):
    return f"favorite:{slot}" if slot < 3 else self.keys.get(slot)

  def actions(self):
    return [("a:engage_openpilot", "Engage"), ("a:disengage_openpilot", "Disengage"), ("a:cycle_driving_personality", "Change driving style"),
            ("a:toggle_screen_off", "Screen off / on"),
            ("favorite:0", "Favorite 1 · Save a clip")]

  def status(self):
    return self.state

  def start_learning(self, slot):
    self.learning = slot

  def cancel_learning(self):
    self.learning = None

  def start_testing(self):
    self.state["testing"] = True

  def stop_testing(self):
    self.state["testing"] = False

  def free_slot(self):
    used = {m["slot"] for m in self.maps}
    return next(s for s in range(3, 13) if s not in used)

  def assign(self, mapping_id, key):
    mapping = next(m for m in self.maps if m["id"] == mapping_id)
    if key.startswith("favorite:"):
      mapping["slot"] = int(key.split(":")[1])
    else:
      self.keys[mapping["slot"]] = key
    return True

  def delete(self, mapping_id):
    self.maps = [m for m in self.maps if m["id"] != mapping_id]


class FakeDevice_:
  def __init__(self, address, name, paired=False, connected=False, audio=False, controller=False):
    self.address, self.name, self.paired, self.connected, self.audio, self.controller = address, name, paired, connected, audio, controller


class FakeBtStatus:
  def __init__(self):
    self.available = self.enabled = self.powered = True
    self.devices = (FakeDevice_("AA", "Car Audio", True, True, audio=True), FakeDevice_("BB", "Pixel 9"),
                    FakeDevice_("CC", "Wheel Remote", True, True, controller=True))
    self.selected_audio = "AA"
    self.offroad = True
    self.discovering = True


class FakeBluetooth:
  def __init__(self):
    self._status = FakeBtStatus()
    self.calls = []

  def tick(self):
    pass

  def set_active(self, active):
    self.calls.append(("active", active))

  def status(self):
    return self._status

  def set_power(self, enabled):
    self.calls.append(("power", enabled))
    self._status.enabled = self._status.powered = enabled
    self._status.discovering = enabled

  def power_busy(self):
    return False

  def select(self, address):
    self.calls.append(("select", address))
    device = next((d for d in self._status.devices if d.address == address), None)
    return bool(device and device.paired and device.connected)

  def disconnect(self, address):
    self.calls.append(("disconnect", address))

  def use_for_audio(self, address):
    self.calls.append(("audio", address))
    self._status.selected_audio = address

  def prompt(self):
    return getattr(self, "_prompt", None)

  def respond(self, prompt_id, accept, value=""):
    self.calls.append(("respond", prompt_id, accept, value))

  def test_audio(self, address):
    self.calls.append(("test", address))

  def audio_test_text(self):
    return "A sound plays in 3…"

  def forget(self, address):
    self.calls.append(("forget", address))


class FakeNetworkTest:
  """The network tester, showing the result a test or render gives it. Nothing is sent anywhere."""

  def __init__(self, shown=None):
    self.shown = shown or Result()
    self.calls = []

  def result(self):
    return self.shown

  def start(self, budget):
    self.calls.append(("start", budget))
    self.shown = Result(Phase.DOWNLOAD, budget=budget)

  def stop(self):
    self.calls.append("stop")
    if self.shown.running:
      self.shown = replace(self.shown, phase=Phase.STOPPED, finished=0.0)


def home_wifi():
  """The connection FakeWifi's device is on."""
  return Connection(Via.WIFI)


class FakeCache:
  """Params as SettingsStore reads and writes them (StarPilot 7's typed get and put)."""

  def __init__(self, values: dict | None = None):
    self.values = dict(values or {})
    self.invalidations = 0

  def get_bool(self, key: str, block: bool = False) -> bool:
    return bool(self.values.get(key, False))

  def get(self, key: str, return_default: bool = False, block: bool = False) -> object:
    return self.values.get(key)

  def put_bool(self, key: str, value: object, block: bool = False) -> None:
    self.values[key] = value

  put = put_bool

  def invalidate(self) -> None:
    self.invalidations += 1


def network(values: dict | None = None) -> tuple:
  """A Network over FakeWifi: (network, wifi, cache, asked), asked collecting (title, done) for each text prompt."""
  from openpilot.selfdrive.ui.tandem.settings.network_tab import Network
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  cache, asked = FakeCache(values), []
  wifi = FakeWifi()
  net = Network(wifi, SettingsStore(cache, lambda: None), ask=lambda title, sub, current, done, *a, **k: asked.append((title, done)))
  return net, wifi, cache, asked


def connections_window() -> object:
  """A settings window whose Connections tab is the real page over FakeWifi and FakeNetworkTest."""
  from openpilot.selfdrive.ui.tandem.settings import connections
  from openpilot.selfdrive.ui.tandem.settings.network_tab import advanced_panel
  from openpilot.selfdrive.ui.tandem.settings.network_test import NetworkTestModel
  from openpilot.selfdrive.ui.tandem.settings.pages import PanelPage
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
  net = network()[0]

  def page() -> object:
    test = NetworkTestModel(FakeNetworkTest(), lambda: net.wifi.connected_ssid, lambda: Connection(Via.WIFI, "Home Wi-Fi", False))
    from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import WheelButtons
    return connections.connections_page(net, lambda: window.push(PanelPage(advanced_panel(net))), window, test, WheelButtons(FakeWheel()),
                                        FakeBluetooth())
  window = SettingsWindow({Tab.CONNECTIONS: page}, initial=Tab.CONNECTIONS)
  return window


class FakePlaces:
  """Places for the destination screens: Home and Work saved, two recents, and canned search results."""

  def __init__(self, routing=True, maps=True):
    self.favs = [{"name": "Home", "place_name": "1428 SE Elm St, Portland", "is_home": True, "latitude": 1, "longitude": 1},
                 {"name": "Work", "place_name": "200 Market St, Portland", "is_work": True, "latitude": 2, "longitude": 2},
                 {"name": "Powell's Books", "place_name": "1005 W Burnside St, Portland", "latitude": 3, "longitude": 3}]
    self.recent = [{"name": "Hardware Store", "place_name": "Hardware Store, 3550 SE Hawthorne Blvd, Portland", "latitude": 4, "longitude": 4},
                   {"name": "Laurelhurst Park", "place_name": "Laurelhurst Park, SE Cesar E Chavez Blvd, Portland", "latitude": 5,
                    "longitude": 5}]
    self.found: list[tuple[str, str]] = []
    self.queries: list[str] = []
    self.chosen: dict | None = None
    self.navigating: dict | None = None
    self.routing, self.maps = routing, maps

  def tick(self):
    pass

  def refresh(self):
    pass

  def active(self):
    return self.navigating

  def favorites(self):
    return self.favs

  def recents(self):
    return self.recent

  def _fav(self, place):
    return next((f for f in self.favs if f["name"] == place.get("name")), None)

  def is_favorite(self, place):
    return self._fav(place) is not None

  def toggle_saved(self, place):
    fav = self._fav(place)
    if fav:
      self.favs.remove(fav)
    else:
      self.favs.append(dict(place))

  def search(self, query):
    self.queries.append(query)
    self.found = [("Hardware Store", "3550 SE Hawthorne Blvd, Portland"), ("Hardware Sales", "2034 SE 11th Ave, Portland"),
                  ("Hardware Park", "SE 12th & Stark, Portland")]

  def results(self):
    return self.found

  def status(self):
    return None if self.found or not self.queries else ("Nothing found", "Try a different place or address")

  def pick_result(self, index):
    name, line = self.found[index]
    self.chosen = {"name": name, "place_name": f"{name}, {line}", "latitude": 9, "longitude": 9}

  def pick(self, place):
    self.chosen = dict(place)

  def draft(self):
    return self.chosen

  def clear_draft(self):
    self.chosen = None

  def saved_as(self):
    fav = self._fav(self.chosen or {})
    return (fav is not None, bool(fav and fav.get("is_home")), bool(fav and fav.get("is_work")))

  def toggle(self, kind):
    fav = self._fav(self.chosen)
    if kind == "favorite":
      if fav:
        self.favs.remove(fav)
      else:
        self.favs.append(dict(self.chosen))
      return
    if fav is None:
      fav = dict(self.chosen)
      self.favs.append(fav)
    key = "is_home" if kind == "home" else "is_work"
    fav[key] = not fav.get(key)

  def can_start(self):
    return self.routing

  def can_search(self):
    return self.routing

  def start(self):
    if not self.routing:
      return False
    self.navigating, self.chosen = self.chosen, None
    return True

  def end_route(self):
    self.navigating = None

  def maps_ready(self):
    return self.maps

  def route(self):
    from openpilot.selfdrive.ui.tandem.routemap import NOT_SET_UP, RoutePlan
    if not self.routing:
      return None, NOT_SET_UP
    if self.chosen is None:
      return None, ""
    path = ((45.512, -122.658), (45.512, -122.650), (45.518, -122.650), (45.521, -122.642), (45.523, -122.636), (45.527, -122.636),
            (45.527, -122.628))
    return RoutePlan(path, 5310.0, 1080.0), ""

  def metric(self):
    return False



class FakeNavigationOwner:
  """StarPilot 7's navigation owner as far as Speed & Steering › Navigation and Where to? use it: Mapbox key saved, a
  Google key too, Home, Work and one favorite."""

  def __init__(self, google: bool = True, mapbox: bool = True):
    self.settings: dict = {"enabled": True, "routeProvider": "mapbox", "gpsSource": "backup", "avoidTolls": True,
                           "avoidHighways": False, "avoidFerries": False, "hasKey": mapbox, "hasGoogleKey": google}
    self.favorites = [{"id": "h", "name": "Home", "address": "1428 SE Elm St, Portland", "latitude": 1.0, "longitude": 1.0, "label": "home"},
                      {"id": "w", "name": "Work", "address": "200 Market St, Portland", "latitude": 2.0, "longitude": 2.0, "label": "work"},
                      {"id": "p", "name": "Powell's Books", "address": "1005 W Burnside St, Portland", "latitude": 3.0, "longitude": 3.0}]
    self.revision = 0

  def snapshot(self) -> dict:
    return dict(self.settings, revision=str(self.revision), favorites=list(self.favorites), recents=[], destination=None)

  def configure(self, patch: dict, revision: str, authorized: object) -> dict:
    if revision != str(self.revision):
      raise ValueError("Navigation changed; refresh and try again")
    self.settings.update(patch)
    self.revision += 1
    return self.snapshot()
