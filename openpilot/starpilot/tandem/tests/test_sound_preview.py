"""Play sample's worker: samples play at once from one loaded worker, the latest of quick taps, and only while parked."""
from __future__ import annotations

import os
import sys
import time

from openpilot.selfdrive.ui.tandem.settings.alerts import SamplePlayer
from openpilot.starpilot.tandem.sound_preview import requests

ECHO = "import sys\nfor line in sys.stdin:\n  open(sys.argv[1], 'a').write(line)\n"


def test_quick_taps_collapse_to_the_latest() -> None:
  read, write = os.pipe()
  os.write(write, b"EngageVolume\nPromptVolume\n\nDisengageVolume\n")
  os.close(write)
  assert list(requests(read)) == ["DisengageVolume"]


def test_one_worker_plays_every_sample_and_only_while_parked(tmp_path) -> None:
  heard = tmp_path / "heard"
  parked = [True]
  player = SamplePlayer(lambda: parked[0], command=[sys.executable, "-c", ECHO, str(heard)])
  player.warm()
  first = player._process
  player("EngageVolume")
  player("PromptVolume")
  assert player._process is first   # the same worker, loaded once
  parked[0] = False
  player("RefuseVolume")             # driving: nothing
  player.close()
  assert first is not None and first.wait(5) == 0
  assert heard.read_text().split() == ["EngageVolume", "PromptVolume"]


def test_an_idle_worker_stops(tmp_path) -> None:
  now = [0.0]
  player = SamplePlayer(lambda: True, command=[sys.executable, "-c", ECHO, str(tmp_path / "heard")], clock=lambda: now[0])
  player.warm()
  process = player._process
  now[0] = SamplePlayer.IDLE_S + 1
  deadline = time.monotonic() + 5
  while process is not None and process.poll() is None and time.monotonic() < deadline:
    time.sleep(0.1)
  assert process is not None and process.poll() is not None and player._process is None
