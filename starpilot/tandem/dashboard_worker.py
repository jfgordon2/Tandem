"""Coordinate Galaxy's background analyzer across the planner and web server."""
from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sys


MODULE = "openpilot.starpilot.tandem.dashboard_worker"


@contextmanager
def launch_lock(status_path: Path) -> Iterator[int | None]:
  """Yield the locked descriptor, or None while a worker holds it."""
  # Keep the inode stable. The child inherits this descriptor and owns the
  # lock until exit, even if the process that started it goes away first.
  with status_path.with_suffix(".lock").open("a") as lock:
    try:
      fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      yield None
    else:
      yield lock.fileno()


def process_start(pid: int) -> str | None:
  try:
    # Field 22 is the Linux start time in ticks. The preceding comm field can
    # contain spaces and parentheses, so split after its closing parenthesis.
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return fields[19] if fields[0] != "Z" else None
  except (OSError, IndexError, UnicodeError):
    return None


def main() -> None:
  os.set_inheritable(int(sys.argv[1]), False)
  from openpilot.common.params import Params
  if Params().get_bool("IsOnroad"):
    return

  from openpilot.starpilot.system.the_galaxy.utilities import warm_dashboard_stats
  warm_dashboard_stats(json.loads(sys.argv[2]))


if __name__ == "__main__":
  main()
