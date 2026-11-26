"""Connections › Android Auto (design/connections-androidauto.html, androidauto-qr.html): StarPilot's StarPort, which shows
StarPilot on the car's own Android Auto screen, with its switch, where setup stands, and a code that opens its setup in
Galaxy.

StarPilot decides what's true and sets it up: StarPort's switch is its StarPortEnabled; the app (Google's Android Auto
package, whose certificate cars ask for) is added, checked and kept in Galaxy; the car and connection are StarPort's saved
config, and its service reports what it's doing while it runs. Adding the app needs a file upload, so setup stays in
Galaxy (its #/starport page), as on StarPilot's own screens. Reads run on a worker thread while the page is open.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Switch
from openpilot.selfdrive.ui.tandem.i18n import N_, t_, tn_
from openpilot.selfdrive.ui.tandem.layout import Align, inset
from openpilot.selfdrive.ui.tandem.overlays import Dialog, DialogResult, Sheet
from openpilot.selfdrive.ui.tandem.rows import ListPanel, Padded, SectionHeader, SettingRow
from openpilot.system.ui.widgets import Widget

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import BluetoothDevices
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow

REFRESH_S = 2.0
GALAXY_PAGE = "#/starport"   # Galaxy's StarPort setup (starpilot/galaxy/web/js/app.js)
CAR_TYPES = {"builtin": N_("Built-in wireless"), "adapter": N_("Wireless adapter"), "usb": N_("USB cable"), "app": N_("Tablet app")}


@dataclass(frozen=True)
class StarPortStatus:
  """What StarPilot says about StarPort: whether this build has it, its switch, the app, the car and what it's doing."""
  supported: bool = False       # StarPort's display and encoder are in this build, and the GPU is there
  enabled: bool = False         # StarPortEnabled
  app: bool = False             # the Android Auto app's certificate is added and valid
  app_days: int | None = None   # days until it expires
  car_type: str = ""            # builtin, adapter, usb or app, once a car or connection is chosen
  car: str = ""                 # the paired car's name
  state: str = ""               # StarPort's service state while it runs ("streaming" while it projects)
  label: str = ""               # its words for that state ("Projecting")


def read_status() -> StarPortStatus:
  """StarPort's status from StarPilot: its switch, the app, the saved car and the running service's state."""
  from pathlib import Path
  from openpilot.common.params import Params
  from openpilot.starpilot.system.starport import apk_identity, identity, settings
  from openpilot.starpilot.system.starport.protocol import StarPortClient
  runtime = Path(apk_identity.__file__).resolve().parent
  supported = ((runtime / "hw/libstarport_encoder.so").is_file() and (runtime / "current_car_ui.py").is_file()
               and Path("/dev/dri/renderD128").exists())   # as Galaxy's install_ready (starpilot/galaxy/server.py)
  app = apk_identity.identity_status()
  config = identity.load_config()
  connection = config.get("connection", "wireless")
  paired = bool(config.get("receiver_address"))
  car_type = ("usb" if connection == "wired" else "app" if connection in ("headunitpad", "openheadunit") else
              (config.get("car_type") or ("adapter" if config.get("companion_address") else "builtin")) if paired else "")
  state = label = ""
  client = StarPortClient(timeout=1.0)
  if client.available:
    try:
      status = client.call("status")["status"]
      state, label = str(status.get("state", "")), str(status.get("label", ""))
    except (OSError, RuntimeError, KeyError, TypeError, ValueError):
      pass
  return StarPortStatus(supported, settings.enabled(Params()), bool(app.get("installed")), app.get("days_left"), car_type,
                        str(config.get("receiver_name") or ""), state, label)


def galaxy_link(parked: Callable[[], bool]) -> str:
  """Galaxy's StarPort setup page: through Remote Access when it's set up, else on this network; "" without either."""
  try:
    from openpilot.starpilot.galaxy.access import default_owner
    from openpilot.starpilot.ui.galaxy_access import GalaxyAccessFlow
    url = GalaxyAccessFlow(default_owner(), parked).update_remote().url
  except Exception:
    url = ""
  if not url:
    try:
      from openpilot.starpilot.galaxy.local_access import LocalAccess
      addresses = LocalAccess().snapshot().get("addresses", [])
      url = str(addresses[0]["url"]) if addresses else ""
    except Exception:
      url = ""
  return url.rstrip("/") + "/" + GALAXY_PAGE if url else ""


