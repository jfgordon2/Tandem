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
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

TABS = [N_("Driving"), N_("Device"), N_("Connections"), N_("Software")]
PAGES = {"speed_steering": N_("Speed & Steering"), "display": N_("Display"), "tuner": N_("Tuner Mode"), "alerts": N_("Alerts"), "model": N_("Driving Model"),
         "vehicle": N_("Vehicle"), "assistance": N_("Assistance")}
SECTIONS = {"speed_steering": [N_("Everyday"), N_("Vehicle Profile"), N_("Weather"), N_("Navigation")],
            "display": [N_("Driving Screen"), N_("Theme & Startup"), N_("Map")],
            "tuner": [N_("Steering"), N_("Gas & Brake"), N_("Following & Stops"), N_("Bundle Overrides")],
            1: [N_("This Device"), N_("General"), N_("Backups"), N_("Storage & Data"), N_("Report a Problem"), N_("Developer")],
            2: [N_("Wi-Fi"), N_("Cellular"), N_("Bluetooth Remote"), N_("Car Audio & Devices")]}
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
  _place(N_("Speed & Steering"), N_("Driving style, speed limits, lane changes and steering"), 0, S),
  Entry(N_("Driving Style"), N_("Sets following gap, acceleration and braking together"), 0, S, 0, "personality relaxed standard sport following distance"),
  Entry(N_("Speed Limits"), N_("Match sets cruise to the posted limit"), 0, S, 0, "slc speed limit controller"),
  Entry(N_("Offset"), N_("Added to every matched limit"), 0, S, 0, "speed limit offset"),
  Entry(N_("Higher limits"), N_("When a posted limit goes up"), 0, S, 0, "confirm speed limit ask raise"),
  Entry(N_("Lower limits"), N_("When a posted limit goes down"), 0, S, 0, "confirm speed limit ask lower slow"),
  Entry(N_("MAX follows limits"), N_("Each new limit sets MAX, so it slows promptly for lower ones"), 0, S, 0,
        "set speed cruise max follow speed limit lower slow down"),
  Entry(N_("Lane Changes"), N_("Nudge or Auto"), 0, S, 0, "nudgeless lane change blinker signal"),
  Entry(N_("Smart Slowdowns"), N_("Slows for curves, stop lights and stopped traffic on its own"), 0, S, 0, "conditional experimental curve"),
  Entry(N_("Always-On Steering"), N_("Keeps steering with cruise off"), 0, S, 0, "always on lateral aol"),
  _place(N_("Vehicle Profile"), N_("Car, SUV, truck or towing"), 0, S, 1, "towing trailer"),
  Entry(N_("Trailer Load"), N_("Weight of a loaded trailer"), 0, S, 1, "towing"),
  _place(N_("Weather"), N_("Drives more cautiously in bad conditions, using local weather"), 0, S, 2, "rain snow fog presets"),
  Entry(N_("Weather heads-up"), N_("Warns before rain, snow or storms start, and says when they should stop"), 0, S, 2,
        "forecast rain snow storm thunderstorm ice warning upcoming"),
  _place(N_("Navigation"), N_("Home, Work and favorites; slows for turns on a route"), 0, S, 3, "route destination"),
  Entry(N_("Other favorites"), N_("Saved places for Where to?"), 0, S, 3, "destinations"),
  Entry(N_("End Route When Parked"), N_("Clears the destination when you turn off the car"), 0, S, 3),
  Entry(N_("Mapbox Keys"), N_("Needed for place search and routes"), 0, S, 3, "mapbox key token api secret search routing navigation"),
  Entry(N_("Offline Maps"), N_("Speed limits and routing without a connection"), 0, S, 3, "download map regions"),
  # Driving › Display
  _place(N_("Display"), N_("The driving screen, theme and startup, and the map"), 0, D),
  Entry(N_("Camera View"), N_("Wide shows more of the road at low speed"), 0, D, 0),
  Entry(N_("Driver Camera in Reverse"), N_("Shows the inside camera while backing up"), 0, D, 0),
  Entry(N_("Driving Style Banner"), N_("Shows the current style when it changes"), 0, D, 0),
  Entry(N_("Compass"), N_("Heading beside the street name, like NE"), 0, D, 0, "heading direction north"),
  Entry(N_("Blind Spot Highlights"), N_("Colors the screen edge and lane when a car is beside you"), 0, D, 0, "bsm"),
  Entry(N_("Lead Car Tag"), N_("Numbers above the car ahead. Off keeps only the bar under it"), 0, D, 0, "gap distance lead numbers"),
  Entry(N_("Developer View"), N_("Side panel with system and controls data"), 0, D, 0, "developer ui metrics"),
  Entry(N_("Lead Insights"), N_("Distance, gap and speed of the car ahead, plus radar points"), 0, D, 0, "lead metrics radar"),
  Entry(N_("Path Style"), N_("Color, width and edges as one preset"), 0, D, 1, "rainbow path lane lines"),
  Entry(N_("Turn Signal"), N_("Chevrons by the speed, or a whimsical animation"), 0, D, 1, "frog cat ball blinker animation"),
  Entry(N_("Boot Logo"), N_("Shown while the device starts up"), 0, D, 1),
  Entry(N_("Startup Message"), N_("The banner when you start the car"), 0, D, 1),
  Entry(N_("Turn-by-Turn on Screen"), N_("Next turn, arrival time and distance while navigating"), 0, D, 2, "navigation"),
  Entry(N_("Speed Limit Sign"), N_("US style, or the round Vienna style used in most other countries"), 0, D, 2, "vienna"),
  Entry(N_("Offline Maps"), N_("Speed limits and routing without a connection"), 0, D, 2, "download map regions"),
  # Driving › Alerts, Driving Model, Vehicle, Assistance
  _place(N_("Alerts"), N_("Volume and the optional chimes"), 0, "alerts", words="sound"),
  _place(N_("Volume"), N_("One volume for everything, or each group on its own"), 0, "alerts", words="loud quiet sound"),
  Entry(N_("Green Light"), N_("When the light turns green and you are stopped"), 0, "alerts", words="chime"),
  Entry(N_("Lead Departure"), N_("When the car ahead pulls away"), 0, "alerts", words="chime"),
  Entry(N_("Speed Limit Change"), N_("When the posted limit changes"), 0, "alerts", words="chime"),
  Entry(N_("Loud Blind Spot"), N_("Signalling into an occupied lane, even when paused"), 0, "alerts", words="chime"),
  Entry(N_("Weather heads-up"), N_("Once, when rain, snow or storms are coming"), 0, "alerts", words="chime forecast rain snow"),
  _place(N_("Driving Model"), N_("The model that drives, and downloading others"), 0, "model", words="download"),
  Entry(N_("Use recommended"), N_("The recommended driving model"), 0, "model"),
  _place(N_("Vehicle"), N_("Your car, its steering wheel buttons and car-specific options"), 0, "vehicle", words="car model fingerprint wrong car"),
  _place(N_("Steering Wheel Buttons"), N_("What the car's own buttons do while driving"), 0, "vehicle", words="lkas distance button"),
  Entry(N_("Auto-Lock Doors"), N_("Locks when you shift out of park"), 0, "vehicle"),
  Entry(N_("More for your car"), N_("Features specific to your make and model"), 0, "vehicle"),
  _place(N_("Assistance"), N_("openpilot's core switches and driver monitoring"), 0, "assistance"),
  Entry("openpilot", N_("Adaptive cruise and lane keeping"), 0, "assistance", words="enable"),
  Entry(N_("Disengage on Gas Pedal"), N_("Pressing the accelerator turns openpilot off"), 0, "assistance", words="accelerator"),
  Entry(N_("Lane Departure Warnings"), N_("Alerts when you drift over a lane line without signaling"), 0, "assistance", words="ldw"),
  Entry(N_("Safe Mode"), N_("Stock tuning, the default model and Relaxed"), 0, "assistance"),
  Entry(N_("Always-On Driver Monitoring"), N_("Watches for distraction even when openpilot is off"), 0, "assistance", words="dm"),
  Entry(N_("Driver Camera"), N_("Check that it can see your face"), 0, "assistance", words="preview dm"),
  Entry(N_("Driver Monitoring"), N_("Forget which side of the car the driver sits on"), 0, "assistance", words="reset dm"),
  Entry(N_("Sentry Mode"), N_("Pictures in Galaxy if the parked car is bumped"), 0, "assistance", words="security parked camera bump theft"),
  Entry(N_("Sensitivity"), N_("High notices smaller bumps"), 0, "assistance", words="sentry motion"),
  _place(N_("Tuner Mode"), N_("Fine-tuning screens for gas, brake, steering and following"), 0, words="tuning"),
  # Driving › Tuner Mode
  _place(N_("Steering"), N_("Learned steering values and the controller"), 0, TN, 0),
  Entry(N_("Steering Delay"), N_("Time from command to wheel response"), 0, TN, 0),
  Entry(N_("Friction"), N_("Extra torque near center"), 0, TN, 0),
  Entry(N_("Lateral Acceleration"), N_("Torque to cornering scaling"), 0, TN, 0),
  Entry(N_("Kp Factor"), N_("Correction strength"), 0, TN, 0),
  Entry(N_("Steering controller"), N_("Vehicle default, neural feedforward or torque"), 0, TN, 0,
        "upstream stock factory nnff auto lite torque"),
  _place(N_("Gas & Brake"), N_("Acceleration and braking profiles and values"), 0, TN, 1, "gas brake"),
  Entry(N_("Acceleration Profile"), N_("How quickly the car speeds up"), 0, TN, 1),
  Entry(N_("Braking Profile"), N_("How early and firmly it slows down"), 0, TN, 1),
  Entry(N_("Maximum Acceleration"), N_("The hardest openpilot will accelerate"), 0, TN, 1),
  Entry(N_("Start Acceleration"), N_("How firmly the car pulls away from a stop"), 0, TN, 1),
  Entry(N_("Stop Acceleration"), N_("Braking held while stopped"), 0, TN, 1),
  Entry(N_("Stopping Rate"), N_("How quickly braking builds into a stop"), 0, TN, 1),
  Entry(N_("Actuator Delay"), N_("Time from command to gas or brake response"), 0, TN, 1),
  _place(N_("Following & Stops"), N_("Following gaps and how the car stops"), 0, TN, 2),
  _place(N_("Following Gaps"), N_("Relaxed, Standard, Aggressive and Traffic"), 0, TN, 2, "distance follow"),
  Entry(N_("Lead Detection Sensitivity"), N_("Lower notices cars ahead sooner"), 0, TN, 2),
  Entry(N_("Stopped Distance"), N_("Extra room left behind a stopped car"), 0, TN, 2),
  Entry(N_("Use Radar for Take-Offs"), N_("Starts moving as soon as the car ahead pulls away"), 0, TN, 2),
  Entry(N_("Force Stops at Lights"), N_("Comes to a full stop for red lights the model detects"), 0, TN, 2),
  Entry(N_("Cruise Button Step"), N_("How far one press of + or − moves the set speed"), 0, TN, 2),
  _place(N_("Bundle Overrides"), N_("Change one option that Developer View or Lead Insights sets"), 0, TN, 3),
  _place(N_("Bar Metrics"), N_("Up to five values in Developer View's strip"), 0, TN, 3, "developer strip"),
  # Device
  _place(N_("This Device"), N_("Pairing, remote access, calibration, restart and power"), 1, section=0),
  Entry(N_("Phone App"), N_("comma connect: see drives and change settings on your phone"), 1, section=0, words="pair"),
  Entry(N_("Remote Access"), N_("Galaxy: reach this device from a web browser"), 1, section=0),
  Entry(N_("Camera Calibration"), N_("How the device is mounted"), 1, section=0, words="recalibrate"),
  Entry(N_("How It Works"), N_("Rules, features and limits"), 1, section=0, words="training guide"),
  Entry(N_("Regulatory"), N_("Regulatory information"), 1, section=0),
  Entry(N_("Device ID and Serial"), N_("This device's IDs"), 1, section=0, words="dongle"),
  Entry(N_("IMEI"), N_("The cellular modem's ID"), 1, section=0, words="imei modem cellular sim lte"),
  _place(N_("Restart"), N_("Restart the device"), 1, section=0, words="reboot"),
  _place(N_("Power Off"), N_("Turn the device off until the car starts"), 1, section=0, words="shut down"),
  _place(N_("General"), N_("Units, language, brightness and standby"), 1, section=1),
  Entry(N_("Units"), N_("Speed and distance everywhere"), 1, section=1, words="metric imperial mph km"),
  Entry(N_("Temperature"), N_("For the weather forecast"), 1, section=1, words="fahrenheit celsius degrees weather units"),
  Entry(N_("Language"), N_("Menus and alerts"), 1, section=1),
  Entry(N_("Screen Brightness"), N_("Auto follows ambient light, day and night"), 1, section=1, words="dim bright"),
  Entry(N_("Standby"), N_("Screen sleeps while driving, wakes for alerts"), 1, section=1, words="screen off"),
  _place(N_("Backups"), N_("Snapshots of your settings"), 1, section=2, words="restore"),
  _place(N_("Storage & Data"), N_("What's using space, and recording and uploads"), 1, section=3, words="space"),
  Entry(N_("Recorded Drives"), N_("Oldest drives are removed when space runs low"), 1, section=3, words="delete"),
  Entry(N_("Offline Maps"), N_("Delete downloaded map data"), 1, section=3),
  Entry(N_("Unused Models"), N_("Downloaded models that aren't in use"), 1, section=3),
  Entry(N_("Record Driver Camera"), N_("Saved and uploaded with your drives"), 1, section=3),
  Entry(N_("Record Microphone"), N_("Cabin audio in your drive recordings"), 1, section=3, words="audio"),
  Entry(N_("Uploads"), N_("Drive logs and video for debugging"), 1, section=3),
  _place(N_("Report a Problem"), N_("Send what happened to the developers"), 1, section=4, words="bug discord"),
  _place(N_("Developer"), N_("ADB, SSH and debug modes"), 1, section=5),
  Entry(N_("CAN test recorder"), N_("Record traffic and mark manual lock/unlock actions"), 1, section=5, words="diagnostic log lock unlock test"),
  Entry(N_("ADB"), N_("Connect over USB or the network"), 1, section=5),
  Entry(N_("SSH"), N_("Remote shell access"), 1, section=5),
  Entry(N_("SSH Keys"), N_("Adds every public key in a GitHub account"), 1, section=5, words="github"),
  Entry(N_("Joystick Debug Mode"), N_("Drive openpilot's controls from a joystick"), 1, section=5),
  Entry(N_("openpilot Longitudinal (Alpha)"), N_("Turns off the car's emergency braking"), 1, section=5, words="alpha"),
  Entry(N_("UI Debug Mode"), N_("Shows touches and the frame rate"), 1, section=5),
  # Connections
  _place(N_("Wi-Fi"), N_("Networks nearby, and joining one"), 2, section=0, words="wifi network internet"),
  _place(N_("IP Address"), N_("This device's local address, beside the connected network"), 2, section=0, words="ip local ssh"),
  Entry(N_("Join a hidden network"), N_("Enter its name and password"), 2, section=0, words="wifi"),
  _place(N_("Cellular"), N_("Hotspot, data use, roaming and APN"), 2, section=1, words="lte sim"),
  Entry(N_("Hotspot"), N_("Share this device's connection"), 2, section=1, words="tether"),
  Entry(N_("Hotspot name"), N_("The name phones see when joining this device"), 2, section=1, words="tether ssid rename"),
  Entry(N_("Hotspot Password"), N_("For phones joining this device's hotspot"), 2, section=1, words="tether"),
  Entry(N_("Save Data"), N_("No large uploads on cellular or phone hotspots"), 2, section=1, words="metered"),
  Entry(N_("Roaming, APN and IP address"), N_("Roaming, APN and the device's IP address"), 2, section=1, words="ip"),
  _place(N_("Bluetooth Remote"), N_("A wheel remote's buttons and what they do"), 2, section=2, words="wheel buttons bluetooth"),
  _place(N_("Car Audio & Devices"), N_("Car audio for alerts, and pairing devices"), 2, section=3, words="bluetooth speaker pair"),
  # Software
  _place(N_("Software"), N_("Updates and the release notes"), 3, words="version update"),
  Entry(N_("Automatic Updates"), N_("Download while parked, install when you turn off the car"), 3),
  Entry(N_("Release Channel"), N_("The branch to download updates from"), 3, words="branch"),
  Entry(N_("Reset Settings"), N_("Back to the Essentials defaults"), 3, words="defaults"),
  _place(N_("Uninstall"), N_("Remove this software from the device"), 3),
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
    self._keys = KeyPad(self._show_all, N_("Search"), MIN_QUERY,
                        voice_hint=N_("Say a setting, like speed limit. Tap the mic when you're done."))
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
                             for e in results] or [Text(t_("No settings match “{}”", self._keys.text))]
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
      hint = (t_("No settings match “{}”", self._keys.text) if len(self._keys.text.strip()) >= MIN_QUERY
              else N_("Type a setting's name or what it does, like brightness or lane changes"))
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
    return draw.text_width(N_("Search settings"), T.font_px(17), T.FONT_SEMIBOLD) + T.px(18 + 20 + 10 + 18), T.px(46)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_2, T.px(14))
    draw.stroke(rect, T.TRACK, T.px(14), T.px(1))
    if self.is_pressed:
      draw.pressed(rect, T.px(14))
    icon, words = row(inset(rect, left=T.px(18), right=T.px(18)), [T.px(20), FILL], T.px(10))
    draw.icon(icon, "search", T.TEXT_SECONDARY, T.px(20))
    draw.text(words, N_("Search settings"), T.font_px(17), T.TEXT_SECONDARY, T.FONT_SEMIBOLD)
