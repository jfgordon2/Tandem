"""StarPilot 7's Bluetooth and controller owners as the Connections screens' sources (settings/bluetooth_tab.py).

StarPilotBluetooth drives StarPilot's NativeBluetoothOwner, as StarPilot's own Bluetooth page does: its D-Bus work runs on
one worker thread, a pairing session lasts while the page is shown, and StarPilot decides what's allowed (pairing and
power only while parked). StarPilot 7 plays no openpilot sounds through Bluetooth, so release's car-audio switch and
sound test have nothing to drive.

StarPilotControllers drives StarPilot's ControllerOwner, the one the controller runtime (star_input.py) feeds presses to.
A remote's button is learned into one of StarPilot's ten action slots and the slot holds its action; StarPilot changes
bindings only while parked. Its three Quick Select slots take a button learned straight into them, which this screen
doesn't offer, so remotes choose from StarPilot's action list.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from openpilot.selfdrive.ui.tandem.i18n import t_

QUICK_SELECT = 3   # StarPilot's slots 0-2 are Quick Select; 3-12 hold an action each


@dataclass(frozen=True)
class BluetoothDevice:
  """A device StarPilot's Bluetooth owner lists."""
  address: str
  name: str
  paired: bool = False
  connected: bool = False
  audio: bool = False
  controller: bool = False


@dataclass(frozen=True)
class BluetoothStatus:
  """The radio and its devices, as the screens read them."""
  available: bool = False
  enabled: bool = False
  powered: bool = False
  discovering: bool = False
  offroad: bool = False
  devices: tuple[BluetoothDevice, ...] = field(default_factory=tuple)
  selected_audio: str = ""


def _owner(parked: Callable[[], bool], session_valid: Callable[[tuple], bool]) -> Any:
  from openpilot.starpilot.bluetooth.native_owner import NativeBluetoothOwner
  return NativeBluetoothOwner(parked, session_valid=session_valid)


