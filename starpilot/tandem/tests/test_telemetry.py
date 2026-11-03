from types import SimpleNamespace


def test_crash_artifacts_stay_local_while_drive_uploads_remain_available(tmp_path, monkeypatch):
  from openpilot.system.loggerd import uploader

  crash = tmp_path / "crash" / "native.crash"
  crash.parent.mkdir()
  crash.write_text("synthetic crash")
  route = tmp_path / "2026-10-31--12-00-00--0"
  route.mkdir()
  for name in ("qlog", "rlog", "fcamera.hevc"):
    (route / name).write_bytes(b"synthetic drive data")

  monkeypatch.setattr(uploader, "AUTOMATIC_DIAGNOSTICS_ENABLED", False)
  monkeypatch.setattr(uploader, "getxattr", lambda *args: None)
  worker = uploader.Uploader.__new__(uploader.Uploader)
  worker.root = str(tmp_path)
  worker.params = SimpleNamespace(get=lambda *args: None)
  worker.immediate_priority = {"qlog": 0}

  available = list(worker.list_upload_files(metered=False))
  assert {name for name, _, _ in available} == {"qlog", "rlog", "fcamera.hevc"}
  assert crash.is_file()


def test_unattended_log_and_performance_workers_do_no_work():
  from openpilot.system.athena import athenad

  def unexpected_work():
    raise AssertionError("automatic diagnostic forwarding must not start")

  stop = SimpleNamespace(is_set=unexpected_work)
  athenad.log_handler(stop)
  athenad.stat_handler(stop)


def test_automatic_starpilot_stats_do_not_read_metadata_or_contact_servers(monkeypatch):
  from openpilot.starpilot.system import starpilot_stats

  def unexpected_work():
    raise AssertionError("automatic statistics reporting must not start")

  monkeypatch.setattr(starpilot_stats, "AUTOMATIC_DIAGNOSTICS_ENABLED", False)
  monkeypatch.setattr(starpilot_stats, "get_build_metadata", unexpected_work)
  starpilot_stats.send_stats()
