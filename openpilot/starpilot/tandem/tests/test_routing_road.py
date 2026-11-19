"""Road data from StarPilot 7's map owner for a map job (routing/road.py), against a stand-in owner that answers as
starpilot/maps/operation_owner.py does."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from openpilot.starpilot.tandem.routing import config as C, road


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))


class Owner:
  """StarPilot's map owner: one region at a time, each new generation keeping the earlier regions."""

  def __init__(self, fail: str | None = None, generation: str = ""):
    self.generation, self.fail = generation, fail
    self.started: list[str] = []
    self.cancelled: list[str] = []
    self.status: dict[str, Any] = {"state": "idle", "operationId": None}
    self.polls = 0

  def __call__(self, message: dict) -> dict:
    op = message["op"]
    if op == "setup":
      return {"maxTransferBytes": 8 << 30, "maxNewDiskBytes": 16 << 30}
    if op == "catalog":
      return {"regions": [{"token": "us_state.IA", "available": True, "groups": 4},
                          {"token": "us_state.IL", "available": True, "groups": 6},
                          {"token": "us_state.GU", "available": False, "groups": 0}]}
    if op == "start":
      assert message["expectedCurrentGeneration"] == self.generation and message["maxTransferBytes"] == 8 << 30
      self.started.append(message["regionToken"])
      self.status = {"state": "transferring", "operationId": f"op{len(self.started)}", "completedGroups": 0, "totalGroups": 4}
      self.polls = 0
      return dict(self.status)
    if op == "cancel":
      self.cancelled.append(message["operationId"])
      return dict(self.status, state="canceled")
    self.polls += 1
    if self.status["state"] == "transferring" and self.polls >= 2:
      if self.fail:
        self.status.update(state="failed", errorCode=self.fail)
      else:
        self.generation = f"{len(self.started):064x}"
        self.status.update(state="completed", completedGroups=4)
    return dict(self.status, selectedGeneration=self.generation)


def test_each_missing_state_is_downloaded_once_and_remembered() -> None:
  owner, progress = Owner(), []
  road.ensure(["us_state.IA", "us_state.IL"], lambda: None, lambda **values: progress.append(values), owner, lambda _: None)
  assert owner.started == ["us_state.IA", "us_state.IL"]
  assert progress[0] == {"phase": "road", "current_regions": ["us_state.IA"], "done": 0, "total": 4}
  assert {"done": 4, "total": 4} in progress
  assert road.present(owner) == {"us_state.IA", "us_state.IL"}
  road.ensure(["us_state.IA", "us_state.IL"], lambda: None, lambda **_: None, owner, lambda _: None)
  assert owner.started == ["us_state.IA", "us_state.IL"]   # nothing again


def test_deleted_maps_need_their_road_data_again() -> None:
  owner = Owner()
  road.ensure(["us_state.IA"], lambda: None, lambda **_: None, owner, lambda _: None)
  owner.generation = ""   # Storage › Delete maps cleared StarPilot's selection
  assert road.present(owner) == set()


def test_a_failed_or_unavailable_region_stops_the_job() -> None:
  with pytest.raises(C.RoutingError, match="road_download_failed"):
    road.ensure(["us_state.IA"], lambda: None, lambda **_: None, Owner(fail="process_failed"), lambda _: None)
  with pytest.raises(C.RoutingError, match="interrupted"):
    road.ensure(["us_state.IA"], lambda: None, lambda **_: None, Owner(fail="not_parked"), lambda _: None)
  with pytest.raises(C.RoutingError, match="coverage_unavailable"):
    road.ensure(["us_state.GU"], lambda: None, lambda **_: None, Owner(), lambda _: None)


def test_cancelling_the_job_cancels_starpilots_download() -> None:
  owner, calls = Owner(), [0]

  def gate() -> None:
    calls[0] += 1
    if calls[0] > 1:
      raise C.RoutingError("cancelled")
  with pytest.raises(C.RoutingError, match="cancelled"):
    road.ensure(["us_state.IA"], gate, lambda **_: None, owner, lambda _: None)
  assert owner.cancelled == ["op1"] and road.present(owner) == set()
