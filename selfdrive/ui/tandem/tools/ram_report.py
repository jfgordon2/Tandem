#!/usr/bin/env python3
"""How processes' memory changed across recent drives, from the drive logs' procLog (one sample every 30 s in qlogs).

Run on the device from /data/openpilot, at low priority, while parked:

  PYTHONPATH=/data/openpilot:/data nice -n 19 /usr/local/venv/bin/python selfdrive/ui/tandem/tools/ram_report.py
  ... ram_report.py --drives 4 starpilot_process modeld

For each drive it prints RAM in use and each named process's resident size at the start, middle and end, the process's
start time (a change means it restarted) and its growth per minute of driving. Sizes are RSS, which counts shared pages
in every process that maps them: compare a process with itself over time, not processes with each other.
"""
from __future__ import annotations

import argparse
import glob
import os
from collections import Counter

from openpilot.starpilot.tandem.processes import process_name

ROOTS = ("/data/media/0/realdata", "/data/media/0/realdata_konik", "/data/media/0/realdata_HD")


def drives(count: int) -> list[str]:
  segments = [p for root in ROOTS for p in glob.glob(f"{root}/*--*--*") if os.path.exists(f"{p}/qlog.zst")]
  names = sorted({p.rsplit("--", 1)[0] for p in segments}, key=lambda d: os.path.getmtime(f"{d}--0") if os.path.exists(f"{d}--0") else 0)
  return names[-count:]


def samples(drive: str):
  from openpilot.tools.lib.logreader import LogReader
  for seg in sorted(glob.glob(f"{drive}--*"), key=lambda p: int(p.rsplit("--", 1)[1])):
    path = f"{seg}/qlog.zst"
    if not os.path.exists(path):
      continue
    for msg in LogReader(path):
      if msg.which() != "procLog":
        continue
      log = msg.procLog
      sizes, starts = Counter(), {}
      for p in log.procs:
        name = process_name(p.name, list(p.cmdline))
        sizes[name] += p.memRss
        starts.setdefault(name, p.startTime)
      yield msg.logMonoTime / 1e9, 100 * (log.mem.total - log.mem.available) / log.mem.total, sizes, starts


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
  parser.add_argument("processes", nargs="*", default=["starpilot_process"])
  parser.add_argument("--drives", type=int, default=6)
  args = parser.parse_args()
  for drive in drives(args.drives):
    rows = list(samples(drive))
    if not rows:
      continue
    minutes = max((rows[-1][0] - rows[0][0]) / 60, 1e-6)
    print(f"{os.path.basename(drive)}: {minutes:.0f} min, RAM used {rows[0][1]:.0f}% -> peak {max(r[1] for r in rows):.0f}%")
    for name in args.processes:
      start, mid, end = (rows[0][2][name], rows[len(rows) // 2][2][name], rows[-1][2][name])
      began = rows[-1][3].get(name)
      if began is None:
        print(f"  {name:22s} not running")
        continue
      sizes = f"{start / 2**20:6.0f} {mid / 2**20:6.0f} {end / 2**20:6.0f} MB"
      print(f"  {name:22s} {sizes}  {(end - start) / 2**20 / minutes:+.1f} MB/min  started {began:.0f}")


if __name__ == "__main__":
  main()
