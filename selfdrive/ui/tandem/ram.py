"""What was using RAM when a drive ran low on it, for Device › RAM (design/systemram.html) and Report a Problem.

StarPilot raises Low Memory above 90% RAM (selfdrived's lowMemory, from deviceState.memoryUsagePercent). The drive
screen tells RamLog each frame the Low on RAM chip shows. It keeps one snapshot per drive, taken at that drive's peak:
the first time the chip shows, then again only when RAM climbs at least a point higher. So a drive hovering around 90%
writes a handful of times, not every few seconds. The last three drives are kept, newest first, in .tandem_ram.json
beside the params folder.

Each process counts by its share of RAM (PSS: a page several processes map counts a part to each), so the sizes add
up to what's in use; resident size counts shared pages once per process and sums past the device's RAM. The kernel and
GPU hold the rest, which no process shows. A minute into each drive, once the driving processes have started, the drive
screen also takes a baseline, so a snapshot can say how much each process grew since then: a steady leak shows as
growth, not just size.

Reading every process's memory map takes about a second on a comma 3X (its 4.9 kernel has no smaps_rollup), so reads run
on a background thread with short pauses between processes, keeping the UI thread's frames on time.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.starpilot.tandem.processes import process_name

KEEP = 3   # drives
TOP = 5    # processes
BASELINE_AFTER = 60.0   # seconds into a drive, once modeld and the rest have started
PAUSE = 0.002           # between processes while reading, so the UI thread keeps the GIL most of the time
PSS = re.compile(rb"^Pss:\s+(\d+) kB", re.M)

# What the processes a driver is likely to see do, in plain words. Anything else shows only its name.
DESCRIPTIONS = {
  "modeld": N_("Driving model"),
  "dmonitoringmodeld": N_("Driver monitoring model"),
  "ui": N_("This screen"),
  "selfdrived": N_("Driving decisions"),
  "controlsd": N_("Steering and speed control"),
  "plannerd": N_("Speed planning"),
  "radard": N_("Radar"),
  "locationd": N_("Position and heading"),
  "paramsd": N_("Car calibration"),
  "calibrationd": N_("Camera calibration"),
  "camerad": N_("Cameras"),
  "encoderd": N_("Video recording"),
  "loggerd": N_("Drive logging"),
  "uploader": N_("Uploads"),
  "athenad": N_("Remote access"),
  "manage_athenad": N_("Remote access"),
  "mapd": N_("Speed limits and curves"),
  "valhalla_service": N_("Routing"),
  "soundd": N_("Sounds"),
  "card": N_("Car interface"),
  "manager": N_("Starts and stops the rest"),
  "starpilot_process": N_("StarPilot's planning"),
  "speed_limit_vision": N_("Speed limit sign reading"),
  "the_galaxy": N_("Remote access"),
  "hardwared": N_("Power and temperature"),
  "bluetooth.daemon": N_("Bluetooth remote"),
  "pandad": N_("Car connection"),
}


@dataclass
class Snapshot:
  when: float                                                            # epoch seconds, at the peak
  percent: int
  top: list[tuple[str, int]] = field(default_factory=list)              # (name, bytes), largest first
  rest: int = 0                                                          # bytes used by other processes and the system
  drive: int = 0                                                         # which drive (the UI's started frame)
  grew: dict[str, int] = field(default_factory=dict)                     # top processes' growth since the baseline, if taken

  def to_json(self) -> dict:
    return {"when": self.when, "percent": self.percent, "top": [list(t) for t in self.top], "rest": self.rest, "drive": self.drive,
            "grew": self.grew}

  @staticmethod
  def from_json(d: dict) -> Snapshot:
    return Snapshot(float(d["when"]), int(d["percent"]), [(str(n), int(b)) for n, b in d.get("top", [])], int(d.get("rest", 0)),
                    int(d.get("drive", 0)), {str(n): int(b) for n, b in d.get("grew", {}).items()})


def pss_of(smaps: bytes) -> int:
  """Bytes of a process's proportional share, from its /proc/<pid>/smaps."""
  return 1024 * sum(int(kb) for kb in PSS.findall(smaps))


def read_processes(pause: float = PAUSE) -> tuple[list[tuple[str, int]], int]:
  """((name, bytes) for every process, largest first; bytes in use). Bytes are PSS where the process's memory map can be
  read; processes that refuse (root's, about 170 MB of RSS on a device) are left to "other processes and the system".
  Without /proc (macOS) it falls back to resident size."""
  import psutil
  linux = os.path.isdir("/proc/self")
  sizes: dict[str, int] = {}
  for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
    info = p.info
    name = process_name(info.get("name") or "", info.get("cmdline") or [])
    if linux:
      try:
        with open(f"/proc/{info['pid']}/smaps", "rb") as stream:
          size = pss_of(stream.read())
      except OSError:
        continue
      time.sleep(pause)
    elif info.get("memory_info"):
      size = int(info["memory_info"].rss)
    else:
      continue
    sizes[name] = sizes.get(name, 0) + size
  vm = psutil.virtual_memory()
  return sorted(sizes.items(), key=lambda kv: kv[1], reverse=True), int(vm.total - vm.available)


