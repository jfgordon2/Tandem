"""Receive-only CAN test logs and tap markers, with an optional guarded OBD input adapter."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import datetime
import gzip
import json
from pathlib import Path
import queue
import secrets
import shutil
import threading
import time

ACTIVE = {"starting", "recording", "saving", "aborting"}
MAX_SECONDS = 600
OBD_MAX_SECONDS = 120
MIN_FREE_BYTES = 64 * 1024 * 1024
CLOCK_ID = getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC)
CLOCK_NAME = "CLOCK_BOOTTIME" if hasattr(time, "CLOCK_BOOTTIME") else "CLOCK_MONOTONIC"
GM_FOCUS_EXCLUDED = {
  0xBE: "ECMAcceleratorPos", 0xD1: "EBCMBrakePedalSensors", 0xF1: "EBCMBrakePedalPosition",
  0x180: "ASCMLKASteeringCmd", 0x1A1: "AcceleratorPedal", 0x1C4: "AcceleratorPedal2",
  0x1E5: "PSCMSteeringAngle", 0x2CB: "ASCMGasRegenCmd", 0x348: "EBCMWheelSpdFront", 0x34A: "EBCMWheelSpdRear",
}


def boot_time_ns() -> int:
  """Match cereal/messaging/messaging.h and common/timing.h, including the macOS fallback."""
  return time.clock_gettime_ns(CLOCK_ID)


@dataclass(frozen=True)
class RecorderState:
  phase: str = "idle"
  session: str = ""
  started_ns: int = 0
  ended_ns: int = 0
  frames: int = 0
  lock_markers: int = 0
  unlock_markers: int = 0
  last_kind: str = ""
  last_marker_ns: int = 0
  reason: str = ""
  power_save: bool | None = None
  input: str = "camera"
  obd_frames: int = 0


class RecorderError(Exception):
  def __init__(self, reason):
    super().__init__(reason)
    self.reason = reason


def default_folder() -> Path:
  from openpilot.system.hardware import PC
  if PC:
    from openpilot.system.hardware.hw import Paths
    return Path(Paths.comma_home()) / "tandem" / "diagnostics" / "can-tests"
  return Path("/data/tandem/diagnostics/can-tests")


class CanSource:
  """Subscribe to pandad's existing feed; this never opens or reconfigures a panda."""

  def __init__(self):
    from cereal import messaging
    from openpilot.common.params import Params
    from openpilot.starpilot.tandem.bluetooth import ParkMonitor
    self._messaging = messaging
    self._params = Params()
    self._park = ParkMonitor()
    self._can = messaging.sub_sock("can", timeout=50)
    self._panda = messaging.sub_sock("pandaStates", conflate=True, timeout=0)

  def allowed(self) -> bool:
    return self._params.get_bool("IsOffroad") or self._park.allowed()

  def info(self) -> dict:
    return self.info_from_params()

  @staticmethod
  def info_from_params() -> dict:
    from cereal import car
    from openpilot.common.params import Params
    raw = Params().get("CarParamsPersistent")
    if raw:
      with car.CarParams.from_bytes(raw) as cp:
        return {"fingerprint": cp.carFingerprint, "brand": getattr(cp, "brand", ""), "network_location": str(cp.networkLocation)}
    return {}

  def poll(self) -> tuple[list[tuple[int, int, int, bytes]], dict | None]:
    health = self._messaging.recv_one_or_none(self._panda)
    state = None
    if health is not None:
      state = {"time_ns": health.logMonoTime, "pandas": [
        {"power_save": p.powerSaveEnabled, "safety": str(p.safetyModel), "rx_overflow": p.rxBufferOverflow,
         "spi_errors": p.spiErrorCount, "faults": [str(f) for f in p.faults],
         "buses": [{"speed": c.canSpeed, "rx_lost": c.totalRxLostCnt, "tx": c.totalTxCnt} for c in (p.canState0, p.canState1, p.canState2)]}
        for p in health.pandaStates]}
    msg = self._messaging.recv_one(self._can)
    frames = [(msg.logMonoTime, f.src, f.address, bytes(f.dat)) for f in msg.can if f.src < 128] if msg is not None else []
    return frames, state