class AndroidAuto:
  """The page's state, read on a worker thread at most every REFRESH_S while it's open, and the StarPort switch.

  Args:
    read: StarPilot's StarPort status (read_status on the device).
    link: Galaxy's StarPort setup address.
    bluetooth: Tandem's Bluetooth Devices source, which turns Bluetooth on (StarPort needs it); None in tests.
    set_enabled: Saves StarPortEnabled.
    clock: Monotonic seconds.
  """

  def __init__(self, read: Callable[[], StarPortStatus], link: Callable[[], str], bluetooth: BluetoothDevices | None = None,
               set_enabled: Callable[[bool], None] | None = None, clock: Callable[[], float] = time.monotonic):
    self._read, self._link, self._bluetooth, self._clock = read, link, bluetooth, clock
    self._set = set_enabled or _save_enabled
    self._worker: ThreadPoolExecutor | None = None
    self._pending: Future[tuple[StarPortStatus, str]] | None = None
    self._next = 0.0
    self.status = StarPortStatus()
    self.link = ""
    self._code: tuple[str, Any] | None = None

  def tick(self) -> None:
    """Takes in the last read and starts another when it's due."""
    if self._pending is not None and self._pending.done():
      try:
        self.status, self.link = self._pending.result()
      except Exception:
        pass   # StarPilot's pieces unreadable: keep the last status
      self._pending = None
    if self._pending is None and self._clock() >= self._next:
      if self._worker is None:
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tandem-android-auto")
      self._next = self._clock() + REFRESH_S
      self._pending = self._worker.submit(lambda: (self._read(), self._link()))

  def close(self) -> None:
    if self._worker is not None:
      self._worker.shutdown(wait=False, cancel_futures=True)
      self._worker = None

  # The rail and the switch

  def summary(self) -> str:
    """Beside Android Auto in the rail: Not set up, Off, Connected, or what it's doing. The rail draws it whenever Connections
    is open, so it keeps the status read too."""
    self.tick()
    s = self.status
    if not s.app:
      return N_("Not set up")
    if not s.enabled:
      return N_("Off")
    return N_("Connected") if s.state == "streaming" else (s.label or N_("On"))

  def headline(self) -> str:
    """Under the page title: what StarPort is doing, or what it is."""
    s = self.status
    if s.enabled and s.state == "streaming":
      return N_("Connected · showing on your car")
    if s.enabled and s.label and s.state not in ("", "idle"):
      return s.label
    return N_("StarPilot on your car's screen, through StarPort")

  def can_switch(self) -> bool:
    """StarPort turns on once this build has it and the app is added; off always."""
    s = self.status
    return s.enabled or (s.supported and s.app)

  def switch_note(self) -> str:
    s = self.status
    if not s.supported:
      return N_("Not available on this device")
    if not s.app:
      return N_("Add the Android Auto app first")
    return N_("Shows StarPilot on your car's Android Auto screen")

  def needs_bluetooth(self) -> bool:
    """Turning StarPort on needs Bluetooth on, as Galaxy asks first."""
    if self._bluetooth is None:
      return False
    status = self._bluetooth.status()
    return status.available and not status.enabled

  def bluetooth_allowed(self) -> bool:
    """Tandem turns Bluetooth on only while parked, as StarPilot allows."""
    return self._bluetooth is not None and self._bluetooth.status().offroad

  def set_enabled(self, on: bool) -> None:
    """Saves StarPort's switch through StarPilot's setting, turning Bluetooth on first when asked to."""
    if on and self.needs_bluetooth() and self._bluetooth is not None:
      self._bluetooth.set_power(True)
    self._set(on)
    self.status = StarPortStatus(**{**self.status.__dict__, "enabled": on})
    self._next = 0.0

  # The steps

  def app_line(self) -> str:
    s = self.status
    if not s.app:
      return N_("Google's app file, from your phone · Not added")
    if s.app_days is not None:
      return tn_("Added · good for {} more day", "Added · good for {} more days", s.app_days)
    return N_("Added")

  def car_line(self) -> str:
    return CAR_TYPES.get(self.status.car_type, N_("Built-in, an adapter, a USB cable or a tablet"))

  def pair_line(self) -> str:
    s = self.status
    if s.car:
      return t_("Paired with {}", s.car)
    if s.car_type in ("usb", "app"):
      return N_("No pairing needed for this connection")
    return N_("Parked, over Bluetooth")

  def pair_done(self) -> bool:
    return bool(self.status.car) or self.status.car_type in ("usb", "app")

  def code(self) -> Any:
    """The setup page's QR code, made again when the address changes."""
    from openpilot.common.qrcode import make_texture
    link = self.link
    if self._code is not None and self._code[0] != link:
      rl.unload_texture(self._code[1])
      self._code = None
    if link and self._code is None:
      self._code = (link, make_texture(link))
    return self._code[1] if self._code is not None else None


def _save_enabled(on: bool) -> None:
  from openpilot.common.params import Params
  from openpilot.starpilot.system.starport import settings
  settings.set_enabled(Params(), on)


