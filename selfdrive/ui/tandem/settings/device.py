"""This Device: pairing, cameras, the training guide, and power.

The actions are upstream's: UpstreamDevice calls DeviceLayout's own handlers, so calibration reset and power off
keep upstream's checks and dialogs. Pairing opens our page (design/pairing.html) around upstream's QR code, which
carries the same comma connect pairing token.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Card, Columns, Label
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonRow, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import Align, inset, place
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow
from openpilot.selfdrive.ui.tandem.i18n import N_


class Calibration:
  CALIBRATED = N_("Calibrated")
  CALIBRATING = N_("Calibrating")
  UNKNOWN = N_("Not calibrated yet")


class Device(Protocol):
  """What the screen needs to know and do. UpstreamDevice is the real one."""

  def is_paired(self) -> bool: ...
  def is_offroad(self) -> bool: ...
  def engaged(self) -> bool: ...
  def calibration(self) -> str: ...
  def remote_access_label(self) -> str: ...
  def ids(self) -> str: ...
  def imei(self) -> str: ...   # the modem's IMEI, or "Not available"
  def show_regulatory(self) -> bool: ...
  def refresh(self) -> None: ...
  def pair(self) -> None: ...
  def pairing_qr(self) -> rl.Texture | None: ...   # the comma connect pairing code, refreshed every 5 minutes
  def driver_camera(self) -> None: ...
  def recalibrate(self) -> None: ...
  def review_guide(self) -> None: ...
  def remote_access(self) -> None: ...
  def remote_access_link(self) -> str: ...   # the Galaxy link once set up, else ""
  def remote_access_qr(self) -> rl.Texture | None: ...
  def set_up_remote_access(self) -> None: ...
  def unpair_remote_access(self) -> None: ...
  def reset_driver_monitoring(self) -> None: ...
  def regulatory(self) -> None: ...
  def restart(self) -> None: ...
  def power_off(self) -> None: ...


def driver_monitoring_rows(device: Device, ask: Callable | None = None) -> list[SettingRow]:
  """The Driver Camera preview and the driver monitoring reset, for Driving › Assistance. ask(title, message, label, action,
  danger, icon) shows our confirm dialog before the reset."""
  ask = ask or (lambda title, message, label, action, danger, icon: action())
  preview = Button(N_("Preview"), device.driver_camera, ButtonStyle.SECONDARY)
  preview.set_enabled(device.is_offroad)
  reset = Button(N_("Reset"), lambda: ask(N_("Reset driver monitoring?"),
                 N_("It forgets which side of the car the driver sits on and learns it again on the next drive."), N_("Reset"),
                                          device.reset_driver_monitoring, False, "restart"),
                 ButtonStyle.SECONDARY)
  reset.set_enabled(device.is_offroad)
  return [SettingRow(N_("Driver Camera"), N_("Check that it can see your face. The car must be off."), preview),
          SettingRow(N_("Driver Monitoring"), N_("Forget which side of the car the driver sits on"), reset)]


class ThisDevicePanel(ListPanel):
  def __init__(self, device: Device, open_pairing: Callable[[], None] | None = None, open_remote_access: Callable[[], None] | None = None,
               ask: Callable | None = None, open_regulatory: Callable[[], None] | None = None):
    """open_pairing and open_remote_access show our pages. ask(title, message, label, action, danger,
    icon) shows our confirm dialog before Restart, Power Off and Recalibrate; the device then runs upstream's action without
    its own dialog. The driver camera and driver monitoring reset are in Driving › Assistance (driver_monitoring_rows)."""
    self._device = device
    ask = ask or (lambda title, message, label, action, danger, icon: action())

    def asking(title: str, message: str, label: str, action: Callable[[], None], danger: bool = False, icon: str = "restart"):
      return lambda: ask(title, message, label, action, danger, icon)

    def action(label: str, on_click, style: ButtonStyle = ButtonStyle.SECONDARY, offroad_only: bool = False) -> Button:
      button = Button(label, on_click, style)
      if offroad_only:
        button.set_enabled(device.is_offroad)
      return button

    pair = action(N_("Pair"), open_pairing or device.pair, ButtonStyle.PRIMARY)
    pair.set_visible(lambda: not device.is_paired())
    power_off = Button(N_("Power Off"), asking(N_("Power off?"), N_("The device stays off until the car starts again."), N_("Power Off"), device.power_off,
                                           True, "power"), ButtonStyle.DANGER_SOFT, height=T.px(52))
    power_off.set_enabled(device.is_offroad)   # shown while driving, greyed out, like the other car-off actions
    restart = Button(N_("Restart"), asking(N_("Restart the device?"), N_("openpilot shuts down and starts again. This takes about a minute."),
                                       N_("Restart"), device.restart), height=T.px(52), weight=T.FONT_BOLD)
    recalibrate = action(N_("Recalibrate"), asking(N_("Recalibrate the camera?"),
                         N_("Calibration starts over. openpilot relearns how the device is mounted over your next few minutes of driving."),
                         N_("Recalibrate"), device.recalibrate))
    recalibrate.set_enabled(lambda: not device.engaged())   # upstream refuses while engaged

    super().__init__([
      # The two ways to reach the car from elsewhere sit together, each naming its service.
      SettingRow(N_("Phone App"),
                 lambda: N_("comma connect · Paired") if device.is_paired() else N_("comma connect · see drives and change settings on your phone"),
                 pair, subtitle_color=lambda: T.SUCCESS_TEXT if device.is_paired() else T.TEXT_TERTIARY),
      SettingRow(N_("Remote Access"), lambda: N_("Galaxy · Set up") if device.remote_access_link() else N_("Galaxy · reach this device from a web browser"),
                 Button(device.remote_access_label, open_remote_access or device.remote_access),
                 subtitle_color=lambda: T.SUCCESS_TEXT if device.remote_access_link() else T.TEXT_TERTIARY),
      SettingRow(N_("Camera Calibration"), device.calibration, recalibrate,
                 subtitle_color=lambda: T.SUCCESS_TEXT if device.calibration() == Calibration.CALIBRATED else T.TEXT_TERTIARY),
      SettingRow(N_("How It Works"), N_("Rules, features and limits"), action(N_("Review"), device.review_guide, offroad_only=True)),
      SectionHeader(N_("MORE")),
      regulatory := SettingRow(N_("Regulatory"), None, action(N_("View"), open_regulatory or device.regulatory, offroad_only=True)),
      SettingRow(N_("Device ID and Serial"), device.ids),
      SettingRow(N_("IMEI"), device.imei),
    ], title=N_("This Device"), footer=ButtonRow([restart, power_off]))
    regulatory.set_visible(device.show_regulatory)

  def show_event(self):
    super().show_event()
    self._device.refresh()


PAIRING_STEPS = [
  (N_("Open connect.comma.ai"), N_("Bookmark it to your home screen to use it like an app")),
  (N_("Tap Add new device"), N_("Sign in first if it asks")),
  (N_("Scan the code"), N_("The Phone App row shows Paired when it's done")),
]
REMOTE_STEPS = [
  (N_("Choose a password"), N_("At least 6 characters. Galaxy asks for it when you sign in")),
  (N_("Scan the code"), N_("It opens this device's page in Galaxy")),
  (N_("Bookmark the page"), N_("The link stays the same until you unpair")),
]


class StepList(Component):
  """Numbered steps: a blue number in a round well (a green check once done), a title and a line."""
  grow_touch_target = False
  ROW, GAP = T.px(46), T.px(22)   # a title and a line, then the gap

  def __init__(self, steps: list[tuple[str, str]], done: Callable[[int], bool] = lambda i: False):
    super().__init__()
    self._steps = steps
    self._done = done

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, len(self._steps) * self.ROW + (len(self._steps) - 1) * self.GAP

  def _render(self, rect: rl.Rectangle):
    y = rect.y
    for i, (title, line) in enumerate(self._steps):
      well = rl.Rectangle(rect.x, y, T.px(40), T.px(40))
      if self._done(i):
        draw.fill(well, T.SUCCESS_SURFACE, well.width / 2)
        draw.icon(well, "check", T.SUCCESS_TEXT, T.px(20))
      else:
        draw.fill(well, T.ACCENT_SURFACE, well.width / 2)
        draw.text(well, str(i + 1), T.font_px(19), T.ACCENT_TEXT, T.FONT_EXTRABOLD, Align.CENTER)
      x = rect.x + T.px(56)
      title_h, line_h = draw.line_height(T.font_px(20)), draw.line_height(T.font_px(15))
      draw.text(rl.Rectangle(x, y, rect.width - T.px(56), title_h), title, T.font_px(20), T.TEXT, T.FONT_BOLD)
      draw.text(rl.Rectangle(x, y + title_h + T.px(3), rect.width - T.px(56), line_h), line, T.font_px(15), T.TEXT_TERTIARY)
      y += self.ROW + self.GAP


class CodeTile(Component):
  """A QR code on a white tile, so it scans in any theme, with a line under it; centered in its card. Without a
  code, a dashed outline holds the empty text."""
  grow_touch_target = False
  TILE, PAD = T.px(268), T.px(16)

  def __init__(self, code: Callable[[], rl.Texture | None], caption: Callable[[], tuple[str, rl.Color, object]], empty: str):
    super().__init__()
    self._code, self._caption, self._empty = code, caption, empty

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self.TILE + T.px(14) + draw.line_height(T.font_px(15))

  def _render(self, rect: rl.Rectangle):
    line_h = draw.line_height(T.font_px(15))
    group = place(rect, self.TILE, self.TILE + T.px(14) + line_h)
    tile = rl.Rectangle(group.x, group.y, self.TILE, self.TILE)
    code = self._code()
    inner = rl.Rectangle(tile.x + self.PAD, tile.y + self.PAD, tile.width - self.PAD * 2, tile.height - self.PAD * 2)
    if code is not None and code.id != 0:
      draw.fill(tile, rl.WHITE, T.px(18))
      rl.draw_texture_pro(code, rl.Rectangle(0, 0, code.width, code.height), inner, rl.Vector2(0, 0), 0, rl.WHITE)
    else:
      draw.stroke(tile, T.SWITCH_TRACK_OFF, T.px(18), T.px(2))
      body = inset(tile, T.px(28))
      lines = draw.paragraph_lines(self._empty, T.font_px(16), T.FONT_SEMIBOLD, body.width)
      step = draw.line_height(T.font_px(16)) * 1.2
      y = body.y + (body.height - step * len(lines)) / 2
      for line in lines:
        draw.text(rl.Rectangle(body.x, y, body.width, step), line, T.font_px(16), T.TEXT_MUTED, T.FONT_SEMIBOLD, Align.CENTER)
        y += step
    text, color, weight = self._caption()
    draw.text(rl.Rectangle(group.x - T.px(60), tile.y + tile.height + T.px(14), self.TILE + T.px(120), line_h), text, T.font_px(15),
              color, weight, Align.CENTER)


REGULATORY_FILE = "selfdrive/assets/offroad/fcc.html"


class HtmlBlock(Component):
  """Upstream's HTML renderer as a row of a ListPanel, so long notices scroll in our panel."""
  grow_touch_target = False

  def __init__(self, path: str):
    super().__init__()
    from openpilot.system.ui.widgets.html_render import ElementType, HtmlRenderer
    self._html = HtmlRenderer(file_path=path, text_size={ElementType.P: T.font_px(17)}, text_color=T.TEXT_SECONDARY)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self._html.get_total_height(int(max_width - T.PANEL_HEADER_INSET * 2)) + T.px(24)

  def _render(self, rect: rl.Rectangle):
    self._html.render(inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(12)))


