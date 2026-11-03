import io
import json
import threading
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem import obd as O
from openpilot.starpilot.tandem import can_recorder as C


class Clock:
  now = 0.
  def __call__(self):
    return self.now


class Route:
  def __init__(self, fail_on=False, fail_off=False):
    self.calls = []
    self.closed = False
    self.fail_on, self.fail_off = fail_on, fail_off

  def select(self, obd):
    self.calls.append(obd)
    if (obd and self.fail_on) or (not obd and self.fail_off):
      raise OSError("lost acknowledgement")

  def close(self):
    self.closed = True


@pytest.fixture(autouse=True)
def vehicle(monkeypatch):
  monkeypatch.setattr(C.CanSource, "info_from_params", lambda: {
    "brand": "gm", "fingerprint": O.FINGERPRINT, "network_location": "fwdCamera"})


@pytest.mark.parametrize("ending", ["eof", "guard", "lease", "limit", "exception"])
def test_independent_watchdog_always_restores_route(monkeypatch, ending):
  route, clock, messages = Route(), Clock(), []
  calls = 0

  def wait(*args):
    clock.now += .3
    if ending == "exception":
      raise RuntimeError("UI connection failed")
    return ([args[0][0]] if ending in {"eof", "limit"} else [], [], [])

  def guard():
    nonlocal calls
    calls += 1
    return ending != "guard" or calls < 3

  O.watch(io.StringIO("" if ending == "eof" else "beat\n"*20), messages.append, guard,
          factory=lambda: route, clock=clock, wait=wait, maximum=.8 if ending == "limit" else 120)
  assert messages[0] == {"ready": True}
  assert messages[-1]["closed"] and messages[-1]["restored"]
  assert route.calls == [True, False] and route.closed
  assert messages[-1]["reason"] == {"eof": "closed", "limit": "time_limit"}.get(ending, "obd_guard")


def test_unknown_car_is_rejected_before_hardware_is_opened(monkeypatch):
  monkeypatch.setattr(C.CanSource, "info_from_params", lambda: {"brand": "toyota"})
  messages = []
  O.watch(io.StringIO(), messages.append, lambda: True, factory=lambda: pytest.fail("hardware opened"))
  assert messages[0] == {"error": "obd"} and messages[-1]["restored"]


def test_failing_route_acknowledgement_still_runs_restore():
  route, messages = Route(fail_on=True), []
  O.watch(io.StringIO(), messages.append, lambda: True, factory=lambda: route)
  assert route.calls == [True, False] and messages[-1]["restored"]


def test_failed_restoration_is_reported_after_three_attempts():
  route, messages = Route(fail_off=True), []
  O.watch(io.StringIO(), messages.append, lambda: True, factory=lambda: route, wait=lambda *a: (a[0], [], []))
  assert route.calls == [True, False, False, False] and route.closed
  assert messages[-1]["closed"] and not messages[-1]["restored"]


def guard_state(monkeypatch):
  p = SimpleNamespace(pandaType="tres", safetyModel="gm", safetyParam=3, controlsAllowed=False,
                      powerSaveEnabled=False, canState1=SimpleNamespace(totalTxCnt=0))
  sm = SimpleNamespace(valid={"pandaStates": True}, alive={"pandaStates": True},
                       recv_time={"pandaStates": 10.}, logMonoTime={"pandaStates": 10_000_000_000}, update=lambda _: None)
  class SM:
    def __getattr__(self, key):
      return getattr(sm, key)
    def __getitem__(self, key):
      assert key == "pandaStates"
      return [p]
  guard = object.__new__(O.NativeGuard)
  guard._sm, guard._parked, guard._tx = SM(), lambda sm: True, None
  monkeypatch.setattr(O.time, "monotonic", lambda: 10.)
  return guard, p, sm


@pytest.mark.parametrize("field,value", [("pandaType", "redPanda"), ("safetyModel", "elm327"), ("safetyParam", 1),
                                         ("controlsAllowed", True), ("powerSaveEnabled", True)])
def test_guard_requires_exact_receive_only_gm_camera_configuration(monkeypatch, field, value):
  guard, panda, sm = guard_state(monkeypatch)
  assert guard()
  setattr(panda, field, value)
  assert not guard()


