"""Each region owns its transfer counter; installation completes the shared selection atomically."""
from types import SimpleNamespace

from openpilot.selfdrive.ui.tandem.settings.map_source import CombinedMaps
from openpilot.selfdrive.ui.tandem.settings.maps import DownloadView, Maps, Progress, RegionProgress


def source(road_progress=None):
  road = SimpleNamespace(_layout=SimpleNamespace(_params=SimpleNamespace(
    get=lambda name, **_: "us_state.IA,us_state.IL" if name == "MapsSelected" else "")),
    tick=lambda: None, progress=lambda: road_progress or Progress(False, 0, 0, ""), selection_summary=lambda: "2 regions")
  return CombinedMaps(road)


def test_queued_update_does_not_show_the_previous_ready_result_while_broker_starts():
  from openpilot.starpilot.tandem.routing import config as C, maps as jobs
  C.atomic_json(C.root() / "map-job.json", {"id": "previous", "phase": "ready", "selection": "us_state.IA,us_state.IL"})
  jobs.request("us_state.IA,us_state.IL")
  maps = source()
  maps.tick()
  progress = maps.progress()
  assert progress.active and progress.phase == "prepare"
  assert [r.code for r in progress.regions] == ["IA", "IL"]
  assert not any(r.finished for r in progress.regions) and all(r.fraction == 0 for r in progress.regions)
  assert jobs.read()["phase"] == "ready"  # the adapter only reads the worker's journal


def test_state_percentages_are_distinct_and_all_selected_states_exist_before_progress():
  maps = source()
  maps.job = {"selection": "us_state.IA,us_state.IL", "phase": "download", "done": 42, "total": 100,
              "current_regions": ["us_state.IA", "us_state.IL"], "region_progress": {
                "us_state.IA": {"done": 64, "total": 100}, "us_state.IL": {"done": 35, "total": 100}}}
  progress = maps.progress()
  assert [r.code for r in progress.regions] == ["IA", "IL"]
  assert [r.fraction for r in progress.regions] == [.64, .35] and progress.fraction == .42
  assert not any(r.finished for r in progress.regions)
  maps.job["region_progress"]["us_state.IA"]["done"] = 100
  assert maps.progress().current.code == "IL"
  maps.job["region_progress"] = {}
  maps.job["done"] = 0
  assert [r.fraction for r in maps.progress().regions] == [0, 0]


def test_road_phase_adds_a_waiting_state_when_mapd_has_not_reported_it_yet():
  maps = source(Progress(True, 8, 10, "Iowa", (RegionProgress("us_state.IA", 8, 10),)))
  maps.job = {"selection": "us_state.IA,us_state.IL", "phase": "road"}
  progress = maps.progress()
  assert [r.code for r in progress.regions] == ["IA", "IL"]
  assert [r.fraction for r in progress.regions] == [.8, 0]
  assert not any(r.finished for r in progress.regions)


def test_reused_state_is_downloaded_but_stays_unready_until_the_set_activates():
  maps = source()
  maps.job = {"selection": "us_state.IA,us_state.IL", "phase": "download", "done": 0, "total": 100,
              "current_regions": ["us_state.IA", "us_state.IL"], "region_progress": {
                "us_state.IA": {"done": 0, "total": 0, "downloaded": True},
                "us_state.IL": {"done": 0, "total": 100, "downloaded": False}}}
  progress = maps.progress()
  assert [r.fraction for r in progress.regions] == [1, 0]
  assert not any(r.finished for r in progress.regions) and progress.current.code == "IL"
  maps.job.update(phase="install", stage="build", done=38, total=100)
  progress = maps.progress()
  assert progress.fraction == .38 and progress.stage == "build" and not any(r.finished for r in progress.regions)
  assert progress.note == "All selected regions are installed together."
  maps.job.update(phase="ready", regions_ready=["us_state.IA", "us_state.IL"])
  progress = maps.progress()
  assert progress.fraction == 1 and all(r.finished for r in progress.regions)
  assert all(progress.step_complete(i) for i in range(4))


def test_eta_does_not_carry_a_transfer_rate_into_installation_or_a_retry(monkeypatch):
  maps = source()
  model = Maps(None, maps)
  view = DownloadView(model)
  maps.job = {"selection": "us_state.IA,us_state.IL", "phase": "download", "done": 40, "total": 100}
  view._update_state()
  assert view._started is not None and view._started[1] == 40
  maps.job.update(phase="install", stage="build", done=0, total=200)
  view._update_state()
  assert view._started is None
  maps.job.update(phase="download", done=0, total=100)
  view._update_state()
  assert view._started[1] == 0


def test_paired_progress_combines_both_downloads_while_road_transport_reports_only_one_state():
  maps = source(Progress(True, 9, 10, "Iowa", (RegionProgress("us_state.IA", 9, 10),)))
  maps.job = {"paired": True, "selection": "us_state.IA,us_state.IL", "phase": "download", "done": 260, "total": 2000,
              "current_regions": ["us_state.IA"], "region_progress": {
                "us_state.IA": {"done": 260, "total": 1000}, "us_state.IL": {"done": 0, "total": 1000}}}
  progress = maps.progress()
  assert progress.paired and progress.unit == "regions" and progress.fraction == .13
  assert [r.fraction for r in progress.regions] == [.26, 0] and progress.current.code == "IA"
  assert progress.note == "Maps download one region at a time."
  maps.job.update(done=1180, current_regions=["us_state.IL"], region_progress={
    "us_state.IA": {"done": 1000, "total": 1000, "downloaded": True}, "us_state.IL": {"done": 180, "total": 1000}})
  progress = maps.progress()
  assert progress.fraction == .59 and progress.current.code == "IL"
  assert progress.regions[0].downloaded and not any(r.finished for r in progress.regions)
  view = DownloadView(Maps(None, maps))
  view._update_state()
  assert view._started is None  # normalized state fractions are not a throughput/time estimate
  maps.job.update(phase="install", stage="build", done=38, total=100)
  progress = maps.progress()
  assert progress.unit == "bytes" and progress.stage == "build" and progress.fraction == .38
  assert not any(r.finished for r in progress.regions)
  maps.job.update(phase="ready")
  progress = maps.progress()
  assert all(r.finished for r in progress.regions) and all(progress.step_complete(i) for i in range(4))
  assert progress.note == "All selected regions are ready."


def test_new_paired_request_is_shown_at_zero_before_the_worker_acknowledges_it():
  from openpilot.starpilot.tandem.routing import config as C, handoff
  C.atomic_json(C.root() / "map-job.json", {"id": "previous", "phase": "ready", "selection": "us_state.IA,us_state.IL"})
  handoff.enqueue("us_state.IA,us_state.IL", paired=True, road_regions=["us_state.IA", "us_state.IL"])
  maps = source()
  maps.tick()
  progress = maps.progress()
  assert progress.paired and progress.active and progress.fraction == 0
  assert [r.fraction for r in progress.regions] == [0, 0] and not any(r.finished for r in progress.regions)