class Step(Component):
  """A setup step: its number (a check once done), title and line."""
  grow_touch_target = False
  HEIGHT = T.px(52)

  def __init__(self, number: int, title: str, line: Callable[[], str], done: Callable[[], bool]):
    super().__init__()
    self._number, self._title, self._line, self._done = number, title, line, done

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self.HEIGHT

  def _render(self, rect: rl.Rectangle) -> None:
    body = inset(rect, left=T.PANEL_HEADER_INSET, right=T.px(18))
    dot = T.px(34)
    circle = rl.Rectangle(body.x, body.y + (body.height - dot) / 2, dot, dot)
    done = self._done()
    draw.fill(circle, T.SUCCESS_SURFACE if done else T.ACCENT_SELECTED, dot / 2)
    if done:
      draw.icon(circle, "check", T.SUCCESS_TEXT, T.px(18))
    else:
      draw.text(circle, str(self._number), T.font_px(16), T.ACCENT_TEXT, T.FONT_BOLD, Align.CENTER)
    text = inset(body, left=dot + T.px(14))
    title_h, line_h = draw.line_height(T.font_px(17)), draw.line_height(T.SIZE_SUBTITLE)
    y = text.y + (text.height - title_h - T.px(2) - line_h) / 2
    draw.text(rl.Rectangle(text.x, y, text.width, title_h), self._title, T.font_px(17), T.TEXT, T.FONT_SEMIBOLD)
    draw.text(rl.Rectangle(text.x, y + title_h + T.px(2), text.width, line_h), draw.fit(self._line(), T.SIZE_SUBTITLE, T.FONT, text.width),
              T.SIZE_SUBTITLE, T.TEXT_TERTIARY)


def setup_sheet(model: AndroidAuto, window: SettingsWindow) -> Sheet:
  """Set up on your phone (design/androidauto-qr.html): a code that opens StarPort's setup in Galaxy."""
  from openpilot.selfdrive.ui.tandem.settings.device import CodeTile
  from openpilot.selfdrive.ui.tandem.blocks import Columns, Stack
  from openpilot.selfdrive.ui.tandem.rows import Text
  caption = lambda: (model.link.removeprefix("https://").removeprefix("http://") if model.link else "", T.ACCENT_TEXT, T.FONT_SEMIBOLD)  # noqa: E731
  notes = Stack([
    Text(N_("Scan with your phone's camera. It opens StarPort setup in Galaxy."), T.font_px(17), T.TEXT_SECONDARY, padding=(0, 0)),
    Text(N_("Set up Remote Access first if Galaxy asks you to sign in."), T.SIZE_SUBTITLE, T.TEXT_MUTED, padding=(0, 0)),
  ], gap=T.px(12))
  body = Columns([CodeTile(model.code, caption, N_("Connect to Wi-Fi or set up Remote Access to get a code")), notes], [1, 1.3])
  return Sheet(N_("Set up on your phone"), body, subtitle=N_("Galaxy walks you through adding the app and pairing your car"),
               actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss)


def android_auto_panel(model: AndroidAuto, window: SettingsWindow) -> Widget:
  """The Android Auto page: StarPort's switch, the three setup steps, and Set up on your phone."""
  model.tick()
  def switch(on: bool) -> None:
    if not on or not model.needs_bluetooth():
      model.set_enabled(on)
      return
    if not model.bluetooth_allowed():
      window.notice(N_("Android Auto"), N_("StarPort needs Bluetooth. Park to turn it on."))
      return

    def done(result: DialogResult) -> None:
      window.dismiss()
      if result == DialogResult.CONFIRM:
        model.set_enabled(True)
    window.present(Dialog(N_("Turn on Bluetooth?"), N_("StarPort needs Bluetooth to reach your car."), N_("Turn On"), done))

  starport = SettingRow(N_("StarPort"), model.switch_note, Switch(lambda: model.status.enabled, switch),
                        subtitle_color=lambda: T.WARNING if not model.status.app else T.TEXT_TERTIARY)
  starport.set_enabled(model.can_switch)
  setup = Button(N_("Set up on your phone"), lambda: window.present(setup_sheet(model, window)), ButtonStyle.PRIMARY, height=T.px(54))
  return ListPanel([
    starport,
    SectionHeader(N_("SETUP")),
    Step(1, N_("Add the Android Auto app"), model.app_line, lambda: model.status.app),
    Step(2, N_("Choose how your car connects"), model.car_line, lambda: bool(model.status.car_type)),
    Step(3, N_("Pair your car"), model.pair_line, model.pair_done),
  ], title=N_("Android Auto"), subtitle=model.headline, dividers=False, bottom=Padded(setup, x=T.PANEL_HEADER_INSET, y=T.px(8)))
