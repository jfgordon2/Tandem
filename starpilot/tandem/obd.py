"""A leased OBD input for the verified Bolt/GM camera setup. Never sends CAN frames.

The existing GM camera safety policy (parameter 3) permits no TX on bus 1 and forwards only between
buses 0 and 2. Keep that policy, heartbeat, bit rates and pandad unchanged. Only select its spare input.
The independent child restores normal routing on lease expiry, guard failure, Stop, or parent death.
"""
from __future__ import annotations

import json
import os
import fcntl
import select
import signal
import subprocess
import sys
import time

from openpilot.starpilot.tandem.can_recorder import CanSource, OBD_MAX_SECONDS, RecorderError

FINGERPRINT = "CHEVROLET_BOLT_ACC_2022_2023"


def supported(info):
  return info.get("brand") == "gm" and info.get("fingerprint") == FINGERPRINT and info.get("network_location") == "fwdCamera"


class NativeGuard:
  def __init__(self):
    from cereal import messaging
    from openpilot.starpilot.tandem.bluetooth import stationary_park
    self._sm = messaging.SubMaster(["carState", "carControl", "pandaStates"])
    self._parked = stationary_park
    self._tx = None

  def __call__(self):
    self._sm.update(0)
    sm = self._sm
    if not self._parked(sm) or not (sm.valid["pandaStates"] and sm.alive["pandaStates"]):
      return False
    now = time.monotonic()
    if not (0 <= now-sm.recv_time["pandaStates"] <= 1 and 0 <= now-sm.logMonoTime["pandaStates"]/1e9 <= 1):
      return False
    pandas = sm["pandaStates"]
    if len(pandas) != 1:
      return False
    p = pandas[0]
    if str(p.pandaType) != "tres" or str(p.safetyModel) != "gm" or p.safetyParam != 3 or p.controlsAllowed or p.powerSaveEnabled:
      return False
    tx = p.canState1.totalTxCnt
    self._tx = tx if self._tx is None else self._tx
    return tx == self._tx


class Routing:
  """Two route selections, with version-checked reads. Panda.connect() is deliberately never called."""
  def __init__(self):
    from panda import Panda
    from panda.python.spi import PandaSpiHandle
    self._lock = open("/tmp/tandem-obd-input.lock", "a")
    try:
      fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
      self._lock.close()
      raise RecorderError("obd") from None
    self._panda = Panda
    self._handle = None
    try:
      self._handle = PandaSpiHandle()
      versions = self._handle.controlRead(Panda.REQUEST_IN, 0xdd, 0, 0, 3, timeout=500)
      if tuple(versions) != (Panda.HEALTH_PACKET_VERSION, Panda.CAN_PACKET_VERSION, Panda.CAN_HEALTH_PACKET_VERSION):
        raise RecorderError("obd")
      if self._handle.controlRead(Panda.REQUEST_IN, 0xc1, 0, 0, 1, timeout=500) != Panda.HW_TYPE_TRES:
        raise RecorderError("obd")
      reader = object.__new__(Panda)
      reader._handle = self._handle
      reader.health_version, reader.can_version, reader.can_health_version = versions
      health = reader.health()
      if health["safety_mode"] != 4 or health["safety_param"] != 3 or health["controls_allowed"] or health["power_save_enabled"]:
        raise RecorderError("obd")
    except Exception:
      self.close()
      raise

  def select(self, obd):
    # Both native pandad and PandaSpiHandle flock /dev/spidev0.0 for each transaction.
    self._handle.controlWrite(self._panda.REQUEST_OUT, 0xdb, int(obd), 0, b"", timeout=500)

  def close(self):
    try:
      if self._handle is not None:
        self._handle.close()
    finally:
      self._lock.close()


