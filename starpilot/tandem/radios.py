"""Independent Wi-Fi and cellular radio controls through NetworkManager."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
import threading
import time
from typing import Any, TYPE_CHECKING

from openpilot.system.ui.lib.networkmanager import NM, NM_IFACE, NM_PATH

if TYPE_CHECKING:
  from jeepney.io.blocking import DBusConnection
  from jeepney.low_level import Message


class Radio(StrEnum):
  """NetworkManager's separate Wi-Fi and mobile broadband switches."""

  WIFI = "wifi"
  CELLULAR = "wwan"


@dataclass(frozen=True)
class RadioState:
  """The radio's effective state and whether the current user can change it."""

  enabled: bool
  hardware_enabled: bool
  allowed: bool

  @property
  def can_toggle(self) -> bool:
    return self.allowed and (self.enabled or self.hardware_enabled)


_PROPERTIES = {
  Radio.WIFI: ("WirelessEnabled", "WirelessHardwareEnabled", 0x1),
  Radio.CELLULAR: ("WwanEnabled", "WwanHardwareEnabled", 0x2),
}


class RadioError(RuntimeError):
  """A radio request was rejected or the radio is unavailable."""


def _connect() -> DBusConnection:
  from jeepney.io.blocking import open_dbus_connection
  return open_dbus_connection(bus="SYSTEM", auth_timeout=2)


def _reply(connection: DBusConnection, message: Message) -> tuple[Any, ...]:
  from jeepney.low_level import MessageType
  reply = connection.send_and_get_reply(message, timeout=2)
  if reply.header.message_type == MessageType.error:
    raise RadioError("NetworkManager rejected the radio request")
  return tuple(reply.body)


def _states(props: dict[str, tuple[str, Any]], permissions: dict[str, str]) -> dict[Radio, RadioState]:
  flags = props.get("RadioFlags", ("u", None))[1]
  states = {}
  for radio, (switch, hardware, bit) in _PROPERTIES.items():
    if isinstance(flags, int) and not flags & bit:
      continue
    enabled = props.get(switch, ("b", None))[1]
    hardware_enabled = props.get(hardware, ("b", None))[1]
    if isinstance(enabled, bool) and isinstance(hardware_enabled, bool):
      allowed = permissions.get(f"{NM}.enable-disable-{radio}") == "yes"
      states[radio] = RadioState(enabled, hardware_enabled, allowed)
  return states


class NetworkRadios:
  """Read and change only radio properties, keeping connection profiles intact."""

  def __init__(self, connect: Callable[[], DBusConnection] = _connect) -> None:
    self._connect = connect

  def read(self) -> dict[Radio, RadioState]:
    """Read available radios and permissions. Call from a worker."""
    from jeepney import DBusAddress, Properties, new_method_call

    address = DBusAddress(NM_PATH, bus_name=NM, interface=NM_IFACE)
    with closing(self._connect()) as connection:
      props, = _reply(connection, Properties(address).get_all())
      permissions, = _reply(connection, new_method_call(address, "GetPermissions"))
    return _states(props, permissions)

  def set_enabled(self, radio: Radio, enabled: bool) -> RadioState:
    """Change one radio and read back its state. Call from a worker."""
    from jeepney import DBusAddress, Properties, new_method_call

    address = DBusAddress(NM_PATH, bus_name=NM, interface=NM_IFACE)
    properties = Properties(address)
    with closing(self._connect()) as connection:
      props, = _reply(connection, properties.get_all())
      permissions, = _reply(connection, new_method_call(address, "GetPermissions"))
      state = _states(props, permissions).get(radio)
      if state is None or not state.allowed or (enabled and not state.hardware_enabled):
        raise RadioError("Radio is unavailable")
      if state.enabled == enabled:
        return state
      _reply(connection, properties.set(_PROPERTIES[radio][0], "b", enabled))
      props, = _reply(connection, properties.get_all())
      state = _states(props, permissions).get(radio)
      if state is None:
        raise RadioError("Radio state is unavailable after the request")
      return state


class RadioControls:
  """Keep D-Bus off the UI thread and read only while a Connections page is open."""

  def __init__(self, backend: NetworkRadios | None = None) -> None:
    self._backend = backend or NetworkRadios()
    self._states: dict[Radio, RadioState] = {}
    self._read_job: threading.Thread | None = None
    self._write_job: threading.Thread | None = None
    self._next_read = 0.0
    self.failed: Radio | None = None
    self.read_failed = False

  @property
  def writing(self) -> bool:
    """Whether a user-requested change is waiting or running."""
    return self._write_job is not None and self._write_job.is_alive()

  def state(self, radio: Radio) -> RadioState | None:
    return self._states.get(radio)

  def refresh(self) -> None:
    now = time.monotonic()
    if self.writing or now < self._next_read or (self._read_job is not None and self._read_job.is_alive()):
      return
    self._next_read = now + 2.0

    def read() -> None:
      try:
        self._states = self._backend.read()
        self.read_failed = False
      except Exception:
        self.read_failed = True

    self._read_job = threading.Thread(target=read, daemon=True)
    self._read_job.start()

  def set_enabled(self, radio: Radio, enabled: bool) -> None:
    state = self.state(radio)
    if self.writing or state is None or not state.can_toggle or state.enabled == enabled:
      return
    read_job = self._read_job
    self.failed = None

    def write() -> None:
      # Finish an in-flight refresh first so it cannot overwrite the confirmed change.
      if read_job is not None:
        read_job.join()
      try:
        result = self._backend.set_enabled(radio, enabled)
        self._states = {**self._states, radio: result}
        if result.enabled != enabled:
          self.failed = radio
      except Exception:
        self.failed = radio

    self._write_job = threading.Thread(target=write, daemon=True)
    self._write_job.start()
