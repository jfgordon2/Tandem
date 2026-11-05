import inspect
import tracemalloc
from datetime import datetime

import pytest

from openpilot.starpilot.tandem import memory_trace as M


@pytest.fixture
def tracing():
  started = tracemalloc.is_tracing()
  if not started:
    tracemalloc.start(1)
  yield
  if not started:
    tracemalloc.stop()


def _tracer(tmp_path, status=None):
  return M.Tracer(tmp_path, wall=lambda: datetime(2026, 11, 4, 16, 38), status=status or (lambda: {"VmRSS": 300 * 1024,
                                                                                                 "RssAnon": 250 * 1024}))


def test_a_drive_report_names_the_lines_that_grew(tmp_path, tracing):
  tracer = _tracer(tmp_path)
  tracer.start(0.0)
  tracer.step(30.0)                       # status only
  tracer.step(61.0)                       # baseline
  leak = [bytes(1024) for _ in range(4096)]   # about 4 MB, from this line
  tracer.finish(600.0)
  text = (tmp_path / "starpilot_process-20261104-163800.txt").read_text()
  assert "RssAnon 250 MB" in text and "baseline snapshot taken" in text
  growth = text.split("growth since the baseline", 1)[1]
  lines, first = inspect.getsourcelines(test_a_drive_report_names_the_lines_that_grew)
  leak_line = first + next(i for i, line in enumerate(lines) if "leak = [" in line)
  top = growth.splitlines()[1]                 # the largest growth is listed first
  assert top.strip().startswith("+4.") and top.endswith(f"test_memory_trace.py:{leak_line}")
  assert leak


def test_a_short_drive_says_it_had_no_baseline(tmp_path, tracing):
  tracer = _tracer(tmp_path)
  tracer.start(0.0)
  tracer.finish(20.0)
  assert "ended before the baseline" in next(tmp_path.glob("*.txt")).read_text()


def test_keeps_the_last_ten_reports(tmp_path, tracing):
  for i in range(12):
    tracer = M.Tracer(tmp_path, wall=lambda i=i: datetime(2026, 11, 4, 10, i))
    tracer.start(0.0)
    tracer.finish(1.0)
  names = sorted(p.name for p in tmp_path.glob("*.txt"))
  assert len(names) == 10 and names[0] == "starpilot_process-20261104-100200.txt"


def test_follows_onroad_and_offroad(tmp_path, tracing):
  calls = []

  class Recorder(M.Tracer):
    def start(self, now): calls.append("start")
    def step(self, now): calls.append("step")
    def finish(self, now): calls.append("finish")
  tracer = Recorder(tmp_path, clock=lambda: 0.0)
  states = iter([True, True, False, False, True])
  stop = RuntimeError("done")

  def sleep(_):
    if not hasattr(sleep, "n"):
      sleep.n = 0
    sleep.n += 1
    if sleep.n == 5:
      raise stop
  with pytest.raises(RuntimeError):
    M.run(tracer, onroad=lambda: next(states), sleep=sleep)
  assert calls == ["start", "step", "finish", "start"]


def test_a_failing_trace_never_breaks_the_planner(monkeypatch):
  from openpilot.starpilot.tandem.navigation import controller_type

  class Base:
    pass
  monkeypatch.setenv("TANDEM_ONROAD", "0")
  monkeypatch.setattr(M, "start", lambda: 1 / 0)
  assert controller_type(Base) is Base                       # unchanged with Tandem's hooks off, and the error is caught


def test_starts_once_per_process(tmp_path, monkeypatch):
  monkeypatch.setenv("TANDEM_DIAGNOSTICS_DIR", str(tmp_path / "out"))
  monkeypatch.setattr(M, "_started", False)
  runs = []
  monkeypatch.setattr(M, "run", lambda tracer: runs.append(tracer))
  was_tracing = tracemalloc.is_tracing()
  try:
    assert M.start() and M.start()
    assert tracemalloc.is_tracing()
  finally:
    if not was_tracing:
      tracemalloc.stop()
  import time
  time.sleep(0.05)
  assert len(runs) == 1 and runs[0].folder == tmp_path / "out"


def test_status_reads_the_memory_lines(tmp_path):
  status = tmp_path / "status"
  status.write_text("Name:\tpython3\nVmRSS:\t  312000 kB\nRssAnon:\t  250000 kB\nRssFile:\t   60000 kB\nRssShmem:\t    2000 kB\nThreads:\t9\n")
  assert M.read_status(str(status)) == {"VmRSS": 312000, "RssAnon": 250000, "RssFile": 60000, "RssShmem": 2000}
  assert M.read_status(str(tmp_path / "missing")) == {}
