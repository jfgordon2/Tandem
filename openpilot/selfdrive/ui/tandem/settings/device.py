"""The release This Device, pairing and Remote Access presentation."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem.fonts import Face
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.blocks import Card, Columns, Label
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonRow, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import Align, inset, place
from openpilot.selfdrive.ui.tandem.rows import ListPanel, SectionHeader, SettingRow
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.settings.pages import PanelPage, Section, SectionPage, TitledPage
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, confirm


def driver_monitoring_rows(device: object, ask: Callable | None = None) -> list[SettingRow]:
  """The Driver Camera preview and the driver monitoring reset, for Driving › Assistance. ask(title, message, label, action,
  danger, icon) shows our confirm dialog before the reset.

  Args:
    device: DeviceOwner (driver_camera, is_offroad, can_reset_driver_monitoring, reset_driver_monitoring).
    ask: The confirm dialog; without it the reset runs at once.
  """
  ask = ask or (lambda title, message, label, action, danger, icon: action())
  owner: Any = device
  preview = Button(N_("Preview"), owner.driver_camera, ButtonStyle.SECONDARY)
  preview.set_enabled(owner.is_offroad)
  reset = Button(N_("Reset"), lambda: ask(N_("Reset driver monitoring?"),
                 N_("It forgets which side of the car the driver sits on and learns it again on the next drive."), N_("Reset"),
                                          owner.reset_driver_monitoring, False, "restart"),
                 ButtonStyle.SECONDARY)
  reset.set_enabled(owner.can_reset_driver_monitoring)
  return [SettingRow(N_("Driver Camera"), N_("Check that it can see your face. The car must be off."), preview),
          SettingRow(N_("Driver Monitoring"), N_("Forget which side of the car the driver sits on"), reset)]


class Calibration:
  """The calibration states the device page shows."""
  CALIBRATED = N_("Calibrated")
  CALIBRATING = N_("Calibrating")
  UNKNOWN = N_("Not calibrated yet")


class Device(Protocol):
  """Presentation state and actions provided by the device owners."""

  def is_paired(self) -> bool: ...
  def is_offroad(self) -> bool: ...
  def calibration(self) -> str: ...
  def can_recalibrate(self) -> bool: ...
  def pairing_supported(self) -> bool: ...
  def provider_name(self) -> str: ...
  def provider_web(self) -> str: ...
  def poll(self) -> None: ...
  def remote_access_label(self) -> str: ...
  def ids(self) -> str: ...
  def imei(self) -> str: ...   # the modem's IMEI, or "Not available"
  def show_regulatory(self) -> bool: ...
  def refresh(self) -> None: ...
  def pairing_qr(self) -> rl.Texture | None: ...   # the comma connect pairing code, refreshed every 5 minutes
  def recalibrate(self) -> None: ...
  def review_guide(self) -> None: ...
  def remote_access_link(self) -> str: ...   # the Galaxy link once set up, else ""
  def remote_access_qr(self) -> rl.Texture | None: ...
  def set_up_remote_access(self) -> None: ...
  def unpair_remote_access(self) -> None: ...
  def restart(self) -> None: ...
  def power_off(self) -> None: ...


type Confirmation = Callable[[str, str, str, Callable[[], None], bool, str], None]


class ThisDevicePanel(ListPanel):
  """Device › This Device: identity, pairing, remote access, calibration, and restart and power off."""

  def __init__(self, device: Device, open_pairing: Callable[[], None], open_remote_access: Callable[[], None],
               ask: Confirmation, open_regulatory: Callable[[], None]):
    """Makes the panel.

    Args:
      device: The device's state and actions.
      open_pairing: Shows the pairing page.
      open_remote_access: Shows the remote access page.
      ask: ask(title, message, label, action, danger, icon) shows our confirm dialog before Restart, Power Off and
        Recalibrate. The device rechecks permission after confirmation.
      open_regulatory: Shows the regulatory page.
    """
    self._device = device

    def asking(title: str, message: str, label: str, action: Callable[[], None], danger: bool = False, icon: str = "restart") -> Callable[[], None]:
      return lambda: ask(title, message, label, action, danger, icon)

    def action(label: str, on_click: Callable[[], None], style: ButtonStyle = ButtonStyle.SECONDARY, offroad_only: bool = False) -> Button:
      button = Button(label, on_click, style)
      if offroad_only:
        button.set_enabled(device.is_offroad)
      return button

    pair = action(N_("Pair"), open_pairing, ButtonStyle.PRIMARY)
    pair.set_visible(lambda: not device.is_paired() and device.pairing_supported())
    power_off = Button(N_("Power Off"), asking(N_("Power off?"), N_("The device stays off until the car starts again."), N_("Power Off"), device.power_off,
                                           True, "power"), ButtonStyle.DANGER_SOFT, height=T.px(52))
    power_off.set_enabled(device.is_offroad)   # shown while driving, greyed out, like the other car-off actions
    restart = Button(N_("Restart"), asking(N_("Restart the device?"), N_("openpilot shuts down and starts again. This takes about a minute."),
                                       N_("Restart"), device.restart), height=T.px(52), weight=T.FONT_BOLD)
    recalibrate = action(N_("Recalibrate"), asking(N_("Recalibrate the camera?"),
                         N_("Calibration starts over. openpilot relearns how the device is mounted over your next few minutes of driving."),
                         N_("Recalibrate"), device.recalibrate))
    recalibrate.set_enabled(device.can_recalibrate)

    super().__init__([
      # The two ways to reach the car from elsewhere sit together, each naming its service.
      SettingRow(N_("Phone App"),
                 lambda: phone_status(device),
                 pair, subtitle_color=lambda: T.SUCCESS_TEXT if device.is_paired() else T.TEXT_TERTIARY),
      SettingRow(N_("Remote Access"), lambda: N_("Galaxy · Set up") if device.remote_access_link() else N_("Galaxy · reach this device from a web browser"),
                 Button(device.remote_access_label, open_remote_access),
                 subtitle_color=lambda: T.SUCCESS_TEXT if device.remote_access_link() else T.TEXT_TERTIARY),
      SettingRow(N_("Camera Calibration"), device.calibration, recalibrate,
                 subtitle_color=lambda: T.SUCCESS_TEXT if device.calibration() == Calibration.CALIBRATED else T.TEXT_TERTIARY),
      SettingRow(N_("How It Works"), N_("Rules, features and limits"), action(N_("Review"), device.review_guide, offroad_only=True)),
      SectionHeader(N_("MORE")),
      regulatory := SettingRow(N_("Regulatory"), None, action(N_("View"), open_regulatory, offroad_only=True)),
      SettingRow(N_("Device ID and Serial"), device.ids),
      SettingRow(N_("IMEI"), device.imei),
    ], title=N_("This Device"), footer=ButtonRow([restart, power_off]))
    regulatory.set_visible(device.show_regulatory)

  def show_event(self) -> None:
    """Read status when This Device opens."""
    super().show_event()
    self._device.refresh()

  def _update_state(self) -> None:
    super()._update_state()
    self._device.poll()


def phone_status(device: Device) -> str:
  """Retain the release text with the current cloud provider's name."""
  provider = device.provider_name()
  if not provider:
    return N_("Not available")
  if provider == "comma connect":
    return N_("comma connect · Paired") if device.is_paired() else N_("comma connect · see drives and change settings on your phone")
  return t_("{} · Paired", provider) if device.is_paired() else t_("{} · see drives and change settings on your phone", provider)


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

  def _render(self, rect: rl.Rectangle) -> None:
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

  def __init__(self, code: Callable[[], rl.Texture | None], caption: Callable[[], tuple[str, rl.Color, Face]], empty: str):
    super().__init__()
    self._code, self._caption, self._empty = code, caption, empty

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self.TILE + T.px(14) + draw.line_height(T.font_px(15))

  def _render(self, rect: rl.Rectangle) -> None:
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