def regulatory_panel() -> ListPanel:
  """The FCC notice upstream shows, in our panel."""
  import os
  from openpilot.common.basedir import BASEDIR
  return ListPanel([HtmlBlock(os.path.join(BASEDIR, REGULATORY_FILE))], title=N_("Regulatory"), header_divider=True)


def pairing_page(device: Device):
  """Pair the phone app: the steps on the left, the code on the right (design/pairing.html)."""
  from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage
  steps = Card([Label(N_("ON YOUR PHONE"), color=T.ACCENT_TEXT, caption=True), StepList(PAIRING_STEPS)], gap=T.px(22))
  caption = lambda: (N_("Paired"), T.SUCCESS_TEXT, T.FONT_BOLD) if device.is_paired() else (N_("A new code every 5 minutes"), T.TEXT_MUTED, T.FONT)  # noqa: E731
  code = Card([CodeTile(lambda: device.pairing_qr(), caption, N_("Getting a code…"))], grow=0)
  return TitledPage(N_("Pair the phone app"), N_("Change settings and see drives from your phone"), Columns([steps, code], [1.25, 1]))


def remote_access_page(device: Device, window):
  """Remote Access (Galaxy): set a password to create the link, then its code; Unpair asks first
  (design/remoteaccess.html, remoteaccessqr.html)."""
  from openpilot.selfdrive.ui.tandem.blocks import SPACER
  from openpilot.selfdrive.ui.tandem.settings.device_sections import confirm
  from openpilot.selfdrive.ui.tandem.settings.pages import TitledPage
  ready = lambda: bool(device.remote_access_link())  # noqa: E731
  set_up = Button(N_("Set up", context="action"), device.set_up_remote_access, ButtonStyle.PRIMARY, height=T.px(58), font_size=T.font_px(18),
                  weight=T.FONT_EXTRABOLD)
  set_up.set_visible(lambda: not ready())
  unpair = Button(N_("Unpair"), lambda: confirm(window, N_("Unpair from Galaxy?"), N_("The link stops working. Setting up again makes a new one."),
                                            N_("Unpair"), device.unpair_remote_access), ButtonStyle.DANGER_SOFT, height=T.px(52),
                  font_size=T.font_px(17))
  unpair.set_visible(ready)
  status = Label(lambda: N_("Set up · protected by your password") if ready() else N_("Not set up"), T.font_px(15),
                 lambda: T.SUCCESS_TEXT if ready() else T.TEXT_TERTIARY, T.FONT_SEMIBOLD, h=Align.END)
  header = Columns([Label(N_("GALAXY"), color=T.ACCENT_TEXT, caption=True), status], [1, 3])
  steps = Card([header, StepList(REMOTE_STEPS, lambda i: i == 0 and ready()),
                SPACER, set_up, unpair], gap=T.px(22))

  def caption():
    link = device.remote_access_link()
    if link:
      return link.split("://", 1)[-1], T.ACCENT_TEXT, T.FONT_SEMIBOLD
    return N_("Choosing a password creates this device's link"), T.TEXT_MUTED, T.FONT
  code = Card([CodeTile(lambda: device.remote_access_qr(), caption, N_("Your code appears here once you choose a password"))], grow=0)
  return TitledPage(N_("Remote Access"), N_("Reach this device from the Galaxy web app"), Columns([steps, code], [1.25, 1]))


