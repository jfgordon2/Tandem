from dataclasses import replace
import gzip
import json
from pathlib import Path
import queue
import threading
import time
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem import can_recorder as C
from openpilot.selfdrive.ui.tandem.settings.can_recorder import CanRecorderPage, duration


class Source:
  def __init__(self, brand="gm"):
    self.brand = brand
    self.parked = True
    self.batches = queue.Queue()
    self.closed = False

  def allowed(self):
    return self.parked

  def info(self):
    return {"brand": self.brand, "fingerprint": "test car"}

  def poll(self):
    try:
      return self.batches.get(timeout=0.01)
    except queue.Empty:
      return [], None

  def close(self):
    self.closed = True


@pytest.fixture
def log_dir(tmp_path):
  return tmp_path / "can-logs"


def wait_for(predicate):
  deadline = time.monotonic()+2
  while not predicate():
    assert time.monotonic() < deadline, "recorder did not reach the expected state"
    time.sleep(0.002)


def finish(recorder):
  recorder.stop()
  recorder._thread.join(2)
  assert not recorder._thread.is_alive()


def lines(path):
  with gzip.open(path, "rt") as f:
    return [json.loads(line) for line in f]


def test_full_capture_focus_filter_and_new_session(log_dir):
  source = Source()
  recorder = C.CanRecorder(log_dir, lambda: source)
  assert recorder.start() and not recorder.start()
  wait_for(lambda: recorder.snapshot().phase == "recording")
  sample = [(10, 0, 0x348, b"wheel"), (20, 0, 0x12A, b"body"), (30, 0, 0x241, b"diagnostic"),
            (40, 2, 0x348, b"other bus"), (50, 0, 0x777, b"unknown")]
  source.batches.put((sample, {"time_ns": 9, "pandas": [{"power_save": True}]}))
  wait_for(lambda: recorder.snapshot().frames == 5)
  finish(recorder)
  state = recorder.snapshot()
  folder = log_dir/state.session
  raw, focus = lines(folder/"can.jsonl.gz"), lines(folder/"focus.jsonl.gz")
  assert raw == [[t, bus, addr, data.hex()] for t, bus, addr, data in sample]
  assert focus == raw[1:]   # only the known main-bus driving message is omitted from the focused copy
  meta = json.loads((folder/"metadata.json").read_text())
  assert meta["passive"] and meta["clock"] == C.CLOCK_NAME and meta["status"] == "saved"
  assert meta["focus_excluded"]["0x348"] == "EBCMWheelSpdFront" and meta["focus_excluded_bus"] == 0
  assert source.closed and state.power_save is True
  assert not recorder.mark("lock")
  assert recorder.start()
  wait_for(lambda: recorder.snapshot().phase == "recording")
  finish(recorder)
  assert recorder.snapshot().session != state.session and len(list(log_dir.iterdir())) == 2


def test_marker_clock_matches_native_can_clock(monkeypatch):
  calls = []
  monkeypatch.setattr(C.time, "clock_gettime_ns", lambda clock: calls.append(clock) or 123)
  assert C.boot_time_ns() == 123
  assert calls == [getattr(time, "CLOCK_BOOTTIME", time.CLOCK_MONOTONIC)]
  assert C.CanRecorder()._clock_ns is C.boot_time_ns
  assert CanRecorderPage(FakeRecorder())._clock_ns is C.boot_time_ns


def test_filtered_messages_are_still_known_gm_driving_messages():
  # Catch a DBC change during an upstream merge before it silently changes the focus filter.
  dbc = Path(__file__).resolve().parents[4] / "opendbc/dbc/gm_global_a_powertrain_generated.dbc"
  for address, name in C.GM_FOCUS_EXCLUDED.items():
    assert f"BO_ {address} {name}:" in dbc.read_text()


def test_other_brands_keep_every_frame_in_the_focus_copy(log_dir):
  source = Source("toyota")
  source.batches.put(([(10, 0, 0x348, b"not a GM wheel message")], None))
  recorder = C.CanRecorder(log_dir, lambda: source)
  recorder.start()
  wait_for(lambda: recorder.snapshot().frames == 1)
  finish(recorder)
  folder = log_dir/recorder.snapshot().session
  assert lines(folder/"focus.jsonl.gz") == lines(folder/"can.jsonl.gz")


