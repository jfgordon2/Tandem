"""Page-scoped, read-only ModemManager/NetworkManager observations.

No AT commands, HTTP probes, connection changes or independent daemon. The
worker owns its D-Bus connection; drawing only reads a small immutable snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
import threading
import time
from typing import Any
from collections.abc import Callable

MM = "org.freedesktop.ModemManager1"
MODEM = MM + ".Modem"
GPP = MODEM + ".Modem3gpp"
BEARER = MM + ".Bearer"
NM = "org.freedesktop.NetworkManager"
ACTIVE = NM + ".Connection.Active"
DEVICE = NM + ".Device"
INTERVAL = 2.0
FRESH = 8.0
APPLY_TIMEOUT = 60.0


@dataclass(frozen=True)
class Observation:
  """One reading of the modem and connection: SIM, registration, technology, signal, address and APN."""
  sim: bool | None = None
  modem: int | None = None
  registration: int | None = None
  technology: str = ""
  quality: int | None = None
  connected: bool = False
  connecting: bool = False
  failed: bool = False
  wifi: bool = False
  address: str = ""
  bearer_apn: str | None = None
  applied_apn: str | None = None
  auto_config: bool | None = None
  identity: tuple = ()


@dataclass(frozen=True)
class Status:
  """The cellular status the settings show: a code (connected, no_sim, ...) and the reading behind it."""
  code: str = "checking"
  observation: Observation | None = None


def technology(bits: int) -> str:
  """The access technology (5G, LTE, 3G or 2G) from ModemManager's AccessTechnologies bits; "" when none is set."""
  if bits & (1 << 15):
    return "5G"
  if bits & ((1 << 14) | (1 << 16) | (1 << 17)):
    return "LTE"
  if bits & sum(1 << i for i in range(5, 14)):
    return "3G"
  if bits & sum(1 << i for i in range(1, 5)):
    return "2G"
  return ""


def unwrap(value: Any) -> Any:
  if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
    return unwrap(value[1])
  if isinstance(value, dict):
    return {key: unwrap(item) for key, item in value.items()}
  if isinstance(value, (tuple, list)):
    return type(value)(unwrap(item) for item in value)
  return value


class Cancelled(Exception):
  """The page closed while a read was in progress."""


def _close(reader: Reader | None) -> None:
  if reader is not None:
    try:
      reader.close()
    except Exception:
      pass


