"""Release's crash-report check on StarPilot 7's system/sentry.py, end to end through the real SDK and a recording
transport: automatic reports never leave the device, its local crash log is still written, and an event tagged as a
report the driver chose to send still goes. Needs StarPilot's Params library, so it runs on the device or a full build."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

try:
  from openpilot.system import sentry
except (ImportError, OSError) as error:   # the Params C library isn't built for this machine
  pytest.skip(f"needs StarPilot's native libraries: {error}", allow_module_level=True)


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SimpleNamespace]:
  sdk = sentry._load_sdk()
  transport_module = __import__("sentry_sdk.transport", fromlist=["Transport"])
  envelopes: list[Any] = []

  class RecordingTransport(transport_module.Transport):
    def capture_envelope(self, envelope: Any) -> None:
      envelopes.append(envelope)

  previous = sdk.get_global_scope().client
  real_init = sdk.init
  monkeypatch.setattr(sdk, "init", lambda *args, **kwargs: real_init(*args, **{**kwargs, "transport": RecordingTransport()}))
  monkeypatch.setattr(sentry, "_load_sdk", lambda: sdk)
  monkeypatch.setattr(sentry, "PC", False)
  monkeypatch.setattr(sentry, "_initialized_pid", None)
  log_root = tmp_path / "logs"
  (log_root / "synthetic_route").mkdir(parents=True)
  (log_root / "synthetic_route" / "qlog").write_bytes(b"synthetic drive context")
  monkeypatch.setattr(sentry.Paths, "log_root", lambda: str(log_root))
  assert sentry.init(sentry.SentryProject.SELFDRIVE)
  client = sdk.get_client()
  try:
    yield SimpleNamespace(sdk=sdk, envelopes=envelopes, client=client, crash=log_root / "crash")
  finally:
    sdk.get_global_scope().set_client(previous)
    client.close()


def events(reports: SimpleNamespace) -> list[dict]:
  return [item.get_event() for envelope in reports.envelopes for item in envelope.items if item.type == "event"]


def test_automatic_crashes_stay_local(reports: SimpleNamespace) -> None:
  try:
    raise RuntimeError("synthetic crash retained locally")
  except RuntimeError:
    sentry.capture_exception()
  sentry.report_tombstone("synthetic.crash", "native crash", "synthetic stack")
  reports.sdk.capture_message("direct SDK event must also be filtered")
  reports.sdk.capture_exception(ValueError("direct SDK crash must also be filtered"))
  reports.sdk.flush()
  assert reports.envelopes == []
  assert any("synthetic crash retained locally" in p.read_text() for p in reports.crash.rglob("error.txt"))


def test_a_report_the_driver_sends_still_goes(reports: SimpleNamespace) -> None:
  reports.sdk.capture_message("Manually submitted issue", tags={"report_type": "manual_issue_report"})
  reports.sdk.capture_message("automatic event after the manual one")
  reports.sdk.flush()
  assert [event["tags"]["report_type"] for event in events(reports)] == ["manual_issue_report"]


def test_no_client_reports_or_transactions(reports: SimpleNamespace) -> None:
  options = reports.client.options
  assert not options["send_client_reports"] and not options["auto_session_tracking"]
  assert options["before_send_transaction"]({"type": "transaction"}, {}) is None