class StarPilotBluetooth:
  """BluetoothDevices over StarPilot's Bluetooth owner.

  Args:
    parked: Whether StarPilot confirms the car is parked.
    owner: Makes the owner (parked, session_valid); StarPilot's NativeBluetoothOwner by default.
    clock: Monotonic seconds.
    executor: Makes the worker; one thread by default.
  """
  REFRESH_S = 2.0

  def __init__(self, parked: Callable[[], bool], owner: Callable[..., Any] = _owner, clock: Callable[[], float] = time.monotonic,
               executor: Callable[[], Any] = lambda: ThreadPoolExecutor(max_workers=1, thread_name_prefix="tandem-bluetooth")):
    self._parked, self._make_owner, self._clock, self._make_executor = parked, owner, clock, executor
    self._owner: Any = None
    self._executor: Any = None
    self._pending: Future | None = None
    self._operation = ""
    self._active = False
    self._session: tuple | None = None
    self._snapshot: dict = {}
    self._next = 0.0
    self._scanned = False

  def _valid(self, identity: tuple) -> bool:
    return self._active and identity == self._session

  def _submit(self, operation: str, work: Callable[[], dict]) -> bool:
    """Run work on the worker; one at a time, as StarPilot's page does. False when another is still running."""
    if self._pending is not None and not self._pending.done():
      return False
    if self._executor is None:
      self._executor = self._make_executor()
    if self._owner is None:
      self._owner = self._make_owner(self._parked, session_valid=self._valid)
    self._operation = operation
    self._pending = self._executor.submit(work)
    return True

  def _request(self, operation: str, **kwargs: Any) -> bool:
    session = self._session

    def work() -> dict:
      return self._owner.request(operation, session=session, **kwargs)
    return self._submit(operation, work)

  def _collect(self) -> None:
    pending = self._pending
    if pending is None or not pending.done():
      return
    self._pending = None
    try:
      result = pending.result()
    except Exception:   # a refusal (not parked, busy) or the radio being away: the next read shows what's true
      self._next = 0.0
      return
    if isinstance(result, dict) and isinstance(result.get("devices"), list):
      self._snapshot = result

  def tick(self) -> None:
    """Keep the page current: collect the last answer, read again every REFRESH_S, and search for devices while it's open."""
    if not self._active:
      return
    self._collect()
    now = self._clock()
    status = self.status()
    if status.powered and status.offroad and not status.discovering and not self._scanned and not self._snapshot.get("pairing"):
      if self._request("scan"):
        self._scanned = True
        return
    if now >= self._next and self._submit("snapshot", lambda: self._owner.snapshot(session=self._session)):
      self._next = now + self.REFRESH_S

  def set_active(self, active: bool) -> None:
    """A pairing session while the page is shown; leaving stops the search and frees the radio."""
    if active == self._active:
      return
    self._active = active
    if active:
      self._session = ("tandem", uuid.uuid4().hex)
      self._scanned = False
      self._next = 0.0
      self.tick()
      return
    self._session = None
    owner, executor = self._owner, self._executor
    if owner is not None and executor is not None:
      executor.submit(owner.close)
      executor.shutdown(wait=False, cancel_futures=False)
    self._owner = self._executor = self._pending = None
    self._snapshot = {}

  def status(self) -> BluetoothStatus:
    snap = self._snapshot
    devices = tuple(BluetoothDevice(str(d.get("address", "")), str(d.get("name") or d.get("address") or ""), bool(d.get("paired")),
                                    bool(d.get("connected")), bool(d.get("audioSink"))) for d in snap.get("devices", []))
    powered = bool(snap.get("powered"))
    return BluetoothStatus(available=bool(snap.get("available")), enabled=powered, powered=powered,
                           discovering=bool(snap.get("discovering")), offroad=bool(self._parked()), devices=devices)

  def set_power(self, enabled: bool) -> None:
    status = self.status()
    if status.available and status.offroad and status.enabled != enabled:
      self._scanned = False
      self._request("power", enabled=enabled)

  def power_busy(self) -> bool:
    return self._operation == "power" and self._pending is not None and not self._pending.done()

  def select(self, address: str) -> bool:
    """Pair a new device or connect a paired one; True when it's already connected and its actions should show."""
    device = next((d for d in self.status().devices if d.address.upper() == address.upper()), None)
    if device is None:
      return False
    if device.paired and device.connected:
      return True
    if device.paired:
      self._request("connect", address=device.address)
    else:
      self._request("pair", address=device.address)
    return False

  def disconnect(self, address: str) -> None:
    self._request("disconnect", address=address)

  def forget(self, address: str) -> None:
    self._request("forget", address=address)

  def prompt(self) -> dict | None:
    """StarPilot's pairing prompt as the screens show it: id, name, kind, value and whether it only shows a code."""
    pairing = self._snapshot.get("pairing") or {}
    prompt = pairing.get("prompt")
    if not prompt:
      return None
    address = str(pairing.get("address", ""))
    name = next((d.name for d in self.status().devices if d.address.upper() == address.upper()), pairing.get("name") or address)
    return {"id": prompt.get("id", ""), "name": name, "kind": prompt.get("kind", ""), "value": prompt.get("value", ""),
            "display_only": bool(prompt.get("displayOnly"))}

  def respond(self, prompt_id: str, accept: bool, value: str = "") -> None:
    self._request("pairing_response", prompt_id=prompt_id, accepted=accept, value=value)


