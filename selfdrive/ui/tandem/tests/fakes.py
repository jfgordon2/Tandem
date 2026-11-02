"""Stand-ins for StarPilot's model controller and car catalog, for tests and headless renders."""
from openpilot.selfdrive.ui.tandem.settings.model import ModelInfo
from openpilot.selfdrive.ui.tandem.settings.vehicle import CarOption, WheelButton


class FakeModels:
  def __init__(self):
    self.items = [ModelInfo("rdf43", "Tidewater", True), ModelInfo("vtx", "Vortex", True, community_pick=True),
                  ModelInfo("nlp", "North Loop", False, community_pick=True), ModelInfo("big", "Highland XL", False, needs_egpu=True)]
    self.current = "rdf43"
    self.downloading = None
    self.calls = []

  def refresh(self):
    self.calls.append("refresh")

  def tick(self):
    pass

  def models(self):
    return self.items

  def current_key(self):
    return self.current

  def recommended_key(self):
    return "rdf43"

  def downloading_key(self):
    return self.downloading

  def progress(self):
    return "45% · about 3 min left"

  def egpu_available(self):
    return False

  def use(self, key):
    self.current = key

  def download(self, key):
    self.downloading = key

  def cancel(self):
    self.downloading = None

  def remove(self, key):
    self.items = [m for m in self.items if m.key != key]

  def removal_blocked(self):
    return ""


class FakeCars:
  def makes(self):
    return ["Chevrolet", "Honda", "Toyota"]

  def models(self, make):
    return {"Toyota": [CarOption("TOYOTA_RAV4_TSS2", "RAV4 2019-21"), CarOption("TOYOTA_RAV4H_TSS2", "RAV4 Hybrid 2019-21")],
            "Honda": [CarOption("HONDA_CIVIC", "Civic 2016-21")], "Chevrolet": [CarOption("CHEVROLET_BOLT_EUV", "Bolt EUV 2022-23")]}[make]

  def actions(self, button):
    return [(0, "Car default"), (1, "Change driving style"), (3, "Pause steering"), (9, "Always-on steering")]

  def buttons(self):
    return [WheelButton("Distance", "Press", "DistanceButtonControl"), WheelButton("Distance", "Long press", "LongDistanceButtonControl"),
            WheelButton("LKAS", "Press", "LKASButtonControl"), WheelButton("Cruise main", "Press", "MainCruiseButtonControl", True)]

  def has_auto_lock(self):
    return True


class FakeData:
  def __init__(self):
    from openpilot.selfdrive.ui.tandem.settings.device_sections import Backup
    self._Backup = Backup
    self.items = [Backup("Backup 2026-10-24 0910", "Oct 24, 2026 9:10 AM"), Backup("Before update", "Oct 2, 2026 6:00 PM")]
    self.lang = "en"
    self.reports = []
    self.restored = []
    self.drives_deleted = False

  def languages(self):
    return [("English", "en"), ("Español", "es"), ("Français", "fr")]

  def language(self):
    return self.lang

  def set_language(self, code):
    self.lang = code

  def backups(self):
    return self.items

  def create_backup(self):
    self.items = [self._Backup("Backup now", "Just now"), *self.items]

  def restore_backup(self, name):
    self.restored.append(name)

  def delete_backup(self, name):
    self.items = [b for b in self.items if b.name != name]

  def storage(self):
    return {"Drives": 21e9, "Maps": 4.2e9, "Models": 1.1e9, "Total": 64e9, "Free": 30e9}

  def delete_drives(self):
    self.drives_deleted = True

  def delete_maps(self):
    self.maps_deleted = True

  def maps_blocked(self):
    return ""

  def send_report(self, issue, discord):
    self.reports.append((issue, discord))


class FakeNet:
  def __init__(self, ssid, strength, security_type=2, is_tethering=False):
    self.ssid, self.strength, self.security_type, self.is_tethering = ssid, strength, security_type, is_tethering


class FakeWifi:
  def __init__(self):
    self.networks = [FakeNet("Home Wi-Fi", 90), FakeNet("Coffee Shop", 60, 0), FakeNet("Neighbor", 30)]
    self.saved = {"Home Wi-Fi"}
    self.connected_ssid = "Home Wi-Fi"
    self.connecting_to_ssid = None
    self.ipv4_address = "192.168.1.42"
    self.tethering_password = "swordfish1"
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

  def set_current_network_metered(self, metered):
    self.calls.append(("metered", metered))

  def update_gsm_settings(self, roaming, apn, metered):
    self.calls.append(("gsm", roaming, apn, metered))


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