def test_marker_keeps_tap_time_when_worker_is_delayed_and_stop_drains_pending_taps(log_dir):
  entered, release = threading.Event(), threading.Event()
  clock = SimpleNamespace(now=1_000_000_000)
  source = Source()

  def blocked_poll():
    entered.set()
    release.wait(2)
    return [], None

  source.poll = blocked_poll
  recorder = C.CanRecorder(log_dir, lambda: source, clock_ns=lambda: clock.now)
  recorder.start()
  assert entered.wait(2)
  clock.now = 1_012_345_678
  assert recorder.mark("lock")
  clock.now = 1_022_345_678
  assert recorder.mark("unlock") and not recorder.mark("other")
  clock.now = 1_900_000_000   # disk/worker work happens much later than the user's taps
  recorder.stop()
  assert not recorder.mark("lock")
  release.set()
  recorder._thread.join(2)
  state = recorder.snapshot()
  marks = [json.loads(line) for line in (log_dir/state.session/"markers.jsonl").read_text().splitlines()]
  assert [m["time_ns"] for m in marks] == [1_012_345_678, 1_022_345_678]
  assert [m["elapsed_ns"] for m in marks] == [12_345_678, 22_345_678]
  assert (state.lock_markers, state.unlock_markers, state.last_kind) == (1, 1, "unlock")
  assert state.phase == "saved"


@pytest.mark.parametrize("reason", ["time_limit", "parked", "storage"])
def test_automatic_stops_close_valid_log_files(log_dir, monkeypatch, reason):
  source = Source()
  clock = SimpleNamespace(now=1_000_000_000)
  calls = []

  def disk_usage(path):
    calls.append(path)
    return SimpleNamespace(free=1 if reason == "storage" and len(calls) > 1 else 100_000_000)

  monkeypatch.setattr(C.shutil, "disk_usage", disk_usage)

  def poll():
    clock.now += 2_000_000_000
    source.parked = reason != "parked"
    return [(clock.now, 0, 0x123, b"data")], None

  source.poll = poll
  recorder = C.CanRecorder(log_dir, lambda: source, clock_ns=lambda: clock.now, max_seconds=1 if reason == "time_limit" else 600)
  recorder.start()
  recorder._thread.join(2)
  state = recorder.snapshot()
  assert state.phase == "saved" and state.reason == reason
  assert lines(log_dir/state.session/"can.jsonl.gz")
  assert source.closed


def test_refuses_start_without_park_and_handles_storage_and_source_failures(log_dir, monkeypatch):
  source = Source()
  source.parked = False
  recorder = C.CanRecorder(log_dir, lambda: source)
  recorder.start()
  recorder._thread.join(2)
  assert recorder.snapshot().phase == "error" and recorder.snapshot().reason == "parked"
  assert not list(log_dir.iterdir())
  source.parked = True
  monkeypatch.setattr(C.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
  recorder.start()
  recorder._thread.join(2)
  assert recorder.snapshot().reason == "storage" and not list(log_dir.iterdir())
  monkeypatch.setattr(C.shutil, "disk_usage", lambda path: SimpleNamespace(free=100_000_000))

  def fail():
    raise RuntimeError("source unavailable")

  recorder._source = fail
  recorder.start()
  recorder._thread.join(2)
  assert recorder.snapshot().phase == "error" and recorder.snapshot().reason == "write"


def test_io_failure_does_not_escape_worker_or_leave_an_unclosed_gzip(log_dir):
  source = Source()

  def fail():
    raise OSError("disk failed")

  source.poll = fail
  recorder = C.CanRecorder(log_dir, lambda: source)
  recorder.start()
  recorder._thread.join(2)
  state = recorder.snapshot()
  assert state.phase == "error" and source.closed
  assert lines(log_dir/state.session/"can.jsonl.gz") == []
  assert json.loads((log_dir/state.session/"metadata.json").read_text())["status"] == "error"


class FakeRecorder:
  def __init__(self):
    self.state = C.RecorderState()
    self.calls = []

  def snapshot(self):
    return self.state

  def start(self):
    self.calls.append("start")
    self.state = replace(self.state, phase="recording", session="test", started_ns=1_000_000_000)

  def mark(self, kind):
    self.calls.append(kind)

  def stop(self, reason="user"):
    self.calls.append(("stop", reason))


def test_page_uses_marker_callbacks_and_saves_on_hide_without_blocking():
  recorder = FakeRecorder()
  page = CanRecorderPage(recorder, allowed=lambda: True, clock_ns=lambda: 13_034_000_000)
  assert not page._mark_lock.enabled and page._start.enabled
  page._start._click_callback()
  page._update_state()
  assert page._mark_lock.enabled and not page._start.enabled and page.elapsed() == "00:12.034"
  page._mark_lock._click_callback()
  page._mark_unlock._click_callback()
  page._stop._click_callback()
  page.hide_event()
  assert recorder.calls == ["start", "lock", "unlock", ("stop", "user"), ("stop", "screen_closed")]


def test_page_blocks_start_when_not_parked_and_formats_exact_relative_time():
  recorder = FakeRecorder()
  page = CanRecorderPage(recorder, allowed=lambda: False)
  page.start()
  assert not recorder.calls and not page._start.enabled
  assert page.detail() == "Park the car to start a test."
  assert duration(62_345_999_999) == "01:02.345" and duration(-1) == "00:00.000"