def test_guard_rejects_stale_state_park_loss_and_new_bus_1_transmission(monkeypatch):
  guard, panda, sm = guard_state(monkeypatch)
  assert guard()
  sm.logMonoTime["pandaStates"] = 8_000_000_000
  assert not guard()
  sm.logMonoTime["pandaStates"] = 10_000_000_000
  guard._parked = lambda sm: False
  assert not guard()
  guard._parked = lambda sm: True
  panda.canState1.totalTxCnt = 1
  assert not guard()


def test_gm_camera_param_3_has_no_bus_1_tx_after_upstream_merges():
  # This upstream assumption is the reason OBD selection can keep the normal UI running.
  import re
  root = Path(__file__).resolve().parents[4]
  source = (root/"opendbc/safety/modes/gm.h").read_text()
  table = source.split("static const CanMsg GM_CAM_LONG_TX_MSGS[] =", 1)[1].split(";", 1)[0]
  buses = [int(b) for b in re.findall(r"\{0x[0-9A-Fa-f]+,\s*(\d+),", table)]
  assert buses and set(buses) <= {0, 2}
  assert "GM_PARAM_HW_CAM = 1" in source and "GM_PARAM_HW_CAM_LONG = 2" in source
  safety = (root/"opendbc/safety/safety.h").read_text()
  forwarding = safety.split("static int get_fwd_bus(int bus_num)", 1)[1].split("int safety_fwd_hook", 1)[0]
  assert re.findall(r"bus_num == (\d+)", forwarding) == ["0", "2"]
  assert re.findall(r"destination_bus = (-?\d+)", forwarding) == ["2", "0", "-1"]
  spi = (root/"selfdrive/pandad/spi.cc").read_text()
  assert "flock(fd, LOCK_EX)" in spi


@pytest.mark.parametrize("bad_version", [False, True])
def test_hardware_adapter_only_writes_input_selection_and_cleans_up(monkeypatch, tmp_path, bad_version):
  from types import ModuleType
  reads, writes, closed = [], [], []
  class Panda:
    HEALTH_PACKET_VERSION, CAN_PACKET_VERSION, CAN_HEALTH_PACKET_VERSION = 1, 2, 3
    REQUEST_IN, REQUEST_OUT, HW_TYPE_TRES = 0xC0, 0x40, b"\x09"
    def health(self):
      return {"safety_mode": 4, "safety_param": 3, "controls_allowed": False, "power_save_enabled": False}
    def __init__(self):
      pytest.fail("Panda.connect would change configuration")

  class Handle:
    def controlRead(self, request_type, request, value, index, length, timeout):
      reads.append(request)
      return bytes([99 if bad_version else 1, 2, 3]) if request == 0xdd else Panda.HW_TYPE_TRES
    def controlWrite(self, *args, **kwargs):
      writes.append((args, kwargs))
    def close(self):
      closed.append(True)

  panda, spi = ModuleType("panda"), ModuleType("panda.python.spi")
  panda.Panda, spi.PandaSpiHandle = Panda, Handle
  monkeypatch.setitem(sys.modules, "panda", panda)
  monkeypatch.setitem(sys.modules, "panda.python.spi", spi)
  original_open = open
  locks = []
  def lock_file(path, mode):
    assert path == "/tmp/tandem-obd-input.lock"
    lock = original_open(tmp_path/"lock", mode)
    locks.append(lock)
    return lock
  monkeypatch.setattr(O, "open", lock_file, raising=False)
  if bad_version:
    with pytest.raises(C.RecorderError, match="obd"):
      O.Routing()
    assert not writes
  else:
    route = O.Routing()
    route.select(True)
    route.select(False)
    route.close()
    assert [args for args, _ in writes] == [(0x40, 0xdb, 1, 0, b""), (0x40, 0xdb, 0, 0, b"")]
    assert reads == [0xdd, 0xc1]
  assert closed == [True] and locks[0].closed


def test_lease_requires_confirmation_of_restore(monkeypatch):
  lease = O.Lease()
  lease.process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(""), returncode=0, wait=lambda timeout: None)
  with pytest.raises(C.RecorderError, match="obd_restore"):
    lease.close()


