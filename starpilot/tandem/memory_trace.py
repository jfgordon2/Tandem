"""Memory tracing inside the process that runs StarPilot's planner, to find what grows while driving.

This lives only on the debug branch, where it's on by default. A marker file beside the params folder turns it off
(`touch /data/params/.tandem_memory_trace_off`, then restart); off, it costs one file check when the planner is created.
On, it starts Python's tracemalloc with one frame per allocation and a background thread that, for each drive:

- writes a status line every minute: the process's resident heap (RssAnon), file-backed (RssFile) and shared (RssShmem)
  memory, and the Python memory tracemalloc sees;
- takes a snapshot a minute into the drive and another once parked, and writes the 25 lines whose allocations grew most
  in between (file:line, size and count), leaving out growth under 64 KB.

Snapshots pause the process briefly, so neither is taken mid-drive past the first minute. Reports go to
/data/tandem/diagnostics/memory/ (TANDEM_DIAGNOSTICS_DIR elsewhere), one file per drive, the last ten kept.
tracemalloc sees allocations Python makes, numpy's included; growth in RssAnon it can't account for is native.

It starts from starpilot/tandem/navigation.py, which StarPilot's planner already imports, and also under
TANDEM_ONROAD=0, so it can compare the planner with and without Tandem's hooks. It never changes what the planner does.
"""
from __future__ import annotations

import os
import threading
import time
import tracemalloc
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

OFF_MARKER = ".tandem_memory_trace_off"
KEEP = 10
TOP = 25
SHOWN_FROM = 64 * 1024   # growth smaller than this is noise
BASELINE_AFTER = 60.0   # seconds into the drive
STATUS_EVERY = 60.0
CHECK_EVERY = 10.0
STATUS_FIELDS = ("VmRSS", "RssAnon", "RssFile", "RssShmem")

_started = False


def marker_path() -> Path:
  if os.getenv("TANDEM_PREFS_DIR"):
    folder = Path(os.environ["TANDEM_PREFS_DIR"])
  else:
    from openpilot.common.params import Params
    folder = Path(Params().get_param_path()).parent
  return folder / OFF_MARKER


def out_dir() -> Path:
  if os.getenv("TANDEM_DIAGNOSTICS_DIR"):
    return Path(os.environ["TANDEM_DIAGNOSTICS_DIR"])
  return Path("/data/tandem/diagnostics/memory")


def read_status(path: str = "/proc/self/status") -> dict[str, int]:
  """The process's memory lines from /proc, in kB; empty where there's no /proc (macOS)."""
  try:
    with open(path) as stream:
      lines = stream.read().splitlines()
  except OSError:
    return {}
  values = {}
  for line in lines:
    key, _, rest = line.partition(":")
    if key in STATUS_FIELDS:
      values[key] = int(rest.split()[0])
  return values


def _onroad() -> bool:
  from openpilot.common.params import Params
  return Params().get_bool("IsOnroad")


class Tracer:
  """One drive at a time: start(now) when onroad begins, step(now) every few seconds, finish() once parked."""

  def __init__(self, folder: Path, clock: Callable[[], float] = time.monotonic, wall: Callable[[], datetime] = datetime.now,
               status: Callable[[], dict[str, int]] = read_status):
    self.folder = folder
    self.clock, self.wall, self.status = clock, wall, status
    self.report: Path | None = None
    self.started = 0.0
    self.last_status = 0.0
    self.baseline: tracemalloc.Snapshot | None = None

  def start(self, now: float) -> None:
    self.folder.mkdir(parents=True, exist_ok=True)
    self.report = self.folder / f"starpilot_process-{self.wall().strftime('%Y%m%d-%H%M%S')}.txt"
    self.started, self.last_status, self.baseline = now, now - STATUS_EVERY, None
    self._write(f"Memory trace of pid {os.getpid()}, drive started {self.wall().isoformat(timespec='seconds')}\n")
    self._prune()

  def step(self, now: float) -> None:
    if self.report is None:
      return
    if now - self.last_status >= STATUS_EVERY:
      self.last_status = now
      self._write(self._status_line(now))
    if self.baseline is None and now - self.started >= BASELINE_AFTER:
      self.baseline = _snapshot()
      self._write(f"{self._minutes(now)} baseline snapshot taken\n")

  def finish(self, now: float) -> None:
    if self.report is None:
      return
    self._write(self._status_line(now))
    if self.baseline is not None:
      self._write(f"\nTop {TOP} growth since the baseline, by line (parked, {self._minutes(now)} into the drive):\n")
      grown = [s for s in _snapshot().compare_to(self.baseline, "lineno") if abs(s.size_diff) >= SHOWN_FROM]
      for stat in grown[:TOP]:
        frame = stat.traceback[0]
        sizes = f"{stat.size_diff / 2**20:+8.2f} MB {stat.count_diff:+8d} blocks  now {stat.size / 2**20:7.2f} MB"
        self._write(f"  {sizes}  {frame.filename}:{frame.lineno}\n")
      if not grown:
        self._write("  nothing Python allocated grew by 64 KB or more; compare RssAnon above for native growth\n")
    else:
      self._write("\nThe drive ended before the baseline snapshot.\n")
    self.report = None

  def _status_line(self, now: float) -> str:
    kb = self.status()
    traced, peak = tracemalloc.get_traced_memory() if tracemalloc.is_tracing() else (0, 0)
    parts = [f"{key} {kb[key] / 1024:.0f} MB" for key in STATUS_FIELDS if key in kb]
    return f"{self._minutes(now)} " + "  ".join(parts + [f"traced {traced / 2**20:.0f} MB (peak {peak / 2**20:.0f})"]) + "\n"

  def _minutes(self, now: float) -> str:
    return f"{(now - self.started) / 60:6.1f} min"

  def _write(self, text: str) -> None:
    if self.report is not None:
      with self.report.open("a") as stream:
        stream.write(text)

  def _prune(self) -> None:
    reports = sorted(self.folder.glob("starpilot_process-*.txt"))
    for old in reports[:-KEEP]:
      old.unlink(missing_ok=True)


def _snapshot() -> tracemalloc.Snapshot:
  # Leave out tracemalloc's own bookkeeping, so the growth shown is the process's.
  return tracemalloc.take_snapshot().filter_traces((tracemalloc.Filter(False, tracemalloc.__file__),))


def run(tracer: Tracer, onroad: Callable[[], bool] = _onroad, sleep: Callable[[float], None] = time.sleep,
        forever: bool = True) -> None:
  """Follow onroad and offroad, a drive per report. forever=False returns after one check (tests)."""
  driving = False
  while True:
    try:
      now = tracer.clock()
      on = onroad()
      if on and not driving:
        tracer.start(now)
      elif driving and not on:
        tracer.finish(now)
      elif on:
        tracer.step(now)
      driving = on
    except Exception:
      pass   # a diagnostic must never take its process down
    if not forever:
      return
    sleep(CHECK_EVERY)


def start_if_requested() -> bool:
  """Called each time the planner is created; starts tracing once per process unless the off marker is there."""
  global _started
  if _started:
    return True
  try:
    if marker_path().is_file():
      return False
    tracemalloc.start(1)
    threading.Thread(target=run, args=(Tracer(out_dir()),), name="tandem-memory-trace", daemon=True).start()
    _started = True
  except Exception:
    return False
  return True
