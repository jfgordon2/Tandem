"""Alerts › Play sample and Sound Pack's sample, played at once: a worker that keeps StarPilot's sound player loaded.

StarPilot's own preview (starpilot/audio/preview.py, Galaxy's) starts a new Python process and loads every alert sound
for each sample, about 5.6 s on a comma 3X, and refuses any tap while one runs. This worker loads them once, while the
settings page wants samples, and plays each through the same play_saved_alert with the same checks: parked, the
driver camera closed, and the same lock as Galaxy's previews so two never play at once. It reloads the sounds before
each sample, so a new Sound Pack plays its own. Requests come one key per line on stdin; when several arrive while one
plays, only the latest plays. It exits when stdin closes.
"""
from __future__ import annotations

import fcntl
import os
import select
import stat
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path


def requests(fd: int) -> Iterator[str]:
  """Each time requests arrive, the newest one: everything waiting is read at once, so taps made while a sample played
  collapse to the last. Ends when the pipe closes.

  Args:
    fd: The pipe's file descriptor (stdin).

  Yields:
    The newest requested alert key.
  """
  pending, done = b"", False
  while not done:
    select.select([fd], [], [])
    while True:
      chunk = os.read(fd, 4096)
      if not chunk:
        done = True
        break
      pending += chunk
      if not select.select([fd], [], [], 0)[0]:
        break
    *lines, pending = pending.split(b"\n")
    keys = [line.decode("utf-8", "replace").strip() for line in lines if line.strip()]
    if keys:
      yield keys[-1]


def main() -> int:
  """Plays each requested alert's sample until stdin closes."""
  from openpilot.common.params import Params
  from openpilot.starpilot.audio.preview import ALERTS, AlertPreviewError, play_saved_alert
  from openpilot.starpilot.galaxy.settings import LiveContextSource
  from openpilot.selfdrive.ui.soundd import AudibleAlert, Soundd
  from openpilot.system import micd
  import sounddevice
  micd.patch_sounddevice(sounddevice)
  params = Params()
  context = LiveContextSource(params)
  sound = Soundd(params)
  lock_path = Path(tempfile.gettempdir()) / f"starpilot-alert-preview-{os.getuid()}.lock"   # Galaxy's preview lock
  print("ready", flush=True)
  try:
    for key in requests(sys.stdin.fileno()):
      if key not in ALERTS or not context.offroad() or params.get_bool("IsDriverViewEnabled"):
        continue
      descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
      try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
          continue
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sound.load_sounds()   # the saved Sound Pack, which may have changed since the last sample
        play_saved_alert(key, params=params, context=context, sound=sound, audio=sounddevice, alert=getattr(AudibleAlert, ALERTS[key]))
      except (AlertPreviewError, BlockingIOError, OSError):
        pass   # not parked any more, the driver camera opened, or Galaxy is playing one: this sample is skipped
      finally:
        os.close(descriptor)
  finally:
    context.close()
  return 0


if __name__ == "__main__":
  sys.exit(main())