def test_lease_accepts_restored_message():
  lease = O.Lease()
  lease.process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(json.dumps({"closed": True, "restored": True})+"\n"),
                                  returncode=0, wait=lambda timeout: None)
  lease.close()
  assert lease.restored and lease.process is None


def test_obd_recording_saves_input_counts_markers_and_restores_before_saved(tmp_path):
  from openpilot.selfdrive.ui.tandem.tests.test_can_recorder import Source, wait_for
  entered, release = threading.Event(), threading.Event()
  source = Source()
  opened = []
  source.open = lambda: opened.append(True)
  source.batches.put(([(10, 1, 0x124, b"obd"), (11, 0, 0x348, b"wheel")], None))

  def close():
    entered.set()
    release.wait(2)
    source.closed = True

  source.close = close
  recorder = C.CanRecorder(tmp_path/"can", obd_source=lambda: source)
  recorder.start(obd=True)
  wait_for(lambda: recorder.snapshot().frames == 2)
  assert recorder.mark("lock")
  recorder.stop()
  assert entered.wait(2) and recorder.snapshot().phase == "saving"
  release.set()
  recorder._thread.join(2)
  state = recorder.snapshot()
  metadata = json.loads((tmp_path/"can"/state.session/"metadata.json").read_text())
  assert state.phase == "saved" and source.closed and opened == [True]
  assert state.input == metadata["input"] == "obd"
  assert state.obd_frames == metadata["obd_frames"] == 1 and state.lock_markers == 1


def test_restore_failure_blocks_new_tests_even_after_log_is_discarded(tmp_path):
  from openpilot.selfdrive.ui.tandem.tests.test_can_recorder import Source, wait_for
  source = Source()

  def close():
    raise C.RecorderError("obd_restore")

  source.close = close
  recorder = C.CanRecorder(tmp_path/"can", obd_source=lambda: source)
  recorder.start(obd=True)
  wait_for(lambda: recorder.snapshot().phase == "recording")
  recorder.stop()
  recorder._thread.join(2)
  assert recorder.snapshot().reason == "obd_restore" and not recorder.start()
  recorder.abort()
  recorder._thread.join(2)
  assert recorder.snapshot().reason == "obd_restore" and not recorder.start()


def test_page_selects_obd_only_while_idle_and_shows_live_obd_count():
  from openpilot.selfdrive.ui.tandem.tests.test_can_recorder import FakeRecorder
  from openpilot.selfdrive.ui.tandem.settings.can_recorder import CanRecorderPage
  recorder = FakeRecorder()
  page = CanRecorderPage(recorder, allowed=lambda: True)
  page.set_input(1)
  page.start()
  page._update_state()
  page.set_input(0)
  assert page._obd and not page._input.enabled and page._obd_count.is_visible
  assert recorder.calls == [("start", "obd")]
  assert page.detail() == "Waiting for OBD traffic. Check the RJ45 cable."


def test_watchdog_restores_after_its_parent_process_dies(tmp_path):
  log = tmp_path/"route.jsonl"
  child = '''import json,sys
from pathlib import Path
from openpilot.starpilot.tandem.obd import watch, FINGERPRINT
from openpilot.starpilot.tandem.can_recorder import CanSource
CanSource.info_from_params=lambda: {"brand":"gm","fingerprint":FINGERPRINT,"network_location":"fwdCamera"}
class Route:
  def select(self, value):
    with Path(sys.argv[1]).open("a") as f:f.write(json.dumps(value)+"\\n")
  def close(self):pass
watch(sys.stdin,lambda msg:print(json.dumps(msg),flush=True),lambda:True,factory=Route)
'''
  parent = f'''import json,os,subprocess,sys
p=subprocess.Popen([sys.executable,"-u","-c",{child!r},sys.argv[1]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                   stderr=subprocess.DEVNULL,text=True,start_new_session=True)
assert json.loads(p.stdout.readline())["ready"]
os._exit(0)
'''
  result = subprocess.run([sys.executable, "-c", parent, str(log)], timeout=5, capture_output=True, text=True)
  assert result.returncode == 0, result.stderr
  deadline = time.monotonic()+3
  while not log.exists() or log.read_text().splitlines() != ["true", "false"]:
    assert time.monotonic() < deadline, "orphaned watchdog failed to restore the input"
    time.sleep(.01)