REGULATORY_FILE = "openpilot/selfdrive/assets/offroad/fcc.html"


class HtmlBlock(Component):
  """Upstream's HTML renderer as a row of a ListPanel, so long notices scroll in our panel."""
  grow_touch_target = False

  def __init__(self, path: str):
    super().__init__()
    from openpilot.system.ui.widgets.html_render import ElementType, HtmlRenderer
    self._html = HtmlRenderer(file_path=path, text_size={ElementType.P: T.font_px(17)}, text_color=T.TEXT_SECONDARY)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self._html.get_total_height(int(max_width - T.PANEL_HEADER_INSET * 2)) + T.px(24)

  def _render(self, rect: rl.Rectangle) -> None:
    self._html.render(inset(rect, x=T.PANEL_HEADER_INSET, y=T.px(12)))


def regulatory_panel() -> ListPanel:
  """The FCC notice upstream shows, in our panel."""
  import os
  from openpilot.common.basedir import BASEDIR
  return ListPanel([HtmlBlock(os.path.join(BASEDIR, REGULATORY_FILE))], title=N_("Regulatory"), header_divider=True)


def pairing_page(device: Device) -> Widget:
  """Pair the phone app: the steps on the left, the code on the right (design/pairing.html)."""
  web = device.provider_web().removeprefix("https://").rstrip("/")
  instructions = PAIRING_STEPS if web == "connect.comma.ai" else [(t_("Open {}", web), PAIRING_STEPS[0][1]), *PAIRING_STEPS[1:]]
  steps = Card([Label(N_("ON YOUR PHONE"), color=T.ACCENT_TEXT, caption=True), StepList(instructions)], gap=T.px(22))
  caption = lambda: (N_("Paired"), T.SUCCESS_TEXT, T.FONT_BOLD) if device.is_paired() else (N_("A new code every 5 minutes"), T.TEXT_MUTED, T.FONT)  # noqa: E731
  code = Card([CodeTile(lambda: device.pairing_qr(), caption, N_("Getting a code…"))], grow=0)
  return TitledPage(N_("Pair the phone app"), N_("Change settings and see drives from your phone"), Columns([steps, code], [1.25, 1]))