class FakeUpdates:
  def __init__(self):
    self.calls = []
    self.target = "release"

  def tick(self):
    pass

  def branches(self):
    return ["release", "staging", "nightly"]

  def target_branch(self):
    return self.target

  def set_branch(self, branch):
    self.target = branch
    self.calls.append(("branch", branch))

  def uninstall(self, erase):
    self.calls.append(("uninstall", erase))

  def release_notes(self):
    return "Version 0.10.1\n• Smoother lane changes\n• Fixes for Toyota"

  def __getattr__(self, name):
    return lambda: self.calls.append(name)


class FakeMaps:
  def __init__(self):
    from openpilot.selfdrive.ui.tandem.settings.maps import Progress, Region
    self._Progress = Progress
    self._regions = [[Region("c:US", "Whole U.S.", "Every state and territory"), Region("pkg:west", "U.S. West Region (13 States)", "AK, AZ, CA")],
                     [Region("s:CA", "California"), Region("s:OR", "Oregon")], [Region("c:CA", "Canada")]]
    self.picked = {"pkg:west"}
    self.state = Progress(False, 0, 0, "")
    self.parked = True
    self.online = True
    self.calls = []

  def tick(self):
    pass

  def refresh(self):
    pass

  def regions(self, tab):
    return self._regions[tab]

  def selected(self, token):
    return token in self.picked

  def set_selected(self, token, on):
    (self.picked.add if on else self.picked.discard)(token)

  def selection_summary(self):
    return f"{len(self.picked)} region{'s' if len(self.picked) != 1 else ''} selected" if self.picked else "No regions selected"

  def has_selection(self):
    return bool(self.picked)

  def downloaded(self):
    return True

  def progress(self):
    return self.state

  def cancelling(self):
    return False

  def checks(self):
    return [("Parked", self.parked), ("Online", self.online)]

  def download(self):
    self.calls.append("download")
    from openpilot.selfdrive.ui.tandem.settings.maps import RegionProgress
    regions = tuple(RegionProgress(f"us_state.{code}", done, total) for code, done, total in (
      ("AK", 4, 4), ("AZ", 3, 3), ("CA", 6, 6), ("CO", 3, 3), ("HI", 1, 1), ("ID", 3, 5), ("MT", 0, 4), ("NV", 0, 3), ("NM", 0, 3),
      ("OR", 0, 4), ("UT", 0, 3), ("WA", 0, 5), ("WY", 0, 6)))
    self.state = self._Progress(True, 21, 50, "California", regions)

  def cancel(self):
    self.calls.append("cancel")

  def remove(self):
    self.calls.append("remove")


class FakeBootLogos:
  def __init__(self):
    self.installs = 0

  def install_tandem(self):
    self.installs += 1

  def image(self, slug):
    return None

  def installed(self):
    return [("aurora_logo", "Aurora Logo"), ("pixel_logo", "Pixel Logo"), ("stock", "Stock")]



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


class FakeDeveloperSource:
  def __init__(self, offroad=True, engaged=False, alpha=True):
    self._offroad, self._engaged, self._alpha = offroad, engaged, alpha
    self.ui_debug: list[bool] = []
    self.fetched: list[str] = []
    self.pending = None
    self.cleared = 0

  def offroad(self):
    return self._offroad

  def engaged(self):
    return self._engaged

  def alpha_available(self):
    return self._alpha

  def set_ui_debug(self, on):
    self.ui_debug.append(on)

  def fetch_keys(self, username, done):
    self.fetched.append(username)
    self.pending = done

  def clear_keys(self):
    self.cleared += 1

  def tick(self):
    pass


class FakeCarExtras:
  """A Toyota without stop and go: auto-unlock, the lock timer and the SNG hack, plus the stock-cruise switch."""

  def __init__(self):
    from openpilot.selfdrive.ui.tandem.settings.vehicle import CarExtra
    self._list = [CarExtra("DisableOpenpilotLongitudinal", "Use the car's own cruise control", "Turns off openpilot's gas and brake control",
                           warn="openpilot stops controlling gas and brakes."),
                  CarExtra("UnlockDoors", "Auto-unlock doors", "Unlocks when you shift into park"),
                  CarExtra("LockDoorsTimer", "Lock doors after", "Locks the doors a while after you turn off the car", "timer"),
                  CarExtra("SNGHack", "Stop and go", "Keep going after a stop on Toyotas that don't do it themselves"),
                  CarExtra("IgnoreIgnitionLine", "CAN ignition only", "Start only from the car's CAN ignition", "flash")]
    self.values = {"UnlockDoors": True}
    self.seconds = 30
    self.calls = []

  def extras(self):
    return self._list

  def value(self, key):
    return self.values.get(key, False)

  def toggle(self, key):
    self.calls.append(("toggle", key))
    self.values[key] = not self.values.get(key, False)

  def flash(self, key):
    self.calls.append(("flash", key))

  def timer(self):
    return self.seconds

  def set_timer(self, seconds):
    self.seconds = seconds
