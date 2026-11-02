"""Settings search (design/searchhub.html, design/search.html): every setting by name, what it does and where it lives.

The index is declared here; tests/test_settings.py opens every place with stand-in data and checks that each entry's row is
really there and that every row on those screens is indexed, so the two can't drift apart. Picking a result opens its page
and section (window.open_at). Rows behind Tuner Mode are found only while Tuner Mode is on, as they're only shown then.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.keyboard import KeyPad
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, place, row
from openpilot.selfdrive.ui.tandem.blocks import Icon
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SettingRow, Text

TABS = ["Driving", "Device", "Connections", "Software"]
PAGES = {"speed_steering": "Speed & Steering", "display": "Display", "tuner": "Tuner Mode", "alerts": "Alerts", "model": "Driving Model",
         "vehicle": "Vehicle", "assistance": "Assistance"}
SECTIONS = {"speed_steering": ["Everyday", "Vehicle Profile", "Weather", "Navigation"],
            "display": ["Driving Screen", "Theme & Startup", "Map"],
            "tuner": ["Steering", "Gas & Brake", "Following & Stops", "Bundle Overrides"],
            1: ["This Device", "General", "Backups", "Storage & Data", "Report a Problem", "Developer"],
            2: ["Wi-Fi", "Cellular", "Bluetooth Remote", "Car Audio & Devices"]}
MIN_QUERY = 2
CARDS = 4   # results shown above the keyboard; Search lists them all


@dataclass(frozen=True)
class Entry:
  name: str
  detail: str
  tab: int
  page: str | None = None
  section: int | None = None
  words: str = ""        # other words people use for it
  row: bool = True       # a row on its screen (checked by the tests); False for a section, page or card

  @property
  def tuner(self) -> bool:
    return self.page == "tuner" or (self.tab == 1 and self.section == 5)

  @property
  def where(self) -> str:
    parts = [TABS[self.tab]]
    if self.page is not None:
      parts.append(PAGES[self.page])
    if self.section is not None:
      parts.append(SECTIONS[self.page if self.page is not None else self.tab][self.section])
    if not self.row and len(parts) > 1 and parts[-1] == self.name:
      parts.pop()   # a section or page is where it is, not inside itself
    return " › ".join(parts)


def _place(name: str, detail: str, tab: int, page: str | None = None, section: int | None = None, words: str = "") -> Entry:
  return Entry(name, detail, tab, page, section, words, row=False)


S, D, TN = "speed_steering", "display", "tuner"
ENTRIES: list[Entry] = [
  # Driving › Speed & Steering
  _place("Speed & Steering", "Driving style, speed limits, lane changes and steering", 0, S),
  Entry("Driving Style", "Sets following gap, acceleration and braking together", 0, S, 0, "personality relaxed standard sport following distance"),
  Entry("Speed Limits", "Match sets cruise to the posted limit", 0, S, 0, "slc speed limit controller"),
  Entry("Offset", "Added to every matched limit", 0, S, 0, "speed limit offset"),
  Entry("Higher limits", "When a posted limit goes up", 0, S, 0, "confirm speed limit ask raise"),
  Entry("Lower limits", "When a posted limit goes down", 0, S, 0, "confirm speed limit ask lower slow"),
  Entry("MAX follows limits", "Each new limit sets MAX, so it slows promptly for lower ones", 0, S, 0,
        "set speed cruise max follow speed limit lower slow down"),
  Entry("Lane Changes", "Nudge or Auto", 0, S, 0, "nudgeless lane change blinker signal"),
  Entry("Smart Slowdowns", "Slows for curves, stop lights and stopped traffic on its own", 0, S, 0, "conditional experimental curve"),
  Entry("Always-On Steering", "Keeps steering with cruise off", 0, S, 0, "always on lateral aol"),
  _place("Vehicle Profile", "Car, SUV, truck or towing", 0, S, 1, "towing trailer"),
  Entry("Trailer Load", "Weight of a loaded trailer", 0, S, 1, "towing"),
  _place("Weather", "Drives more cautiously in bad conditions, using local weather", 0, S, 2, "rain snow fog presets"),
  Entry("Weather heads-up", "Warns before rain, snow or storms start, and says when they should stop", 0, S, 2,
        "forecast rain snow storm thunderstorm ice warning upcoming"),
  _place("Navigation", "Home, Work and favorites; slows for turns on a route", 0, S, 3, "route destination"),
  Entry("Other favorites", "Saved places for Where to?", 0, S, 3, "destinations"),
  Entry("End Route When Parked", "Clears the destination when you turn off the car", 0, S, 3),
  Entry("Mapbox Keys", "Needed for place search and routes", 0, S, 3, "mapbox key token api secret search routing navigation"),
  Entry("Offline Maps", "Speed limits and routing without a connection", 0, S, 3, "download map regions"),
  # Driving › Display
  _place("Display", "The driving screen, theme and startup, and the map", 0, D),
  Entry("Camera View", "Wide shows more of the road at low speed", 0, D, 0),
  Entry("Driver Camera in Reverse", "Shows the inside camera while backing up", 0, D, 0),
  Entry("Driving Style Banner", "Shows the current style when it changes", 0, D, 0),
  Entry("Compass", "Heading beside the street name, like NE", 0, D, 0, "heading direction north"),
  Entry("Blind Spot Highlights", "Colors the screen edge and lane when a car is beside you", 0, D, 0, "bsm"),
  Entry("Lead Car Tag", "Numbers above the car ahead. Off keeps only the bar under it", 0, D, 0, "gap distance lead numbers"),
  Entry("Developer View", "Side panel with system and controls data", 0, D, 0, "developer ui metrics"),
  Entry("Lead Insights", "Distance, gap and speed of the car ahead, plus radar points", 0, D, 0, "lead metrics radar"),
  Entry("Path Style", "Color, width and edges as one preset", 0, D, 1, "rainbow path lane lines"),
  Entry("Turn Signal", "Chevrons by the speed, or a whimsical animation", 0, D, 1, "frog cat ball blinker animation"),
  Entry("Boot Logo", "Shown while the device starts up", 0, D, 1),
  Entry("Startup Message", "The banner when you start the car", 0, D, 1),
  Entry("Turn-by-Turn on Screen", "Next turn, arrival time and distance while navigating", 0, D, 2, "navigation"),
  Entry("Speed Limit Sign", "US style, or the round Vienna style used in most other countries", 0, D, 2, "vienna"),
  Entry("Offline Maps", "Speed limits and routing without a connection", 0, D, 2, "download map regions"),
  # Driving › Alerts, Driving Model, Vehicle, Assistance
  _place("Alerts", "Volume and the optional chimes", 0, "alerts", words="sound"),
  _place("Volume", "One volume for everything, or each group on its own", 0, "alerts", words="loud quiet sound"),
  Entry("Green Light", "When the light turns green and you are stopped", 0, "alerts", words="chime"),
  Entry("Lead Departure", "When the car ahead pulls away", 0, "alerts", words="chime"),
  Entry("Speed Limit Change", "When the posted limit changes", 0, "alerts", words="chime"),
  Entry("Loud Blind Spot", "Signalling into an occupied lane, even when paused", 0, "alerts", words="chime"),
  Entry("Weather heads-up", "Once, when rain, snow or storms are coming", 0, "alerts", words="chime forecast rain snow"),
  _place("Driving Model", "The model that drives, and downloading others", 0, "model", words="download"),
  Entry("Use recommended", "The recommended driving model", 0, "model"),
  _place("Vehicle", "Your car, its steering wheel buttons and car-specific options", 0, "vehicle", words="car model fingerprint wrong car"),
  _place("Steering Wheel Buttons", "What the car's own buttons do while driving", 0, "vehicle", words="lkas distance button"),
  Entry("Auto-Lock Doors", "Locks when you shift out of park", 0, "vehicle"),
  Entry("More for your car", "Features specific to your make and model", 0, "vehicle"),
  _place("Assistance", "openpilot's core switches and driver monitoring", 0, "assistance"),
  Entry("openpilot", "Adaptive cruise and lane keeping", 0, "assistance", words="enable"),
  Entry("Disengage on Gas Pedal", "Pressing the accelerator turns openpilot off", 0, "assistance", words="accelerator"),
  Entry("Lane Departure Warnings", "Alerts when you drift over a lane line without signaling", 0, "assistance", words="ldw"),
  Entry("Safe Mode", "Stock tuning, the default model and Relaxed", 0, "assistance"),
  Entry("Always-On Driver Monitoring", "Watches for distraction even when openpilot is off", 0, "assistance", words="dm"),
  Entry("Driver Camera", "Check that it can see your face", 0, "assistance", words="preview dm"),
  Entry("Driver Monitoring", "Forget which side of the car the driver sits on", 0, "assistance", words="reset dm"),
  _place("Tuner Mode", "Fine-tuning screens for gas, brake, steering and following", 0, words="tuning"),
  # Driving › Tuner Mode
  _place("Steering", "Learned steering values and the controller", 0, TN, 0),
  Entry("Steering Delay", "Time from command to wheel response", 0, TN, 0),
  Entry("Friction", "Extra torque near center", 0, TN, 0),
  Entry("Lateral Acceleration", "Torque to cornering scaling", 0, TN, 0),
  Entry("Kp Factor", "Correction strength", 0, TN, 0),
  Entry("Steering Controller", "Torque, or NNFF when your car has a model", 0, TN, 0, "nnff torque"),
  _place("Gas & Brake", "Acceleration and braking profiles and values", 0, TN, 1, "gas brake"),
  Entry("Acceleration Profile", "How quickly the car speeds up", 0, TN, 1),
  Entry("Braking Profile", "How early and firmly it slows down", 0, TN, 1),
  Entry("Maximum Acceleration", "The hardest openpilot will accelerate", 0, TN, 1),
  Entry("Start Acceleration", "How firmly the car pulls away from a stop", 0, TN, 1),
  Entry("Stop Acceleration", "Braking held while stopped", 0, TN, 1),
  Entry("Stopping Rate", "How quickly braking builds into a stop", 0, TN, 1),
  Entry("Actuator Delay", "Time from command to gas or brake response", 0, TN, 1),
  _place("Following & Stops", "Following gaps and how the car stops", 0, TN, 2),
  _place("Following Gaps", "Relaxed, Standard, Aggressive and Traffic", 0, TN, 2, "distance follow"),
  Entry("Lead Detection Sensitivity", "Lower notices cars ahead sooner", 0, TN, 2),
  Entry("Stopped Distance", "Extra room left behind a stopped car", 0, TN, 2),
  Entry("Use Radar for Take-Offs", "Starts moving as soon as the car ahead pulls away", 0, TN, 2),
  Entry("Force Stops at Lights", "Comes to a full stop for red lights the model detects", 0, TN, 2),
  Entry("Cruise Button Step", "How far one press of + or − moves the set speed", 0, TN, 2),
  _place("Bundle Overrides", "Change one option that Developer View or Lead Insights sets", 0, TN, 3),
  _place("Bar Metrics", "Up to five values in Developer View's strip", 0, TN, 3, "developer strip"),
  # Device
  _place("This Device", "Pairing, remote access, calibration, restart and power", 1, section=0),
  Entry("Phone App", "comma connect: see drives and change settings on your phone", 1, section=0, words="pair"),
  Entry("Remote Access", "Galaxy: reach this device from a web browser", 1, section=0),
  Entry("Camera Calibration", "How the device is mounted", 1, section=0, words="recalibrate"),
  Entry("How It Works", "Rules, features and limits", 1, section=0, words="training guide"),
  Entry("Regulatory", "Regulatory information", 1, section=0),
  Entry("Device ID and Serial", "This device's IDs", 1, section=0, words="dongle"),
  Entry("IMEI", "The cellular modem's ID", 1, section=0, words="imei modem cellular sim lte"),
  _place("Restart", "Restart the device", 1, section=0, words="reboot"),
  _place("Power Off", "Turn the device off until the car starts", 1, section=0, words="shut down"),
  _place("General", "Units, language, brightness and standby", 1, section=1),
  Entry("Units", "Speed and distance everywhere", 1, section=1, words="metric imperial mph km"),
  Entry("Temperature", "For the weather forecast", 1, section=1, words="fahrenheit celsius degrees weather units"),
  Entry("Language", "Menus and alerts", 1, section=1),
  Entry("Screen Brightness", "Auto follows ambient light, day and night", 1, section=1, words="dim bright"),
  Entry("Standby", "Screen sleeps while driving, wakes for alerts", 1, section=1, words="screen off"),
  _place("Backups", "Snapshots of your settings", 1, section=2, words="restore"),
  _place("Storage & Data", "What's using space, and recording and uploads", 1, section=3, words="space"),
  Entry("Recorded Drives", "Oldest drives are removed when space runs low", 1, section=3, words="delete"),
  Entry("Offline Maps", "Delete downloaded map data", 1, section=3),
  Entry("Unused Models", "Downloaded models that aren't in use", 1, section=3),
  Entry("Record Driver Camera", "Saved and uploaded with your drives", 1, section=3),
  Entry("Record Microphone", "Cabin audio in your drive recordings", 1, section=3, words="audio"),
  Entry("Uploads", "Drive logs and video for debugging", 1, section=3),
  _place("Report a Problem", "Send what happened to the developers", 1, section=4, words="bug discord"),
  _place("Developer", "ADB, SSH and debug modes", 1, section=5),
  Entry("ADB", "Connect over USB or the network", 1, section=5),
  Entry("SSH", "Remote shell access", 1, section=5),
  Entry("SSH Keys", "Adds every public key in a GitHub account", 1, section=5, words="github"),
  Entry("Joystick Debug Mode", "Drive openpilot's controls from a joystick", 1, section=5),
  Entry("openpilot Longitudinal (Alpha)", "Turns off the car's emergency braking", 1, section=5, words="alpha"),
  Entry("UI Debug Mode", "Shows touches and the frame rate", 1, section=5),
  # Connections
  _place("Wi-Fi", "Networks nearby, and joining one", 2, section=0, words="wifi network internet"),
  _place("IP Address", "This device's local address, beside the connected network", 2, section=0, words="ip local ssh"),
  Entry("Join a hidden network", "Enter its name and password", 2, section=0, words="wifi"),
  _place("Cellular", "Hotspot, data use, roaming and APN", 2, section=1, words="lte sim"),
  Entry("Hotspot", "Share this device's connection", 2, section=1, words="tether"),
  Entry("Hotspot Password", "For phones joining this device's hotspot", 2, section=1, words="tether"),
  Entry("Save Data", "No large uploads on cellular or phone hotspots", 2, section=1, words="metered"),
  Entry("Roaming, APN and IP address", "Roaming, APN and the device's IP address", 2, section=1, words="ip"),
  _place("Bluetooth Remote", "A wheel remote's buttons and what they do", 2, section=2, words="wheel buttons bluetooth"),
  _place("Car Audio & Devices", "Car audio for alerts, and pairing devices", 2, section=3, words="bluetooth speaker pair"),
  # Software
  _place("Software", "Updates and the release notes", 3, words="version update"),
  Entry("Automatic Updates", "Download while parked, install when you turn off the car", 3),
  Entry("Release Channel", "The branch to download updates from", 3, words="branch"),
  Entry("Reset Settings", "Back to the Essentials defaults", 3, words="defaults"),
  _place("Uninstall", "Remove this software from the device", 3),
]


def search(query: str, tuner: bool) -> list[Entry]:
  """Entries matching every word of the query, best first: the name starting with it, then in the name, then anywhere."""
  words = query.lower().split()
  if len(query.strip()) < MIN_QUERY:
    return []
  scored = []
  for i, e in enumerate(ENTRIES):
    if e.tuner and not tuner:
      continue
    name, rest = e.name.lower(), f"{e.detail} {e.where} {e.words}".lower()
    if not all(w in name or w in rest for w in words):
      continue
    rank = 0 if name.startswith(query.lower().strip()) else 1 if all(w in name for w in words) else 2
    scored.append((rank, i, e))
  return [e for _, _, e in sorted(scored, key=lambda t: t[:2])]


class ResultCard(Component):
  """One result above the keyboard: a chevron, the setting's name and where it lives."""
  grow_touch_target = False

  def __init__(self, index: int, results: Callable[[], list[Entry]], on_pick: Callable[[Entry], None]):
    super().__init__()
    self._index, self._results = index, results
    self.set_click_callback(lambda: self._pick(on_pick))

  def _pick(self, on_pick: Callable[[Entry], None]) -> None:
    results = self._results()
    if self._index < len(results):
      on_pick(results[self._index])

  def _render(self, rect: rl.Rectangle):
    results = self._results()
    if self._index >= len(results):
      return
    entry = results[self._index]
    draw.fill(rect, T.SURFACE_2, T.px(14))
    if self.is_pressed:
      draw.pressed(rect, T.px(14))
    icon, words = row(inset(rect, x=T.px(16)), [T.px(18), FILL], T.px(12))
    draw.chevron(icon, T.ACCENT_TEXT, T.px(18))
    title_h, line_h = draw.line_height(T.font_px(17)), draw.line_height(T.font_px(13))
    block = place(words, words.width, title_h + line_h)
    draw.text(rl.Rectangle(block.x, block.y, block.width, title_h), draw.fit(entry.name, T.font_px(17), T.FONT_SEMIBOLD, block.width),
              T.font_px(17), T.TEXT, T.FONT_SEMIBOLD)
    draw.text(rl.Rectangle(block.x, block.y + title_h, block.width, line_h), draw.fit(entry.where, T.font_px(13), T.FONT, block.width),
              T.font_px(13), T.TEXT_TERTIARY)


