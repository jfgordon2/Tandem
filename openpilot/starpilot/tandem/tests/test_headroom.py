"""The Help steer chime (starpilot/tandem/headroom.py) over StarPilot 7's sound daemon's alert choice."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from openpilot.cereal import log
from openpilot.starpilot.tandem import headroom
from openpilot.starpilot.tandem.state import HEADROOM

AudibleAlert = log.SelfdriveState.AudibleAlert


class Base:
  """StarPilot's Soundd, as far as the chime uses it: its alert choice and update_alert."""

  def __init__(self) -> None:
    self.current_alert = AudibleAlert.none
    self.selfdrive_timeout_alert = False
    self.played: list = []

  def get_audible_alert(self, sm: object) -> None:
    pass

  def update_alert(self, alert: object) -> None:
    self.played.append(alert)
    self.current_alert = alert


class Messages:
  def __init__(self, size: str = "none") -> None:
    state = log.Event.new_message().init("selfdriveState")
    state.alertSize = size
    self.state = state
    self.valid = {"selfdriveState": True}

  def __getitem__(self, name: str) -> object:
    return self.state


@pytest.fixture(autouse=True)
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path))
  monkeypatch.delenv("TANDEM_ONROAD", raising=False)


def test_each_new_warning_chimes_once() -> None:
  sound = headroom.sound_type(Base)()
  sound.get_audible_alert(Messages())
  assert sound.played == []
  HEADROOM.write(time.monotonic())
  sound.get_audible_alert(Messages())
  sound.current_alert = AudibleAlert.none
  sound.get_audible_alert(Messages())
  assert sound.played == [AudibleAlert.prompt]


def test_no_chime_over_another_alert_or_for_an_old_warning() -> None:
  sound = headroom.sound_type(Base)()
  HEADROOM.write(time.monotonic())
  sound.get_audible_alert(Messages("small"))
  assert sound.played == []
  HEADROOM.write(time.monotonic() - 5)
  sound.get_audible_alert(Messages())
  assert sound.played == []


def test_starpilots_own_daemon_without_tandems_driving_screen(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("TANDEM_ONROAD", "0")
  assert headroom.sound_type(Base) is Base
