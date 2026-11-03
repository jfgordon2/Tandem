from types import SimpleNamespace

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from openpilot.system import sentry

pytestmark = pytest.mark.filterwarnings(r"ignore:sentry_sdk\.(push_scope|configure_scope) is deprecated:DeprecationWarning")


@pytest.fixture
def reports(monkeypatch, tmp_path):
  envelopes = []

  class RecordingTransport(Transport):
    def capture_envelope(self, envelope):
      envelopes.append(envelope)

  previous = sentry_sdk.get_global_scope().client
  transport = RecordingTransport()
  real_init = sentry_sdk.init

  def init(*args, **kwargs):
    return real_init(*args, transport=transport, **kwargs)

  monkeypatch.setattr(sentry, "AUTOMATIC_DIAGNOSTICS_ENABLED", False)
  monkeypatch.setattr(sentry, "PC", False)
  monkeypatch.setattr(sentry, "ERROR_LOGS_PATH", tmp_path)
  log_root = tmp_path / "route_logs"
  route = log_root / "synthetic_route"
  route.mkdir(parents=True)
  (route / "qlog").write_bytes(b"synthetic drive context")
  monkeypatch.setattr(sentry.Paths, "log_root", lambda: str(log_root))
  monkeypatch.setattr(sentry, "params", SimpleNamespace(get=lambda *args, **kwargs: "synthetic-test-device"))
  monkeypatch.setattr(sentry, "get_version", lambda: "test")
  monkeypatch.setattr(sentry, "get_build_metadata", lambda: SimpleNamespace(
    channel="test", openpilot=SimpleNamespace(git_origin="test", git_commit="test")))
  monkeypatch.setattr(sentry.sentry_sdk, "init", init)
  sentry.init(sentry.SentryProject.SELFDRIVE)
  client = sentry_sdk.get_client()
  try:
    yield SimpleNamespace(envelopes=envelopes, client=client, directory=tmp_path)
  finally:
    sentry_sdk.get_global_scope().set_client(previous)
    client.close()


def events(reports):
  return [item.get_event() for envelope in reports.envelopes for item in envelope.items if item.type == "event"]


def test_automatic_crashes_and_performance_stay_local(reports):
  try:
    raise RuntimeError("synthetic crash retained locally")
  except RuntimeError:
    sentry.capture_exception()
  sentry.capture_message("raylib UI frame hitches", level="warning", extras={"total_hitches": 3})
  sentry.report_tombstone("synthetic.crash", "native crash", "synthetic stack")
  sentry.capture_block()
  sentry_sdk.capture_message("direct SDK event must also be filtered")
  sentry_sdk.capture_exception(ValueError("direct SDK crash must also be filtered"))
  sentry_sdk.flush()

  assert "synthetic crash retained locally" in (reports.directory / "error.txt").read_text()
  assert list(reports.directory.glob("*.log"))
  assert reports.envelopes == []


def test_manual_reports_still_send_without_allowing_later_automatic_events(reports):
  sentry.capture_report("synthetic-user", "Manually submitted issue", {"test_toggle": True})
  sentry.capture_flm_tune_submission({"discordUsername": "synthetic-user", "carName": "Test car", "tune": {"gain": 1}})
  sentry_sdk.capture_message("automatic event after manual submission")
  sentry_sdk.flush()

  sent = events(reports)
  assert [event["tags"]["report_type"] for event in sent] == ["manual_issue_report", "flm_tune_submission"]
  assert sent[0]["contexts"]["Toggle Values"] == {"test_toggle": True}
  assert sent[1]["extra"]["flm_tune"] == {"gain": 1}


def test_sdk_has_no_automatic_integrations_sessions_or_tracing(reports):
  options = reports.client.options
  assert not reports.client.integrations
  assert not options["auto_session_tracking"]
  assert not options["send_client_reports"]
  assert options["traces_sample_rate"] is None
  assert options["profiles_sample_rate"] == 0.0
  assert options["before_send_transaction"]({"type": "transaction"}, {}) is None