class SettingsSearch(Component):
  """Full screen over settings: the field and the best results above the keyboard; Search lists every result without the
  keyboard, and tapping the field brings it back. Picking a result closes search and opens its place."""
  grow_touch_target = False

  def __init__(self, tuner: Callable[[], bool], on_pick: Callable[[Entry], None], on_close: Callable[[], None]):
    super().__init__()
    self._tuner = tuner
    self._on_pick = on_pick
    self._keys = KeyPad(self._show_all, "Search", MIN_QUERY,
                        voice_hint="Say a setting, like speed limit. Tap the mic when you're done.")
    self._typing = True
    back_glyph = lambda r, c, s: draw.chevron(r, c, T.px(26), "left")  # noqa: E731
    self._back = self._child(Button(on_click=self._back_or_close(on_close), style=ButtonStyle.NAV, height=T.px(56), width=T.px(56),
                                    radius=T.px(14), glyph=back_glyph))
    self._clear = self._child(Button(on_click=lambda: self._keys.set_text(""), style=ButtonStyle.SECONDARY, height=T.px(36),
                                     width=T.px(36), radius=T.px(18), glyph=lambda r, c, s: draw.icon(r, "close", T.TEXT_SECONDARY, T.px(16))))
    self._field = self._child(Button(on_click=self._type_again, style=ButtonStyle.GHOST, height=T.px(56)))
    self._cards = [self._child(ResultCard(i, self.results, on_pick)) for i in range(CARDS)]
    self._list: ListPanel | None = None
    self._list_key: object = None

  @property
  def text(self) -> str:
    return self._keys.text

  def type(self, text: str) -> None:
    self._keys.set_text(text)

  def results(self) -> list[Entry]:
    return search(self._keys.text, self._tuner())

  def _back_or_close(self, on_close: Callable[[], None]) -> Callable[[], None]:
    def back() -> None:
      if self._typing:
        on_close()
      else:
        self._typing = True
    return back

  def _show_all(self) -> None:
    self._typing = False

  def _type_again(self) -> None:
    self._typing = True

  def _results_list(self) -> ListPanel:
    results = self.results()
    key = tuple(id(e) for e in results)
    if self._list is None or key != self._list_key:
      items: list[Widget] = [SettingRow(e.name, e.where, on_click=lambda e=e: self._on_pick(e), leading=Icon("search"))
                             for e in results] or [Text(f"No settings match “{self._keys.text}”")]
      self._list = self._child(ListPanel(items, header_divider=False))
      self._list_key = key
    return self._list

  def _render_field(self, rect: rl.Rectangle) -> None:
    back, field = row(rect, [T.px(56), FILL], T.px(10))
    self._back.render(back)
    draw.fill(field, T.SURFACE_2, T.px(14))
    if self._typing:
      draw.stroke(field, T.ACCENT, T.px(14), T.px(2))
    else:
      self._field.render(field)
    icon, text, clear = row(inset(field, left=T.px(16), right=T.px(10)), [T.px(20), FILL, T.px(36)], T.px(12))
    draw.icon(icon, "search", T.TEXT_TERTIARY, T.px(20))
    if self._typing:
      self._keys.render_text(text)
      if self._keys.text:
        self._clear.render(place(clear, T.px(36), T.px(36)))
    else:
      draw.text(text, self._keys.text, T.font_px(20), T.TEXT)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.BG)
    if not self._typing:
      body = inset(rect, left=T.px(16), right=T.px(16), top=T.px(14), bottom=T.px(14))
      field, panel = column(body, [T.px(56), FILL], T.px(12))
      self._render_field(field)
      self._results_list().render(panel)
      return
    if self._keys.voice_active:           # as design/voicelistening.html: the field, then voice typing below it
      top, panel = column(rect, [T.px(80), FILL])
      self._render_field(inset(top, left=T.px(16), right=T.px(16), top=T.px(14), bottom=T.px(10)))
      self._keys.render_keys(panel)
      return
    top, keys = column(rect, [T.px(206), FILL])
    body = inset(top, left=T.px(16), right=T.px(16), top=T.px(14), bottom=T.px(10))
    field, grid = column(body, [T.px(56), FILL], T.px(10))
    self._render_field(field)
    results = self.results()
    if not results:
      hint = (f"No settings match “{self._keys.text}”" if len(self._keys.text.strip()) >= MIN_QUERY
              else "Type a setting's name or what it does, like brightness or lane changes")
      draw.text(inset(grid, left=T.px(6)), hint, T.font_px(15), T.TEXT_TERTIARY)
    else:
      first, second = column(grid, [FILL, FILL], T.px(8))
      cells = row(first, [FILL, FILL], T.px(8)) + row(second, [FILL, FILL], T.px(8))
      for card, cell in zip(self._cards, cells, strict=True):
        card.render(cell)
    self._keys.render_keys(keys)


class SearchButton(Component):
  """The hub's way into search: a quiet field-like button, top right."""
  grow_touch_target = False

  def __init__(self, on_click: Callable[[], None]):
    super().__init__()
    self.set_click_callback(on_click)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return draw.text_width("Search settings", T.font_px(17), T.FONT_SEMIBOLD) + T.px(18 + 20 + 10 + 18), T.px(46)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_2, T.px(14))
    draw.stroke(rect, T.TRACK, T.px(14), T.px(1))
    if self.is_pressed:
      draw.pressed(rect, T.px(14))
    icon, words = row(inset(rect, left=T.px(18), right=T.px(18)), [T.px(20), FILL], T.px(10))
    draw.icon(icon, "search", T.TEXT_SECONDARY, T.px(20))
    draw.text(words, "Search settings", T.font_px(17), T.TEXT_SECONDARY, T.FONT_SEMIBOLD)
