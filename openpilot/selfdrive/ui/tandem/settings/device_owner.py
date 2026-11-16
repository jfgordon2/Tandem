"""Current StarPilot owners for the release This Device screen."""
from __future__ import annotations

from collections.abc import Callable
from functools import cached_property
import threading
import time
from typing import TYPE_CHECKING, Any

from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.settings.device import Calibration
from openpilot.starpilot.ui.raylib import rl

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.widgets.pairing_dialog import PairingDialog
  from openpilot.starpilot.ui.galaxy_access import GalaxyAccessFlow


def calibration_label(status: str, resetting: bool) -> str:
  """Render the release label for saved calibration or a reset in progress."""
  if resetting or status == "recalibrating":
    return Calibration.CALIBRATING
  return Calibration.CALIBRATED if status == "calibrated" else Calibration.UNKNOWN


class DeviceOwner:
  """Keep device logic with native Params, calibration, cloud and Galaxy owners."""

  def __init__(self, ui: Any, ask_password: Callable[[int, Callable[[str], None]], None], notify: Callable[[str], None]):
    self._ui = ui
    self._ask_password = ask_password
    self._notify = notify
    self._label = Calibration.UNKNOWN
    self._ids = ""
    self._imei = ""
    self._imei_busy = False
    self._provider_name = ""
    self._provider_key = ""
    self._provider_web = ""
    self._pairing: PairingDialog | None = None
    self._remote_code: tuple[str, rl.Texture] | None = None
    self._next = 0.0

  def _local(self) -> bool:
    return not self._ui.projection_read_only and self._ui.replay_clock is None

  def is_paired(self) -> bool:
    """Read the active provider's pairing state."""
    return bool(self._provider_key and self._ui.prime_state.is_paired())

  def pairing_supported(self) -> bool:
    """Whether the active cloud provider supports pairing."""
    return self._local() and bool(self._provider_key)

  def provider_name(self) -> str:
    """The name of the active cloud provider."""
    return self._provider_name

  def provider_web(self) -> str:
    """The official pairing entry point for the current provider."""
    return self._provider_web

  def is_offroad(self) -> bool:
    """Use the vehicle-off gate for local device actions."""
    return self._local() and bool(self._ui.is_offroad())

  def calibration(self) -> str:
    """The release calibration label."""
    return self._label

  def _resetting(self) -> bool:
    from openpilot.starpilot.ui.calibration_reset import calibration_reset

    return calibration_reset.pending

  def can_recalibrate(self) -> bool:
    """Keep the native engagement, reset and cycle gates."""
    return (self._local() and not self._ui.engaged and not self._resetting()
            and not self._ui.params.get_bool("OnroadCycleRequested"))

  def recalibrate(self) -> None:
    """Submit through the native reset owner with a fresh confirmation gate."""
    from openpilot.starpilot.ui.calibration_reset import calibration_reset

    if self.can_recalibrate() and calibration_reset.request(self._ui.params):
      self._label = Calibration.CALIBRATING
      self._next = 0.0

  def restart(self) -> None:
    """Use the native reboot request after a fresh engagement check."""
    if self._local() and not self._ui.engaged:
      self._ui.params.put_bool("DoReboot", True)

  def power_off(self) -> None:
    """Use the native shutdown request only while the car is off."""
    if self.is_offroad() and not self._ui.engaged:
      self._ui.params.put_bool("DoShutdown", True)

  def _read_calibration(self) -> str:
    from openpilot.cereal import log, messaging
    from openpilot.common.swaglog import cloudlog
    from openpilot.starpilot.schema_cache import get_cache

    if self._resetting():
      return Calibration.CALIBRATING
    raw = get_cache(self._ui.params, "CalibrationParams")
    if raw:
      try:
        status = messaging.log_from_bytes(raw, log.Event).extrinsicsCalibration.calStatus
        return calibration_label(str(status), False)
      except Exception:
        cloudlog.exception("Invalid CalibrationParams")
    return Calibration.UNKNOWN

  def _read_imei(self) -> None:
    if self._imei_busy or self._imei or not self.show_regulatory():
      return
    self._imei_busy = True

    def read() -> None:
      from openpilot.common.hardware import HARDWARE

      try:
        for attempt in range(6):
          try:
            self._imei = str(HARDWARE.get_imei() or "").strip()
          except (OSError, RuntimeError, TimeoutError):
            pass
          if self._imei:
            break
          if attempt < 5:
            time.sleep(1.5)
      finally:
        self._imei_busy = False

    threading.Thread(target=read, daemon=True, name="tandem-device-imei").start()

  def refresh(self) -> None:
    """Refresh slow status when This Device opens."""
    self._next = 0.0
    self.poll()
    self._read_imei()

  def poll(self) -> None:
    """Refresh saved state at a bounded rate while the page is open."""
    from openpilot.starpilot.connect.provider import active_provider
    from openpilot.starpilot.ui.calibration_reset import calibration_reset

    now = time.monotonic()
    if now < self._next:
      return
    self._next = now + 2.0
    provider = active_provider()
    name = provider.name if provider.name in ("comma", "konik") else ""
    if name != self._provider_key:
      self._pairing = None
    self._provider_key, self._provider_name = name, provider.label if name else ""
    self._provider_web = provider.web if name else ""
    self._label = self._read_calibration()
    self._ids = f'{self._ui.params.get("DongleId") or "N/A"} · {self._ui.params.get("HardwareSerial") or "N/A"}'
    if self._local() and (error := calibration_reset.take_error()):
      self._notify(error)

  def ids(self) -> str:
    """The device ID and hardware serial."""
    return self._ids

  def imei(self) -> str:
    """The last IMEI obtained from the modem."""
    return self._imei or N_("Not available")

  def show_regulatory(self) -> bool:
    """The release regulatory row is shown on comma 3 hardware."""
    from openpilot.common.hardware import HARDWARE

    return HARDWARE.get_device_type() in ("tici", "tizi")

  def pairing_qr(self) -> rl.Texture | None:
    """Use the native token and five-minute refresh without pushing a second screen."""
    from openpilot.selfdrive.ui.widgets.pairing_dialog import PairingDialog

    self.poll()
    if not self.pairing_supported() or self.is_paired():
      self._pairing = None
      return None
    if self._pairing is None:
      self._pairing = PairingDialog()
    self._pairing._check_qr_refresh()
    return self._pairing.qr_texture

  def review_guide(self) -> None:
    """Open the native training guide if the car is off."""
    from openpilot.selfdrive.ui.layouts.onboarding import TrainingGuide
    from openpilot.system.ui.lib.application import gui_app

    if self.is_offroad():
      gui_app.push_widget(TrainingGuide())

  @cached_property
  def _galaxy(self) -> GalaxyAccessFlow:
    from openpilot.starpilot.galaxy.access import default_owner
    from openpilot.starpilot.ui.galaxy_access import GalaxyAccessFlow

    return GalaxyAccessFlow(default_owner(), self.is_offroad)

  def remote_access_link(self) -> str:
    """Read the current link from StarPilot's native Galaxy flow."""
    return self._galaxy.update_remote().url if self._local() else ""

  def remote_access_label(self) -> str:
    """Keep the release setup and management labels."""
    return N_("Manage") if self.remote_access_link() else N_("Set Up")

  def remote_access_qr(self) -> rl.Texture | None:
    """Replace the link QR when the native flow changes its URL."""
    from openpilot.common.qrcode import make_texture

    link = self.remote_access_link()
    if self._remote_code is not None and self._remote_code[0] != link:
      rl.unload_texture(self._remote_code[1])
      self._remote_code = None
    if link and self._remote_code is None:
      self._remote_code = (link, make_texture(link))
    return self._remote_code[1] if self._remote_code is not None else None

  def set_up_remote_access(self) -> None:
    """Pass a confirmed password to StarPilot's Galaxy pairing flow."""
    if not self.is_offroad() or self.remote_access_link() or self._galaxy.busy:
      return

    def entered(password: str) -> None:
      if self.is_offroad() and not self.remote_access_link():
        self._galaxy.pair(password)

    self._ask_password(6 if self._galaxy.remote.legacy else 8, entered)

  def unpair_remote_access(self) -> None:
    """Recheck vehicle admission after the release confirmation."""
    if self.is_offroad() and self.remote_access_link():
      self._galaxy.unpair()