class UpstreamDevice:
  """Device backed by upstream's DeviceLayout and ui_state. Imported only on the device."""

  def __init__(self):
    from openpilot.selfdrive.ui.layouts.settings.device import DeviceLayout
    from openpilot.selfdrive.ui.ui_state import ui_state
    from openpilot.system.hardware import TICI
    from openpilot.selfdrive.ui.tandem.settings.controllers import confirmed_controller
    self._layout = confirmed_controller(DeviceLayout)()
    self._ui_state = ui_state
    self._params = ui_state.ui_params
    self._tici = TICI
    self._calibration = Calibration.UNKNOWN
    self._ids = ""
    self._imei = ""          # read once from the modem, in the background
    self._imei_reading = False
    self._pairing = None   # upstream PairingDialog, made on first use
    self._camera = None    # our driver camera, made on first use
    self._galaxy_qr = None   # (link, upstream GalaxyQRDialog) for the current link
    self.refresh()

  def refresh(self) -> None:
    """Calibration and IDs change rarely, so they're read when the screen opens, not every frame."""
    self._calibration = self._read_calibration()
    dongle = self._params.get("DongleId") or "N/A"
    serial = self._params.get("HardwareSerial") or "N/A"
    self._ids = f"{dongle} · {serial}"
    self._read_imei()

  IMEI_TRIES, IMEI_WAIT_S = 6, 1.5   # openpilot gives each modem call 0.1 s, which the first call often misses

  def _read_imei(self) -> None:
    """Asking the modem goes over D-Bus and can be slow or fail while it starts up, so it's read off the UI thread and
    tried a few times, about 10 s in all; until then the row says Not available, and opening the screen again retries."""
    if self._imei or self._imei_reading or not self._tici:
      return
    import threading
    import time

    def read():
      try:
        from openpilot.system.hardware import HARDWARE
        for attempt in range(self.IMEI_TRIES):
          try:
            self._imei = str(HARDWARE.get_imei(0) or "").strip()
          except Exception:
            pass
          if self._imei:
            return
          if attempt + 1 < self.IMEI_TRIES:
            time.sleep(self.IMEI_WAIT_S)
      finally:
        self._imei_reading = False

    self._imei_reading = True
    threading.Thread(target=read, daemon=True).start()

  def _read_calibration(self) -> str:
    from cereal import log, messaging
    data = self._params.get("CalibrationParams")
    if not data:
      return Calibration.UNKNOWN
    try:
      status = messaging.log_from_bytes(data, log.Event).liveCalibration.calStatus
    except Exception:
      return Calibration.UNKNOWN
    if status == log.LiveCalibrationData.Status.calibrated:
      return Calibration.CALIBRATED
    return Calibration.UNKNOWN if status == log.LiveCalibrationData.Status.uncalibrated else Calibration.CALIBRATING

  def is_paired(self) -> bool:
    return self._ui_state.prime_state.is_paired()

  def is_offroad(self) -> bool:
    return self._ui_state.is_offroad()

  def calibration(self) -> str:
    return self._calibration

  def remote_access_label(self) -> str:
    return N_("Manage") if self._layout._is_galaxy_paired() else N_("Set Up")

  def ids(self) -> str:
    return self._ids

  def imei(self) -> str:
    return self._imei or N_("Not available")

  def show_regulatory(self) -> bool:
    return self._tici

  def pair(self) -> None:
    self._layout._pair_device()

  def pairing_qr(self) -> rl.Texture | None:
    """Upstream's pairing dialog makes the code (its token request and 5-minute refresh); we only draw it."""
    if self._pairing is None:
      from openpilot.selfdrive.ui.widgets.pairing_dialog import PairingDialog
      self._pairing = PairingDialog()
    self._pairing._check_qr_refresh()
    return self._pairing.qr_texture

  def driver_camera(self) -> None:
    """Upstream's camera with our overlay; one instance, as upstream keeps one (it registers a timeout callback)."""
    from openpilot.system.ui.lib.application import gui_app
    if self._camera is None:
      from openpilot.selfdrive.ui.tandem.drivercamera import driver_camera
      self._camera = driver_camera()
    gui_app.push_widget(self._camera)

  def recalibrate(self) -> None:
    self._layout.run_confirmed("reset_calibration", self._layout._reset_calibration_prompt)

  def review_guide(self) -> None:
    self._layout._on_review_training_guide()

  def remote_access(self) -> None:
    self._layout._pair_galaxy()

  def remote_access_link(self) -> str:
    slug = self._layout._get_galaxy_slug() if self._layout._is_galaxy_paired() else ""
    return f"https://galaxy.firestar.link/{slug}" if slug else ""

  def remote_access_qr(self) -> rl.Texture | None:
    """Upstream's Galaxy dialog makes the code for the link; we only draw it."""
    link = self.remote_access_link()
    if not link:
      return None
    if self._galaxy_qr is None or self._galaxy_qr[0] != link:
      from openpilot.selfdrive.ui.layouts.settings.device import GalaxyQRDialog
      self._galaxy_qr = (link, GalaxyQRDialog(link))
    return self._galaxy_qr[1]._qr_texture

  def set_up_remote_access(self) -> None:
    """Our keyboard with upstream's Galaxy rules (a password, at least 6 characters), then the same files upstream
    writes. Upstream's own handler would end on its QR dialog; our page shows the code instead."""
    import hashlib
    import secrets
    from openpilot.selfdrive.ui.layouts.settings import device as upstream
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.system.ui.widgets import DialogResult
    from openpilot.selfdrive.ui.tandem.keyboard import EssentialsKeyboard
    layout = self._layout
    keyboard = EssentialsKeyboard(min_text_size=6, password_mode=True, show_password_toggle=True, action=N_("Set up", context="action"))

    def done(result: int) -> None:
      password = keyboard.text.strip()
      keyboard.clear()
      if result != DialogResult.CONFIRM or len(password) < 6:
        return
      layout._galaxy_dir.mkdir(parents=True, exist_ok=True)
      layout._galaxy_auth_path.write_text(hashlib.sha256(password.encode("utf-8")).hexdigest(), encoding="utf-8")
      layout._galaxy_session_path.write_text(secrets.token_hex(32), encoding="utf-8")
      layout._galaxy_slug_path.write_text("".join(secrets.choice(upstream.GALAXY_SLUG_CHARS) for _ in range(16)), encoding="utf-8")

    keyboard.clear()
    keyboard.set_title(N_("Choose a Galaxy password"), N_("At least 6 characters. Galaxy asks for it when you sign in."))
    keyboard.set_callback(done)
    gui_app.push_widget(keyboard)

  def unpair_remote_access(self) -> None:
    from openpilot.system.ui.widgets import DialogResult
    self._layout._unpair_galaxy(DialogResult.CONFIRM)   # our page has already asked

  def reset_driver_monitoring(self) -> None:
    self._layout.run_confirmed("reset_driver_monitoring", self._layout._reset_driver_monitoring_prompt)

  def regulatory(self) -> None:
    self._layout._on_regulatory()

  def restart(self) -> None:
    from openpilot.system.ui.widgets import DialogResult
    self._layout._perform_reboot(DialogResult.CONFIRM)

  def power_off(self) -> None:
    from openpilot.system.ui.widgets import DialogResult
    self._layout._perform_power_off(DialogResult.CONFIRM)   # upstream checks engaged again

  def engaged(self) -> bool:
    return bool(self._ui_state.engaged)