def summarize(processes: list[tuple[str, int]], used: int) -> tuple[list[tuple[str, int]], int]:
  top = processes[:TOP]
  return top, max(0, used - sum(b for _, b in top))


class RamLog:
  def __init__(self, path: Path, read: Callable[[], tuple[list[tuple[str, int]], int]] = read_processes,
               clock: Callable[[], float] = lambda: datetime.now().timestamp(), background: bool = True):   # wall clock: shown as a date
    self._path = path
    self._read = read
    self._clock = clock
    self._background = background
    self._lock = threading.Lock()
    self._busy = False
    self._drive = -1
    self._peak = 0
    self._started = 0.0                          # monotonic, when this drive was first seen
    self._baseline: dict[str, int] | None = None  # sizes a minute into the drive
    self._baseline_busy = False
    self._snapshots: list[Snapshot] | None = None
    self._unseen = False

  # The drive screen

  def drive(self, drive: int, now: float) -> None:
    """Called each frame while onroad (now: monotonic). Takes the drive's baseline once, BASELINE_AFTER seconds in."""
    self._switch(drive, now)
    if self._baseline is not None or self._baseline_busy or now - self._started < BASELINE_AFTER:
      return
    self._baseline_busy = True
    self._run(self._take_baseline, drive)

  def _switch(self, drive: int, now: float = 0.0) -> None:
    if drive != self._drive:
      self._drive, self._peak, self._started, self._baseline = drive, 0, now, None

  def _take_baseline(self, drive: int) -> None:
    try:
      sizes = dict(self._read()[0])
      if drive == self._drive:
        self._baseline = sizes
    except Exception:
      pass
    finally:
      self._baseline_busy = False

  def _run(self, task: Callable, *args) -> None:
    if self._background:
      threading.Thread(target=task, args=args, daemon=True).start()
    else:
      task(*args)

  def note(self, drive: int, percent: int) -> None:
    """Called each frame the Low on RAM chip shows. Captures at the drive's first notice and at each new peak."""
    self._switch(drive)
    if percent <= self._peak or self._busy:
      return
    self._peak = percent
    self._busy = True
    self._run(self._capture, drive, percent)

  def _capture(self, drive: int, percent: int) -> None:
    try:
      top, rest = summarize(*self._read())
      baseline = self._baseline
      grew = {} if baseline is None else {name: size - baseline.get(name, 0) for name, size in top}
      snap = Snapshot(self._clock(), percent, top, rest, drive, grew)
      with self._lock:
        kept = [s for s in self._load() if s.drive != drive or s.when > snap.when]   # this drive's earlier peak gives way
        self._snapshots = ([snap] + kept)[:KEEP]
        self._unseen = True
        self._save()
    except Exception:
      pass
    finally:
      self._busy = False

  # Device › RAM

  def snapshots(self) -> list[Snapshot]:
    """The last drives that ran low, newest first."""
    with self._lock:
      return list(self._load())

  def unseen(self) -> bool:
    with self._lock:
      self._load()
      return self._unseen

  def mark_seen(self) -> None:
    with self._lock:
      self._load()
      if self._unseen:
        self._unseen = False
        self._save()

  def _load(self) -> list[Snapshot]:
    if self._snapshots is None:
      try:
        data = json.loads(self._path.read_text())
        self._snapshots = [Snapshot.from_json(d) for d in data.get("drives", [])][:KEEP]
        self._unseen = bool(data.get("unseen", False))
      except (OSError, ValueError, KeyError, TypeError):
        self._snapshots = []
    return self._snapshots

  def _save(self) -> None:
    tmp = self._path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"drives": [s.to_json() for s in self._snapshots or []], "unseen": self._unseen}))
    tmp.replace(self._path)


def report_text(snapshots: list[Snapshot]) -> str:
  """For Report a Problem: one line per drive, in English for the developers."""
  lines = []
  for s in snapshots:
    when = datetime.fromtimestamp(s.when).strftime("%Y-%m-%d %H:%M")
    procs = ", ".join(f"{n} {b / 2**20:.0f} MB" + (f" ({s.grew[n] / 2**20:+.0f})" if n in s.grew else "") for n, b in s.top)
    lines.append(f"Low on RAM {when} {s.percent}%: {procs}, rest {s.rest / 2**20:.0f} MB")
  return "\n".join(lines)


_now = [0.0, 0]


def now_percent() -> int:
  """RAM in use now, as deviceState reports it, read at most once a second."""
  import psutil
  if time.monotonic() - _now[0] >= 1.0:
    _now[0], _now[1] = time.monotonic(), int(round(psutil.virtual_memory().percent))
  return int(_now[1])


_shared: list[RamLog] = []


def shared_log() -> RamLog:
  """One log for the drive screen and Device › RAM, beside the params folder."""
  if not _shared:
    from openpilot.selfdrive.ui.tandem.prefs import prefs_dir
    _shared.append(RamLog(prefs_dir() / ".tandem_ram.json"))
  return _shared[0]
