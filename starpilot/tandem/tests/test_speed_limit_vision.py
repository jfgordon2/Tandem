from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem import speed_limit_vision as vision


def test_vision_releases_models_offroad_and_at_critical_pressure(monkeypatch: pytest.MonkeyPatch) -> None:
  events: list[str] = []

  def load(daemon: vision.TandemSpeedLimitVisionDaemon) -> None:
    events.append("load")
    daemon.net, daemon.classifier_net, daemon.reject_classifier_net = object(), object(), object()

  monkeypatch.setattr(vision.TandemSpeedLimitVisionDaemon, "_load_model", load)
  daemon = vision.TandemSpeedLimitVisionDaemon(use_runtime=False)

  def trim() -> None:
    assert daemon.net is daemon.classifier_net is daemon.reject_classifier_net is None
    assert daemon.current_frame_bgr is None
    assert daemon.client is None
    events.append("trim")

  monkeypatch.setattr(vision, "trim_heap", trim)
  assert events == []
  assert daemon._prepare_models(False, 0.0)
  assert events == []
  assert daemon._prepare_models(True, 1.0)
  assert daemon.last_inference_at == -float("inf")
  assert daemon._prepare_models(True, 2.0)
  assert events == ["load"]
  daemon.client, daemon.current_frame_bgr = object(), object()
  assert daemon._prepare_models(False, 3.0)
  assert daemon._prepare_models(False, 4.0)
  assert events == ["load", "trim"]

  assert daemon._prepare_models(True, 5.0)
  daemon.memory_pressure_state = "critical"
  assert daemon._prepare_models(True, 6.0)
  assert daemon._prepare_models(True, 7.0)
  assert events == ["load", "trim", "load", "trim"]
  daemon.memory_pressure_state = "pressure"
  assert daemon._prepare_models(True, 8.0)
  assert events == ["load", "trim", "load", "trim", "load"]


def test_failed_model_load_retries_without_spinning(monkeypatch: pytest.MonkeyPatch) -> None:
  attempts = []
  clock = SimpleNamespace(monotonic=lambda: 12.0)
  monkeypatch.setattr(vision, "time", clock)
  daemon = vision.TandemSpeedLimitVisionDaemon(use_runtime=False)
  monkeypatch.setattr(daemon, "_load_model", lambda: attempts.append("load"))

  assert not daemon._prepare_models(True, 10.0)
  assert not daemon._prepare_models(True, 12.0)
  assert attempts == ["load"]
  assert not daemon._prepare_models(True, 12.0 + vision.MODEL_RETRY_SECONDS)
  assert attempts == ["load", "load"]


@pytest.mark.parametrize(("started", "status"), [(False, "Idle - offroad"), (True, "Memory pressure - inference paused")])
def test_idle_vision_loop_clears_previous_sign(monkeypatch: pytest.MonkeyPatch, started: bool, status: str) -> None:
  class SubMaster(dict):
    updated = {"userBookmark": False, "livePose": False}
    valid = {"starpilotCarState": False}

    def update(self, _timeout: int) -> None:
      pass

  class StopLoop(Exception):
    pass

  def stop() -> None:
    raise StopLoop

  daemon = vision.TandemSpeedLimitVisionDaemon(use_runtime=False)
  daemon.use_runtime = True
  daemon.sm = SubMaster(deviceState=SimpleNamespace(started=started), mapdOut=SimpleNamespace(roadName=""))
  daemon.Ratekeeper = lambda *_args: SimpleNamespace(keep_time=stop)
  daemon.memory_pressure_state = "critical" if started else "normal"
  daemon.published_speed_limit_mph = 45
  daemon.published_confidence = 0.95
  statuses = []
  publish = daemon._publish_status

  def record_status(text: str, clear_speed: bool = False) -> None:
    statuses.append(text)
    publish(text, clear_speed=clear_speed)

  monkeypatch.setattr(daemon, "_update_memory_pressure", lambda: None)
  monkeypatch.setattr(daemon, "_start_debug_session", lambda: False)
  monkeypatch.setattr(daemon, "_publish_runtime_telemetry", lambda *_args, **_kwargs: None)
  monkeypatch.setattr(daemon, "_publish_status", record_status)
  with pytest.raises(StopLoop):
    daemon.run()

  assert statuses == [status]
  assert daemon.published_speed_limit_mph == 0
  assert daemon.published_confidence == 0.0