class StarPilotControllers:
  """WheelSource over StarPilot's ControllerOwner.

  Args:
    owner: Gives StarPilot's ControllerOwner, or None when the controller runtime isn't running.
  """
  favorite_slots = QUICK_SELECT

  def __init__(self, owner: Callable[[], Any]):
    self._owner = owner
    self._testing = False

  def _snapshot(self) -> dict:
    owner = self._owner()
    return owner.snapshot() if owner is not None else {}

  def _action(self, payload: dict) -> bool:
    owner = self._owner()
    if owner is None:
      return False
    try:
      owner.action(payload)
    except (PermissionError, RuntimeError, ValueError, OSError):
      return False
    return True

  def _save(self, slot: int, key: str | None) -> bool:
    snap = self._snapshot()
    slots = [s["key"] for s in snap.get("slots", [])[QUICK_SELECT:]]
    if not slots or not QUICK_SELECT <= slot < QUICK_SELECT + len(slots):
      return False
    slots[slot - QUICK_SELECT] = key
    return self._action({"operation": "save", "revision": snap.get("revision"), "enabled": True, "slots": slots})

  def mappings(self) -> list[dict]:
    """The remote's learned buttons: id, slot, the remote's name, and a name for the button."""
    return [{"id": f"{b['deviceId']}:{b['code']}", "slot": b["slot"], "device_name": b["name"], "deviceId": b["deviceId"],
             "code": b["code"], "event_name": t_("Button {}", b["code"])} for b in self._snapshot().get("bindings", [])]

  def action(self, slot: int) -> str | None:
    slots = self._snapshot().get("slots", [])
    return slots[slot]["key"] if 0 <= slot < len(slots) else None

  def actions(self) -> list[tuple[str, str]]:
    return [(o["key"], o["label"]) for o in self._snapshot().get("options", [])]

  def status(self) -> dict:
    """What the screens read: testing, the last tested or learned press, the learning countdown, and the remotes."""
    snap = self._snapshot()
    press = snap.get("lastPress") or {}
    if self._testing and not snap.get("testing") and not snap.get("learning"):
      self._action({"operation": "test", "enabled": True})   # StarPilot's test lasts 20 s; keep it while the page is open
    out: dict[str, Any] = {"testing": bool(snap.get("testing")), "devices": snap.get("devices", [])}
    learning = snap.get("learning")
    if learning:
      out["remaining_seconds"] = float(learning.get("expiresIn", 0))
    if press:
      identity = f"{press.get('deviceId')}:{press.get('code')}"
      if press.get("message") == "Button learned":
        out["last_learned"] = {"id": identity, "slot": press.get("slot"), "event_name": t_("Button {}", press.get("code"))}
      elif press.get("message") == "Test press detected":
        out["last_tested"] = {"mapped": press.get("slot") is not None, "slot": press.get("slot")}
    return out

  def start_learning(self, slot: int) -> None:
    snap = self._snapshot()
    self._action({"operation": "learn", "revision": snap.get("revision"), "slot": slot})

  def cancel_learning(self) -> None:
    self._action({"operation": "cancel"})

  def start_testing(self) -> None:
    self._testing = True
    self._action({"operation": "test", "enabled": True})

  def stop_testing(self) -> None:
    self._testing = False
    self._action({"operation": "test", "enabled": False})

  def free_slot(self) -> int | None:
    """An action slot no button uses and no action fills."""
    snap = self._snapshot()
    used = {b["slot"] for b in snap.get("bindings", [])}
    return next((s["index"] for s in snap.get("slots", [])[QUICK_SELECT:] if s["key"] is None and s["index"] not in used), None)

  def assign(self, mapping_id: str, key: str) -> bool:
    """Give a learned button an action, through its own action slot; False for a button on a Quick Select or shared slot,
    which StarPilot can only move by learning it again."""
    mappings = self.mappings()
    mapping = next((m for m in mappings if m["id"] == mapping_id), None)
    if mapping is None or key not in dict(self.actions()):
      return False
    slot = mapping["slot"]
    if slot < QUICK_SELECT or sum(m["slot"] == slot for m in mappings) > 1:
      return False
    return self._save(slot, key)

  def delete(self, mapping_id: str) -> None:
    mappings = self.mappings()
    mapping = next((m for m in mappings if m["id"] == mapping_id), None)
    if mapping is None:
      return
    snap = self._snapshot()
    if self._action({"operation": "remove", "revision": snap.get("revision"), "deviceId": mapping["deviceId"], "code": mapping["code"]}):
      slot = mapping["slot"]
      if slot >= QUICK_SELECT and not any(m["slot"] == slot for m in mappings if m["id"] != mapping_id):
        self._save(slot, None)   # its slot holds no action once no button uses it