class CanRecorder:
  def __init__(self, folder: Path | None = None, source: Callable = CanSource, clock_ns: Callable[[], int] = boot_time_ns,
               max_seconds: float = MAX_SECONDS, obd_source: Callable | None = None):
    self._folder = folder
    self._source = source
    self._obd_source = obd_source
    self._clock_ns = clock_ns
    self._max_seconds = max_seconds
    self._lock = threading.Lock()
    self._state = RecorderState()
    self._thread: threading.Thread | None = None
    self._stop = threading.Event()
    self._abort_requested = threading.Event()
    self._directory: Path | None = None
    self._markers: queue.SimpleQueue = queue.SimpleQueue()
    self._stop_reason = "user"

  def snapshot(self) -> RecorderState:
    with self._lock:
      return self._state

  def _update(self, **values):
    with self._lock:
      if self._abort_requested.is_set() and "phase" in values:
        values["phase"] = "aborting"
      self._state = replace(self._state, **values)

  def start(self, obd: bool = False) -> bool:
    with self._lock:
      if self._state.phase in ACTIVE or self._state.reason in {"delete", "obd_restore"} or (self._thread is not None and self._thread.is_alive()):
        return False
      session = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(3)
      self._state = RecorderState(phase="starting", session=session, started_ns=self._clock_ns(), input="obd" if obd else "camera")
      self._markers = queue.SimpleQueue()
      self._stop.clear()
      self._abort_requested.clear()
      self._directory = None
      self._stop_reason = "user"
      self._thread = threading.Thread(target=self._run, daemon=True, name="tandem-can-recorder")
      self._thread.start()
    return True

  def mark(self, kind: str) -> bool:
    # Capture the tap time here, before the worker or filesystem can delay the event.
    stamp = self._clock_ns()
    if kind not in {"lock", "unlock"}:
      return False
    with self._lock:
      if self._state.phase != "recording":
        return False
      self._markers.put({"time_ns": stamp, "elapsed_ns": stamp-self._state.started_ns, "event": kind})
    return True

  def stop(self, reason: str = "user") -> None:
    with self._lock:
      if self._state.phase in {"starting", "recording"}:
        self._stop_reason = reason
        self._state = replace(self._state, phase="saving")
        self._stop.set()

  def abort(self) -> bool:
    """Discard only this session, after its writer has closed. Never wait on the UI thread."""
    with self._lock:
      if not self._state.session or self._state.phase == "aborting":
        return False
      self._abort_requested.set()
      self._stop.set()
      self._state = replace(self._state, phase="aborting")
      writer = self._thread
      self._thread = threading.Thread(target=self._discard, args=(writer,), daemon=True, name="tandem-can-discard")
      self._thread.start()
    return True

  def _discard(self, writer):
    if writer is not None:
      writer.join()
    try:
      if self._directory is not None and self._directory.exists():
        shutil.rmtree(self._directory)
      with self._lock:
        self._state = (RecorderState(phase="error", reason="obd_restore") if self._state.reason == "obd_restore"
                       else RecorderState(phase="discarded"))
    except OSError:
      with self._lock:
        self._state = replace(self._state, phase="error", reason="delete", ended_ns=self._clock_ns())

  def _run(self):
    state = self.snapshot()
    directory = None
    source = None
    metadata = {"version": 1, "clock": CLOCK_NAME, "started_ns": state.started_ns, "session": state.session,
                "passive": True, "status": "starting", "input": state.input}

    def close_source():
      nonlocal source
      closing, source = source, None
      close = getattr(closing, "close", None)
      if close is not None:
        close()

    def save_metadata():
      temporary = directory / "metadata.tmp"
      temporary.write_text(json.dumps(metadata, indent=2) + "\n")
      temporary.replace(directory / "metadata.json")

    try:
      root = self._folder if self._folder is not None else default_folder()
      root.mkdir(parents=True, exist_ok=True)
      if shutil.disk_usage(root).free < MIN_FREE_BYTES:
        self._update(phase="error", reason="storage", ended_ns=self._clock_ns())
        return
      if state.input == "obd":
        from openpilot.starpilot.tandem.obd import ObdSource
        source = (self._obd_source or ObdSource)()
      else:
        source = self._source()
      if not source.allowed():
        self._update(phase="error", reason="parked", ended_ns=self._clock_ns())
        return
      candidate = root / state.session
      candidate.mkdir()
      directory = self._directory = candidate
      vehicle = source.info()
      start_source = getattr(source, "open", None)
      if start_source is not None and not self._stop.is_set():
        start_source()
      excluded = GM_FOCUS_EXCLUDED if vehicle.get("brand") == "gm" else {}
      metadata.update(vehicle=vehicle, status="recording", ready_ns=self._clock_ns(),
                      focus_excluded_bus=0, focus_excluded={hex(k): v for k, v in excluded.items()})
      save_metadata()
      with gzip.open(directory / "can.jsonl.gz", "xt", compresslevel=1) as frames_file, \
           gzip.open(directory / "focus.jsonl.gz", "xt", compresslevel=1) as focus_file, \
           (directory / "markers.jsonl").open("x") as markers_file, (directory / "health.jsonl").open("x") as health_file:
        with self._lock:
          if not self._stop.is_set():
            self._state = replace(self._state, phase="recording")
        frame_count = obd_count = lock_count = unlock_count = 0
        last_check = last_flush = self._clock_ns()
        last_kind, last_marker = "", 0
        power_save = None

        def drain_markers():
          nonlocal lock_count, unlock_count, last_kind, last_marker
          while not self._markers.empty():
            marker = self._markers.get_nowait()
            markers_file.write(json.dumps(marker, separators=(",", ":")) + "\n")
            markers_file.flush()
            last_kind, last_marker = marker["event"], marker["time_ns"]
            lock_count += last_kind == "lock"
            unlock_count += last_kind == "unlock"
          self._update(lock_markers=lock_count, unlock_markers=unlock_count, last_kind=last_kind, last_marker_ns=last_marker)

        reason = "user"
        while not self._stop.is_set():
          drain_markers()
          batch, health = source.poll()
          source_reason = getattr(source, "ended_reason", None)
          if source_reason:
            reason = source_reason
            break
          if batch:
            for t, bus, address, data in batch:
              line = json.dumps([t, bus, address, data.hex()], separators=(",", ":")) + "\n"
              frames_file.write(line)
              if bus != 0 or address not in excluded:
                focus_file.write(line)
            frame_count += len(batch)
            obd_count += sum(bus == 1 for _, bus, _, _ in batch)
          if health is not None:
            health_file.write(json.dumps(health, separators=(",", ":")) + "\n")
            power_save = any(p["power_save"] for p in health.get("pandas", []))
          now = self._clock_ns()
          self._update(frames=frame_count, obd_frames=obd_count, power_save=power_save)
          if now-last_flush >= 1_000_000_000:
            frames_file.flush()
            focus_file.flush()
            health_file.flush()
            last_flush = now
          limit = min(self._max_seconds, OBD_MAX_SECONDS) if state.input == "obd" else self._max_seconds
          if now-state.started_ns >= limit*1e9:
            reason = "time_limit"
            break
          if frame_count >= 1_000_000:
            reason = "frame_limit"
            break
          if now-last_check >= 1_000_000_000:
            last_check = now
            if not source.allowed():
              reason = "parked"
              break
            if shutil.disk_usage(root).free < MIN_FREE_BYTES//2:
              reason = "storage"
              break
        with self._lock:
          self._state = replace(self._state, phase="aborting" if self._abort_requested.is_set() else "saving")
          if self._stop.is_set():
            reason = self._stop_reason
        drain_markers()   # preserve every tap accepted before Stop, including taps queued during a CAN read
      ended = self._clock_ns()
      close_source()  # normal input must be restored before Saved is shown or another test can start
      final = self.snapshot()
      metadata.update(status="saved", ended_ns=ended, reason=reason, frames=frame_count,
                      obd_frames=obd_count, lock_markers=final.lock_markers, unlock_markers=final.unlock_markers)
      save_metadata()
      self._update(phase="saved", reason=reason, ended_ns=ended)
    except Exception as error:
      ended = self._clock_ns()
      reason = error.reason if isinstance(error, RecorderError) else "write"
      if directory is not None:
        metadata.update(status="error", reason=reason, ended_ns=ended)
        try:
          save_metadata()
        except OSError:
          pass
      self._update(phase="error", reason=reason, ended_ns=ended)
    finally:
      try:
        close_source()
      except Exception:
        self._update(phase="error", reason="obd_restore", ended_ns=self._clock_ns())
