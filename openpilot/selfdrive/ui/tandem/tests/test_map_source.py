"""Offline Maps' source on StarPilot 7 (settings/map_source.py): the selection, both map sets' readiness, and a map job's
progress as the download view shows it."""
from __future__ import annotations

from pathlib import Path

import pytest

from openpilot.selfdrive.ui.tandem.settings.map_source import TandemMaps
from openpilot.selfdrive.ui.tandem.settings.maps import Maps
from openpilot.selfdrive.ui.tandem.tests.fakes import sample_maps
from openpilot.starpilot.tandem.routing import config as C, maps as jobs

IA, IL = "us_state.IA", "us_state.IL"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))


def test_groups_and_the_whole_us_select_their_states() -> None:
  maps = sample_maps(chosen=frozenset())
  maps.set_selected("group.midwest", True)
  assert maps.selected("group.midwest") and maps.selected(IA) and maps.selection_summary() == "12 regions"
  maps.set_selected(IA, False)
  assert not maps.selected("group.midwest")
  maps.set_selected("nation.US", True)
  assert maps.selection_summary() == "Whole U.S."
  assert [r.name for r in maps.regions(2)] == ["Canada", "Mexico"] and maps.name("nation.CA") == "Canada"


def test_each_region_says_which_map_sets_it_has() -> None:
  maps = sample_maps()
  assert maps.region_status(IA) == ("Road data ready", "Routes ready")
  assert maps.region_status(IL) == ("Not downloaded", "Routes not downloaded")
  assert maps.region_status("nation.CA") == ("Not downloaded", "Routes not available yet")
  assert maps.status() == "All maps ready" and maps.download_label() == "Update maps"
  maps.set_selected(IL, True)
  summary = maps.summary()
  assert summary["road"] == "Download missing road data" and not summary["route_ready"] and summary["available"]
  assert maps.download_label() == "Download selected maps"


def test_download_queues_one_job_for_both_map_sets() -> None:
  maps = sample_maps()
  maps.set_selected(IL, True)
  maps.download()
  assert jobs.read("map-request.json")["selection"] == f"{IA},{IL}"


def test_road_progress_moves_a_region_at_a_time() -> None:
  maps = sample_maps(job={"id": "j", "selection": f"{IA},{IL}", "phase": "road", "current_regions": [IL], "done": 3, "total": 6})
  progress = maps.progress()
  assert progress.active and progress.phase == "road" and progress.unit == "regions" and progress.step == 1
  assert [(r.location, r.finished) for r in progress.regions] == [(IA, True), (IL, False)]
  assert progress.fraction == pytest.approx(0.75)   # Iowa done, Illinois half
  assert progress.current is not None and progress.current.location == IL


def test_routes_then_install_then_ready() -> None:
  download = sample_maps(job={"id": "j", "selection": IA, "phase": "download", "current_regions": [IA], "done": 50, "total": 200})
  progress = download.progress()
  assert progress.unit == "bytes" and progress.fraction == 0.25 and progress.step == 1
  install = sample_maps(job={"id": "j", "selection": IA, "phase": "install", "done": 9, "total": 9}).progress()
  assert install.step == 2 and install.fraction == 0.99   # never 100% until it's ready
  ready = sample_maps(job={"id": "j", "selection": IA, "phase": "ready", "regions_ready": [IA]}).progress()
  assert not ready.active and ready.step == 3 and ready.fraction == 1 and ready.regions[0].finished


def test_a_new_request_shows_from_the_start_before_the_broker_answers() -> None:
  C.atomic_json(C.root() / "map-job.json", {"id": "old", "selection": IA, "phase": "ready"})
  C.atomic_json(C.root() / "map-request.json", {"id": "new", "selection": IL})
  maps = TandemMaps(lambda: True, lambda: True, lambda: None, owner=lambda _: {"selectedGeneration": ""})
  maps.tick()
  progress = maps.progress()
  assert progress.active and progress.phase == "road" and progress.fraction == 0


def test_remove_needs_downloaded_maps_parked_and_no_download() -> None:
  maps = sample_maps()
  Maps(maps)
  maps.remove()
  assert maps.removed == 1
  maps._parked = lambda: False
  maps.remove()
  assert maps.removed == 1 and not maps.can_remove()