def remote_access_page(device: Device, window: SettingsWindow) -> Widget:
  """Remote Access (Galaxy): set a password to create the link, then its code; Unpair asks first
  (design/remoteaccess.html, remoteaccessqr.html)."""
  from openpilot.selfdrive.ui.tandem.blocks import SPACER
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

  def caption() -> tuple[str, rl.Color, Face]:
    link = device.remote_access_link()
    if link:
      return link.split("://", 1)[-1], T.ACCENT_TEXT, T.FONT_SEMIBOLD
    return N_("Choosing a password creates this device's link"), T.TEXT_MUTED, T.FONT
  code = Card([CodeTile(lambda: device.remote_access_qr(), caption, N_("Your code appears here once you choose a password"))], grow=0)
  return TitledPage(N_("Remote Access"), N_("Reach this device from the Galaxy web app"), Columns([steps, code], [1.25, 1]))


def device_page(window: SettingsWindow, device: Device, sections: Sequence[Section]) -> SectionPage:
  """Keep This Device first, followed by the remaining release sections."""
  def this_device() -> ThisDevicePanel:
    return ThisDevicePanel(
      device,
      lambda: window.push(pairing_page(device)),
      lambda: window.push(remote_access_page(device, window)),
      lambda title, message, label, action, danger, icon: confirm(window, title, message, label, action, danger, icon),
      lambda: window.push(PanelPage(regulatory_panel())),
    )
  return SectionPage(N_("DEVICE"), [Section(N_("This Device"), this_device), *sections])
