"""What was using RAM when a drive ran low on it, for Device › RAM (design/systemram.html) and Report a Problem.

StarPilot raises Low Memory above 90% RAM (selfdrived's lowMemory, from deviceState.memoryUsagePercent). The drive
screen tells RamLog each frame the Low on RAM chip shows. It keeps one snapshot per drive, taken at that drive's peak:
the first time the chip shows, then again only when RAM climbs at least a point higher. So a drive hovering around 90%
writes a handful of times, not every few seconds. The last three drives are kept, newest first, in .tandem_ram.json
beside the params folder.

Reading every process takes a moment, so the capture runs on a background thread.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openpilot.selfdrive.ui.tandem.i18n import N_

KEEP = 3   # drives
TOP = 5    # processes

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
  "routingd": N_("Routing"),
  "native_worker": N_("Routing"),
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
  rest: int = 0                                                          # bytes used by everything else
  drive: int = 0                                                         # which drive (the UI's started frame)

  def to_json(self) -> dict:
    return {"when": self.when, "percent": self.percent, "top": [list(t) for t in self.top], "rest": self.rest, "drive": self.drive}

  @staticmethod
  def from_json(d: dict) -> Snapshot:
    return Snapshot(float(d["when"]), int(d["percent"]), [(str(n), int(b)) for n, b in d.get("top", [])], int(d.get("rest", 0)),
                    int(d.get("drive", 0)))


GENERIC = {"daemon", "main", "service", "server"}   # module names that need their package to mean anything


def _module_name(module: str) -> str:
  """selfdrive.selfdrived.selfdrived → selfdrived; starpilot.system.bluetooth.daemon → bluetooth.daemon."""
  parts = module.split(".")
  return ".".join(parts[-2:]) if parts[-1] in GENERIC and len(parts) > 1 else parts[-1]


def process_name(name: str, cmdline: list[str]) -> str:
  """The name a process goes by. Manager titles most Python processes with their module (selfdrive.selfdrived.selfdrived);
  others run as python -m <module> (the UI) or python <script> (manager.py, comma's /usr/comma services)."""
  title = cmdline[0] if cmdline else name
  title = os.path.basename(title.split(" ", 1)[0]) or name
  if title.startswith("python"):
    args = iter(cmdline[1:])
    for arg in args:
      if arg == "-m":
        return _module_name(next(args, title))
      if arg.startswith("-"):
        continue
      return os.path.basename(arg).removesuffix(".py") or title
    return title
  return _module_name(title) if "." in title and not title.endswith(".py") else title


def read_processes() -> tuple[list[tuple[str, int]], int]:
  """((name, resident bytes) for every process, largest first; bytes in use), as psutil reads them."""
  import psutil
  sizes: dict[str, int] = {}
  for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
    info = p.info
    if not info.get("memory_info"):
      continue
    name = process_name(info.get("name") or "", info.get("cmdline") or [])
    sizes[name] = sizes.get(name, 0) + int(info["memory_info"].rss)
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
    self._snapshots: list[Snapshot] | None = None
    self._unseen = False

  # The drive screen

  def note(self, drive: int, percent: int) -> None:
    """Called each frame the Low on RAM chip shows. Captures at the drive's first notice and at each new peak."""
    if drive != self._drive:
      self._drive, self._peak = drive, 0
    if percent <= self._peak or self._busy:
      return
    self._peak = percent
    self._busy = True
    if self._background:
      threading.Thread(target=self._capture, args=(drive, percent), daemon=True).start()
    else:
      self._capture(drive, percent)

  def _capture(self, drive: int, percent: int) -> None:
    try:
      top, rest = summarize(*self._read())
      snap = Snapshot(self._clock(), percent, top, rest, drive)
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
    procs = ", ".join(f"{n} {b / 2**20:.0f} MB" for n, b in s.top)
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