def watch(stream, emit, guard, factory=Routing, clock=time.monotonic, wait=select.select, maximum=OBD_MAX_SECONDS):
  link = None
  reason, restored = "obd_guard", True

  def publish(message):
    try:
      emit(message)
    except (BrokenPipeError, OSError):
      pass   # parent death must not interrupt restoration

  try:
    deadline = clock()+2
    while not guard():
      if clock() >= deadline:
        raise RecorderError("parked")
      time.sleep(.02)
    if not supported(CanSource.info_from_params()):
      raise RecorderError("obd")
    link = factory()
    restored = False   # restore even if the route write succeeds but its acknowledgement is lost
    link.select(True)
    publish({"ready": True})
    start = last = clock()
    while True:
      readable, _, _ = wait([stream], [], [], .2)
      if readable:
        if not stream.readline():
          reason = "closed"
          break
        last = clock()
      now = clock()
      if now-start >= maximum:
        reason = "time_limit"
        break
      if now-last > 2 or not guard():
        break
  except Exception as error:
    publish({"error": error.reason if isinstance(error, RecorderError) else "obd"})
  finally:
    if link is not None:
      for _ in range(3):
        try:
          link.select(False)
          restored = True
          break
        except Exception:
          pass
      try:
        link.close()
      except Exception:
        pass   # route restoration, rather than closing the reader, determines the result
    publish({"closed": True, "restored": restored, "reason": reason})


class Lease:
  def __init__(self):
    self.process = None
    self.ended_reason = None
    self.restored = None
    self._beat = 0.

  def open(self):
    self.process = subprocess.Popen([sys.executable, "-u", "-m", "openpilot.starpilot.tandem.obd"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, bufsize=1, start_new_session=True)
    ready, _, _ = select.select([self.process.stdout], [], [], 6)
    if not ready:
      self.close()
      raise RecorderError("obd")
    msg = json.loads(self.process.stdout.readline())
    if not msg.get("ready"):
      self.close()
      raise RecorderError(msg.get("error", "obd"))

  def tick(self):
    p = self.process
    if p is None or self.ended_reason:
      return
    while select.select([p.stdout], [], [], 0)[0]:
      line = p.stdout.readline()
      if not line:
        self.ended_reason = "obd_guard"
        break
      msg = json.loads(line)
      if msg.get("closed"):
        self.restored = msg["restored"]
        self.ended_reason = msg.get("reason", "obd_guard")
        break
    if not self.ended_reason and time.monotonic()-self._beat >= .3:
      try:
        p.stdin.write("beat\n")
        p.stdin.flush()
        self._beat = time.monotonic()
      except (BrokenPipeError, OSError):
        self.ended_reason = "obd_guard"

  def close(self):
    if self.process is None:
      return
    p, self.process = self.process, None
    try:
      p.stdin.close()   # EOF makes the independent watchdog restore normal routing
      p.wait(timeout=4)
      for line in p.stdout:
        msg = json.loads(line)
        if msg.get("closed"):
          self.restored = msg["restored"]
    except (OSError, subprocess.TimeoutExpired):
      # The child has its own 2 s lease timeout, plus bounded SPI retries; don't kill it before cleanup.
      raise RecorderError("obd_restore") from None
    finally:
      p.stdout.close()
    if self.restored is not True:
      raise RecorderError("obd_restore")


class ObdSource(CanSource):
  def __init__(self, lease_factory=Lease):
    super().__init__()
    self._lease = lease_factory()
    self.ended_reason = None

  def allowed(self):
    return self._park.allowed()   # OBD needs fresh live Park, including with the ignition on

  def info(self):
    info = super().info()
    if not supported(info):
      raise RecorderError("obd")
    return {**info, "obd_bus": 1, "obd_safety": "gm_camera_param_3_no_bus_1_tx"}

  def open(self):
    self._lease.open()

  def poll(self):
    self._lease.tick()
    self.ended_reason = self._lease.ended_reason
    return super().poll() if not self.ended_reason else ([], None)

  def close(self):
    self._lease.close()


if __name__ == "__main__":
  def interrupted(signum, frame):
    raise RecorderError("obd")
  signal.signal(signal.SIGTERM, interrupted)
  signal.signal(signal.SIGINT, interrupted)
  watch(sys.stdin, lambda msg: print(json.dumps(msg), flush=True), NativeGuard())
  os._exit(0)
