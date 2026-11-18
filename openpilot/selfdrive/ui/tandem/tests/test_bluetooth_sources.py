"""Connections' Bluetooth sources (settings/bluetooth_sources.py) over StarPilot 7's real controller owner and a stand-in
Bluetooth owner."""
from __future__ import annotations

import time
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from openpilot.starpilot.controllers.owner import ControllerOwner
from openpilot.starpilot.favorites.state import FavoriteAction, FavoriteResult, FavoriteSlot, FavoriteSnapshot
from openpilot.selfdrive.ui.tandem.settings.bluetooth_sources import StarPilotBluetooth, StarPilotControllers


@pytest.fixture
def owner(tmp_path: Path) -> tuple[ControllerOwner, list[bool]]:
  """StarPilot's ControllerOwner over temporary saved settings, parked, with a remote connected."""
  params = SimpleNamespace(get_param_path=lambda key: str(tmp_path / key))
  parked = [True]
  actions = {key: FavoriteAction(key, label, available=True, invoke=lambda: True) for key, label in
             (("engage", "Engage"), ("bookmark", "Bookmark"))}
  favorites = FavoriteSnapshot(tuple(FavoriteSlot(i) for i in range(3)), (), "r", True, True)
  real = ControllerOwner(params, parked=lambda: parked[0], actions=lambda: actions, favorites=lambda: favorites,
                         invoke_favorite=lambda request: FavoriteResult(True, ""))
  real.set_devices([{"id": "remote-1", "name": "Wheel Remote", "bus": 5}])
  return real, parked


def press(owner: ControllerOwner, code: int) -> None:
  owner.feed({"device_id": "remote-1", "code": code, "timestamp_ns": time.monotonic_ns()})


def test_a_button_is_learned_into_a_free_slot_and_given_an_action(owner: tuple[ControllerOwner, list[bool]]) -> None:
  real, _ = owner
  source = StarPilotControllers(lambda: real)
  slot = source.free_slot()
  assert slot == 3 and [k for k, _ in source.actions()] == ["bookmark", "engage"]
  source.start_learning(slot)
  press(real, 288)
  learned = source.status()["last_learned"]
  assert learned["slot"] == slot and learned["id"] == "remote-1:288"
  assert source.assign(learned["id"], "engage") and source.action(slot) == "engage"
  assert [m["id"] for m in source.mappings()] == ["remote-1:288"] and source.free_slot() == 4


def test_test_mode_shows_presses_and_removing_frees_the_slot(owner: tuple[ControllerOwner, list[bool]]) -> None:
  real, _ = owner
  source = StarPilotControllers(lambda: real)
  source.start_learning(3)
  press(real, 288)
  source.assign("remote-1:288", "bookmark")
  source.start_testing()
  press(real, 288)
  status = source.status()
  assert status["testing"] and status["last_tested"] == {"mapped": True, "slot": 3}
  source.stop_testing()
  source.delete("remote-1:288")
  assert source.mappings() == [] and source.action(3) is None and source.free_slot() == 3


def test_nothing_changes_while_driving(owner: tuple[ControllerOwner, list[bool]]) -> None:
  real, parked = owner
  parked[0] = False
  source = StarPilotControllers(lambda: real)
  source.start_learning(3)
  assert "remaining_seconds" not in source.status() and source.mappings() == []


def test_without_the_controller_runtime_the_remote_is_empty() -> None:
  source = StarPilotControllers(lambda: None)
  assert source.mappings() == [] and source.actions() == [] and source.free_slot() is None
  assert not source.assign("x:1", "engage")


class Now:
  """Runs each piece of work at once, as the worker thread would."""

  def submit(self, work: Any) -> Future:
    future: Future = Future()
    try:
      future.set_result(work())
    except Exception as error:
      future.set_exception(error)
    return future

  def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
    pass


class Radio:
  """StarPilot's Bluetooth owner, as far as the page uses it."""

  def __init__(self, parked: Any, session_valid: Any) -> None:
    self.session_valid = session_valid
    self.requests: list[tuple[str, dict]] = []
    self.devices = [{"address": "AA", "name": "Pixel 9", "paired": False, "connected": False, "audioSink": True}]
    self.pairing: dict | None = None
    self.closed = False

  def snapshot(self, session: Any = None) -> dict:
    return {"available": True, "powered": True, "discovering": False, "devices": self.devices, "pairing": self.pairing}

  def request(self, operation: str, **kwargs: Any) -> dict:
    assert self.session_valid(kwargs["session"])
    self.requests.append((operation, kwargs))
    if operation == "pair":
      self.pairing = {"address": "AA", "state": "pairing", "prompt": {"id": "f" * 32, "kind": "confirm", "value": "123456", "displayOnly": False}}
    return self.snapshot()

  def close(self) -> None:
    self.closed = True


def test_bluetooth_reads_searches_pairs_and_answers_the_prompt() -> None:
  radios: list[Radio] = []

  def make(parked: Any, session_valid: Any) -> Radio:
    radios.append(Radio(parked, session_valid))
    return radios[-1]
  bt = StarPilotBluetooth(lambda: True, owner=make, clock=lambda: 0.0, executor=Now)
  bt.set_active(True)
  bt.tick()
  bt.tick()
  radio = radios[0]
  assert [op for op, _ in radio.requests] == ["scan"]
  assert bt.status().devices[0].name == "Pixel 9" and not bt.status().devices[0].paired
  assert not bt.select("AA")
  bt.tick()
  prompt = bt.prompt()
  assert prompt == {"id": "f" * 32, "name": "Pixel 9", "kind": "confirm", "value": "123456", "display_only": False}
  bt.respond(prompt["id"], True)
  assert radio.requests[-1] == ("pairing_response", {"session": radio.requests[0][1]["session"], "prompt_id": "f" * 32, "accepted": True, "value": ""})
  bt.set_active(False)
  assert radio.closed and not radio.session_valid(radio.requests[0][1]["session"])