class Reader:
  """Reads ModemManager and NetworkManager over the system D-Bus. Read-only."""

  def __init__(self, keep: Callable[[], bool] = lambda: True) -> None:
    from jeepney import DBusAddress, new_method_call
    from jeepney.io.blocking import open_dbus_connection
    from jeepney.low_level import MessageType
    self.address, self.call, self.error = DBusAddress, new_method_call, MessageType.error
    self.keep = keep
    self.connection = open_dbus_connection(bus="SYSTEM", auth_timeout=2)

  def request(self, bus: str, path: str, interface: str, method: str, signature: str | None = None, body: tuple = ()) -> Any:
    if not self.keep():
      raise Cancelled()
    msg = self.call(self.address(path, bus_name=bus, interface=interface), method, signature, body)
    reply = self.connection.send_and_get_reply(msg, timeout=2)
    if reply.header.message_type == self.error:
      raise RuntimeError("Cellular status unavailable")  # never log a D-Bus payload
    return unwrap(reply.body)

  def props(self, bus: str, path: str, interface: str) -> dict:
    return dict(self.request(bus, path, "org.freedesktop.DBus.Properties", "GetAll", "s", (interface,))[0])

  def close(self) -> None:
    self.connection.close()

  def read(self) -> Observation:
    """One observation of the modem (the connected one when there are several), its bearer and NetworkManager's state."""
    objects = self.request(MM, "/org/freedesktop/ModemManager1", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")[0]
    modems = [(path, interfaces) for path, interfaces in objects.items() if MODEM in interfaces]
    if not modems:
      return Observation()
    # Prefer the connected modem if a device exposes more than one.
    path, interfaces = max(modems, key=lambda row: row[1][MODEM].get("State", 0))
    modem, gpp = interfaces[MODEM], interfaces.get(GPP, {})
    state = modem.get("State")
    sim_path = modem.get("Sim")
    sim = None
    if sim_path and sim_path != "/":
      sim = True
    elif sim_path == "/" and (state is not None and state >= 3 or modem.get("StateFailedReason") == 2):
      sim = False
    quality, recent = modem.get("SignalQuality", (0, False))
    quality = min(100, max(0, int(quality))) if recent else None
    nm = self.props(NM, "/org/freedesktop/NetworkManager", NM)
    wifi, connecting, failed = False, state in (7, 10), state in (-1, 2) or gpp.get("RegistrationState") == 3
    connected, address, bearer_apn, applied_apn, auto_config = False, "", None, None, None
    identity: tuple = ()
    # Bearers need not be exported by ObjectManager (some versions manage only
    # modem objects). Read their properties directly when absent from its reply.
    bearers = [(name, objects.get(name, {}).get(BEARER) or self.props(MM, name, BEARER)) for name in modem.get("Bearers", [])]
    for active_path in nm.get("ActiveConnections", []):
      active = self.props(NM, active_path, ACTIVE)
      active_state, kind = active.get("State"), active.get("Type")
      if kind == "802-11-wireless" and active_state == 2:
        wifi |= bool(active.get("Default") or active.get("Default6"))
      if kind != "gsm":
        continue
      for device_path in active.get("Devices", []):
        device = self.props(NM, device_path, DEVICE)
        if device.get("DeviceType") != 8:
          continue
        iface = device.get("IpInterface") or device.get("Interface")
        matching = [(name, props) for name, props in bearers if props.get("Connected") and props.get("Interface") == iface]
        if device.get("Udi") != path and not matching and len(modems) != 1:
          continue
        connecting |= active_state == 1 or 40 <= device.get("State", 0) < 100
        failed |= device.get("State") == 120
        if active_state != 2 or state != 11 or not matching:
          continue
        name, bearer = matching[0]
        connected = True
        identity = (path, name, active_path)
        bearer_apn = bearer.get("Properties", {}).get("apn")
        try:
          applied = self.request(NM, device_path, DEVICE, "GetAppliedConnection", "u", (0,))[0].get("gsm", {})
          applied_apn, auto_config = applied.get("apn"), applied.get("auto-config")
        except (OSError, RuntimeError):
          pass  # older NM may omit applied settings; the bearer still identifies an explicit APN
        for field, interface in (("Ip4Config", NM + ".IP4Config"), ("Ip6Config", NM + ".IP6Config")):
          config = active.get(field, "/")
          if config == "/":
            continue
          for entry in self.props(NM, config, interface).get("AddressData", []):
            try:
              value = ipaddress.ip_address(entry.get("address", ""))
              if not (value.is_unspecified or value.is_loopback or value.is_link_local):
                address = str(value)
                break
            except ValueError:
              pass
          if address:
            break
    return Observation(sim, state, gpp.get("RegistrationState"), technology(modem.get("AccessTechnologies", 0)), quality,
                       connected, connecting, failed, wifi, address, bearer_apn, applied_apn, auto_config, identity)


class Monitor:
  """Reads cellular status in the background while the page is open, and judges what it means for the chosen APN."""

  def __init__(self, reader_factory: Callable[..., Reader] | None = Reader, clock: Callable[[], float] = time.monotonic) -> None:
    self.factory, self.clock = reader_factory, clock
    self._lock = threading.RLock()
    self._wake = threading.Event()
    self._thread: threading.Thread | None = None
    self._active = False
    self._generation = 0
    self._observation: Observation | None = None
    self._updated: float | None = None
    self._target = ""
    self._pending: float | None = None
    self._baseline: tuple = ()
    self._changed_auto = False
    self._saw_down = False

  def set_active(self, active: bool, apn: str | None = None) -> None:
    """Starts or stops reading, as the page shows or hides.

    Args:
      active: The page is open.
      apn: The APN the driver chose, when known.
    """
    with self._lock:
      if apn is not None and apn != self._target:
        self._target = apn
        self._generation += 1
      if self._active != active:
        self._active = active
        self._generation += 1
        self._updated = None
      if active and self.factory is not None and self._thread is None:
        self._thread = threading.Thread(target=self._run, name="tandem-cellular-status", daemon=True)
        self._thread.start()
      self._wake.set()

  def apn_saved(self, apn: str, previous: str) -> None:
    """Notes a saved APN, so the status waits for the connection to come back with it instead of trusting the old one."""
    with self._lock:
      self._baseline = self._observation.identity if self._observation else ()
      self._changed_auto = not apn and apn != previous
      self._saw_down = False
      self._target, self._pending = apn, self.clock()
      self._observation, self._updated = None, None
      self._generation += 1
      self._wake.set()

  def status(self) -> Status:
    """The status for the page: checking until a fresh reading, then what it says, judged against the chosen APN."""
    with self._lock:
      now = self.clock()
      pending = self._pending is not None and 0 <= now - self._pending < APPLY_TIMEOUT
      value = self._observation
      if value is None or self._updated is None or not 0 <= now - self._updated <= FRESH:
        return Status("connecting" if pending else "checking")
      if value.sim is False:
        return Status("no_sim", value)
      if value.sim is None or value.modem in (None, 0, 1, 4, 5):
        return Status("checking", value)
      matches = (value.bearer_apn or "").strip().casefold() == self._target.casefold() if self._target else True
      if self._changed_auto:
        matches = value.auto_config is True or self._saw_down or value.identity != self._baseline
      if value.connected and matches:
        self._pending = None
        return Status("connected", value)
      if (value.modem in (6, 7) and value.registration in (0, 2) and value.quality in (None, 0) and not value.technology):
        return Status("no_signal", value)
      if value.failed:
        return Status("not_connected", value)
      if pending or value.connecting:
        return Status("connecting", value)
      if value.connected:  # an old APN/bearer cannot confirm the requested settings
        return Status("not_connected", value)
      return Status("wifi" if value.wifi else "not_connected", value)

  def _run(self) -> None:
    factory = self.factory
    if factory is None:   # set_active starts this thread only with a reader
      return
    reader: Reader | None = None
    try:
      while True:
        with self._lock:
          if not self._active:
            return
          generation = self._generation
          self._wake.clear()
        try:
          if reader is None:
            reader = factory(lambda: self._active)
          value = reader.read()
        except Cancelled:
          continue
        except Exception:
          value = None
          if reader is not None:
            _close(reader)
            reader = None
        with self._lock:
          if self._active and generation == self._generation:
            self._observation, self._updated = value, self.clock() if value is not None else None
            if value is not None and not value.connected:
              self._saw_down = True
        self._wake.wait(INTERVAL)
    finally:
      _close(reader)
      with self._lock:
        self._thread = None
        # A rapid hide/show may race the worker's exit. Restart without blocking drawing.
        if self._active:
          self.set_active(True)


def monitor() -> Monitor:
  return Monitor(reader_factory=Reader if Path("/TICI").exists() else None)
